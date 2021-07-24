# Enviro Pi CSV

Python script to read sensor data from the Enviro+ hat and save it in a csv along with GPS data.

You will need to ensure that the python requirements are installed, see the enviro+ tutorials for that info.

This script needs to know which port your GPS module is running on (currently hardcoded below).

Script also expects a particulate sensor to be attached (will probably fail it not present)

At startup the script should show what it is doing on the Enviro+ lcd display.

You can also connect a button to the Enviro+ btween breakout pin #4 (pass through to GPIO4) and GND.
Pressing the button for more than 3 seconds (but less than 10) will reset the csv collection, creating a new file
in the process. 
Pressing the button for more than 10 seconds will safely shutdown the Raspberry Pi.

This script should live in the pi users home directory /home/pi/enviro_pi_csv.py

To make the script run at start up we need to create a service for systemd. We can do that with the following:
From the pi, run:
 
    sudo nano /lib/systemd/system/enviropi.service

Then in the resulting file, paste in the following text: 

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

    sudo systemctl daemon-reload
    sudo systemctl enable enviropi.service

Now when the pi stats up or reboots, it should automatically run the enviro_pi_csv.py data collection script.
We can manually start, stop and restart the service with the following commands:

    sudo systemctl start enviropi.service
    sudo systemctl stop enviropi.service
    sudo systemctl restart enviropi.service
