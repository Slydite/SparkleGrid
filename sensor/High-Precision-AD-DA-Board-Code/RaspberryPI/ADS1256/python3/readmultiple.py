#!/usr/bin/env python3
# -*- coding:utf-8 -*-

import ADS1256      # Import the ADS1256 library
import config       # Import the config library (for init/exit)
import psycopg2     # For Database
import numpy as np  # For RMS calculation
import datetime     # For Timestamps
import time
import sys
import queue        # For Queue
import logging
import signal
import threading

# ==============================================================================
# ==                         SENSOR CONFIGURATION                             ==
# ==============================================================================
# Define all sensors to be read here.
# Each dictionary must contain:
#   'channel': ADC channel number (0-7)
#   'sensor_id': Unique integer ID for this sensor in the database.
#   'name': String name for the database (e.g., "Voltage Ch2", "Current Ch6").
#   'type': String type for the database (e.g., "Voltage", "Current").
#
# *** IMPORTANT: 'sensor_id' values MUST be unique across all dictionaries! ***
# ------------------------------------------------------------------------------
SENSORS_CONFIG = [
    {
        'channel': 2,
        'sensor_id': 1, # Unique ID for DB
        'name': 'Voltage Sensor Ch2',
        'type': 'Voltage'
    },
    {
        'channel': 6,
        'sensor_id': 2, # Unique ID for DB
        'name': 'Voltage Sensor Ch6', 
        'type': 'Voltage'             
    },
    {
        'channel':4,
        'sensor_id':3,
        'name':'Voltage Sensor Ch4',
        'type':'Voltage'
    }
    # --- Add more sensors here if needed ---
    # {
    #     'channel': 0,
    #     'sensor_id': 3,
    #     'name': 'Voltage Sensor Ch0',
    #     'type': 'Voltage'
    # },
]
# ==============================================================================

# --- Common ADC/System Config ---
VREF = 5.0          # *** IMPORTANT: Set this to the ACTUAL measured Vref voltage! ***
ADC_GAIN = ADS1256.ADS1256_GAIN_E['ADS1256_GAIN_1'] # Gain 1 (Applies to ALL channels read sequentially)
ADC_RATE_ENUM = ADS1256.ADS1256_DRATE_E['ADS1256_1000SPS'] # 1000 SPS Rate
ADC_SAMPLE_RATE_HZ = 1000 # ADC hardware rate in Hz (MUST match ADC_RATE_ENUM)
# Effective sample rate PER CHANNEL will be approx. ADC_SAMPLE_RATE_HZ / number_of_sensors

# --- Database Configuration ---
DB_HOST = "localhost"
DB_NAME = "gridsense_db"
DB_USER = "gridsense_user"
DB_PASSWORD = "microgrid"
DB_TABLE = "measurements_six" # Make sure this table exists in gridsense_db

# --- Queue and Batching Configuration ---
DB_WRITE_INTERVAL_S = 1.0 # How often DB writer wakes up to check queue (seconds)
# Max SETS of readings (one from each sensor) to buffer before forcing DB write
# Adjust based on number of sensors and desired buffer time
NUM_SENSORS = len(SENSORS_CONFIG)
EFFECTIVE_RATE_PER_SENSOR = ADC_SAMPLE_RATE_HZ / NUM_SENSORS if NUM_SENSORS > 0 else 0
MAX_QUEUE_SIZE = int(EFFECTIVE_RATE_PER_SENSOR * 5) if EFFECTIVE_RATE_PER_SENSOR > 0 else 100 # Approx 5 seconds worth of reading SETS

# --- Clamping Limits for NUMERIC(5, 2) in DB ---
NUMERIC_5_2_MAX = 999.99
NUMERIC_5_2_MIN = -999.99

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(threadName)s - %(levelname)s - %(message)s')

# --- Global Variables ---
# Queue holds tuples: (timestamp, {sensor_id_1: voltage_1, sensor_id_2: voltage_2, ...})
data_queue = queue.Queue(maxsize=MAX_QUEUE_SIZE)
stop_event = threading.Event() # Event for stopping threads gracefully
ADC = None # ADC object holder
# Dictionary to map sensor_id back to its config (for DB writer)
SENSOR_ID_TO_CONFIG = {sensor['sensor_id']: sensor for sensor in SENSORS_CONFIG}


