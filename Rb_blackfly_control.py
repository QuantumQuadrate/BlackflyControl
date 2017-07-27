# This standalone Python code writen by Garrett Hickman is based on an example
# file provided by FLIR. The following copyright statement applies to their
# software:
#
# -*- coding: utf-8 -*-
#=============================================================================
# Copyright 2017 FLIR Integrated Imaging Solutions, Inc. All Rights Reserved.
#
# This software is the confidential and proprietary information of FLIR
# Integrated Imaging Solutions, Inc. ("Confidential Information"). You
# shall not disclose such Confidential Information and shall use it only in
# accordance with the terms of the license agreement you entered into
# with FLIR Integrated Imaging Solutions, Inc. (FLIR).
#
# FLIR MAKES NO REPRESENTATIONS OR WARRANTIES ABOUT THE SUITABILITY OF THE
# SOFTWARE, EITHER EXPRESSED OR IMPLIED, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR
# PURPOSE, OR NON-INFRINGEMENT. FLIR SHALL NOT BE LIABLE FOR ANY DAMAGES
# SUFFERED BY LICENSEE AS A RESULT OF USING, MODIFYING OR DISTRIBUTING
# THIS SOFTWARE OR ITS DERIVATIVES..
#=============================================================================

import PyCapture2   #Python wrapper for BlackFly camera control software
import time   #used to pause program execution
import h5py   #package used to create and manage .hdf5 files

from sys import exit
# from time import sleep
import thread, time
import numpy as np
from scipy import misc


#
# Main
#

cameraSerial = 16483677
#cameraSerial = 16483678

triggDelay = 0      # trigger delay in ms
exposureTime = 1    # exposure time in ms

timeToSleep = 1000   # time that the computer sleeps between image acquisitions, in ms
timeToWait = 1000    # time the camera waits for a new trigger before throwing an error, in ms

# Ensures sufficient cameras are found
bus = PyCapture2.BusManager()
numCams = bus.getNumOfCameras()
# serial = getCameraSerialNumberFromIndex(1)   #this line not necessary at the moment
print "Number of cameras detected: ", numCams
if not numCams:
    print "Insufficient number of cameras. Exiting..."
    exit()

#c = PyCapture2.Camera()
c = PyCapture2.GigECamera()

# Look up the camera's serial number and pass it to this function:
c.connect(bus.getCameraFromSerialNumber(cameraSerial))

# Powers on the Camera
cameraPower = 0x610
powerVal = 0x80000000
c.writeRegister(cameraPower, powerVal)

# Waits for camera to power up
retries = 10
timeToSleep = 0.1	#seconds
for i in range(retries):
    time.sleep(timeToSleep)
    try:
        regVal = c.readRegister(cameraPower)
    except PyCapture2.Fc2error:	# Camera might not respond to register reads during powerup.
        pass
    awake = True
    if regVal == powerVal:
        break
    awake = False
if not awake:
    print "Could not wake Camera. Exiting..."
    exit()

# Enables resending of lost packets, to avoid "Image Consistency Error"
cameraConfig = c.getGigEConfig()
c.setGigEConfig(enablePacketResend = True, registerTimeoutRetries = 3)

# Configures trigger mode for hardware triggering
trigger_mode = c.getTriggerMode()
trigger_mode.onOff = True
trigger_mode.mode = 0
trigger_mode.polarity = 1
trigger_mode.source = 0		# Using an external hardware trigger
c.setTriggerMode(trigger_mode)

# Sets the trigger delay
trigger_delay = c.getTriggerDelay()
trigger_delay.absControl = True
trigger_delay.onOff = True
trigger_delay.onePush = True
trigger_delay.autoManualMode = True
trigger_delay.valueA = 0   #this field is used when the "absControl" field is set to "False"
   #defines the trigger delay, in units of 40.69 ns (referenced to a 24.576 MHz internal clock)
   #range of this field is 0-4095. It's preferred to use the absValue variable.
#trigger_delay.valueB = 0     #I don't know what this value does
trigger_delay.absValue = triggDelay*1e-3   #this field is used when the "absControl" field is set to "True"
   #units are seconds. It is preferred to use this variable rather than valueA
c.setTriggerDelay(trigger_delay)


# Sets the camera exposure time using register writes
shutter_address = 0x81C
# "shutter" variable format:
# bit [0]: indicates presence of this feature. 0 = not available, 1 = available
# bit [1]: absolute value control. 0 = control with the "Value" field
                                #  1 = control with the Absolute value register
# bits [2-4]: reserved
# bit [5]: one push auto mode. read: 0 = not in operation, 1 = in operation
#                              write: 1 = begin to work (self-cleared after operation)
# bit [6]: turns this feature on or off. 0 = off, 1 = on.
# bit [7]: auto/manual mode. 0 = manual, 1 - automatic
# bits [8-19]: high value. (not sure what this does)
# bits [20-31]: shutter exposure time, in (units of ~19 microseconds).
bits0_7 = '10000010'
bits8_19 = '000000000000'
shutter_value = int(round((exposureTime*1000+22.08)/18.81))   #converts the shutter exposure time from ms to base clock units
    #in units of approximately 19 microseconds, up to a value of 1000.
    #after a value of roughly 1,000 the behavior is nonlinear
    #max. value is 4095
    #for values between 5 and 1000, shutter time is very well approximated by: t = (value*18.81 - 22.08) us
