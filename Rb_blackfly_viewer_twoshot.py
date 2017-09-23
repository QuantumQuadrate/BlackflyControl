# This standalone Python code writen by Garrett Hickman is based on an example
# file provided by FLIR. The following copyright statement applies to their
# software:
# Modified:2017-08-16 by Minho Kwon
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
import scipy.ndimage.measurements as measurements
from scipy.ndimage.morphology import binary_opening, binary_erosion
from scipy.signal import medfilt

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
scatter2=pg.ScatterPlotItem()
#scatter.setData(size=10,symbol='o',brush=(255,0,0))
text= pg.TextItem()
text2= pg.TextItem()
view.addItem(img)
view.addItem(scatter)
view.addItem(scatter2)
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
#print 'configuring trigger mode'
trigger_mode = c.getTriggerMode()
trigger_mode.onOff = True # True is using external trigger
trigger_mode.mode = 0 # 0 is standard trigger
trigger_mode.polarity = 1 # 1 is triggering on rising edges
trigger_mode.source = 0        # Using an external hardware trigger
c.setTriggerMode(trigger_mode)

# Sets the trigger delay
#print 'configuring trigger delay'
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

settings= {"offsetX": 0, "offsetY": 0, "width": 960, "height":600, "pixelFormat": PyCapture2.PIXEL_FORMAT.MONO8}
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

def calculate_statistics(data):
    percentile = 99.5
    starttime=time.time()
    threshold = np.percentile(data, percentile)  # Set threshold
    thresholdmask = data > threshold
    # Apply dilation-erosion to exclude isolated bright pixels
    openingmask = binary_opening(thresholdmask)
    temp=np.ma.array(data, mask=np.invert(openingmask))
    # Fill 0 to masked pixels so they do not contribute to the following center of mass calculation
    temp2=temp.filled(0)
    # Full image analysis
    [COM_X, COM_Y, error]=locator(temp2,threshold)

    which_laser(temp2,COM_X,COM_Y,threshold)
    return COM_X, COM_Y,temp2

def which_laser(preprocessed_data,COM_X,COM_Y,threshold):
    # Subimage analysis : Use the center of mass obtained from full analysis to distinguish red and FORT sites.
    [fullwidth, fullheight]=np.shape(preprocessed_data)
    [fort_spacer,subimage_halfheight,subimage_halfwidth]=[42,15,15]
    verts=[[0,1],[0,-1]]
    horiz=[[-2,0],[-1,0],[1,0],[2,0]]
    temp_ones=np.ones((fullwidth,fullheight))
    vert_detect=0
    for i in verts:
        X1=i[0]*fort_spacer+np.int(COM_X)-subimage_halfheight
        X2=i[0]*fort_spacer+np.int(COM_X)+subimage_halfheight
        Y1=i[1]*fort_spacer+np.int(COM_Y)-subimage_halfwidth
        Y2=i[1]*fort_spacer+np.int(COM_Y)+subimage_halfwidth
        temp_ones[X1:X2,Y1:Y2]=0
        temp3=np.ma.array(preprocessed_data,mask=temp_ones)
        temp4=temp3.filled(0)
        [sub_X,sub_Y,sub_error]=locator(temp4,threshold)
        if sub_error==0: # If vertical component exists,
            vert_detect=1 # raise vert flag, claim this to be ground laser
    if vert_detect==1:
        print "this is ground!"
    elif vert_detect==0:
        print "this is likely FORT"

def locator(data,threshold):
    error=1
    if threshold>np.max(data):
        #print "Warning: Low SNR"
        [COM_X, COM_Y]=[0,0]
    else:
        [COM_X, COM_Y] = measurements.center_of_mass(data)  # Center of mass
        error=0

    return [COM_X, COM_Y, error]

def updateData():
    try:
        starttime=time.time()
        image = c.retrieveBuffer()# Capture first image
        data=np.array(image.getData())
        latency=int(1000 * (time.time() - starttime))
        image2 = c.retrieveBuffer() # Capture second image
        data2=np.array(image2.getData())
        nrows = PyCapture2.Image.getRows(image)   #finds the number of rows in the image data
        ncols = PyCapture2.Image.getDataSize(image)/nrows   #finds the number of columns in the image data
        reshapeddata1=np.reshape(data,(nrows,ncols))
        reshapeddata2=np.reshape(data2,(nrows,ncols))
        orienteddata1=np.flip(reshapeddata1.transpose(1,0),1)
        orienteddata2=np.flip(reshapeddata2.transpose(1,0),1)
        orienteddata=orienteddata1-orienteddata2
        [FORT_COM_X,FORT_COM_Y,temp1]=calculate_statistics(orienteddata1)#np.unravel_index(np.argmax(orienteddata),orienteddata.shape) # locate maximum arg
        [Ground_COM_X,Ground_COM_Y,temp2]=calculate_statistics(orienteddata2)#np.unravel_index(np.argmin(orienteddata),orienteddata.shape) # locate maximum arg
        #displayeddata=np.absolute(orienteddata)
        displayeddata=np.zeros((ncols,nrows,3))
        displayeddata[:,:,0]=temp1#orienteddata1
        displayeddata[:,:,1]=temp2#orienteddata2
        displayeddata[:,:,2]=0#np.absolute(orienteddata1-orienteddata2)
        img.setImage(displayeddata)
        #img.setLevels([0,np.max(displayeddata)])
        scatter.setData(pos=[[FORT_COM_X,FORT_COM_Y]],size=8,symbol='o',brush=(255,0,120))
        scatter2.setData(pos=[[Ground_COM_X,Ground_COM_Y]],size=8,symbol='o',brush=(0,255,120))
        text.setHtml("<font size=4>From {} <br /> "
                         "Latency: {} ms, refresh time : {} ms <br/>"
                         "Delta X:{:.2f}, Delta Y:{:.2f} <br/>".format(str(cameraSerial), int(latency), int(interval), float(FORT_COM_X-Ground_COM_X),float(FORT_COM_Y-Ground_COM_Y)))
        QtCore.QTimer.singleShot(interval, updateData)
    except PyCapture2.Fc2error as fc2Err:
        #print "Error retrieving buffer : ", fc2Err
        text.setHtml("<font size=4> No image to draw or could not retrive image from the camera")
        QtCore.QTimer.singleShot(interval, updateData)

updateData()
## Start Qt event loop unless running in interactive mode.
if __name__ == '__main__':
    import sys
    if (sys.flags.interactive != 1) or not hasattr(QtCore, 'PYQT_VERSION'):
        QtGui.QApplication.instance().exec_()