# --- Clamping Function ---
def clamp_value(value, min_val=NUMERIC_5_2_MIN, max_val=NUMERIC_5_2_MAX):
    """Clamps a value within the specified min/max range. Handles None."""
    if not isinstance(value, (int, float)):
        return 0.0 # Default value for non-numeric types (like None)
    return max(min_val, min(max_val, value))

# --- Database Functions (No changes needed from previous versions) ---
def create_connection():
    """Establishes a connection to the PostgreSQL database."""
    connection = None
    try:
        connection = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port="5432"
        )
        logging.info(f"Connection to PostgreSQL DB '{DB_NAME}' successful")
    except psycopg2.OperationalError as e:
        logging.error(f"Database connection error: {e}", exc_info=True)
    return connection

def get_max_id(connection):
    """Gets the maximum ID from the specified database table."""
    max_id = 0
    try:
        with connection.cursor() as cursor:
            query = f"SELECT MAX(id) FROM {DB_TABLE};"
            cursor.execute(query)
            result = cursor.fetchone()
            if result and result[0] is not None:
                max_id = result[0]
    except psycopg2.Error as e:
        logging.error(f"Error getting max ID from {DB_TABLE}: {e}")
    return max_id

def calculate_rms(voltage_list):
    """Calculates RMS value from a list of voltage floats."""
    if not voltage_list:
        return 0.0
    numeric_array = np.array([v for v in voltage_list if isinstance(v, (int, float))], dtype=float)
    if numeric_array.size == 0:
        return 0.0
    return np.sqrt(np.mean(np.square(numeric_array)))

def insert_batch_data(connection, batch_id, sensor_id, batch_start_time, sensdata_batch, sname, stype):
    """ Inserts a batch of sensor data into the database for ONE sensor. """
    if not sensdata_batch:
        logging.warning(f"Attempted to insert empty batch for Sensor ID {sensor_id}.")
        return False

    voltages_only = [item[0] for item in sensdata_batch]
    rms_value = calculate_rms(voltages_only)

    clamped_rms = clamp_value(rms_value)
    if clamped_rms != rms_value:
        logging.warning(f"Clamped RMS value from {rms_value:.4f} to {clamped_rms:.2f} for Sensor ID {sensor_id}, Batch ID {batch_id}")

    try:
        with connection.cursor() as cursor:
            timestamp = batch_start_time.isoformat()
            query = f"""
            INSERT INTO {DB_TABLE}(id, sensor_id, sensdata, time, rmsvalue, sname, stype, thd, pf)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
            """
            cursor.execute(query, (
                batch_id,
                sensor_id,
                sensdata_batch, # Already clamped [voltage, delta_t] pairs
                timestamp,
                float(clamped_rms),
                sname,
                stype,
                0,  # Placeholder for THD
                0   # Placeholder for PF
            ))
            connection.commit()
            logging.debug(f"Successfully inserted batch ID {batch_id} for Sensor ID {sensor_id} with {len(sensdata_batch)} samples.")
            return True

    except (psycopg2.Error, TypeError) as e:
        logging.error(f"Error inserting batch ID {batch_id} for Sensor ID {sensor_id}: {e}", exc_info=True)
        try: connection.rollback()
        except psycopg2.Error as rb_e: logging.error(f"Error rolling back transaction: {rb_e}")
        return False

