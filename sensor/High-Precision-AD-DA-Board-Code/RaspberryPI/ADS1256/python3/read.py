#!/usr/bin/env python3
# -*- coding:utf-8 -*-

import ADS1256      # Import the ADS1256 library
import config       # Import the config library (for init/exit)
import time
import sys
import logging
import signal
import threading
import numpy as np  # <-- Import numpy

# --- Configuration ---
ADC_CHANNEL = 2
VREF = 5.065  # *** IMPORTANT: SET THIS TO THE MEASURED VREF!!! ***
ADC_GAIN = ADS1256.ADS1256_GAIN_E['ADS1256_GAIN_1']
ADC_RATE_ENUM = ADS1256.ADS1256_DRATE_E['ADS1256_1000SPS']

# --- Calibration Values ---
MEASURED_GAIN = 759.1  # <--- START WITH GAIN = 1, we will test different values
MEASURED_OFFSET_V = -1.348 # Your measured offset -  KEEP COMMENTED OUT INITIALLY
DATASHEET_OFFSET_V = 1.5 # Datasheet specified 1.5V offset

# How often to read and print (seconds)
READ_INTERVAL = 0.1 # Read 10 times per second

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# --- Global Variables ---
stop_event = threading.Event()
ADC = None

# --- Signal Handler ---
def signal_handler(sig, frame):
    logging.info('Interrupt received, stopping readings...')
    stop_event.set()

# --- Main Execution ---
if __name__ == "__main__":
    logging.info(f"Starting ADS1256 reader for Channel {ADC_CHANNEL}...")

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        ADC = ADS1256.ADS1256()
        if ADC.ADS1256_init() != 0:
            logging.critical("Failed to initialize ADS1256 hardware. Exiting.")
            try:
                 if 'config' in sys.modules and hasattr(config, 'module_exit'):
                     config.module_exit()
            except Exception as clean_e:
                 logging.error(f"Error during cleanup on init fail: {clean_e}")
            sys.exit(1)
        logging.info("ADS1256 hardware initialized successfully.")
        logging.warning(f"Using VREF = {VREF}V for voltage calculation. Ensure this is correct!")

        if not ADC.ADS1256_ConfigADC(ADC_GAIN, ADC_RATE_ENUM):
             logging.critical("Failed to configure ADC Gain/Rate. Exiting.")
             raise RuntimeError("ADC Configuration Failed")
        gain_str = [k for k, v in ADS1256.ADS1256_GAIN_E.items() if v == ADC_GAIN][0]
        rate_str = [k for k, v in ADS1256.ADS1256_DRATE_E.items() if v == ADC_RATE_ENUM][0]
        logging.info(f"ADC Configured: Gain={gain_str}, Rate={rate_str}")

        logging.info(f"Starting continuous readings from Channel {ADC_CHANNEL}. Press Ctrl+C to stop.")

        voltage_batch = [] # List to store voltage readings for RMS calculation
        max_adc_count = 0x7FFFFF # 8388607.0

        while not stop_event.is_set():
            read_start_time = time.monotonic()

            raw_value = ADC.ADS1256_GetChannalValue(ADC_CHANNEL)

            if raw_value is not None:
                # --- Calibrated Voltage Calculation ---
                voltage_raw = (raw_value / max_adc_count) * VREF
                voltage_biased = voltage_raw - DATASHEET_OFFSET_V
                voltage_scaled = voltage_biased / MEASURED_GAIN
                voltage_calibrated = voltage_scaled - MEASURED_OFFSET_V
                voltage = voltage_raw
                logging.info(f"Channel {ADC_CHANNEL}: Raw = {raw_value:8d}, Voltage = {voltage: 9.5f} (unCalibrated)")


                voltage_batch.append(voltage) # Add voltage to batch list
                logging.info(f"Channel {ADC_CHANNEL}: Raw = {raw_value:8d}, Voltage = {voltage: 9.5f} V (unCalibrated)")

            else:
                logging.warning(f"Failed to read ADC channel {ADC_CHANNEL} (returned None)")
                time.sleep(0.5)

            # --- RMS Calculation and Logging (after collecting a batch) ---
            if len(voltage_batch) >= 100: # Process batch of 100 samples
                voltage_array = np.array(voltage_batch)
                rms_voltage = np.sqrt(np.mean(np.square(voltage_array)))
                logging.info(f"uncalibrated RMS Voltage (Batch of {len(voltage_batch)}): {rms_voltage:.6f} V")
                voltage_batch = [] # Clear batch for next set of readings


            read_end_time = time.monotonic()
            elapsed_time = read_end_time - read_start_time
            sleep_time = max(0, READ_INTERVAL - elapsed_time)
            stop_event.wait(sleep_time)


    except RuntimeError as e:
         logging.critical(f"Runtime error encountered: {e}", exc_info=True)
    except KeyboardInterrupt:
        logging.info("KeyboardInterrupt received, exiting loop.")
    except Exception as e:
        logging.critical(f"An unhandled exception occurred: {e}", exc_info=True)

    finally:
        logging.info("Cleaning up hardware resources...")
        try:
            if 'config' in sys.modules and hasattr(config, 'module_exit'):
                 config.module_exit()
                 logging.info("Hardware resources released via config.module_exit().")
            else:
                 logging.warning("config.module_exit() not available for cleanup.")
        except Exception as e:
            logging.error(f"Error during final hardware cleanup: {e}")

        logging.info("ADS1256 reader finished.")