"""BlackflyCamera.py
   Part of the future AQuA Cesium Controller software package

   author = Garrett Hickman
   created = 2017-06-23
   modified >= 2017-06-23

   This program interfaces with the Blackfly cameras. It can control camera
   settings and read out images.
   The code is based off of "andor.py", written by Martin Lichtman.

   Video mode has not been added yet, but may come later given sufficient
   popular demand.

   This code makes use of the PyCapture2 python wrapper for Blackfly cameras,
   available from the FLIR downloads website at:
   https://www.ptgrey.com/support/downloads
   Version dated 2017-4-24. The PyCapture2 package must
   be installed in order for this program to run.
   """

__author__ = 'Garrett Hickman'
# import logging
# logger = logging.getLogger(__name__)
import time
import PyCapture2

import numpy
import scipy.ndimage.measurements as measurements
from scipy.ndimage.morphology import binary_opening
from scipy.optimize import curve_fit

def print_image_info(image):
    """Print image PyCapture2 image object info.

    startCapture callback function for testing.
    """
    # retrieves raw image data from the camera buffer
    raw_image_data = PyCapture2.Image.getData(image)
    # finds the number of rows in the image data
    nrows = PyCapture2.Image.getRows(image)
    # finds the number of columns in the image data
    ncols = PyCapture2.Image.getDataSize(image) / nrows
    # reshapes the data into a 2d array
    data = numpy.reshape(raw_image_data, (nrows, ncols), 'C')
    print (0, nrows, ncols, data)


