#!/usr/bin/env python3
# -*- coding:utf-8 -*-

import ADS1256      # Import the ADS1256 library
import config       # Import the config library (for init/exit)
import time
import sys
import logging
import signal
import threading

# --- Configuration ---
ADC_CHANNEL = 6   # *** Set the channel to read from ***
VREF = 5.0          # *** IMPORTANT: Set this to the ACTUAL measured Vref voltage of your ADS1256 board! ***
ADC_GAIN = ADS1256.ADS1256_GAIN_E['ADS1256_GAIN_1'] # Set Gain to 1 (adjust if needed)
# Choose a data rate (e.g., 1000 SPS)
ADC_RATE_ENUM = ADS1256.ADS1256_DRATE_E['ADS1256_1000SPS']
#ADC_RATE_HZ = 1000 # Corresponding approximate sample rate

# How often to read and print (seconds)
READ_INTERVAL = 0.1 # Read 10 times per second

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# --- Global Variables ---
stop_event = threading.Event() # Using threading Event for cleaner signal handling
ADC = None # ADC object holder

# --- Signal Handler ---
def signal_handler(sig, frame):
    logging.info('Interrupt received, stopping readings...')
    stop_event.set()

# --- Main Execution ---
if __name__ == "__main__":
    logging.info(f"Starting ADS1256 reader for Channel {ADC_CHANNEL}...")

    # Register signal handlers for graceful exit
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # 1. Initialize ADC Hardware using the library
        ADC = ADS1256.ADS1256()
        if ADC.ADS1256_init() != 0:
            logging.critical("Failed to initialize ADS1256 hardware via ADS1256_init(). Exiting.")
            # Attempt cleanup even on init fail
            try:
                 if 'config' in sys.modules and hasattr(config, 'module_exit'):
                     config.module_exit()
            except Exception as clean_e:
                 logging.error(f"Error during cleanup on init fail: {clean_e}")
            sys.exit(1)
        logging.info("ADS1256 hardware initialized successfully.")
        logging.warning(f"Using VREF = {VREF}V for voltage calculation. Ensure this is correct!")

        # 2. Configure ADC Gain and Rate (Optional, but good practice)
        # Note: ADS1256_init might set defaults, this explicitly sets them.
        if not ADC.ADS1256_ConfigADC(ADC_GAIN, ADC_RATE_ENUM):
             logging.critical("Failed to configure ADC Gain/Rate. Exiting.")
             raise RuntimeError("ADC Configuration Failed") # Raise exception to trigger finally block
        gain_str = [k for k, v in ADS1256.ADS1256_GAIN_E.items() if v == ADC_GAIN][0]
        rate_str = [k for k, v in ADS1256.ADS1256_DRATE_E.items() if v == ADC_RATE_ENUM][0]
        logging.info(f"ADC Configured: Gain={gain_str}, Rate={rate_str}")


        # 3. Reading Loop
        logging.info(f"Starting continuous readings from Channel {ADC_CHANNEL}. Press Ctrl+C to stop.")
        while not stop_event.is_set():
            read_start_time = time.monotonic()

            # Get the raw ADC value for the specified channel
            # ADS1256_GetChannalValue handles setting the MUX, SYNC, WAKEUP, and Read Data
            raw_value = ADC.ADS1256_GetChannalValue(ADC_CHANNEL)

            if raw_value is not None:
                # Convert raw ADC value to voltage
                # ADS1256 is 24-bit, max positive value is 0x7FFFFF for +VREF input
                # Formula: voltage = (raw_adc / (2^23 - 1)) * Vref / Gain
                # Since Gain is 1 here, we simplify:
                max_adc_count = 0x7FFFFF # 8388607.0
                voltage = (raw_value / max_adc_count) * VREF

                logging.info(f"Channel {ADC_CHANNEL}: Raw = {raw_value:8d}, Voltage = {voltage: 9.5f} V")

            else:
                # ADS1256_GetChannalValue returned None, likely due to DRDY timeout
                logging.warning(f"Failed to read ADC channel {ADC_CHANNEL} (returned None)")
                # Add a small delay if errors are frequent to avoid spamming
                time.sleep(0.5)

            # --- Calculate sleep time for target interval ---
            read_end_time = time.monotonic()
            elapsed_time = read_end_time - read_start_time
            sleep_time = max(0, READ_INTERVAL - elapsed_time)

            # Use event wait for interruptible sleep
            stop_event.wait(sleep_time)


    except RuntimeError as e:
         logging.critical(f"Runtime error encountered: {e}", exc_info=True)
    except KeyboardInterrupt:
        logging.info("KeyboardInterrupt received, exiting loop.")
    except Exception as e:
        logging.critical(f"An unhandled exception occurred: {e}", exc_info=True)

    finally:
        # 4. Cleanup hardware resources
        logging.info("Cleaning up hardware resources...")
        try:
            # Check if config module was imported and has the function
            if 'config' in sys.modules and hasattr(config, 'module_exit'):
                 config.module_exit()
                 logging.info("Hardware resources released via config.module_exit().")
            else:
                 logging.warning("config.module_exit() not available for cleanup.")
        except Exception as e:
            logging.error(f"Error during final hardware cleanup: {e}")

        logging.info("ADS1256 reader finished.")