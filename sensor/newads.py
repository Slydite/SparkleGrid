#!/usr/bin/python
# -*- coding:utf-8 -*-

import time
import ADS1256
import RPi.GPIO as GPIO
import psycopg2
from psycopg2 import OperationalError
import numpy as np
import datetime

# Function to create a database connection
def create_connection(host_name, user_name, password, db_name):
    connection = None
    try:
        connection = psycopg2.connect(
            dbname=db_name,
            user=user_name,
            password=password,
            host=host_name,
            port="5432"
        )
        print("Connection to PostgreSQL DB successful")
    except OperationalError as e:
        print(f"The error '{e}' occurred")
    return connection

# Function to get the max id from the table
def get_max_id(connection):
    cursor = connection.cursor()
    cursor.execute("SELECT MAX(id) FROM microgrid_back_measurementssix;")
    max_id = cursor.fetchone()[0]
    cursor.close()
    return max_id if max_id else 0

# Function to calculate RMS value
def calculate_rms(data_array):
    return np.sqrt(np.mean(np.square(data_array)))

# Function to insert voltage data into the database
def insert_voltage_data(connection, sensor_id, voltage_values, timestamps):
    cursor = connection.cursor()
    query = """
    INSERT INTO microgrid_back_measurementssix(sensor_id, sensdata, time, rmsvalue, pf, thd, sname, stype)
    VALUES (%s, %s::numeric[], %s, COALESCE(%s, 0), COALESCE(%s, 0), COALESCE(%s, 0), %s, %s);
    """
    default_stype = "DefaultType"  # Provide your default value for stype here
    for voltage, timestamp in zip(voltage_values, timestamps):
        # Provide default values (0) for rmsvalue, pf, and thd in case of NULL
        cursor.execute(query, (sensor_id, [voltage], timestamp, None, None, None, "DefaultName", default_stype))
    connection.commit()
    cursor.close()



# Function to read data from the ADS1256
def read_ads1256_data(ADC, num_samples):
    voltage_values = []
    timestamps = []
    for _ in range(num_samples):
        ADC_Value = ADC.ADS1256_GetAll()
        sensor_value = ADC_Value[7] * 5.0 / 0x7fffff  # Assuming reading from channel 7
        voltage_values.append(sensor_value)
        timestamps.append(datetime.datetime.now().isoformat())
    return voltage_values, timestamps

# Replace with your actual database credentials
connection = create_connection("localhost", "gridsense_user", "microgrid", "gridsense_db")

# Initialize the ADS1256 ADC
ADC = ADS1256.ADS1256()
ADC.ADS1256_init()

try:
    while True:
        # Read 1000 samples from the ADS1256 in 1 second
        voltage_values, timestamps = read_ads1256_data(ADC, num_samples=1000)
        
        # Insert the batch of voltage values into the database
        insert_voltage_data(connection, sensor_id=1, voltage_values=voltage_values, timestamps=timestamps)
        
        print("Inserted a batch of 1000 values into the database at t=", timestamps[0])
        
        # Wait for the next second
        time.sleep(1.0 - (time.time() % 1.0))  # Adjust for drift
except KeyboardInterrupt:
    print("Exiting...")
    if connection:
        connection.close()
        print("PostgreSQL connection is closed")
