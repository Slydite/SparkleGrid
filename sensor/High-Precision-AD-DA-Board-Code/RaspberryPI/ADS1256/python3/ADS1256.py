import config
# import RPi.GPIO as GPIO # Removed this import
import time
ScanMode = 0

# --- Constants (GAIN, DRATE, REG, CMD) remain unchanged ---
# gain channel
ADS1256_GAIN_E = {'ADS1256_GAIN_1' : 0, # GAIN   1
                  'ADS1256_GAIN_2' : 1,	# GAIN   2
                  'ADS1256_GAIN_4' : 2,	# GAIN   4
                  'ADS1256_GAIN_8' : 3,	# GAIN   8
                  'ADS1256_GAIN_16' : 4,# GAIN  16
                  'ADS1256_GAIN_32' : 5,# GAIN  32
                  'ADS1256_GAIN_64' : 6,# GAIN  64
                 }

# data rate
ADS1256_DRATE_E = {'ADS1256_30000SPS' : 0xF0, # reset the default values
                   'ADS1256_15000SPS' : 0xE0,
                   'ADS1256_7500SPS' : 0xD0,
                   'ADS1256_3750SPS' : 0xC0,
                   'ADS1256_2000SPS' : 0xB0,
                   'ADS1256_1000SPS' : 0xA1,
                   'ADS1256_500SPS' : 0x92,
                   'ADS1256_100SPS' : 0x82,
                   'ADS1256_60SPS' : 0x72,
                   'ADS1256_50SPS' : 0x63,
                   'ADS1256_30SPS' : 0x53,
                   'ADS1256_25SPS' : 0x43,
                   'ADS1256_15SPS' : 0x33,
                   'ADS1256_10SPS' : 0x20,
                   'ADS1256_5SPS' : 0x13,
                   'ADS1256_2d5SPS' : 0x03
                  }

# registration definition
REG_E = {'REG_STATUS' : 0,  # x1H
         'REG_MUX' : 1,     # 01H
         'REG_ADCON' : 2,   # 20H
         'REG_DRATE' : 3,   # F0H
         'REG_IO' : 4,      # E0H
         'REG_OFC0' : 5,    # xxH
         'REG_OFC1' : 6,    # xxH
         'REG_OFC2' : 7,    # xxH
         'REG_FSC0' : 8,    # xxH
         'REG_FSC1' : 9,    # xxH
         'REG_FSC2' : 10,   # xxH
        }

# command definition
CMD = {'CMD_WAKEUP' : 0x00,     # Completes SYNC and Exits Standby Mode 0000  0000 (00h)
       'CMD_RDATA' : 0x01,      # Read Data 0000  0001 (01h)
       'CMD_RDATAC' : 0x03,     # Read Data Continuously 0000   0011 (03h)
       'CMD_SDATAC' : 0x0F,     # Stop Read Data Continuously 0000   1111 (0Fh)
       'CMD_RREG' : 0x10,       # Read from REG rrr 0001 rrrr (1xh)
       'CMD_WREG' : 0x50,       # Write to REG rrr 0101 rrrr (5xh)
       'CMD_SELFCAL' : 0xF0,    # Offset and Gain Self-Calibration 1111    0000 (F0h)
       'CMD_SELFOCAL' : 0xF1,   # Offset Self-Calibration 1111    0001 (F1h)
       'CMD_SELFGCAL' : 0xF2,   # Gain Self-Calibration 1111    0010 (F2h)
       'CMD_SYSOCAL' : 0xF3,    # System Offset Calibration 1111   0011 (F3h)
       'CMD_SYSGCAL' : 0xF4,    # System Gain Calibration 1111    0100 (F4h)
       'CMD_SYNC' : 0xFC,       # Synchronize the A/D Conversion 1111   1100 (FCh)
       'CMD_STANDBY' : 0xFD,    # Begin Standby Mode 1111   1101 (FDh)
       'CMD_RESET' : 0xFE,      # Reset to Power-Up Values 1111   1110 (FEh)
      }

