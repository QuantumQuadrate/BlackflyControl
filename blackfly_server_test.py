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
        self.test_serial = msg['serial']

        camera_info = self.available_cameras[0]
        camera_info['serial'] = serial

        resp = "Camera: `{}` has been initialized."
        status = 0
        logger = self.logger.info

        logger(resp)
        self.socket.send(json.dumps({
            'cameras': [camera_info],
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
        num_cams = self.settings["max_cameras"]
        self.available_cameras = [{}]

    def get_available_cameras(self, msg):
        """Respond to a request for information on available cameras."""
        self.socket.send(json.dumps({
            'cameras': [c for c in self.available_cameras],
            'status': 0,
            'message': 'success'
        }))

    def get_image(self, msg):
        self.socket.send(json.dumps({
            'image': [0, []],
            'status': 0,
            'message': 'success'
        }))

    def get_results(self, msg):
        """Iterate through cameras and return images and processed data.

        For now just fetch the image data.
        """
        results = {}
        results[self.test_serial] = {
            'error': 0,
            'data': []],
            'stats': {'X0':100, 'X1': 125, 'Y0': 24.3, 'Y1': 61.2}
        }
        self.socket.send_json({
            'camera_data': results,
            'status': 0,
            'message': 'success'
        })

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
            action = msg['action']
        except:
            resp = "Unable to parse message from client: {}."
            self.logger.exception(resp.format(msg))
        self.logger.debug('received `{}` cmd'.format(action))

        # register an error as the fall through
        valid = False
        # echo for heartbeat connection verification
        if action == 'ECHO':
            valid = True
            msg['status'] = 0
            self.socket.send_json(msg)
        # requesting a list of info for available cameras
        if action == 'GET_CAMERAS':
            valid = True
            self.get_available_cameras(msg)
        # requesting a list of info for available cameras
        if action == 'GET_RESULTS':
            valid = True
            self.get_results(msg)
        # Initialize and update camera by serial number
        if action == 'ADD_CAMERA':
            valid = True
            self.add_camera(msg)
        # Remove camera from list of active cameras by serial number
        if action == 'REMOVE_CAMERA':
            valid = True
            self.remove_camera(msg)
        # update settings on listed cameras
        if action == 'UPDATE':
            valid = True
            self.update(msg)
        # update setting on camera by serial number
        if action == 'UPDATE_CAMERA':
            valid = True
            self.update_camera(msg)
        # retrieve an image from the camera buffer
        if action == 'GET_IMAGE':
            valid = True
            self.get_image(msg)
        # software trigger to wait for next hardware trigger
        if action == 'START':
            valid = True
            self.start(msg)

        if not valid:
            # return the command with bad status and message
            msg['status'] = 1
            error_msg = 'Unrecognized action requested: `{}`'
            msg['message'] = error_msg.format(msg['action'])
            self.socket.send_json(msg)

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

        camera_info = self.available_cameras[0]

        resp = "Camera: `{}` has been updated."
        status = 0
        logger = self.logger.info

        logger(resp)
        self.socket.send(json.dumps({
            'cameras': [camera_info.__dict__],
            'status': status,
            'message': resp.format(serial)
        }))

if __name__ == "__main__":
    bfs = BlackflyServer()