# --- ADC Sampling Thread (MODIFIED FOR MULTIPLE SENSORS) ---
def adc_sampler_thread():
    """Continuously samples all configured ADC channels sequentially and puts results onto the queue."""
    if not SENSORS_CONFIG:
        logging.error("Sampler: No sensors configured in SENSORS_CONFIG. Stopping thread.")
        stop_event.set()
        return

    sensor_channels = [s['channel'] for s in SENSORS_CONFIG] # List of channels to read
    sensor_ids = [s['sensor_id'] for s in SENSORS_CONFIG] # List of sensor IDs in same order
    num_sensors = len(sensor_channels)

    logging.info(f"ADC Sampler started - Reading {num_sensors} channels {sensor_channels} sequentially.")
    logging.info(f"Target ADC Rate: {ADC_SAMPLE_RATE_HZ} SPS. Effective rate/channel approx {EFFECTIVE_RATE_PER_SENSOR:.1f} SPS.")

    max_adc_count = 0x7FFFFF # 8388607.0

    while not stop_event.is_set():
        read_start_time = time.monotonic() # Time the whole read cycle
        raw_readings = {} # Store raw values for this cycle {channel: raw_value}
        read_success = True

        # Read all configured channels sequentially
        for channel in sensor_channels:
            if not ADC.ADS1256_SetChannal(channel):
                logging.error(f"Sampler: Failed to set ADC channel {channel}.")
                read_success = False
                break # Stop reading this cycle if channel set fails

            raw_value = ADC.ADS1256_Read_ADC_Data()
            if raw_value is None:
                logging.warning(f"Sampler: Failed to read ADC channel {channel} (WaitDRDY Timeout?)")
                # Decide how to handle partial failure: continue?, discard cycle?
                # For now, mark as failure and don't queue this cycle's data
                read_success = False
                break
            raw_readings[channel] = raw_value

        # If any part of the read cycle failed, skip queueing and delay slightly
        if not read_success:
            time.sleep(0.1)
            continue

        # All reads successful, get timestamp and process
        measurement_time = datetime.datetime.now(datetime.timezone.utc)
        voltage_readings = {} # {sensor_id: voltage}

        for i, sensor_config in enumerate(SENSORS_CONFIG):
            channel = sensor_config['channel']
            sensor_id = sensor_config['sensor_id']
            raw_value = raw_readings.get(channel) # Should exist if read_success is True

            if raw_value is not None: # Should always be true here, but good practice
                 voltage = (raw_value / max_adc_count) * VREF if VREF != 0 else 0.0
                 voltage_readings[sensor_id] = voltage
            # else: # This case shouldn't happen if read_success is True
            #     voltage_readings[sensor_id] = None # Or handle error

        # Put results onto the queue
        try:
            data_queue.put((measurement_time, voltage_readings), block=True, timeout=0.5)
        except queue.Full:
            logging.warning("Data queue is full. Sample SET might be dropped.")
        except Exception as e:
             logging.error(f"Error putting data onto queue: {e}")

        # --- Calculate sleep time ---
        read_end_time = time.monotonic()
        elapsed_time = read_end_time - read_start_time
        expected_time = num_sensors / ADC_SAMPLE_RATE_HZ if ADC_SAMPLE_RATE_HZ > 0 else 0.01
        sleep_time = max(0, expected_time - elapsed_time)
        stop_event.wait(sleep_time) # Interruptible sleep

    logging.info("ADC Sampler thread finished.")