class ADS1256:
    def __init__(self):
        self.rst_pin = config.RST_PIN
        self.cs_pin = config.CS_PIN
        self.drdy_pin = config.DRDY_PIN
        # Note: GPIO devices are now managed within the config module

    # Hardware reset
    def ADS1256_reset(self):
        # Use 1 for HIGH, 0 for LOW
        config.digital_write(self.rst_pin, 1)
        config.delay_ms(200)
        config.digital_write(self.rst_pin, 0)
        config.delay_ms(200)
        config.digital_write(self.rst_pin, 1)

    def ADS1256_WriteCmd(self, reg):
        # Use 0 for LOW, 1 for HIGH
        config.digital_write(self.cs_pin, 0) # cs low
        config.spi_writebyte([reg])
        config.digital_write(self.cs_pin, 1) # cs high

    def ADS1256_WriteReg(self, reg, data):
        # Use 0 for LOW, 1 for HIGH
        config.digital_write(self.cs_pin, 0) # cs low
        config.spi_writebyte([CMD['CMD_WREG'] | reg, 0x00, data])
        config.digital_write(self.cs_pin, 1) # cs high

    def ADS1256_Read_data(self, reg):
        # Use 0 for LOW, 1 for HIGH
        config.digital_write(self.cs_pin, 0) # cs low
        config.spi_writebyte([CMD['CMD_RREG'] | reg, 0x00])
        # Small delay might be needed depending on SPI speed and device response time
        # config.delay_ms(1)
        data = config.spi_readbytes(1)
        #buf = config.spi_readbytes(3)
        #print(f"DEBUG: Raw SPI buffer read: {buf}")
        config.digital_write(self.cs_pin, 1) # cs high
        return data

    def ADS1256_WaitDRDY(self):
        # DRDY is active low. Wait until config.digital_read returns 0.
        # Add a timeout mechanism
        timeout = time.time() + 1.0 # 1 second timeout
        while time.time() < timeout:
            if config.digital_read(self.drdy_pin) == 0:
                return True # Success
        # Timeout occurred
        print ("ADS1256_WaitDRDY() Time Out ...\r\n")
        return False # Failure


    def ADS1256_ReadChipID(self):
        if not self.ADS1256_WaitDRDY():
             return -1 # Indicate timeout/error
        id_data = self.ADS1256_Read_data(REG_E['REG_STATUS'])
        if id_data: # Check if data was read successfully
             id_val = id_data[0] >> 4
             # print 'ID', id_val # Python 3 print
             return id_val
        else:
             return -1 # Indicate read error


    #The configuration parameters of ADC, gain and data rate
    def ADS1256_ConfigADC(self, gain, drate):
        if not self.ADS1256_WaitDRDY():
            print("Timeout waiting for DRDY before configuring ADC.")
            return False # Indicate failure

        buf = [0,0,0,0,0,0,0,0]
        # STATUS: Buffer disabled, Auto-cal disabled, Order MSB first
        buf[0] = (0<<3) | (1<<2) | (0<<1)
        # MUX: Defaults P=AIN0, N=AINCOM
        buf[1] = 0x08 # This might be adjusted later by SetChannel/SetDiffChannel
        # ADCON: Clock out OFF, Sensor Detect OFF, PGA gain = gain
        buf[2] = (0<<5) | (0<<3) | (gain<<0)
        # DRATE: Data rate = drate
        buf[3] = drate
        # GPIO: All default to inputs (can be changed if needed)
        # buf[4] = 0xE0 # Example if setting some GPIOs on the chip

        # Use 0 for LOW, 1 for HIGH
        config.digital_write(self.cs_pin, 0) # cs low
        # Write to registers starting from REG_STATUS (address 0) for 4 registers (0, 1, 2, 3)
        config.spi_writebyte([CMD['CMD_WREG'] | REG_E['REG_STATUS'], 0x03]) # 0x03 means write 4 registers (count-1)
        config.spi_writebyte(buf[0:4]) # Write the first 4 buffer bytes
        config.digital_write(self.cs_pin, 1) # cs high

        config.delay_ms(1) # Short delay after configuration
        return True # Indicate success


    def ADS1256_SetChannal(self, Channal):
        if Channal > 7:
            print(f"Error: Channel {Channal} is out of range (0-7).")
            return False
        # MUX : P = AIN[Channal], N = AINCOM (1000)
        self.ADS1256_WriteReg(REG_E['REG_MUX'], (Channal << 4) | (1 << 3))
        return True

    def ADS1256_SetDiffChannal(self, Channal):
        """ Sets differential channel pairs: 0: 0-1, 1: 2-3, 2: 4-5, 3: 6-7 """
        mux_lookup = {
            0: (0 << 4) | 1, # P = AIN0, N = AIN1
            1: (2 << 4) | 3, # P = AIN2, N = AIN3
            2: (4 << 4) | 5, # P = AIN4, N = AIN5
            3: (6 << 4) | 7  # P = AIN6, N = AIN7
        }
        if Channal not in mux_lookup:
            print(f"Error: Differential channel pair {Channal} is out of range (0-3).")
            return False

        self.ADS1256_WriteReg(REG_E['REG_MUX'], mux_lookup[Channal])
        return True

    def ADS1256_SetMode(self, Mode):
        global ScanMode
        ScanMode = Mode

    def ADS1256_init(self):
        if (config.module_init() != 0):
            print("Hardware Initialization failed.")
            return -1

        self.ADS1256_reset()
        config.delay_ms(100) 
        id_val = self.ADS1256_ReadChipID()

        if id_val == 3 :
            print("ID Read success (Expected 3)")
        elif id_val != -1:
            print(f"ID Read unexpected value: {id_val} (Expected 3)")
            # Decide if this is fatal, maybe continue?
            # return -1
        else: # id_val was -1 (error)
            print("ID Read failed (Timeout or SPI error)")
            return -1

        # Configure ADC with default gain and desired data rate
        if not self.ADS1256_ConfigADC(ADS1256_GAIN_E['ADS1256_GAIN_1'], ADS1256_DRATE_E['ADS1256_30000SPS']):
             print("Failed to configure ADC.")
             return -1

        print("ADS1256 Initialized successfully.")
        return 0

    def ADS1256_Read_ADC_Data(self):
        if not self.ADS1256_WaitDRDY():
            return None # Return None to indicate failure (timeout)

        # Use 0 for LOW, 1 for HIGH
        config.digital_write(self.cs_pin, 0) # cs low
        config.spi_writebyte([CMD['CMD_RDATA']])
        # Datasheet suggests minimum t6 delay (4*tCLKIN) before reading data
        # With 7.68MHz clock, tCLKIN=130ns. 4*tCLKIN ~ 0.52us.
        # A tiny delay might be beneficial at high SPI speeds, but often unnecessary
        # config.delay_ms(1) # Probably too long, use us delay if needed

        buf = config.spi_readbytes(3)
        config.digital_write(self.cs_pin, 1) # cs high

        # Combine bytes and handle sign extension for 24-bit data
        read = (buf[0] << 16) | (buf[1] << 8) | buf[2]

        # Sign extension if the MSB (bit 23) is 1
        if (read & 0x800000):
            # Extend the sign bit (1s) to the left for a 32-bit representation
            read |= 0xFF000000
            # Python handles large integers, but this makes it explicit
            # Or convert to a signed integer representation if needed elsewhere
            # Example: Convert to signed 32-bit int
            # if read > 0x7FFFFF: # If negative
            #    read -= 0x1000000

        return read

    def ADS1256_GetChannalValue(self, Channel):
        global ScanMode
        value = None # Default to None (indicating error or invalid channel)

        if ScanMode == 0: # Single-ended input
            if not (0 <= Channel <= 7):
                print(f"Error: Single-ended channel {Channel} out of range (0-7).")
                return None
            if not self.ADS1256_SetChannal(Channel):
                 return None # Error setting channel
        else: # Differential input
            if not (0 <= Channel <= 3):
                print(f"Error: Differential channel pair {Channel} out of range (0-3).")
                return None
            if not self.ADS1256_SetDiffChannal(Channel):
                 return None # Error setting channel

        # --- Common sequence for both modes ---
        self.ADS1256_WriteCmd(CMD['CMD_SYNC'])
        # SYNC command requires minimum 24 tCLKIN delay (~3.1us for 7.68MHz clock)
        # A small software delay might be added here if timing is critical, but
        # the subsequent WAKEUP and WaitDRDY usually provide enough delay.
        # config.delay_ms(1) # Likely excessive

        self.ADS1256_WriteCmd(CMD['CMD_WAKEUP'])
        # WAKEUP command requires minimum 24 tCLKIN delay (~3.1us)
        # config.delay_ms(1) # Likely excessive

        # Read the ADC data (includes WaitDRDY)
        value = self.ADS1256_Read_ADC_Data()

        # Return the raw integer value or None if Read_ADC_Data failed
        return value

    def ADS1256_GetAll(self):
        """ Reads all 8 single-ended channels. Assumes ScanMode is 0. """
        global ScanMode
        if ScanMode != 0:
            print("Warning: ADS1256_GetAll() called but ScanMode is not 0 (Single-ended).")
            # Or force ScanMode = 0 here? For now, just return empty.
            return []

        ADC_Value = [0] * 8 # Initialize list
        for i in range(8):
            adc_reading = self.ADS1256_GetChannalValue(i)
            if adc_reading is not None:
                 ADC_Value[i] = adc_reading
            else:
                 # Handle error case, maybe set to a specific value like None or NaN?
                 ADC_Value[i] = None # Indicate read failure for this channel
                 print(f"Failed to read channel {i}")

        return ADC_Value
### END OF FILE ###