class BlackflyCamera(object):

    def __init__(self, parameters):
        # initializes the 'data' varable for holding image data
        self.data = []
        self.error = 0
        self.status = 'STOPPED'
        # creates an array to hold camera data for one image
        # self.data.append(numpy.zeros(self.cam_resolution, dtype=float))

        # default parameters
        self.parameters = {
            'serial': 16483677,  # should this be hardcoded? MK
            'triggerDelay': 0,
            'exposureTime': 1
        }

        for key in parameters:
            self.parameters[key] = parameters[key]

        self.imageNum = 0

    def __del__(self):
        # if self.isInitialized:
        self.powerdown()

    # "initialize()" powers on the camera, configures it for hardware
    # triggering, and starts the camera's image capture process.
    def initialize(self):
        # called only once, before calling "update" for the first time

        # logger.info('Blackfly camera {} is being initialized'.format(self.serial))

        # adds an instance of PyCapture2's camera class
        self.bus = PyCapture2.BusManager()
        self.camera_instance = PyCapture2.GigECamera()

        # connects the software camera object to a physical camera
        self.camera_instance.connect(self.bus.getCameraFromSerialNumber(self.parameters['serial']))

        # Powers on the Camera
        cameraPower = 0x610
        powerVal = 0x80000000
        try:
            self.camera_instance.writeRegister(cameraPower, powerVal)
        except PyCapture2.Fc2error:
            print "problem"

        # Waits for camera to power up
        retries = 10
        timeToSleep = 0.1  # seconds
        for i in range(retries):
            try:
                regVal = self.camera_instance.readRegister(cameraPower)
            # Camera might not respond to register reads during powerup.
            except PyCapture2.Fc2error:
                pass
            awake = True
            if regVal == powerVal:
                break
            awake = False
            time.sleep(timeToSleep)
        if not awake:    # aborts if Python was unable to wake the camera
            # logger.info('Could not wake Blackfly camera. Exiting...')
            exit()

        # # Use these three lines to check camera info, if desired
        # self.camInfo = self.camera_instance.getCameraInfo()
        # resolution_str = self.camInfo.sensorResolution
        # converts the resolution information to an int list
        # self.cam_resolution = map(int, resolution_str.split('x'))
        # # print "Serial number - ", self.camInfo.serialNumber
        # # print "Camera model - ", self.camInfo.modelName

        # # Enables the camera's 3.3V, 120mA output on GPIO pin 3 (red jacketed
        # lead) if needed
        # output_voltage = 0x19D0
        # voltage_mode = 0x00000001
        # self.camera[cam_index].writeRegister(output_voltage, voltage_mode)

        # Configures trigger mode for hardware triggering
        trigger_mode = self.camera_instance.getTriggerMode()
        trigger_mode.onOff = True   # turns the trigger on
        trigger_mode.mode = 0
        trigger_mode.polarity = 1
        trigger_mode.source = 0  # specifies an external hardware trigger
        self.camera_instance.setTriggerMode(trigger_mode)
        # # Sets the camera grab mode:
        # # 0 = The camera retrieves only the newest image from the buffer each time the RetrieveBuffer() function
        # #     is called. Older images will be dropped. See p. 93 in the PyCapture 2 API Reference manual.
        # # 1 = The camera retrieves the oldest image from the buffer each time RetrieveBuffer() is called.
        # #     Ungrabbed images will accumulated until the buffer is full, after which the oldest will be deleted.
        PyCapture2.GRAB_MODE = 0
        self.isInitialized = True

    def update(self, parameters={}):
        # sends parameters that have been updated in software to the cameras,
        # if camera is "enabled"
        for key in parameters:
            self.parameters[key] = parameters[key]

        self.SetTriggerDelay(self.parameters['triggerDelay'])
        self.SetExposureTime(self.parameters['exposureTime'])
        self.SetGigEConfig(self.parameters['gigEConfig'])
        self.SetGigEStreamChannel(self.parameters['gigEStreamChannel'])
        # print self.camera_instance.getGigEStreamChannelInfo(0).__dict__
        self.SetGigEImageSettings(self.parameters['gigEImageSettings'])

    # Sets the delay between external trigger and frame acquisition
    def SetTriggerDelay(self, triggerDelay):
        self.camera_instance.setTriggerDelay(**triggerDelay)

    def SetGigEConfig(self, gigEConfig):
        self.camera_instance.setGigEConfig(**gigEConfig)

    def SetGigEImageSettings(self, gigEImageSettings):
        self.camera_instance.setGigEImageSettings(**gigEImageSettings)
        # print self.camera_instance.getGigEImageSettings().__dict__

    def SetGigEStreamChannel(self, gigEStreamChannel):
        if 'packetSize' in gigEStreamChannel:
            ptype = PyCapture2.GIGE_PROPERTY_TYPE.GIGE_PACKET_SIZE
            gigEProp = self.camera_instance.getGigEProperty(ptype)
            gigEProp.value = gigEStreamChannel['packetSize']
            self.camera_instance.setGigEProperty(gigEProp)
        if 'interPacketDelay' in gigEStreamChannel:
            ptype = PyCapture2.GIGE_PROPERTY_TYPE.GIGE_PACKET_DELAY
            gigEProp = self.camera_instance.getGigEProperty(ptype)
            gigEProp.value = gigEStreamChannel['interPacketDelay']
            self.camera_instance.setGigEProperty(gigEProp)

    # Sets the exposure time
    def SetExposureTime(self, exposureTime):
        """Writes the software-defined exposure time to hardware"""
        shutter_address = 0x81C
        # "shutter" variable format:
        # bit [0]: indicates presence of this feature. 0 = not available, 1 = available
        # bit [1]: absolute value control. 0 = control with the "Value" field
        #                                  1 = control with the Absolute value register
        # bits [2-4]: reserved
        # bit [5]: one push auto mode. read: 0 = not in operation, 1 = in operation
        #                              write: 1 = begin to work (self-cleared after operation)
        # bit [6]: turns this feature on or off. 0 = off, 1 = on.
        # bit [7]: auto/manual mode. 0 = manual, 1 - automatic
        # bits [8-19]: high value. (not sure what this does)
        # bits [20-31]: shutter exposure time, in (units of ~19 microseconds).
        bits0_7 = '10000010'
        bits8_19 = '000000000000'

        # specifies the shutter exposure time
        # in units of approximately 19 microseconds, up to a value of 1000.
        # After a value of roughly 1,000 the behavior is nonlinear.
        # The maximum value is 4095.
        # For values between 5 and 1000, shutter time is very well approximated
        # by: t = (shutter_value*18.81 - 22.08) us
        shutter_value = int(round((exposureTime*1000+22.08)/18.81))
        if shutter_value > 4095:
            shutter_value = 4095
        bits20_31 = format(shutter_value, '012b')
        print exposureTime
        print shutter_value
        print bits20_31
        shutter_bin = bits0_7 + bits8_19 + bits20_31
        # converts the binary value to base-10 integer
        shutter = int(shutter_bin, 2)
        # writes to the camera
        self.camera_instance.writeRegister(shutter_address, shutter)

    def sanity_check(self, data):
        nth_largest=10
        value=numpy.partition(data.flatten(),-nth_largest)[-nth_largest]
        return value

    def centroid_calc(self, data):
        #percentile = 98
        nth_largest= 8000
        # Set threshold based on the percentile
        threshold=numpy.partition(data.flatten(),-nth_largest)[-nth_largest]
        #threshold = numpy.percentile(data, percentile)
        # Mask pixels having brightness less than given threshold
        thresholdmask = data > threshold
        # Apply dilation-erosion to exclude possible noise
        openingmask = binary_opening(thresholdmask)
        temp=numpy.ma.array(data, mask=numpy.invert(openingmask))
        temp2=temp.filled(0)
        if threshold>numpy.max(temp2): # if there is no signal, assign NaN
           [COM_Y, COM_X]=[numpy.nan,numpy.nan]
           self.error=1
        else:
           [COM_Y, COM_X] = measurements.center_of_mass(temp2)  # Center of mass.
        return COM_X, COM_Y, temp2

    def calculate_statistics(self,data,shot):
        # Shot dependent magnification.
        # This will convert the camera location into atom plane distance in um
        #
        PG_pixelsize=3.75
        [mag_Red, mag_FORT]=[20.9, 23.8]
        [conv_Red, conv_FORT]=[PG_pixelsize/mag_Red, PG_pixelsize/mag_FORT]
        self.error=0 # initialize error flag to zero
        if shot == 0:
            self.stats = {}  # If this is the first shot, empty the stat.
        offsetX=self.parameters['gigEImageSettings']['offsetX'] # Image acqiured from the camera may not be at full screen. Add offset to pass absolute positions.
        offsetY=self.parameters['gigEImageSettings']['offsetY']
        # Get initial guesses
        EV = self.sanity_check(data) # measure of correct exposure. 0 to 255
        self.stats['EV{}'.format(shot)] = float(EV)
        if EV==255:
            self.error=1
            print "Overexposed"
        Centroid_X, Centroid_Y, preconditioned_data = self.centroid_calc(data)

        if self.error==0:
            img,offsetx,offsety = img_crop(preconditioned_data,Centroid_X, Centroid_Y)
            Fit_values_x, error_x = gaussianfit_x(preconditioned_data,Centroid_X)
            Fit_values_y, error_y = gaussianfit_y(preconditioned_data,Centroid_Y)
            if error_x==0 and error_y==0:
                [centerx,centery] = [Fit_values_x,Fit_values_y]
                [location_X, location_Y]=[centerx+offsetX, centery+offsetY]
                if shot==0: # Red is configured to be the first shot
                    [atomplane_X, atomplane_Y]=[conv_Red*location_X, conv_Red*location_Y]
                elif shot==1:
                    [atomplane_X, atomplane_Y]=[conv_FORT*location_X, conv_FORT*location_Y]
                self.stats['X{}'.format(shot)] = atomplane_X
                self.stats['Y{}'.format(shot)] = atomplane_Y
            else:
                self.error=1

        if self.error==1:
            self.stats['X{}'.format(shot)] = numpy.NaN
            self.stats['Y{}'.format(shot)] = numpy.NaN

    # Gets one image from the camera
    def GetImage(self):
            # Attempts to read an image from the camera buffer
        self.error = 0
        self.data = []
        try:
            shots = self.parameters['shotsPerMeasurement']
        except KeyError:
            shots = 1
        for shot in range(shots):
            #print "Delta t:{} ms. Starting to take shot:{}".format(int(1000*(time.time()-self.start_time)), shot)
            try:
                image = self.camera_instance.retrieveBuffer()
                #print "buffer retrieved"

                # retrieves raw image data from the camera buffer
                raw_image_data = numpy.array(image.getData(), dtype=numpy.uint8)
                self.nrows = PyCapture2.Image.getRows(image)
                self.ncols = PyCapture2.Image.getCols(image)
                # reshapes the data into a 2d array
                reshaped_image_data = numpy.reshape(
                    raw_image_data,
                    (self.nrows, self.ncols),
                    'C'
                )
                self.calculate_statistics(reshaped_image_data, shot)
            except PyCapture2.Fc2error as fc2Err:
                print fc2Err
                print "Error occured. statistics for this shot will be set to NaN"
                self.stats['X{}'.format(shot)] = numpy.NaN
                self.stats['Y{}'.format(shot)] = numpy.NaN
                self.stats['EV{}'.format(shot)] = numpy.NaN
                self.error=1
                #return (1, "Error", {})
        #print self.stats
        return (self.error, self.data, self.stats)

    def get_data(self):
        data = self.data
        error = self.error
        stats = self.stats
        # clear data and error
        self.data = []
        self.error = 0
        self.stats = {}
        return (error, data, stats)

    def WaitForAcquisition(self):
        # Pauses program for 'pausetime' seconds, to allow the camera to
        # acquire an image
        pausetime = 0.025
        time.sleep(pausetime)

    # Powers down the camera
    def powerdown(self):
        cameraPower = 0x610
        powerVal = 0x00000000
        self.camera_instance.writeRegister(cameraPower, powerVal)
        return

    def start_capture(self):
        """Software trigger to begin capturing an image."""
        # callback function causes server to crash
        # self.camera_instance.startCapture(print_image_info)
        self.camera_instance.startCapture()
        self.status = 'ACQUIRING'
        self.start_time = time.time()

    def stop_capture(self):
        """Software trigger to stop capturing an image."""
        self.camera_instance.stopCapture()
        self.status = 'STOPPED'

    def shutdown(self):
        try:
            self.camera_instance.stopCapture()
        except:
            print "exception"
        try:
            self.camera_instance.disconnect()
        except:
            print "exception 2"