bits20_31 = format(shutter_value,'012b')
shutter_bin = bits0_7 + bits8_19 + bits20_31
shutter = int(shutter_bin, 2)
c.writeRegister(shutter_address, shutter)


# Instructs the camera to retrieve only the newest image from the buffer each time the RetrieveBuffer() function is called.
# Older images will be dropped.
PyCapture2.GRAB_MODE = 0

# # Returns the serial number of the Blackfly camera
#sNumber = PyCapture2.CameraInfo.serialNumber

# # Configures the camera strobe using register writes
# # Calculates the base register address
# offset = c.readRegister(0x48C)
# offset = 4*offset    #result is 0xf01300. Remove the 'f' before passing to the camera
# # Configures camera strobe
# relative_address = 0x204
# strobe_address = 0x01504

# # "strobe_mode" variable format:
# # bit [0] (MSB): presence inquiry. Indicates the presence of the feature. 0 = not available, 1 = available.
# # bits [1-5]: reserved.
# # bit [6]: on/off. Turns the function on or off. 0 = OFF, 1 = ON.
# # bit [7]: signal polarity. 0 = active low output, 1 = active high output.
# # bits [8-19]: delay. Value indicates the delay after start of exposure until the strobe signal asserts.
# # bits [20-31]: duration. Value indicates the duration of the strobe signal.
# #               With a value of '0' the signal de-asserts at the end of exposure.
# bits0_7 ='10000011'
# delay_value = 0 #range of this parameter is 0 - 4095
# bits8_19 = format(delay_value,'012b')  #formats the delay value into binary with leading 0's
# duration_value = 0 #in microseconds, range of this parameter is 0 - 4095
#     #if the value given is 0, the strobe pulse lasts as long as the exposure time
# bits20_31 = format(duration_value,'012b')  #formats the duration value into binary with leading 0's
# strobe_mode_bin = bits0_7 + bits8_19 + bits20_31
# strobe_mode = int(strobe_mode_bin,2)   #converts the binary value to base-10 integer
# c.writeRegister(strobe_address, strobe_mode)

# # Enables the 3.3V, 120mA output on GPIO pin 3 (red jacketed lead)
# output_voltage = 0x19D0
# voltage_mode = 0x00000001
# c.writeRegister(output_voltage, voltage_mode)

# # Configures the camera strobe to activate at start of exposure, rather than activating at receipt of the trigger pulse
# # See pp. 131-132 of the FLIR Blackfly technical reference v14.0 manual for more info
# strobe_start_address = 0x1104
# # "strobe_start" variable format:
# # bit [0] (MSB): current mode. 0 = strobe start is relative to start of integration
# #                              1 = strobe start is relative to external trigger
# # bits [1-12]: reserved
# # bit [13]: shutter mode (read only). 0 = rolling shutter mode, 1 = global reset mode
# # bits [14-15]: pixels exposed. 00 = line 1 exposed, 01 = any pixel exposed, 10 = all pixels exposed, 11 = invalid
# # bits [16-31]: reserved
# strobe_start_bin = '00000000000000010000000000000000'
# strobe_start = int(strobe_start_bin, 2)   #converts binary to decimal integer
# c.writeRegister(strobe_start_address, strobe_start)


# Sets how long the camera will wait for its trigger, in ms
c.setConfiguration(grabTimeout = timeToWait)

# Starts acquisition
c.startCapture()

imageNum = 0
while True:     # loops indefinitely 
    
    # Attempts to retrieve an image from the camera buffer and save it to disk
    try:
        image = c.retrieveBuffer()
        image.save("test_images/MOT_image_{}.png".format(imageNum), 6)
        imageNum += 1
        #the '6' indicates .png file format, see p. 99 of the PyCapture 2 manual for more info

        ## Saves the data to an hdf5 file
        #raw_image_data = PyCapture2.Image.getData(image)   #retrieves raw image data from the camera buffer
        #nrows = PyCapture2.Image.getRows(image)   #finds the number of rows in the image data
        #ncols = PyCapture2.Image.getDataSize(image)/nrows   #finds the number of columns in the image data
        #image_file = h5py.File("image_file.hdf5", "w")
        #image_data = image_file.create_dataset("image_dataset", (nrows, ncols), dtype='i')
        #image_data[:] = np.reshape(raw_image_data, (nrows, ncols), 'C')   #reshapes the data into a 2d array
        #image_file.close()
        
        print "Got an image."
        
    except PyCapture2.Fc2error as fc2Err:
        print "Error retrieving buffer : ", fc2Err
        # Pauses to allow the camera to acquire an image
        time.sleep(timeToSleep/1000)


## Disables the 3.3V, 120mA output on GPIO pin 3 (red jacketed lead)
#voltage_mode = 0x0000000
#c.writeRegister(output_voltage, voltage_mode)

# Turns off hardware triggering
c.setTriggerMode(onOff = False)
print "Finished grabbing images!"

#Disconnects the camera
c.stopCapture()
c.disconnect()

print "Done!"