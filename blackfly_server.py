"""blackfly_server.py
   Part of the future AQuA Cesium Controller software package

   author = Matthew Ebert
   created = 2017-07-31

   This program hosts a server that maintains connections to multiple Blackfly
   cameras. It can control camera settings and read out images.

   Video mode has not been added yet, but may come later given sufficient
   popular demand.
   """

import zmq
import json
import logging
import PyCapture2
from BlackflyCamera import BlackflyCamera

__author__ = 'Matthew Ebert'


class BlackflyServer(object):
    """A ZMQ server interface for multiple pointgrey (FLIR) blackfly cameras."""

    settings = {
        'protocol': "tcp",
        'port': 55555,
        'max_cameras': 2
    }

    def __init__(self, settings={}):
        """Initialize the BlackflyServer server class.

        @param settings A dictionary containing the settings
        """
        for key in settings:
            self.settings[key] = settings[key]

        # a dictionary of instantiated camera objects with serial numbers as
        # the keys
        self.cameras = {}
        # set up console logging
        self.setup_logger()
        # get available camera serial numbers
        self.get_cameras()
        # setup server socket
        self.setup_server()
        # enter poller loop
        self.loop()

    def add_camera(self, msg):
        serial = msg['serial']

        camera_info = None
        for c in self.available_cameras:
            if serial == c.serialNumber:
                camera_info = c
                break

        if camera_info is None:
            resp = "Camera: `{}` is not in list of available cameras."
            status = 1
            logger = self.logger.error

        if not (camera_info is None) and not (serial in self.cameras):
            # serial number is required
            parameters = {'serial': serial}
            if 'trigger_delay' in msg:
                parameters['triggerDelay'] = msg['trigger_delay']
            if 'exposure_time' in msg:
                parameters['exposureTime'] = msg['exposure_time']
            self.cameras[serial] = BlackflyCamera(parameters)
            try:
                self.cameras[serial].initialize()
                self.cameras[serial].update()
            except:
                resp = "Problem initializing camera: `{}`"
                status = 1
                logger = self.logger.exception
            else:
                resp = "Camera: `{}` has been initialized."
                status = 0
                logger = self.logger.info
        else:
            resp = "Camera: `{}` is already initialized."
            status = 1
            logger = self.logger.warning

        logger(resp)
        self.socket.send(json.dumps({
            'cameras': [camera_info.__dict__],
            'status': status,
            'message': resp.format(serial)
        }))

    def get_cameras(self):
        """Get all attached blackfly cameras.

        Populates a list of ethernet cameras: self.available_cameras
        the list objects are of type: PyCapture2.CameraInfo class

        @return available_cameras A list of cameras detected which could be
            connected
        """
        self.bus = PyCapture2.BusManager()
        # discover at most `max_cameras` cameras on the subnet
        num_cams = self.settings["max_cameras"]
        self.available_cameras = self.bus.discoverGigECameras(numCams=num_cams)

    def get_available_cameras(self, msg):
        """Respond to a request for information on available cameras."""
        self.socket.send(json.dumps({
            'cameras': [c.__dict__ for c in self.available_cameras],
            'status': 0,
            'message': 'success'
        }))

    def get_image(self, msg):
        serial = msg['serial']
        err, data = self.cameras[serial].GetImage()
        if err:
            self.logger.exception("does this work?")
        else:
            self.logger.info('all good')
            self.logger.info(type(data))
        self.socket.send(json.dumps({
            'image': data.tolist(),
            'status': 0,
            'message': 'success'
        }))


    def loop(self):
        """Run the server loop continuously."""
        should_continue = True
        err_msg = "Exception encountered closing server."
        while should_continue:
            try:
                msg = self.socket.recv()
                self.logger.info(msg)
                self.parse_msg(msg)
            except zmq.ZMQError as e:
                if e.errno != zmq.EAGAIN:
                    self.logger.exception(err_msg)
                    break
            except KeyboardInterrupt:
                self.logger.info('Shutting down server nicely.')
                break
            except:
                self.logger.exception(err_msg)
                break
        self.shutdown()

    def parse_msg(self, msg):
        """Parse and act on a request from a client."""
        try:
            parsed_msg = json.loads(msg)
            action = parsed_msg['action']
        except:
            resp = "Unable to parse message from client: {}."
            self.logger.exception(resp.format(msg))

        self.logger.debug('recieved `{}` cmd'.format(action))

        # requesting a list of info for available cameras
        if action == 'GET_CAMERAS':
            self.get_available_cameras(parsed_msg)
        # Initialize and update camera by serial number
        if action == 'ADD_CAMERA':
            self.add_camera(parsed_msg)
        # update setting on camera by serial number
        if action == 'UPDATE_CAMERA':
            self.update_camera(parsed_msg)
        # retrieve an image from the camera buffer
        if action == 'GET_IMAGE':
            self.get_image(parsed_msg)

    def setup_server(self):
        """Initialize the server port and begin listening for instructions."""
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REP)
        self.socket.setsockopt(zmq.RCVTIMEO, 1000)
        addr = "{}://*:{}".format(
            self.settings["protocol"],
            self.settings["port"]
        )
        self.logger.info("server binding to: `{}`".format(addr))
        self.socket.bind(addr)

    def setup_logger(self):
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.DEBUG)
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        fmtstr = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        formatter = logging.Formatter(fmtstr)
        ch.setFormatter(formatter)
        logger.addHandler(ch)
        logger.info('Logger initialized')
        self.logger = logger

    def shutdown(self):
        """Close the server down."""
        self.socket.close()
        self.context.term()

    def update_camera(self, msg):
        serial = msg['serial']

        camera_info = None
        for c in self.available_cameras:
            if serial == c.serialNumber:
                camera_info = c
                break

        if camera_info is None:
            resp = "Camera: `{}` is not in list of available cameras."
            status = 1
            logger = self.logger.error

        if not (camera_info is None) and (serial in self.cameras):
            # serial number is required
            parameters = {'serial': serial}
            if 'trigger_delay' in msg:
                parameters['triggerDelay'] = msg['trigger_delay']
            if 'exposure_time' in msg:
                parameters['exposureTime'] = msg['exposure_time']
            self.cameras[serial] = BlackflyCamera(parameters)
            try:
                self.cameras[serial].update()
            except:
                resp = "Problem updating camera: `{}`"
                status = 1
                logger = self.logger.exception
            else:
                resp = "Camera: `{}` has been updated."
                status = 0
                logger = self.logger.info
        else:
            resp = "Camera: `{}` is not initialized."
            status = 1
            logger = self.logger.warning

        logger(resp)
        self.socket.send(json.dumps({
            'cameras': [camera_info.__dict__],
            'status': status,
            'message': resp.format(serial)
        }))

if __name__ == "__main__":
    bfs = BlackflyServer()
