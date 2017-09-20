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

    def calculate_statistics(self, data, shot):
        if shot == 0:
            self.stats = {}  # If this is the first shot, empty the stat.
        percentile = 99.5
        threshold = numpy.percentile(data, percentile)  # Set threshold
        # Mask pixels having brightness less than given threshold
        thresholdmask = data > threshold
        # Apply dilation-erosion to exclude possible noise
        openingmask = binary_opening(thresholdmask)
        temp=numpy.ma.array(data, mask=numpy.invert(openingmask))
        temp2=temp.filled(0)
        if threshold>numpy.max(temp2):
            print "Warning : Could not locate beam, shot:{}".format(shot)
            self.error=2
            [COM_X, COM_Y]=[numpy.nan,numpy.nan]
        else:
        # Is image flipped for titled?
            [COM_Y, COM_X] = measurements.center_of_mass(temp2)  # Center of mass.
            self.stats['X{}'.format(shot)] = COM_X
            self.stats['Y{}'.format(shot)] = COM_Y

    # Gets one image from the camera
    def GetImage(self):
            # Attempts to read an image from the camera buffer
        self.error = 1
        self.data = []
        try:
            shots = self.parameters['shotsPerMeasurement']
        except KeyError:
            shots = 1
        for shot in range(shots):
            #print "Delta t:{} ms. Starting to take shot:{}".format(int(1000*(time.time()-self.start_time)), shot)
            try:
                image = self.camera_instance.retrieveBuffer()
                print "buffer retrieved"
            except PyCapture2.Fc2error as fc2Err:
                print fc2Err
                return (1, "Error", {})

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
        if self.error==1:
            self.error = 0
        elif self.error==2:
            self.error=1

        print self.stats
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
