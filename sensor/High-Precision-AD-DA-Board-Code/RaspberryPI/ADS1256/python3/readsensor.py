#!/usr/bin/env python3
# -*- coding:utf-8 -*-

import ADS1256      # Import the ADS1256 library
import config       # Import the config library (for init/exit)
import psycopg2     # <-- Added for Database
import numpy as np  # <-- Added for RMS calculation
import datetime     # <-- Added for Timestamps
import time
import sys
import queue        # <-- Added for Queue
import logging
import signal
import threading

# --- Configuration ---
ADC_CHANNEL = 2   # Channel to read from
VREF = 5.0          # *** IMPORTANT: Set this to the ACTUAL measured Vref voltage! ***
ADC_GAIN = ADS1256.ADS1256_GAIN_E['ADS1256_GAIN_1'] # Gain 1
ADC_RATE_ENUM = ADS1256.ADS1256_DRATE_E['ADS1256_1000SPS'] # 1000 SPS Rate
ADC_SAMPLE_RATE_HZ = 1000 # Corresponding sample rate in Hz (MUST match ADC_RATE_ENUM)

# --- Database Configuration ---
DB_HOST = "localhost"
DB_NAME = "gridsense_db"
DB_USER = "gridsense_user"
DB_PASSWORD = "microgrid"
DB_TABLE = "measurements_six" # Make sure this table exists in gridsense_db

SENSOR_ID_DB = 1 # Sensor ID to use in the database table (adjust if needed)
SENSOR_NAME_DB = f"Voltage Sensor Ch{ADC_CHANNEL}"
SENSOR_TYPE_DB = "Voltage"

# --- Queue and Batching Configuration ---
DB_WRITE_INTERVAL_S = 1.0 # How often DB writer wakes up to check queue (seconds)
# Max samples to buffer before forcing a DB write (safety measure)
MAX_QUEUE_SIZE = ADC_SAMPLE_RATE_HZ * 5 # 5 seconds worth of data

# --- Clamping Limits for NUMERIC(5, 2) in DB ---
NUMERIC_5_2_MAX = 999.99
NUMERIC_5_2_MIN = -999.99

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(threadName)s - %(levelname)s - %(message)s')

# --- Global Variables ---
data_queue = queue.Queue(maxsize=MAX_QUEUE_SIZE) # Queue for ADC data
stop_event = threading.Event() # Event for stopping threads gracefully
ADC = None # ADC object holder

# --- Clamping Function ---
def clamp_value(value, min_val=NUMERIC_5_2_MIN, max_val=NUMERIC_5_2_MAX):
    """Clamps a value within the specified min/max range."""
    return max(min_val, min(max_val, value))

# --- Database Functions ---
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
    """ Inserts a batch of sensor data into the database.
        sensdata_batch should be a list of [clamped_voltage, clamped_delta_time_ms] pairs.
    """
    if not sensdata_batch:
        logging.warning("Attempted to insert empty batch.")
        return False

    voltages_only = [item[0] for item in sensdata_batch] # Voltages are already clamped here
    rms_value = calculate_rms(voltages_only)

    clamped_rms = clamp_value(rms_value)
    if clamped_rms != rms_value:
        logging.warning(f"Clamped RMS value from {rms_value:.4f} to {clamped_rms:.2f} for batch ID {batch_id}")

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
            logging.debug(f"Successfully inserted batch ID {batch_id} with {len(sensdata_batch)} samples.")
            return True

    except (psycopg2.Error, TypeError) as e:
        logging.error(f"Error inserting batch ID {batch_id}: {e}", exc_info=True)
        try: connection.rollback()
        except psycopg2.Error as rb_e: logging.error(f"Error rolling back transaction: {rb_e}")
        return False

# --- ADC Sampling Thread ---
def adc_sampler_thread():
    """Continuously samples the ADC and puts data onto the queue."""
    logging.info(f"ADC Sampler thread started - Target Rate: {ADC_SAMPLE_RATE_HZ} SPS.")
    sample_interval = 1.0 / ADC_SAMPLE_RATE_HZ
    max_adc_count = 0x7FFFFF # 8388607.0 for clarity in calculation

    # --- !!! CHANGE: Set channel ONCE before the loop !!! ---
    if not ADC.ADS1256_SetChannal(ADC_CHANNEL):
        logging.error(f"Failed to set ADC channel {ADC_CHANNEL} initially. Stopping thread.")
        stop_event.set() # Signal other threads to stop too
        return # Exit thread
    logging.info(f"ADC Channel set to {ADC_CHANNEL}")
    # Optional small delay after setting channel before starting reads
    time.sleep(0.01)
    # --------------------------------------------------------

    while not stop_event.is_set():
        read_start_time = time.monotonic()
        measurement_time = datetime.datetime.now(datetime.timezone.utc) # Timestamp for the reading

        # --- !!! CHANGE: Call Read_ADC_Data directly !!! ---
        # This function waits for DRDY and reads the latest completed conversion
        raw_value = ADC.ADS1256_Read_ADC_Data()
        # ---------------------------------------------------

        if raw_value is not None:
            # Convert raw ADC value to voltage (using explicit max count)
            voltage = (raw_value / max_adc_count) * VREF if VREF != 0 else 0.0
            #logging.info(f"Read Raw={raw_value}, V={voltage:.4f}") # Uncomment for deep debug

            try:
                # Put (timestamp, voltage) tuple onto the queue
                data_queue.put((measurement_time, voltage), block=True, timeout=0.5)
            except queue.Full:
                logging.warning("Data queue is full. Sample might be dropped.")
            except Exception as e:
                 logging.error(f"Error putting data onto queue: {e}")

        else:
            # Read_ADC_Data returned None, likely WaitDRDY timeout
            logging.warning(f"Failed to read ADC channel {ADC_CHANNEL} (WaitDRDY Timeout?)")
            time.sleep(0.1) # Small delay on read failure

        # --- Calculate sleep time for target rate ---
        read_end_time = time.monotonic()
        elapsed_time = read_end_time - read_start_time
        sleep_time = max(0, sample_interval - elapsed_time)

        stop_event.wait(sleep_time) # Interruptible sleep

    logging.info("ADC Sampler thread finished.")
    
    
