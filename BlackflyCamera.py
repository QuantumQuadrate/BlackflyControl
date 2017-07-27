"""blackfly_threaded.py
   Part of the future AQuA Cesium Controller software package

   author = Garrett Hickman
   created = 2017-06-23
   modified >= 2017-06-23

   This program interfaces with the Blackfly cameras. It can control camera settings and read out images.
   The code is based off of "andor.py", written by Martin Lichtman.

   Video mode has not been added yet, but may come later given sufficient popular demand.

   This code makes use of the PyCapture2 python wrapper for Blackfly cameras, available from the FLIR downloads
   website at: https://www.ptgrey.com/support/downloads. Version dated 2017-4-24. The PyCapture2 package must
   be installed in order for this program to run.

   """

__author__ = 'Garrett Hickman'
# import logging
# logger = logging.getLogger(__name__)
from time import sleep    #allows pausing of program execution
import PyCapture2   #Python wrapper for BlackFly camera control software, needed for this code to work

import numpy



class BlackflyCamera(Instrument):

    parameters = {'serial':16483677, 'triggerDelay':0, 'exposureTime':1}


    def __init__(self, parameters):
        self.data = []    # initializes the 'data' varable for holding image data
        self.data.append(numpy.zeros(self.cam_resolution, dtype = float))    # creates an array to hold camera data for one image

        self.serial = parameters.serial
        self.triggerDelay = parameters.triggerDelay
        self.exposureTime = parameters.exposureTime

        # self.serial = 16483677  # for testing
        # self.serial = 16483678  # for testing


    def __del__(self):
        # if self.isInitialized:
        self.powerDown()

    # "initialize()" powers on the camera, configures it for hardware triggering, and
    # starts the camera's image capture process.
    def initialize(self):   # called only once, before calling "update" for the first time

        # logger.info('Blackfly camera {} is being initialized'.format(self.serial))

        # adds an instance of PyCapture2's camera class
        self.bus = PyCapture2.BusManager()
        self.camera_instance = PyCapture2.Camera()

        # connects the software camera object to a physical camera
        self.camera_instance.connect(self.bus.getCameraFromSerialNumber(self.serial))

        # Powers on the Camera
        cameraPower = 0x610
        powerVal = 0x80000000
        self.camera_instance.writeRegister(cameraPower, powerVal)

        # Waits for camera to power up
        retries = 10
        timeToSleep = 0.1  # seconds
        for i in range(retries):
            try:
                regVal = self.camera_instance.readRegister(cameraPower)
            except PyCapture2.Fc2error:  # Camera might not respond to register reads during powerup.
                pass
            awake = True
            if regVal == powerVal:
                break
            awake = False
            sleep(timeToSleep)
        if not awake:    # aborts if Python was unable to wake the camera
            # logger.info('Could not wake Blackfly camera. Exiting...')
            exit()

        # # Use these three lines to check camera info, if desired
        # self.camInfo = self.camera_instance.getCameraInfo()
        # resolution_str = self.camInfo.sensorResolution
        # self.cam_resolution = map(int, resolution_str.split('x'))    # converts the resolution information to an int list
        # # print "Serial number - ", self.camInfo.serialNumber
        # # print "Camera model - ", self.camInfo.modelName

        # # Enables the camera's 3.3V, 120mA output on GPIO pin 3 (red jacketed lead) if needed
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

        self.camera_instance.startCapture()    # prepares the cameras to acquire images

        # # Sets the camera grab mode:
        # # 0 = The camera retrieves only the newest image from the buffer each time the RetrieveBuffer() function
        # #     is called. Older images will be dropped. See p. 93 in the PyCapture 2 API Reference manual.
        # # 1 = The camera retrieves the oldest image from the buffer each time RetrieveBuffer() is called.
        # #     Ungrabbed images will accumulated until the buffer is full, after which the oldest will be deleted.
        # PyCapture2.GRAB_MODE = 0

        self.isInitialized = True


    def update(self, parameters):   # sends parameters that have been updated in software to the cameras, if camera is "enabled"
        self.serial = parameters.serial
        self.triggerDelay = parameters.triggerDelay
        self.exposureTime = parameters.exposureTime

        self.SetTriggerDelay()
        self.SetExposureTime()

    # Sets the delay between external trigger and frame acquisition
    def SetTriggerDelay(self):    # takes the software-defined trig delay time and writes to hardware
        trigger_delay_obj = self.camera_instance.getTriggerDelay()
        trigger_delay_obj.absControl = True
        trigger_delay_obj.onOff = True
        trigger_delay_obj.onePush = True
        trigger_delay_obj.autoManualMode = True
        # trigger_delay.valueA = 0   #this field is used when the "absControl" field is set to "False"
        #     #defines the trigger delay, in units of 40.69 ns (referenced to a 24.576 MHz internal clock)
        #     #range of this field is 0-4095. It's preferred to use the absValue variable.
        #     #trigger_delay.valueB = 0     #I don't know what this value does
        trigger_delay_obj.absValue = self.triggerDelay   #this field is used when the "absControl" field is set to "True"
            #units are seconds. It is preferred to use this variable rather than valueA.
        self.camera_instance.setTriggerDelay(trigger_delay_obj)
        return

    # Sets the exposure time
    def SetExposureTime(self):    # takes the software-defined exposure time and writes it to hardware
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
        shutter_value = self.exposureTime   #specifies the shutter exposure time
            #in units of approximately 19 microseconds, up to a value of 1000.
            #After a value of roughly 1,000 the behavior is nonlinear.
            #The maximum value is 4095.
            #For values between 5 and 1000, shutter time is very well approximated by: t = (shutter_value*18.81 - 22.08) us
        bits20_31 = format(shutter_value,'012b')
        shutter_bin = bits0_7 + bits8_19 + bits20_31
        shutter = int(shutter_bin, 2)   #converts the binary value to base-10 integer
        self.camera_instance.writeRegister(shutter_address, shutter)    #writes to the camera
        return

    # Gets one image from the camera
    def GetImage(self):

        # Attempts to read an image from the camera buffer
        try:
            image = self.camera_instance.retrieveBuffer()
        except PyCapture2.Fc2error as fc2Err:
            # logger.error('Error {} when retrieving buffer from camera {}: '.format(fc2Err, cam_index))

        # Saves the data in the 'image' to the 'self.data' variable
        raw_image_data = PyCapture2.Image.getData(image)  # retrieves raw image data from the camera buffer
        self.nrows = PyCapture2.Image.getRows(image)  # finds the number of rows in the image data
        self.ncols = PyCapture2.Image.getDataSize(image) / self.nrows  # finds the number of columns in the image data
        self.data[:] = numpy.reshape(raw_image_data, (self.nrows, self.ncols), 'C')  # reshapes the data into a 2d array
        return self.data[:]

    def WaitForAcquisition(self):
        # Pauses program for 'pausetime' seconds, to allow the camera to acquire an image
        pausetime = 0.025
        time.sleep(pausetime)

    # Writes the results
    def writeResults(self, hdf5):

        # logger.info('Blackfly cameras are writing results')
        # logger.debug("Writing results from Blackfly to Blackfly_{}".format(self.serial))

        # writes the data in the self.data variable to the experiment hdf5 file
        if self.enable:
            try:
                hdf5['Blackfly_{}/columns'.format(self.serial)] = self.ncols
                hdf5['Blackfly_{}/rows'.format(self.serial)] = self.nrows
                hdf5['Blackfly_{}/numShots'.format(self.serial)] = 1    # doing only 1 shot per itteration, for now
                array = numpy.array(self.data, dtype=numpy.int32)
                array.resize(int(self.subimage_size[1]), int(self.subimage_size[0]))
                hdf5['Blackfly_{}/shots/1'.format(self.serial,i)] = array # Defines the name of hdf5 node in which to write the results.
            except Exception as e:
                # logger.exception('in Blackfly.writeResults')
                raise PauseError


    # Powers down the camera
    def powerDown(self):
        cameraPower = 0x610
        powerVal = 0x00000000
        self.camera_instance.writeRegister(cameraPower, powerVal)
        return