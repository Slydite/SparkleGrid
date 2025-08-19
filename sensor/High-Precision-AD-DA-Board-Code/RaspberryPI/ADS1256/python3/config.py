# /*****************************************************************************
# * | File        :	  config.py (Modified for gpiozero)
# * | Author      :   Waveshare team / Modified for gpiozero
# * | Function    :   Hardware underlying interface
# * | Info        :
# *----------------
# * |	This version:   V1.1 (gpiozero)
# * | Date        :   2024-07-26
# * | Info        :   Replaced RPi.GPIO with gpiozero for Pi 5 compatibility
# ******************************************************************************/
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documnetation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to  whom the Software is
# furished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS OR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#

import spidev
from gpiozero import DigitalOutputDevice, DigitalInputDevice # Import gpiozero classes
import time

# Pin definition (Using BCM numbering)
RST_PIN         = 18
CS_PIN          = 22
DRDY_PIN        = 17

# --- Global variables for GPIO device objects ---
# These will be initialized in module_init()
rst_pin_device = None
cs_pin_device = None
drdy_pin_device = None

# SPI device, bus = 0, device = 0
# Initialize SPI here or within module_init
SPI = spidev.SpiDev()

def digital_write(pin, value):
    """ Writes to the specified GPIO pin. value should be 0 or 1. """
    if pin == RST_PIN and rst_pin_device:
        rst_pin_device.value = value
    elif pin == CS_PIN and cs_pin_device:
        cs_pin_device.value = value
    else:
        # Handle other pins or error if necessary
        print(f"Warning: Attempted to write to unconfigured pin {pin}")


def digital_read(pin):
    """ Reads from the specified GPIO pin. """
    if pin == DRDY_PIN and drdy_pin_device:
        # gpiozero returns 0 for low, 1 for high.
        # Original code checked for 0 (active low), so we return the direct value.
        return drdy_pin_device.value
    else:
        # Handle other pins or error if necessary
        print(f"Warning: Attempted to read from unconfigured pin {pin}")
        return None # Or raise an error

def delay_ms(delaytime):
    """ Delays for the specified number of milliseconds. """
    time.sleep(delaytime / 1000.0)

def spi_writebyte(data):
    """ Writes data (list of bytes) to SPI bus. """
    SPI.writebytes(data)

def spi_readbytes(num_bytes):
    """ Reads num_bytes from SPI bus. """
    return SPI.readbytes(num_bytes)


def module_init():
    """ Initializes GPIO pins and SPI communication using gpiozero. """
    global rst_pin_device, cs_pin_device, drdy_pin_device, SPI

    try:
        # Initialize GPIO devices
        rst_pin_device = DigitalOutputDevice(RST_PIN)
        cs_pin_device = DigitalOutputDevice(CS_PIN)
        # DRDY is active low, input with pull-up enabled
        drdy_pin_device = DigitalInputDevice(DRDY_PIN, pull_up=True)

        # Initialize SPI
        SPI.open(0, 0) # Open SPI bus 0, device 0
        SPI.max_speed_hz = 2000000  # Set SPI speed (adjust as needed, e.g., 2MHz or 4MHz)
        SPI.mode = 0b01           # Set SPI mode (CPOL=0, CPHA=1)

        print("GPIO and SPI initialized successfully using gpiozero.")
        return 0 # Success

    except Exception as e:
        print(f"Error initializing hardware: {e}")
        # Cleanup partially initialized resources if necessary
        if rst_pin_device: rst_pin_device.close()
        if cs_pin_device: cs_pin_device.close()
        if drdy_pin_device: drdy_pin_device.close()
        if SPI: SPI.close()
        rst_pin_device = cs_pin_device = drdy_pin_device = None
        return -1 # Failure

def module_exit():
    """ Cleans up GPIO and SPI resources. """
    global rst_pin_device, cs_pin_device, drdy_pin_device, SPI
    print("Cleaning up hardware resources...")
    if rst_pin_device:
        rst_pin_device.close()
    if cs_pin_device:
        cs_pin_device.close()
    if drdy_pin_device:
        drdy_pin_device.close()
    if SPI:
        SPI.close()
    print("Hardware resources released.")

### END OF FILE ###