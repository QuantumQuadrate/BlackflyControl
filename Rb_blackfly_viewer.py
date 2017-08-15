# This standalone Python code writen by Garrett Hickman is based on an example
# file provided by FLIR. The following copyright statement applies to their
# software:
# Modified:2017-07-27 by Minho Kwon
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
# For fitting
import Rb_blackfly_image_gauss as fits

# For plotting
from pyqtgraph.Qt import QtCore, QtGui
import pyqtgraph as pg
import urllib2, cStringIO
from PIL import Image
import collections

# For Blackfly control
import PyCapture2   #Python wrapper for BlackFly camera control software
import time   #used to pause program execution
import h5py   #package used to create and manage .hdf5 files

from sys import exit
# from time import sleep
import thread, time
import numpy as np
import scipy
from scipy import misc, ndimage

# pyqtgraph part
app = QtGui.QApplication([])
## Create window with GraphicsView widget
win = pg.GraphicsLayoutWidget()
win.show()  ## show widget alone in its own window
win.setWindowTitle('Pointgrey Monitor by Minho')
view = win.addViewBox()
view.setAspectLocked(True) # lock the aspect ratio so pixels are always square
## Create image item and textitem
img = pg.ImageItem()
scatter=pg.ScatterPlotItem()
#scatter.setData(size=10,symbol='o',brush=(255,0,0))
text= pg.TextItem()
text2= pg.TextItem()
view.addItem(img)
view.addItem(scatter)
view.addItem(text)
view.addItem(text2)
text.setAnchor((0,2))
text2.setAnchor((-1,7))
#
# Main
#

cameraSerial = 15102504# Rubidium's Pointgrey

triggDelay = 0      # trigger delay in ms
exposureTime = 2    # exposure time in ms

timeToSleep = 1000   # time that the computer sleeps between image acquisitions, in ms
timeToWait = 1000   # time the camera waits for a new trigger before throwing an error, in ms

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
timeToSleep = 0.1    #seconds
for i in range(retries):
    time.sleep(timeToSleep)
    try:
        regVal = c.readRegister(cameraPower)
    except PyCapture2.Fc2error:    # Camera might not respond to register reads during powerup.
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
print 'configuring trigger mode'
trigger_mode = c.getTriggerMode()
trigger_mode.onOff = True
trigger_mode.mode = 1
trigger_mode.polarity = 1
trigger_mode.source = 0        # Using an external hardware trigger
c.setTriggerMode(trigger_mode)

# Sets the trigger delay
print 'configuring trigger delay'
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

settings= {"offsetX": 300, "offsetY": 0, "width": 900, "height":500, "pixelFormat": PyCapture2.PIXEL_FORMAT.MONO8}
c.setGigEImageSettings(**settings)
# Instructs the camera to retrieve only the newest image from the buffer each time the RetrieveBuffer() function is called.
# Older images will be dropped.
PyCapture2.GRAB_MODE = 0

# Sets how long the camera will wait for its trigger, in ms
c.setConfiguration(grabTimeout = timeToWait)

# Starts acquisition
c.startCapture()

imageNum = 0
interval=5 # ms
percentile=99.5
def updateData():
    try:
        starttime=time.time()
        image = c.retrieveBuffer()
        latency=int(1000 * (time.time() - starttime))
    except PyCapture2.Fc2error as fc2Err:
        print "Error retrieving buffer : ", fc2Err
        #text.setHtml("<font size=4>From {} <br /> "
                         #"Error retrieving buffer: {}".format(str(cameraSerial),str(fc2Err)))
        #image.save("test_images/MOT_image_{}.png".format(imageNum), 6) #if the directory does not exist, it will output an general failure error
        #imageNum += 1
        #the '6' indicates .png file format, see p. 99 of the PyCapture 2 manual for more info
        ## Saves the data to an hdf5 file
        #raw_image_data = PyCapture2.Image.getData(image)   #retrieves raw image data from the camera buffer
    try:
        nrows = PyCapture2.Image.getRows(image)   #finds the number of rows in the image data
        ncols = PyCapture2.Image.getDataSize(image)/nrows   #finds the number of columns in the image data
        #ncols = PyCapture2.Image.getCols(image)  #finds the number of columns in the image data
        data=np.array(image.getData())
        reshapeddata=np.reshape(data,(nrows,ncols))
        baseline=np.median(data)
        orienteddata=np.flip(reshapeddata.transpose(1,0),1)-baseline #subtract median baseline
        img.setImage(orienteddata)
        if int(np.max(orienteddata))>80:
            #[COM_X,COM_Y]=fits.fort_gauss(orienteddata)['x'],fits.fort_gauss(orienteddata)['y']
            #[COM_X,COM_Y]=scipy.ndimage.measurements.center_of_mass(orienteddata)
            [COM_X,COM_Y]=np.unravel_index(np.argmax(orienteddata),orienteddata.shape) # locate maximum arg
            scatter.setData(pos=[[COM_X,COM_Y]],size=10,symbol='o',brush=(255,0,0))
            #print np.max(orienteddata)
        else:
            #[COM_X,COM_Y]=scipy.ndimage.measurements.center_of_mass(orienteddata)
            [COM_X,COM_Y]=np.unravel_index(np.argmax(orienteddata),orienteddata.shape)
            scatter.setData(pos=[[COM_X,COM_Y]],size=10,symbol='o',brush=(0,255,0))
        text.setHtml("<font size=4>From {} <br /> "
                         "Latency: {} ms, refresh time : {} ms <br/>"
                         "Center X:{:.2f}, Y:{:.2f} <br/>"
                         "{}th percentile: {}".format(str(cameraSerial), int(latency), int(interval), float(COM_X),float(COM_Y),float(percentile),int(np.percentile(orienteddata,percentile))))
        QtCore.QTimer.singleShot(interval, updateData)
    except:
        text.setHtml("<font size=4> No image to draw or could not retrive image from the camera")
        QtCore.QTimer.singleShot(interval, updateData)
## Disables the 3.3V, 120mA output on GPIO pin 3 (red jacketed lead)
#voltage_mode = 0x0000000
#c.writeRegister(output_voltage, voltage_mode)

# Turns off hardware triggering
#c.setTriggerMode(onOff = False)
#print "Finished grabbing images!"

#Disconnects the camera
#c.stopCapture()
#c.disconnect()

#print "Done!"
updateData()
## Start Qt event loop unless running in interactive mode.
if __name__ == '__main__':
    import sys
    if (sys.flags.interactive != 1) or not hasattr(QtCore, 'PYQT_VERSION'):
        QtGui.QApplication.instance().exec_()
