import os
import time
import datetime
import serial
import logging
from dataclasses import dataclass

from enviroplus import gas
from enviroplus import noise
from pms5003 import PMS5003, ReadTimeoutError
from smbus2 import SMBus
from bme280 import BME280  # Note: Don't pip instal the 'bme280' package, use the pimoroni one 'pimoroni-bme280'
import ltr559
import ST7735
from PIL import Image, ImageDraw, ImageFont
from fonts.ttf import RobotoMedium
from gpiozero import Button

"""Python script to read sensor data from the Enviro+ hat and save it in a csv along with GPS data

You will need to ensure that the python requirements are installed, see the enviro+ tutorials for that info.

This script needs to know which port your GPS module is running on (currently hardcoded below).
Script also expects a particulate sensor to be attached (will probably fail it not present)

At startup the script should show what it is doing on the Enviro+ lcd display.

You can also connect a button to the Enviro+ breakout pin #4 (pass through to GPIO4).
Pressing the button for more than 3 seconds (but less than 10) will reset the csv collection, creating a new file
in the process. Pressing the button for more than 10 seconds will safely shutdown the Raspberry Pi.

This script should live in the pi users home directory /home/pi/enviro_pi_csv.py

To make the script run at start up we need to create a service for systemd. We can do that with the following:
From the pi, run:
 
pi@enviropi:~ $ sudo nano /lib/systemd/system/enviropi.service

Then in the resulting file, paste in the following text: 
(Note the indents are just to make it clear what needs to be copied and should probably not be included,
might work with but not tested)

    [Unit]
    Description=Enviro Pi CSV data collection script.
    After=multi-user.target
    
    [Service]
    WorkingDirectory=/home/pi
    User=pi
    ExecStart=/usr/bin/python3 /home/pi/enviro_pi_csv.py
    Restart=always
    
    [Install]
    WantedBy=multi-user.target


Then press ctrl+x followed by y and enter. 
Next we need to enable the newly created service with the following commands:

pi@enviropi:~ $ sudo systemctl daemon-reload
pi@enviropi:~ $ sudo systemctl enable enviropi.service

Now when the pi stats up or reboots, it should automatically run the enviro_pi_csv.py data collection script.

We can manually start, stop and restart the service with the following commands:
pi@enviropi:~ $ sudo systemctl start enviropi.service
pi@enviropi:~ $ sudo systemctl stop enviropi.service
pi@enviropi:~ $ sudo systemctl restart enviropi.service
"""

# Create a button we can use to reset the collection or shutdown the pi etc
button_4 = Button(4)

# Create a serial port
physicalPort = '/dev/ttyACM0'  # Which serial port to use
serialPort = serial.Serial(physicalPort)  # open serial port and assign that object to a variable

# Create an instance of the LCD class
lcd_display = ST7735.ST7735(
    port=0,
    cs=1,
    dc=9,
    backlight=12,
    rotation=270,
    spi_speed_hz=10000000
)
lcd_display.begin()  # Init the display
# Create a PIL canvas, this is what we will 'draw' on and we will display the result on the lcd
img = Image.new('RGB', (lcd_display.width, lcd_display.height), color=(0,0,0))
draw = ImageDraw.Draw(img)
# Font settings
my_font = ImageFont.truetype(RobotoMedium, 10)
draw.text((0,0), "Script initialized...", font=my_font)
lcd_display.display(img)  # Display the image we have created on the LCD
# import time
# time.sleep(5)

def create_new_file():
    """Create a csv file using the current timestamp as part of the filename so we dont overwrite existing data"""
    ts, _ = str(time.time()).split(".")  # Get the bit of the timestamp we want to use in the filename
    csv_header = "GPS sentence prefix, Latitude, Heading, Longitude, Heading, Time, Data Valid, PMS 1.0, PMS 2.5, PMS 10.0, Gas ADC, Gas Oxidizing, Gas Reducing, Gas NH3, Noise Low, Noise Mid, Noise High, Noise Total, Temperature, Humidity, Pressure, Altitude, Lux, Proximity"
    print(f"Creating csv file gps_{ts}.csv")  # Output the filename to the console
    print(f"{csv_header}")
    f = open(f"gps_{ts}.csv", 'w')  # Create the file
    f.write(csv_header)
    f.close()  # Close the file
    draw.rectangle((0, 12, 160, 80), (0, 0, 0))  # Clear the portion of the display we will be rewriting
    draw.text((0, 12), f"Created {f.name}", font=my_font)
    lcd_display.display(img)  # Display the image we have created on the LCD
    return f"gps_{ts}.csv"  # Return the filename

def write_to_csv(data, file_name):
    """Write 'data' to the existing file 'file_name'"""
    f = open(file_name, "a")  # Open the file
    f.write(data.rstrip())  # Write the data
    f.write("\n")  # Write a newline
    draw.rectangle((0, 24, 160, 80), (0, 0, 0))  # Clear the portion of the display we will be repeatedly writing to
    draw.text((0, 24), f"Writing data to csv:", font=my_font)
    draw.text((0, 36), f"{data}", font=my_font)
    lcd_display.display(img)  # Display the image we have created on the LCD
    f.close()  # Close the file


@dataclass
class Weather_Data:
    """A data class to store the weather data for easier access - might be over kill but dataclasses are my new favourite thing in Python"""
    temperature: str
    humidity: str
    pressure: str
    altitude: str