# --- Database Writer Thread (Copied from previous script) ---
def database_writer_thread(db_connection):
    """ Periodically collects data from the queue and writes batches to the database. """
    logging.info("Database Writer thread started.")
    last_write_time = time.monotonic()
    current_raw_batch = [] # Store raw (timestamp, voltage) tuples first
    current_db_id = get_max_id(db_connection) # Get initial max ID

    while not stop_event.is_set() or not data_queue.empty(): # Process remaining queue items after stop signal
        try:
            timestamp, voltage = data_queue.get(block=True, timeout=0.1)
            current_raw_batch.append((timestamp, voltage))
            data_queue.task_done()
        except queue.Empty:
            if stop_event.is_set():
                logging.debug("Queue empty and stop event set, proceeding to final write check.")
            pass

        current_time = time.monotonic()
        force_write = len(current_raw_batch) >= (MAX_QUEUE_SIZE * 0.9)
        time_to_write = (current_time - last_write_time) >= DB_WRITE_INTERVAL_S

        if (time_to_write or force_write or (stop_event.is_set() and current_raw_batch)) and current_raw_batch:
             if force_write:
                 logging.warning(f"Forcing DB write due to large batch size ({len(current_raw_batch)} samples).")

             batch_start_time = current_raw_batch[0][0]

             sensdata_for_db = []
             for item_timestamp, item_voltage in current_raw_batch:
                 clamped_voltage = clamp_value(item_voltage)
                 if clamped_voltage != item_voltage:
                     logging.debug(f"Clamped voltage from {item_voltage:.4f} to {clamped_voltage:.2f}")

                 delta_t_ms = (item_timestamp - batch_start_time).total_seconds() * 1000.0
                 clamped_delta_t_ms = clamp_value(delta_t_ms)
                 if clamped_delta_t_ms != delta_t_ms:
                     logging.debug(f"Clamped delta_t from {delta_t_ms:.4f} to {clamped_delta_t_ms:.2f}")

                 sensdata_for_db.append([round(clamped_voltage, 2), round(clamped_delta_t_ms, 2)])

             current_db_id += 1
             success = insert_batch_data(
                 db_connection, current_db_id, SENSOR_ID_DB, batch_start_time,
                 sensdata_for_db, SENSOR_NAME_DB, SENSOR_TYPE_DB
             )
             if success:
                 pass
                 logging.info(f"DB Write: ID {current_db_id}, Samples: {len(sensdata_for_db)}, StartTime: {batch_start_time.time()}")
             else:
                 logging.error(f"DB Write failed for batch starting at {batch_start_time}")
                 current_db_id -= 1

             current_raw_batch = []
             last_write_time = current_time

        if not current_raw_batch and not stop_event.is_set():
            time.sleep(0.05) # Short sleep when idle

    logging.info("Database Writer thread finished.")

# --- Signal Handler (Keep as is) ---
def signal_handler(sig, frame):
    logging.info('Interrupt received, shutting down...')
    stop_event.set()

# --- Main Execution (Adapted for Threads and DB) ---
if __name__ == "__main__":
    logging.info(f"Starting ADS1256 Data Logger for Channel {ADC_CHANNEL}...")
    db_connection = None
    sampler = None
    db_writer = None

    # Register signal handlers for graceful exit
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # 1. Initialize ADC Hardware
        ADC = ADS1256.ADS1256()
        if ADC.ADS1256_init() != 0:
            logging.critical("Failed to initialize ADS1256 hardware via ADS1256_init(). Exiting.")
            try:
                 if 'config' in sys.modules and hasattr(config, 'module_exit'):
                     config.module_exit()
            except Exception as clean_e: logging.error(f"Error during cleanup on init fail: {clean_e}")
            sys.exit(1)
        logging.info("ADS1256 hardware initialized successfully.")
        logging.warning(f"Using VREF = {VREF}V for voltage calculation. Ensure this is correct!")

        # 2. Configure ADC Gain and Rate
        if not ADC.ADS1256_ConfigADC(ADC_GAIN, ADC_RATE_ENUM):
             logging.critical("Failed to configure ADC Gain/Rate. Exiting.")
             raise RuntimeError("ADC Configuration Failed")
        gain_str = [k for k, v in ADS1256.ADS1256_GAIN_E.items() if v == ADC_GAIN][0]
        rate_str = [k for k, v in ADS1256.ADS1256_DRATE_E.items() if v == ADC_RATE_ENUM][0]
        logging.info(f"ADC Configured: Gain={gain_str}, Rate={rate_str} ({ADC_SAMPLE_RATE_HZ} SPS target)")

        # 3. Connect to Database
        db_connection = create_connection()
        if not db_connection:
            logging.critical("Failed to connect to database. Exiting.")
            raise RuntimeError("Database Connection Failed")

        # 4. Create and start threads (Instead of simple read loop)
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
        logging.info("KeyboardInterrupt received, initiating shutdown...")
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
            logging.info(f"DB writer queue size approx {data_queue.qsize()} on exit signal.")
            db_writer.join(timeout=max(10.0, DB_WRITE_INTERVAL_S * 2))

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

        logging.info("ADS1256 Data Logger finished.")