# Five site gaussian function
def quintuplegaussian(x, c1, mu1, sigma1,c2, mu2, sigma2,c3, mu3, sigma3,c4, mu4, sigma4,c5, mu5, sigma5, B):
    res = c1 * numpy.exp( - (x - mu1)**2.0 / (2.0 * sigma1**2.0) ) + c2 * numpy.exp( - (x - mu2)**2.0 / (2.0 * sigma2**2.0) ) + c3 * numpy.exp( - (x - mu3)**2.0 / (2.0 * sigma3**2.0) ) + c4 * numpy.exp( - (x - mu4)**2.0 / (2.0 * sigma4**2.0) ) + c5 * numpy.exp( - (x - mu5)**2.0 / (2.0 * sigma5**2.0) ) + B
    return res

# Single gaussian function
def gaussian( x, c1, mu1, sigma1,B):
    res = c1 * numpy.exp( - (x - mu1)**2.0 / (2.0 * sigma1**2.0) ) + B
    return res

def img_crop(data,COM_X,COM_Y):
   [window_H,window_W]=[150,300] # desired window size
   [image_H,image_W] = numpy.shape(data)
   if image_H>window_H and image_W>window_W: # check if image is larger than the size we want to crop in.
       startx = numpy.max([0,int(COM_X-(window_W/2))])
       endx = numpy.min([image_W,int(COM_X+(window_W/2))])
       starty = numpy.max([1,int(COM_Y-(window_H/2))])
       endy = numpy.min([image_H,int(COM_Y+(window_H/2))])

       new_img = data[starty:endy,startx:endx]
       [offsetx,offsety] = [startx,starty]
       return new_img,offsetx,offsety
   else:
       return data, 0, 0

