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
        """Add a camera to the list of active cameras and respond."""
        status, resp, camera_info = self.add_camera_task(msg)
        self.socket.send_json({
            'cameras': [camera_info.__dict__],
            'status': status,
            'message': resp
        })

    def add_camera_task(self, msg):
        """Add a camera to the list of active cameras and don't respond."""
        serial = msg['serial']
        status = 1
        camera_info = None
        for c in self.available_cameras:
            if serial == c.serialNumber:
                camera_info = c
                break

        if camera_info is None:
            resp = "Camera: `{}` is not in list of available cameras."
            logger = self.logger.error
        else:
            if not (camera_info is None) and not (serial in self.cameras):
                # serial number is required
                parameters = {'serial': serial}
                if 'triggerDelay' in msg:
                    parameters['triggerDelay'] = msg['triggerDelay']
                if 'exposureTime' in msg:
                    parameters['exposureTime'] = msg['exposureTime']
                self.cameras[serial] = BlackflyCamera(parameters)
                try:
                    self.cameras[serial].initialize()
                    self.cameras[serial].update(msg)
                except:
                    resp = "Problem initializing camera: `{}`"
                    logger = self.logger.exception
                else:
                    resp = "Camera: `{}` has been initialized."
                    status = 0
                    logger = self.logger.info
            else:
                resp = "Camera: `{}` is already initialized."
                logger = self.logger.warning

        resp = resp.format(serial)
        logger(resp)
        return (status, resp, camera_info)

    def check_cameras(self):
        for serial in self.cameras:
            if self.cameras[serial].status == 'ACQUIRING':
                err, data, stats = self.cameras[serial].GetImage()
                if err == 0:
                    # TODO: multi shot experiments
                    self.logger.info('Received image.')
                else:
                    self.logger.error('An error occurred getting an image.')
                self.cameras[serial].stop_capture()

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
        self.logger.debug('available cameras requested')
        self.socket.send_json({
            'cameras': [c.__dict__ for c in self.available_cameras],
            'status': 0,
            'message': 'success'
        })

    def get_results(self, msg):
        """Iterate through cameras and return images and processed data.

        For now just fetch the image data.
        """
        results = {}
        resp = 'success'
        status = 0
        for c in self.cameras:
            msg = 'Fetching information from Camera: `{}`'.format(c)
            self.logger.info(msg)
            err, data, stats = self.cameras[c].get_data()
            try:
                results[c] = {
                    'error': err,
                    'data': data,
                    'stats': stats
                }
            except AttributeError:
                results[c] = {'error': 1, 'data': {}}
                resp = "Error retrieving image data."
                #status = 1
        self.socket.send_json({
            'camera_data': results,
            'status': status,
            'message': resp
        })


    def get_image(self, msg):
        """Retrieve a single image from a camera by serial number."""
        serial = msg['serial']
        err, data, stats = self.cameras[serial].get_data()
        resp = 'success'
        if err:
            resp = "An error was encountered acquiring image data."
            self.logger.error(resp)
        self.socket.send_json({
            'image': data.tolist(),
            'status': err,
            'message': resp
        })

    def loop(self):
        """Run the server loop continuously."""
        should_continue = True
        err_msg = "Unexpected exception encountered closing server."
        while should_continue:
            try:
                msg = self.socket.recv_json()
                self.logger.info(msg)
                self.parse_msg(msg)
                self.check_cameras()
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

    def remove_camera(self, msg):
        """Remove a camera by serial number from the list of active cameras."""
        serial = msg['serial']
        error = 1
        if serial not in self.cameras:
            resp = "Camera: `{}` is not in list of active cameras."
            logger = self.logger.error

        if not error:
            del self.cameras[serial]
            logger = self.logger.info
            resp = "Camera: `{}` successfully deactivated."
            error = 0

        logger(resp)
        self.socket.send_json({
            'cameras': [c.__dict__ for c in self.available_cameras],
            'status': error,
            'message': resp.format(serial)
        })

    def setup_server(self):
        """Initialize the server port and begin listening for instructions."""
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REP)
        # set polling to be short so that the cameras can be checked frequently
        self.socket.setsockopt(zmq.RCVTIMEO, 50)
        addr = "{}://*:{}".format(
            self.settings["protocol"],
            self.settings["port"]
        )
        self.logger.info("server binding to: `{}`".format(addr))
        self.socket.bind(addr)

    def setup_logger(self):
        """Initialize a logger for the server."""
        logger = logging.getLogger(__name__)
        #logger.setLevel(logging.DEBUG)
        logger.setLevel(logging.INFO)
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
        for c in self.cameras:
            self.cameras[c].shutdown()
        self.socket.close()
        self.context.term()

    def start(self, msg):
        """Set all active cameras to wait for next hardware trigger."""
        try:
            for c in self.cameras:
                self.cameras[c].start_capture()
            status = 0
            resp = "Acquisition successfully started."
            self.logger.info("Acquisition successfully started.")
        except:
            status = 1
            resp = "Error encountered during acqusition."
            self.logger.exception(resp)
            # stop capturing on all cameras
            for c in self.cameras:
                self.cameras[c].stop_capture()
        self.socket.send_json({
            'status': status,
            'message': resp
        })

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
        self.socket.send_json({
            'cameras': [camera_info.__dict__],
            'status': status,
            'message': resp.format(serial)
        })

    def update(self, msg):
        try:
            client_cams = msg['settings']['cameras']
            for c in client_cams:
                serial = client_cams[c]['serial']
                try:
                    self.cameras[serial].update(parameters=client_cams[c])
                except KeyError:
                    # if the camera has not been added to the active camera
                    # list add it now
                    self.logger.info('Activating camera: `{}`'.format(serial))
                    self.add_camera_task(client_cams[c])
            status = 0
            resp = 'Update successful'
        except KeyError:
            status = 1
            resp = 'Server error'
            self.logger.exception("error")
        self.socket.send_json({
            'status': status,
            'message': resp
        })


if __name__ == "__main__":
    bfs = BlackflyServer()