# --- Database Writer Thread (MODIFIED FOR MULTIPLE SENSORS) ---
def database_writer_thread(db_connection):
    """ Periodically collects data from the queue and writes batches to the database (one row per sensor per batch). """
    logging.info("Database Writer thread started.")
    last_write_time = time.monotonic()

    # Use a dictionary to store raw batches, keyed by sensor_id
    # { sensor_id_1: [(ts, voltage), (ts, voltage), ...], sensor_id_2: [...], ... }
    current_raw_batches = {sensor_id: [] for sensor_id in SENSOR_ID_TO_CONFIG.keys()}

    current_db_id = get_max_id(db_connection) # Get initial max ID

    while not stop_event.is_set() or not data_queue.empty():
        try:
            # Dequeue the data: (timestamp, {sensor_id: voltage, ...})
            timestamp, voltage_dict = data_queue.get(block=True, timeout=0.1)

            # Distribute the voltages to the correct raw batch lists
            for sensor_id, voltage in voltage_dict.items():
                if sensor_id in current_raw_batches:
                    current_raw_batches[sensor_id].append((timestamp, voltage))
                else:
                    logging.warning(f"DB Writer: Received data for unknown sensor_id {sensor_id}. Ignoring.")
            data_queue.task_done()
        except queue.Empty:
            if stop_event.is_set():
                logging.debug("Queue empty and stop event set, proceeding to final write check.")
            pass # No data arrived in timeout window

        current_time = time.monotonic()
        # Check if ANY batch is nearing the max size or if write interval passed
        # Note: MAX_QUEUE_SIZE is for SETS of readings. Each batch length relates to this.
        longest_batch_len = 0
        if current_raw_batches:
             longest_batch_len = max(len(batch) for batch in current_raw_batches.values())

        force_write = longest_batch_len >= (MAX_QUEUE_SIZE * 0.9)
        time_to_write = (current_time - last_write_time) >= DB_WRITE_INTERVAL_S
        has_data = longest_batch_len > 0 # Check if there is any data to write

        if (time_to_write or force_write or (stop_event.is_set() and has_data)) and has_data:
            if force_write:
                logging.warning(f"Forcing DB write. Longest batch has {longest_batch_len} samples.")

            write_start_time = time.monotonic()
            batches_processed_count = 0

            # Iterate through each sensor's batch
            for sensor_id, raw_batch in current_raw_batches.items():
                if not raw_batch: # Skip if this sensor's batch is empty
                    continue

                batches_processed_count += 1
                sensor_config = SENSOR_ID_TO_CONFIG.get(sensor_id)
                if not sensor_config:
                     logging.error(f"DB Writer: Cannot find config for sensor_id {sensor_id}. Skipping batch.")
                     continue # Skip this batch

                # Process this sensor's batch
                batch_start_time = raw_batch[0][0]
                sensdata_for_db = []
                for item_timestamp, item_voltage in raw_batch:
                    clamped_voltage = clamp_value(item_voltage)
                    delta_t_ms = (item_timestamp - batch_start_time).total_seconds() * 1000.0
                    clamped_delta_t_ms = clamp_value(delta_t_ms)
                    sensdata_for_db.append([round(clamped_voltage, 2), round(clamped_delta_t_ms, 2)])

                # Increment DB ID and insert
                current_db_id += 1
                success = insert_batch_data(
                    db_connection, current_db_id, sensor_id, batch_start_time,
                    sensdata_for_db, sensor_config['name'], sensor_config['type']
                )

                if success:
                    logging.info(f"DB Write: ID {current_db_id}, SensorID {sensor_id}, Samples: {len(sensdata_for_db)}, StartTime: {batch_start_time.time()}")
                else:
                    logging.error(f"DB Write failed for SensorID {sensor_id} batch starting at {batch_start_time}")
                    current_db_id -= 1 # Decrement ID on failure

            # --- Reset ALL batches and timer ---
            for sensor_id in current_raw_batches:
                current_raw_batches[sensor_id] = [] # Clear the list for this sensor
            last_write_time = current_time
            logging.debug(f"DB write cycle finished processing {batches_processed_count} batches in {time.monotonic() - write_start_time:.3f}s")


        # Prevent busy-waiting when queue is empty
        if not has_data and not stop_event.is_set():
            time.sleep(0.05)

    logging.info("Database Writer thread finished.")


# --- Signal Handler (Keep as is) ---
def signal_handler(sig, frame):
    logging.info('Interrupt received, shutting down...')
    stop_event.set()

