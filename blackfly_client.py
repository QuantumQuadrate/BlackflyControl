import zmq
import json
import pprint

context = zmq.Context()
socket = context.socket(zmq.REQ)
socket.setsockopt(zmq.RCVTIMEO, 5000)
addr = "{}://{}:{}".format("tcp", "127.0.0.1", 55555)
print addr
socket.connect(addr)
cmd = {
    'action': 'GET_CAMERAS'
}
print cmd
socket.send(json.dumps(cmd))
resp = json.loads(socket.recv())
print "status: " + str(resp["status"])
print "server message: " + resp["message"]
print "cameras:"
for c in resp["cameras"]:
    print "\tserNo: {}".format(c["serialNumber"])
    print "\tIP: {}".format(c["ipAddress"])
    print

for c in resp["cameras"]:
    if c['serialNumber'] == 16483677:
        camera = c

cmd = {
    'action': 'ADD_CAMERA',
    'serial': camera['serialNumber']
}
socket.send(json.dumps(cmd))
resp = json.loads(socket.recv())
print "status: " + str(resp["status"])
print "server message: " + resp["message"]

cmd = {
    'action': 'GET_IMAGE',
    'serial': camera['serialNumber']
}
socket.send(json.dumps(cmd))
resp = json.loads(socket.recv())
print "status: " + str(resp["status"])
print "server message: " + resp["message"]
print "image: {}".format(resp["image"])
