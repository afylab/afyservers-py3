"""
### BEGIN NODE INFO
[info]
name = DCXS power
version = 1.0
description = DCXS sputtering gun power supply controller.

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""

from labrad.server import setting
from labrad.devices import DeviceServer, DeviceWrapper
from twisted.internet.defer import inlineCallbacks
from labrad.types import Value
import time

TIMEOUT = Value(2, 's')
BAUD = 38400
BYTESIZE = 8
STOPBITS = 1
PARITY = 0


class DCXSPowerWrapper(DeviceWrapper):

    @inlineCallbacks
    def connect(self, server, port='COM4'):
        """Connect to a device."""
        print('connecting to "%s" on port "%s"...' % (server.name, port), end=' ')
        self.server = server
        self.ctx = server.context()
        self.port = port
        p = self.packet()
        p.open(port)
        p.baudrate(BAUD)
        p.bytesize(BYTESIZE)
        p.stopbits(STOPBITS)
        p.setParity = PARITY
        p.timeout(TIMEOUT)
        p.read()  # clear out the read buffer
        # Set timeout to 0
        p.timeout(None)
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
        p.read()
        ans = yield p.send()
        return ans.read

    @inlineCallbacks
    def query(self, code):
        """ Write, then read. """
        p = self.packet()
        p.timeout(TIMEOUT)
        p.write(code)
        p.read()
        ans = yield p.send()
        return ans.read


class PowerSupplyServer(DeviceServer):
    name = 'DCXS_power'
    deviceName = 'DCXS Power'
    deviceWrapper = DCXSPowerWrapper

    def __init__(self):
        super().__init__()
        self.state = False

    @inlineCallbacks
    def initServer(self):
        print('loading config info...', end=' ')
        self.reg = self.client.registry()
        yield self.loadConfigInfo()
        print('done.')
        print(self.serialLinks)
        yield DeviceServer.initServer(self)
        self.busy = False

    @inlineCallbacks
    def loadConfigInfo(self):
        reg = self.reg
        yield reg.cd(['', 'Servers', 'DCXS Power', 'Links'], True)
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
        devs = []
        for name, (serServer, port) in self.serialLinks.items():
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

    @setting(10, state='?', returns='s')
    def switch(self, c, state=None):
        """Turn on or off a scope channel display.
        State must be in [A - ON, B - OFF].
        Channel must be int or string.
        """
        dev = self.selectedDevice(c)
        if state is not None:
            if state not in ['A', 'B']:
                raise Exception('state must be A - ON, B - OFF')
            yield dev.write(state.encode("ASCII", "ignore"))
            self.state = not self.state
        resp = yield dev.query('a'.encode("ASCII", "ignore"))
        return resp

    @setting(11, p='?')
    def mode(self, c, p=None):
        """Get or set the regulation mode: 0 - Power, 1 - Voltage, 2 - Current"""
        dev = self.selectedDevice(c)
        if p is None:
            mode = yield dev.query(b'c')
        elif p in [0, 1, 2]:
            yield dev.write(('D' + str(p)).encode("ASCII", "ignore"))
            mode = yield dev.query(b'c')
        else:
            raise Exception('p should be 0, 1 or 2')
        return mode

    @setting(12, p='?', returns='?')
    def output_set(self, c, p=None):
        """Get or set the set point (not the actual!) power, voltage or
        current (0 - 1000) depending on what regime is chosen."""
        dev = self.selectedDevice(c)
        if isinstance(p, (bool, str, list, dict, tuple, float)):
            raise Exception('Incorrect format, must be integer')
        if isinstance(p, int) and (p >= 0) and (p < 1001):
            dec = len(str(p))
            out_p = '0' * (4 - dec) + str(p)
            yield dev.write(('C' + out_p).encode("ASCII", "ignore"))
        elif p is None:
            setpoint = yield dev.query('b'.encode("ASCII", "ignore"))
            try:
                setpoint = int(setpoint)
            except ValueError:
                print('Something wrong with the output. Check the hardware display.')
            return setpoint
        else:
            raise Exception('set point should be 0 - 1000')

    @setting(13, returns='?')
    def output_act(self, c):
        """Get the actual power, voltage or current (0 - 1000)
        depending on what regime is chosen."""
        dev = self.selectedDevice(c)
        mode = yield dev.query('c'.encode("ASCII", "ignore"))
        if mode == 0:
            p = yield dev.query('d'.encode("ASCII", "ignore"))
        elif mode == 1:
            p = yield dev.query('e'.encode("ASCII", "ignore"))
        else:
            p = yield dev.query('f'.encode("ASCII", "ignore"))
        try:
            p = int(p)
        except ValueError:
            print('Something wrong with the output. Check the hardware display.')
        return p

    @setting(14, p='?', returns='?')
    def ramptime(self, c, p=None):
        """Get or set (0 - 99s) the ramp time"""
        dev = self.selectedDevice(c)
        if p is None:
            ramp_time = yield dev.query('g'.encode("ASCII", "ignore"))
        elif isinstance(p, int) and (p >= 0) and (p < 100) and len(str(p)) < 3:
            dec = len(str(p))
            out_p = '0' * (2 - dec) + str(p)
            ramp_time = yield dev.query(('E'+out_p).encode("ascii", "ignore"))
        else:
            raise Exception('ramp time should be 0 - 99s')

        return ramp_time

    @setting(15, returns='?')
    def identification(self, c):
        """Get or set (0 - 99s) the ramp time"""
        dev = self.selectedDevice(c)
        iden = yield dev.query('?'.encode("ASCII", "ignore"))
        return iden

    @setting(16, returns='b')
    def returnstate(self, c):
        return self.state

__server__ = PowerSupplyServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
