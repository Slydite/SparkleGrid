import ADS1256
import config  # Assuming config.py handles hardware init/cleanup
import psycopg2
import numpy as np
import datetime
import threading
import time
import signal
import sys
import queue
import logging

# --- Configuration Constants ---
DB_HOST = "localhost"
DB_NAME = "gridsense_db"
DB_USER = "gridsense_user"
DB_PASSWORD = "microgrid"
DB_TABLE = "measurements_six" # Make sure this table exists in gridsense_db

ADC_CHANNEL = 2  # Channel to read voltage from
ADC_GAIN = ADS1256.ADS1256_GAIN_E['ADS1256_GAIN_1']
ADC_RATE_ENUM = ADS1256.ADS1256_DRATE_E['ADS1256_2000SPS']
ADC_SAMPLE_RATE_HZ = 2000  # Target sampling rate (should match ADC_RATE_ENUM if possible)
VREF = 5.0 # Reference voltage for ADC conversion

SENSOR_ID_DB = 1 # Sensor ID to use in the database table
SENSOR_NAME_DB = f"Voltage Sensor Ch{ADC_CHANNEL}"
SENSOR_TYPE_DB = "Voltage"

# How often the database writer thread tries to write a batch (seconds)
DB_WRITE_INTERVAL_S = 1.0
# Max samples to buffer before forcing a DB write (safety measure)
MAX_QUEUE_SIZE = ADC_SAMPLE_RATE_HZ * 5 # e.g., 5 seconds worth

# --- !!! NEW: Clamping Limits for NUMERIC(5, 2) ---
NUMERIC_5_2_MAX = 999.99
NUMERIC_5_2_MIN = -999.99
# ----------------------------------------------------

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(threadName)s - %(levelname)s - %(message)s')

# --- Global Variables ---
data_queue = queue.Queue(maxsize=MAX_QUEUE_SIZE)
stop_event = threading.Event()
ADC = None # ADC object holder

# --- Clamping Function ---
def clamp_value(value, min_val=NUMERIC_5_2_MIN, max_val=NUMERIC_5_2_MAX):
    """Clamps a value within the specified min/max range."""
    return max(min_val, min(max_val, value))

# --- Database Functions ---
def create_connection():
    # ... (no changes needed) ...
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
    # ... (no changes needed) ...
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
        # Depending on strategy, could return None or raise error
    return max_id

def calculate_rms(voltage_list):
    # ... (no changes needed) ...
    """Calculates RMS value from a list of voltage floats."""
    if not voltage_list:
        return 0.0
    numeric_array = np.array(voltage_list, dtype=float)
    return np.sqrt(np.mean(np.square(numeric_array)))