# --- Main Execution (Adapted for Parameterized Sensors) ---
if __name__ == "__main__":
    if not SENSORS_CONFIG:
        logging.critical("No sensors defined in SENSORS_CONFIG. Exiting.")
        sys.exit(1)

    # --- Validate Sensor Config ---
    sensor_ids = [s['sensor_id'] for s in SENSORS_CONFIG]
    if len(sensor_ids) != len(set(sensor_ids)):
        logging.critical("Configuration Error: Duplicate 'sensor_id' values found in SENSORS_CONFIG! IDs must be unique.")
        sys.exit(1)
    channels = [s['channel'] for s in SENSORS_CONFIG]
    if len(channels) != len(set(channels)):
        logging.warning("Configuration Warning: Duplicate 'channel' values found in SENSORS_CONFIG. Reading same channel multiple times.")
    # ------------------------------

    logging.info(f"Starting ADS1256 Data Logger for {len(SENSORS_CONFIG)} sensor(s)...")
    db_connection = None
    sampler = None
    db_writer = None

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # 1. Initialize ADC Hardware
        ADC = ADS1256.ADS1256()
        if ADC.ADS1256_init() != 0:
            logging.critical("Failed to initialize ADS1256 hardware via ADS1256_init(). Exiting.")
            raise RuntimeError("ADC Initialization Failed")
        logging.info("ADS1256 hardware initialized successfully.")
        logging.warning(f"Using VREF = {VREF}V for voltage calculation. Ensure this is correct!")

        # 2. Configure ADC Gain and Rate (Applies to the sequence of reads)
        if not ADC.ADS1256_ConfigADC(ADC_GAIN, ADC_RATE_ENUM):
             logging.critical("Failed to configure ADC Gain/Rate. Exiting.")
             raise RuntimeError("ADC Configuration Failed")
        gain_str = [k for k, v in ADS1256.ADS1256_GAIN_E.items() if v == ADC_GAIN][0]
        rate_str = [k for k, v in ADS1256.ADS1256_DRATE_E.items() if v == ADC_RATE_ENUM][0]
        logging.info(f"ADC Configured: Gain={gain_str}, Rate={rate_str} ({ADC_SAMPLE_RATE_HZ} SPS hardware rate)")
        if EFFECTIVE_RATE_PER_SENSOR > 0:
            logging.info(f"Effective sample rate PER CHANNEL approx {EFFECTIVE_RATE_PER_SENSOR:.1f} SPS.")
        else:
             logging.warning("Cannot calculate effective sample rate (0 sensors or 0 Hz?).")

        # 3. Connect to Database
        db_connection = create_connection()
        if not db_connection:
            logging.critical("Failed to connect to database. Exiting.")
            raise RuntimeError("Database Connection Failed")

        # 4. Create and start threads
        sampler = threading.Thread(target=adc_sampler_thread, name="ADCSampler")
        db_writer = threading.Thread(target=database_writer_thread, args=(db_connection,), name="DBWriter")

        sampler.daemon = False # Ensure graceful shutdown
        db_writer.daemon = False

        logging.info("Starting worker threads...")
        sampler.start()
        db_writer.start()

        # 5. Keep main thread alive while worker threads run
        while not stop_event.is_set():
            if not sampler.is_alive() or not db_writer.is_alive():
                 logging.error("A worker thread has unexpectedly stopped. Signaling shutdown.")
                 stop_event.set()
                 break
            stop_event.wait(1.0) # Check every second

    except RuntimeError as e:
         logging.critical(f"Runtime error encountered: {e}", exc_info=True)
         stop_event.set() # Ensure threads are signaled to stop
    except KeyboardInterrupt:
        logging.info("KeyboardInterrupt received (detected in main). Signalling shutdown...")
        stop_event.set() # Signal threads to stop
    except Exception as e:
        logging.critical(f"An unhandled exception occurred in main thread: {e}", exc_info=True)
        stop_event.set() # Ensure threads are signaled to stop

    finally:
        # 6. Wait for threads to finish and cleanup
        logging.info("Waiting for threads to finish...")
        if sampler and sampler.is_alive():
            sampler.join(timeout=5.0)
        if db_writer and db_writer.is_alive():
            q_size = data_queue.qsize()
            # Estimate wait time based on queue size and batch interval
            wait_time = max(10.0, DB_WRITE_INTERVAL_S * 2 + (q_size * DB_WRITE_INTERVAL_S * 0.5)) # Heuristic
            logging.info(f"DB writer queue size approx {q_size} on exit signal. Waiting up to {wait_time:.1f}s")
            db_writer.join(timeout=wait_time)

        if sampler and sampler.is_alive(): logging.warning("ADC Sampler thread did not exit gracefully.")
        if db_writer and db_writer.is_alive(): logging.warning("Database Writer thread did not exit gracefully.")

        logging.info("Closing database connection...")
        if db_connection:
            try:
                db_connection.close()
                logging.info("PostgreSQL connection closed.")
            except Exception as e: logging.error(f"Error closing database connection: {e}")

        logging.info("Cleaning up hardware resources...")
        try:
            if 'config' in sys.modules and hasattr(config, 'module_exit'):
                 config.module_exit()
                 logging.info("Hardware resources released via config.module_exit().")
            else: logging.warning("config.module_exit() not available for cleanup.")
        except Exception as e: logging.error(f"Error during final hardware cleanup: {e}")

        logging.info(f"ADS1256 Data Logger finished.")