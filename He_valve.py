#he_valve control server
import platform
global serial_server_name
serial_server_name = (platform.node() + '_serial_server').replace('-', '_').lower()

from labrad.server import setting
from labrad.devices import DeviceServer, DeviceWrapper
from twisted.internet.defer import inlineCallbacks, returnValue
import labrad.units as units
from labrad.types import Value
import time

from traceback import format_exc

TIMEOUT = Value(5, 's')
BAUD = 9600
BYTESIZE = 8
STOPBITS = 1
PARITY = 0

class HeValveWrapper(DeviceWrapper):
    @inlineCallbacks
    def connect(self, server, port):
        """Connect to a device."""
        print('connecting to "%s" on port "%s"...' % (server.name, port), end=' ')
        self.server = server
        self.ctx = server.context()
        self.port = port
        p = self.packet()
        p.open(port)
        # Testing no pulse serial connect
        #p.open(port, True) #If this is left on there will be a flattening error
        p.baudrate(BAUD)
        p.bytesize(BYTESIZE)
        p.stopbits(STOPBITS)
        p.setParity = PARITY
        p.read()  # clear out the read buffer
        p.timeout(TIMEOUT)
        # p.timeout(None)
        print(" CONNECTED ")       
        yield p.send()

    def packet(self):
        """Create a packet in our private context"""
        return self.server.packet(context=self.ctx)

    def shutdown(self):
        """Disconnect from the serial port when we shut down"""
        return self.packet().close().send()
        
    @inlineCallbacks
    def write(self, code):
        """Write a data value to the device"""
        yield self.packet().write(code).send()

    @inlineCallbacks
    def read(self):
        """Read a response line from the device"""
        p = self.packet()
        p.read_line()
        ans = yield p.send()
        returnValue(ans.read_line)

    @inlineCallbacks
    def waiting(self):
        """Read a response line from the device"""
        p = self.packet()
        p.in_waiting()
        ans = yield p.send()
        returnValue(ans.in_waiting)
    
    @inlineCallbacks
    def query(self, code):
        """ Write, then read. """
        p = self.packet()
        p.write_line(code)
        p.read_line()
        ans = yield p.send()
        returnValue(ans.read_line)
    

class HeValve(DeviceServer):
    name = 'He_valve'
    deviceName = 'He_valve_due'
    deviceWrapper = HeValveWrapper

    @inlineCallbacks
    def initServer(self):
        print('loading config info...', end=' ')
        self.reg = self.client.registry()
        yield self.loadConfigInfo()
        print('done.')
        print(self.serialLinks) 
        yield DeviceServer.initServer(self)

    @inlineCallbacks
    def loadConfigInfo(self):
        reg = self.reg
        yield reg.cd(['', 'Servers', 'He_valve', 'Links'], True) #THIS NEEDS TO BE CHANGED FOR EACH SERVER
        dirs, keys = yield reg.dir()
        p = reg.packet()
        print("Created packet")
        print("printing all the keys", keys)
        for k in keys:
            print("k=", k)
            p.get(k, key=k)
        ans = yield p.send()
        print("ans=", ans)
        self.serialLinks = dict((k, ans[k]) for k in keys)

    @inlineCallbacks
    def findDevices(self):
        try:
            devs = []
            for name, (serServer, port) in list(self.serialLinks.items()):
                if serServer not in self.client.servers:
                    print(serServer)
                    print(self.client.servers)
                    continue
                server = self.client[serServer]
                ports = yield server.list_serial_ports()
                if port not in ports:
                    continue
                devName = '%s - %s' % (serServer, port)
                devs += [(devName, (server, port))]
            return devs
        except:
            print(format_exc())

    @setting(10, returns='s')
    def valve_open(self, c):
        """Opens the valve"""
        dev = self.selectedDevice(c)
        yield dev.write('o')  # Use the write method to send the command
        response = yield dev.read()  # Use the read method to get the response
        returnValue(response)

    @setting(20, returns='s')
    def valve_close(self, c):
        """Closes the valve"""
        dev = self.selectedDevice(c)
        yield dev.write('c')  # Use the write method to send the command
        response = yield dev.read()  # Use the read method to get the response
        returnValue(response)

    @setting(30, returns='s')
    def valve_status(self, c):
        """Reports if valve is open or closed"""
        dev = self.selectedDevice(c)
        yield dev.write('v')  # Use the write method to send the command
        response = yield dev.read()  # Use the read method to get the response
        returnValue(response)
    
    @setting(40, returns='s')
    def manual_status(self, c):
        """Reports if manual control is enabled or disabled"""
        dev = self.selectedDevice(c)
        yield dev.write('m')  # Use the write method to send the command
        response = yield dev.read()  # Use the read method to get the response
        returnValue(response)

    @setting(50,returns = 's')
    def read_port(self, c):
        """Reads a line from the buffer"""
        dev = self.selectedDevice(c)
        response = yield dev.read()
        returnValue(response)

    @setting(60, returns = 's')
    def view_port(self, c):
        """Returns the number of bytes in the input buffer"""
        dev = self.selectedDevice(c)
        response = yield dev.waiting()
        returnValue(response)

    @setting(70, returns='s')
    def manual_enable(self, c):
        """Enables manual control"""
        dev = self.selectedDevice(c)
        yield dev.write('e')  # Use the write method to send the command
        response = yield dev.read()  # Use the read method to get the response
        returnValue(response)

    @setting(80, returns='s')
    def manual_disable(self, c):
        """Disables manual control"""
        dev = self.selectedDevice(c)
        yield dev.write('d')  # Use the write method to send the command
        response = yield dev.read()  # Use the read method to get the response
        returnValue(response)

__server__ = HeValve()

if __name__ == "__main__":
    from labrad import util
    util.runServer(__server__)