def insert_batch_data(connection, batch_id, sensor_id, batch_start_time, sensdata_batch, sname, stype):
    """ Inserts a batch of sensor data into the database.
        sensdata_batch should be a list of [clamped_voltage, clamped_delta_time_ms] pairs.
    """
    if not sensdata_batch:
        logging.warning("Attempted to insert empty batch.")
        return False

    # RMS is calculated *before* clamping voltages in sensdata, which might be desired?
    # If RMS should also reflect clamped values, calculate it from sensdata_batch[*][0]
    voltages_only = [item[0] for item in sensdata_batch] # Voltages are already clamped here
    rms_value = calculate_rms(voltages_only)

    # --- Clamp RMS value before insertion ---
    clamped_rms = clamp_value(rms_value)
    if clamped_rms != rms_value:
        logging.warning(f"Clamped RMS value from {rms_value:.4f} to {clamped_rms:.2f} for batch ID {batch_id}")
    # --------------------------------------

    try:
        with connection.cursor() as cursor:
            timestamp = batch_start_time.isoformat()
            query = f"""
            INSERT INTO {DB_TABLE}(id, sensor_id, sensdata, time, rmsvalue, sname, stype, thd, pf)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
            """
            # Pass the list-of-lists directly, psycopg2 adapts it to numeric[][]
            cursor.execute(query, (
                batch_id,
                sensor_id,
                sensdata_batch, # Already clamped [voltage, delta_t] pairs
                timestamp,
                float(clamped_rms), # Pass clamped standard Python float
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
        try:
            connection.rollback()
        except psycopg2.Error as rb_e:
            logging.error(f"Error rolling back transaction: {rb_e}")
        return False

# --- ADC Sampling Thread ---
def adc_sampler_thread():
    # ... (no changes needed in sampling itself) ...
    """Continuously samples the ADC and puts data onto the queue."""
    logging.info("ADC Sampler thread started.")
    sample_interval = 1.0 / ADC_SAMPLE_RATE_HZ

    while not stop_event.is_set():
        read_start_time = time.monotonic()
        measurement_time = datetime.datetime.now(datetime.timezone.utc) # Timestamp for the reading

        raw_value = ADC.ADS1256_GetChannalValue(ADC_CHANNEL)
        # if raw_value == 0:
        #     logging.warning("Raw value is 0! Reading diagnostic MUX register.")
        #     try:
        #         # Use the direct read function from the library
        #         # *** Access REG_E through the ADS1256 module ***
        #         mux_reg_val = ADC.ADS1256_Read_data(ADS1256.REG_E['REG_MUX']) # <-- Corrected line
        #         if mux_reg_val:
        #             logging.warning(f"Attempted MUX register readback: {hex(mux_reg_val[0])}")
        #         else:
        #             logging.warning("MUX register readback failed (returned None/empty).")

        #         # You could add reads for other registers here too, if needed:
        #         # status_reg = ADC.ADS1256_Read_data(ADS1256.REG_E['REG_STATUS'])
        #         # adcon_reg = ADC.ADS1256_Read_data(ADS1256.REG_E['REG_ADCON'])
        #         # drate_reg = ADC.ADS1256_Read_data(ADS1256.REG_E['DRATE'])
        #         # logging.warning(f"STATUS={hex(status_reg[0]) if status_reg else 'Fail'} | ADCON={hex(adcon_reg[0]) if adcon_reg else 'Fail'} | DRATE={hex(drate_reg[0]) if drate_reg else 'Fail'}")

        #     except Exception as diag_e:
        #         logging.error(f"Error reading diagnostic registers: {diag_e}", exc_info=True)
                
        if raw_value is not None:
            # Convert raw ADC value to voltage
            # ADS1256 is 24-bit, max positive value is 0x7FFFFF for VREF input
            voltage = (raw_value / 0x7FFFFF) * VREF if VREF != 0 else 0.0
            logging.info(f"Calculated Voltage: {voltage:.4f}")
            try:
                # Put (timestamp, voltage) tuple onto the queue
                data_queue.put((measurement_time, voltage), block=True, timeout=0.5) # Block with timeout
            except queue.Full:
                logging.warning("Data queue is full. Sample might be dropped.")
                # Optional: Implement strategy for full queue (e.g., discard oldest)
            except Exception as e:
                 logging.error(f"Error putting data onto queue: {e}")

        else:
            logging.warning(f"Failed to read ADC channel {ADC_CHANNEL}")
            # Optional: add a small delay here if read failures are frequent

        # --- Calculate sleep time for target rate ---
        read_end_time = time.monotonic()
        elapsed_time = read_end_time - read_start_time
        sleep_time = max(0, sample_interval - elapsed_time)

        # Use event wait for interruptible sleep
        stop_event.wait(sleep_time)

    logging.info("ADC Sampler thread finished.")


# --- Database Writer Thread ---
def database_writer_thread(db_connection):
    """ Periodically collects data from the queue and writes batches to the database. """
    logging.info("Database Writer thread started.")
    last_write_time = time.monotonic()
    current_raw_batch = [] # Store raw (timestamp, voltage) tuples first
    current_db_id = get_max_id(db_connection) # Get initial max ID

    while not stop_event.is_set() or not data_queue.empty(): # Process remaining queue items after stop signal
        try:
            # Get data from queue with a timeout
            timestamp, voltage = data_queue.get(block=True, timeout=0.1)
            current_raw_batch.append((timestamp, voltage)) # Store raw data
            data_queue.task_done()

        except queue.Empty:
            if stop_event.is_set():
                logging.debug("Queue empty and stop event set, proceeding to final write check.")
            pass

        current_time = time.monotonic()
        force_write = len(current_raw_batch) >= (MAX_QUEUE_SIZE * 0.9)
        time_to_write = (current_time - last_write_time) >= DB_WRITE_INTERVAL_S

        # Process and write batch if conditions met AND batch has data
        if (time_to_write or force_write or stop_event.is_set()) and current_raw_batch:
             if force_write:
                 logging.warning("Forcing DB write due to large batch size.")

             batch_start_time = current_raw_batch[0][0] # Timestamp of the first item

             # --- !!! Clamp values and format batch for DB !!! ---
             sensdata_for_db = []
             for item_timestamp, item_voltage in current_raw_batch:
                 # Clamp Voltage
                 clamped_voltage = clamp_value(item_voltage)
                 if clamped_voltage != item_voltage:
                     logging.warning(f"Clamped voltage from {item_voltage:.4f} to {clamped_voltage:.2f}")

                 # Calculate and Clamp Delta Time
                 delta_t_ms = (item_timestamp - batch_start_time).total_seconds() * 1000.0
                 clamped_delta_t_ms = clamp_value(delta_t_ms)
                 if clamped_delta_t_ms != delta_t_ms:
                     # This will happen often for samples near the end of the 1-sec batch
                     logging.debug(f"Clamped delta_t from {delta_t_ms:.4f} to {clamped_delta_t_ms:.2f}")

                 # Append clamped values, rounded to 2 decimal places for DB
                 sensdata_for_db.append([round(clamped_voltage, 2), round(clamped_delta_t_ms, 2)])
            # -------------------------------------------------------

             current_db_id += 1
             success = insert_batch_data(
                 db_connection,
                 current_db_id,
                 SENSOR_ID_DB,
                 batch_start_time,
                 sensdata_for_db, # Pass the batch with clamped values
                 SENSOR_NAME_DB,
                 SENSOR_TYPE_DB
             )
             if success:
                 logging.info(f"DB Write: ID {current_db_id}, Samples: {len(sensdata_for_db)}, StartTime: {batch_start_time.time()}")
             else:
                 logging.error(f"DB Write failed for batch starting at {batch_start_time}")
                 current_db_id -= 1 # Decrement ID on failure

             # Reset raw batch and timer
             current_raw_batch = []
             last_write_time = current_time

        if not current_raw_batch and not stop_event.is_set():
            time.sleep(0.05)

    logging.info("Database Writer thread finished.")


# --- Signal Handler ---
def signal_handler(sig, frame):
    # ... (no changes needed) ...
    logging.info('Interrupt received, shutting down...')
    stop_event.set()


# --- Main Execution ---
if __name__ == "__main__":
    # ... (no changes needed in main setup/teardown) ...
    logging.info("Starting Microgrid Data Logger...")
    db_connection = None
    sampler = None
    db_writer = None

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Initialize ADC Hardware (make sure config.py is loaded/used by ADS1256)
        ADC = ADS1256.ADS1256()
        if ADC.ADS1256_init() != 0:
            logging.critical("Failed to initialize ADS1256 hardware. Exiting.")
            sys.exit(1)

        # Configure ADC Gain/Rate (optional if init sets desired values)
        if not ADC.ADS1256_ConfigADC(ADC_GAIN, ADC_RATE_ENUM):
             logging.critical("Failed to configure ADC Gain/Rate. Exiting.")
             # Attempt cleanup before exiting
             try:
                 config.module_exit()
             except Exception as e:
                 logging.error(f"Error during hardware cleanup on config fail: {e}")
             sys.exit(1)
        logging.info(f"ADC Configured: Gain={list(ADS1256.ADS1256_GAIN_E.keys())[list(ADS1256.ADS1256_GAIN_E.values()).index(ADC_GAIN)]}, Rate={ADC_SAMPLE_RATE_HZ}SPS (approx)")

        # Connect to Database
        db_connection = create_connection()
        if not db_connection:
            logging.critical("Failed to connect to database. Exiting.")
            # Attempt cleanup before exiting
            try:
                 config.module_exit()
            except Exception as e:
                 logging.error(f"Error during hardware cleanup on DB fail: {e}")
            sys.exit(1)

        # Create and start threads
        sampler = threading.Thread(target=adc_sampler_thread, name="ADCSampler")
        db_writer = threading.Thread(target=database_writer_thread, args=(db_connection,), name="DBWriter")

        sampler.daemon = False # Set to False for graceful shutdown
        db_writer.daemon = False

        logging.info("Starting worker threads...")
        sampler.start()
        db_writer.start()

        # Keep main thread alive, periodically checking if threads are running
        while not stop_event.is_set():
            if not sampler.is_alive() or not db_writer.is_alive():
                 logging.error("A worker thread has unexpectedly stopped. Signaling shutdown.")
                 stop_event.set()
            # Sleep or wait here, allowing signal handler to interrupt
            time.sleep(1.0) # Check threads every second

    except Exception as e:
        logging.critical(f"An unhandled exception occurred in the main thread: {e}", exc_info=True)
        stop_event.set() # Signal threads to stop on critical error

    finally:
        logging.info("Waiting for threads to finish...")
        if sampler and sampler.is_alive():
            sampler.join(timeout=5.0)
        if db_writer and db_writer.is_alive():
            # Wait longer for DB thread, especially if queue has items
            db_writer.join(timeout=10.0)

        if sampler and sampler.is_alive():
            logging.warning("ADC Sampler thread did not exit gracefully.")
        if db_writer and db_writer.is_alive():
            logging.warning("Database Writer thread did not exit gracefully.")

        # Final Cleanup
        logging.info("Closing database connection...")
        if db_connection:
            try:
                db_connection.close()
                logging.info("PostgreSQL connection closed.")
            except Exception as e:
                logging.error(f"Error closing database connection: {e}")

        logging.info("Cleaning up hardware resources...")
        try:
            if 'config' in sys.modules: # Check if config module was imported successfully
                 config.module_exit()
                 logging.info("Hardware resources released via config.module_exit().")
            else:
                 logging.warning("config module not found in sys.modules, skipping module_exit().")
        except AttributeError:
             logging.warning("config module does not have module_exit() function.")
        except Exception as e:
            logging.error(f"Error during final hardware cleanup: {e}")

        logging.info("Microgrid Data Logger finished.")