"""The main part of the program"""
file_name = create_new_file()  # Create a new file
pms5003 = PMS5003()  # Create an instance of the PMS5003 class to read the PMS data from
env_noise = noise.Noise()  # Create an instance of the envirohat noise class to read the noise data from
i2c_bus = SMBus(1)  # Create an instance of the I2C bus for the BME280 temp, humidity and pressure sensor
bme = BME280(i2c_dev=i2c_bus)  # Create an instance of the BME280 class to read the weather data from
ltr559 = ltr559.LTR559()

time.sleep(1.0)
button_timer = 0
button_timer_start = False
time_since_button_pressed = None

while True:  # Do forever

    # When the button on GPIO4 is pressed we can start a timer
    # When the timer reaches say 3 seconds, restart the csv collection
    # When the timer reaches say 10 seconds, we can restart the enviropi.service
    # When the timer reaches say 20 seconds, we can shut the pi down safely
    if button_4.is_active:
        if button_timer_start:  # Button timer has already been started
            # Record how long its been since the button was pressed and held down
            # Note: We don't act on this timer until the button state is not pressed
            time_since_button_pressed = datetime.datetime.now() - button_timer
        else:
            button_timer_start = True
            button_timer = datetime.datetime.now()
    else:
        # Button is no longer pressed... act on the duration of the recorded button press
        if button_timer_start:
            if time_since_button_pressed.total_seconds() > 3.0 and time_since_button_pressed.total_seconds() < 10.0:
                print("Reset the csv collection")
                draw.rectangle((0, 12, 160, 80), (0, 0, 0))  # Clear the portion of the display we will be rewriting
                draw.text((0, 12), f"Resetting data collection", font=my_font)
                lcd_display.display(img)  # Display the image we have created on the LCD
                time.sleep(3)
                file_name = create_new_file()
            if time_since_button_pressed.total_seconds() > 10.0 and time_since_button_pressed.total_seconds() < 20.0:
                print("Reset the service")
                draw.rectangle((0, 12, 160, 80), (0, 0, 0))  # Clear the portion of the display we will be rewriting
                draw.text((0, 12), f"Restarting enviropi service", font=my_font)
                lcd_display.display(img)  # Display the image we have created on the LCD
                time.sleep(3)
                os.system("sudo systemctl restart enviropi.service")
            elif time_since_button_pressed.total_seconds() > 20.0:
                print("Shut down the pi")
                draw.rectangle((0, 0, 160, 80), (0, 0, 0))  # Clear the portion of the display we will be rewriting
                time.sleep(1)
                draw.text((0, 0), f"Shutting down!", font=my_font)
                lcd_display.display(img)  # Display the image we have created on the LCD
                os.system("sudo shutdown -h now")
            else:
                print("Button not pressed long enough to do anything")
        button_timer = None  # Reset the button timer when not pressed
        button_timer_start = False

    gps_data = None
    pms_data = None

    if serialPort.in_waiting:  # If there is serial data
        gps_data = serialPort.readline()  # Get the data from the serial port
        if b'$GPGLL' in gps_data:  # If we have the location data, write it to the file
            logging.info(gps_data)  # Output data to console
            # Only bother reading the other data when we have some GPS location data
            try:
                pms_data = pms5003.read()

            except ReadTimeoutError:
                pms5003 = PMS5003()

            pms_csv = f"{pms_data.pm_ug_per_m3(1.0)},{pms_data.pm_ug_per_m3(2.5)},{pms_data.pm_ug_per_m3(10.0)}"

            gas_data = gas.read_all()  # Gas is not a class so we can just call the function
            gas_csv = f"{gas_data.adc},{gas_data.oxidising},{gas_data.reducing},{gas_data.nh3}"  # Format the data for csv

            noise_data = env_noise.get_noise_profile()  # Get the noise profile
            noise_csv = f"{noise_data[0]},{noise_data[1]},{noise_data[2]},{noise_data[3]}"  # Format the data for csv

            # Create an instance of the Weather_Data() class and fill it with the bme280 data
            weather_data = Weather_Data(bme.get_temperature(), bme.get_humidity(), bme.get_pressure(), bme.get_altitude())
            weather_csv = f"{weather_data.temperature},{weather_data.humidity},{weather_data.pressure},{weather_data.altitude}"

            # Get the light data
            light_csv = f"{ltr559.get_lux()},{ltr559.get_proximity()}"
            # CSV Header:
            # PREFIX, Latitude, Heading, Longitude, Heading, Time, Data Valid, PMS 1.0, PMS 2.5, PMS 10.0,
            # Gas ADC, Gas Oxidizing, Gas Reducing, Gas NH3,
            # Noise Low, Noise Mid, Noise High, Noise Total,
            # Temperature, Humidity, Pressure, Altitude,
            # Lux, Proximity
            # Only write data to the csv file if we have data for everything
            if gps_data and pms_csv and gas_csv and noise_csv and weather_csv and light_csv:
                data = f"{gps_data.decode().strip()},{pms_csv},{gas_csv},{noise_csv},{noise_csv},{weather_csv},{light_csv}"  # Combine all the parts into a long csv line
                print(data)  # Print the data on the console so we can see what is happening
                write_to_csv(data, file_name)  # Write csv data to file