def gaussianfit_x(data,COM_X):
    error=0
    gaussian_X=numpy.NaN
    data_1d=numpy.sum(data,axis=0) # check if the axis correctf
    leng = range(0,len(data_1d))
    [amp,bg] = [numpy.max(data_1d)-numpy.median(data_1d),numpy.median(data_1d)]
    [site_separation,sigma]=[52,20]
    tolerance=20.0
    try:
        # primary guess is fit3
        fit1 = curve_fit(gaussian,leng,data_1d,[0.4*amp,COM_X-2*site_separation,sigma,bg])
        fit2 = curve_fit(gaussian,leng,data_1d,[0.6*amp,COM_X-1*site_separation,sigma,bg])
        fit3 = curve_fit(gaussian,leng,data_1d,[amp,COM_X,sigma,bg])
        fit4 = curve_fit(gaussian,leng,data_1d,[0.6*amp,COM_X+1*site_separation,sigma,bg])
        fit5 = curve_fit(gaussian,leng,data_1d,[0.4*amp,COM_X+2*site_separation,sigma,bg])
        amps=[fit1[0][0],fit2[0][0],fit3[0][0],fit4[0][0],fit5[0][0]]
        centers=[fit1[0][1],fit2[0][1],fit3[0][1],fit4[0][1],fit5[0][1]]
        max_index=numpy.argmax(amps)
        X_candidate=centers[max_index]
        #print "COM_X:{}".format(COM_X)
        #print "X Candidate:{}".format(X_candidate)
        if numpy.absolute(X_candidate-COM_X)<=tolerance and amps[max_index]>0:
            gaussian_X=X_candidate
    except RuntimeError:
        error=1

    return gaussian_X, error

def gaussianfit_y(data,COM_Y):
    error=0
    data_1d=numpy.sum(data,axis=1) # check if the axis correctf
    leng = range(0,len(data_1d))
    [maxx,bg] = [numpy.max(data_1d),numpy.min(data_1d)]
    sigma=30
    try:
        fit = curve_fit(gaussian,leng,data_1d,[maxx,COM_Y,sigma,bg])
        gaussian_Y=fit[0][1]
    except RuntimeError:
        gaussian_Y=numpy.NaN
        error=1
    return gaussian_Y, error
