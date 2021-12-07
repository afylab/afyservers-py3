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
from twisted.internet import reactor, defer
from labrad.types import Value
import numpy as np
# from time import sleep
import serial
TIMEOUT = Value(2, 's')
BAUD = 38400
BYTESIZE = 8
STOPBITS = 1
PARITY = serial.PARITY_NONE


class DCXSPowerWrapper(DeviceWrapper):

    @inlineCallbacks
    def connect(self, server, port):
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

    # @inlineCallbacks
    # def read(self):
    #     """Read a response line from the device"""
    #     p = self.packet()
    #     p.read()
    #     ans = yield p.send()
    #     return ans.read
    #
    # @inlineCallbacks
    # def query(self, code):
    #     """ Write, then read. """
    #     p = self.packet()
    #     p.timeout(TIMEOUT)
    #     p.write(code)
    #     p.read()
    #     ans = yield p.send()
    #     return ans.read

    @inlineCallbacks
    def read(self):
        """Read a response line from the device"""
        p=self.packet()
        p.read_line()
        ans=yield p.send()
        return ans.read_line

    @inlineCallbacks
    def query(self, code):
        """ Write, then read. """
        p = self.packet()
        p.write(code)
        p.read_line()
        ans = yield p.send()
        return ans.read_line

class PowerSupplyServer(DeviceServer):
    name = 'DCXS_power'
    deviceName = 'DCXS Power'
    deviceWrapper = DCXSPowerWrapper

    def __init__(self):
        super().__init__()
        self.state = False
        self.abort = False
        self.setpoint = -1

    @inlineCallbacks
    def initServer(self):
        print('loading config info...', end=' ')
        self.reg = self.client.registry()
        yield self.loadConfigInfo()
        print('done.')
        # print(self.serialLinks)
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
        # print("ans=", ans)
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

    @setting(10, state='s', start_setpoint='i', returns='?')
    def switch(self, c, state, start_setpoint=10):
        """Turn on or off a scope channel display.
        State must be in "ON" or "OFF".
        start_setpoint is the power to spark the plasma with if turning on, usually
        10 - 30 W (in power mode) is used. According to the manual more than 30 W
        is not necessary to spark the plasma. Once the plasma is established ramp
        to the desired rate for deposition.
        """
        dev = self.selectedDevice(c)
        if state == "ON":
            if start_setpoint >= 0 and start_setpoint <= 350:
                yield self.set_setpoint(c, start_setpoint)
                yield dev.write("A".encode("ASCII", "ignore"))
                # yield self.sleep(0.1)
                self.state = True
            else:
                raise Exception('setpoint should be 0 - 350')
        elif state == "OFF":
            yield dev.write("B".encode("ASCII", "ignore"))
            # yield self.sleep(0.1)
            self.setpoint = -1
            self.state = False
        else:
            raise Exception('state must be ON or OFF')
        return self.state

    @setting(11, p='?')
    def mode(self, c, p=None):
        """
        Get or set the regulation mode: 0 - Power, 1 - Voltage, 2 - Current.
        If None will query the mode.
        """
        dev = self.selectedDevice(c)
        if p is None:
            mode = yield dev.query(b'c')
        elif p in [0, 1, 2]:
            yield dev.write(('D' + str(p)).encode("ASCII", "ignore"))
            yield dev.write('c')
            # yield self.sleep(0.1)
            mode = yield dev.read()
        else:
            raise Exception('Mode should be 0, 1 or 2')
        return mode

    @setting(12, p='i', returns='?')
    def set_setpoint(self, c, p):
        """
        Set the set point (not the actual!) power, voltage or
        current (0 - 20) depending on what regime is chosen (normally power).
        Setpoint should be an integer between 1 and 350
        """
        dev = self.selectedDevice(c)
        if not isinstance(p, int):
            raise Exception('Incorrect format, must be integer')
        elif p >= 0 and p <= 350:
            dec = len(str(p))
            self.setpoint = p
            print("Setpoint:", self.setpoint) # For Debugging
            out_p = '0' * (4 - dec) + str(p)
            yield dev.write(('C' + out_p).encode("ASCII", "ignore"))
            # yield self.sleep(0.1)
            yield dev.write('b')
            # yield self.sleep(0.1)
            setpoint = yield dev.read()
            try:
                setpoint = int(setpoint)
            except ValueError:
                print('Something wrong with the output setpoint.')
                print(setpoint)
            return setpoint
        else:
            raise Exception('setpoint should be 0 - 350')

    @setting(13, setpoint='i', ramprate='i', returns='?')
    def ramp(self, c, setpoint, ramprate=10):
        '''
        Ramps from the current setpoint to the given setpoint at the given ramprate.
        Will not ramp the setpoint below 10, if given setpoint is less than 10 will
        ramp to 10.

        Setpoint is the target setpoint
        Ramprate is in W/min, 10-20 W/min is recommended (Watts in power mode).
        '''
        if self.state and self.setpoint >= 0:
            if self.setpoint == setpoint:
                return "Already at setpoint"
            if setpoint < 10:
                setpoint = 10
            print("Ramping from", self.setpoint, "to", setpoint)
            delta = (setpoint - self.setpoint)
            num_points = int(np.abs(delta)/(ramprate/60))
            increment = delta/num_points
            current = self.setpoint
            while self.setpoint != setpoint:
                if self.abort:
                    yield self.switch("OFF")
                    self.abort = False
                    return "Ramp Aborted"
                current += increment
                yield self.set_setpoint(int(current))
                yield self.sleep(1) # important that the sleeptime equals one, throws off timing otherwise.
            return "Ramp Complete"
    #

    @setting(14, returns='?')
    def get_setpoint(self, c):
        """Get the setpoint value (0 - 1000)."""
        dev = self.selectedDevice(c)
        yield dev.write('b'.encode("ASCII", "ignore"))
        # yield self.sleep(0.1)
        setpoint = yield dev.read()
        try:
            setpoint = int(setpoint)
        except ValueError:
            print('Something wrong with the setpoint reading. Check the hardware display.')
        return setpoint

    @setting(15, returns='?')
    def get_power(self, c):
        """Get the actual power (0 - 1000)."""
        dev = self.selectedDevice(c)
        yield dev.write('d'.encode("ASCII", "ignore"))
        # yield self.sleep(0.1)
        p = yield dev.read()
        try:
            p = int(p)
        except ValueError:
            print('Something wrong with the power reading. Check the hardware display.')
        return p

    @setting(16, returns='?')
    def get_voltage(self, c):
        """Get the actual voltage (0 - 1000)."""
        dev = self.selectedDevice(c)
        yield dev.write('e'.encode("ASCII", "ignore"))
        # yield self.sleep(0.1)
        p = yield dev.read()
        try:
            p = int(p)
        except ValueError:
            print('Something wrong with the voltage reading. Check the hardware display.')
        return p

    @setting(17, returns='?')
    def get_current(self, c):
        """Get the actual current (0 - 1000)."""
        dev = self.selectedDevice(c)
        yield dev.write('f'.encode("ASCII", "ignore"))
        # yield self.sleep(0.1)
        p = yield dev.read()
        try:
            p = int(p)
        except ValueError:
            print('Something wrong with the current reading. Check the hardware display.')
        return p

    @setting(18, returns='?')
    def iden(self, c):
        """Get the device identification."""
        dev = self.selectedDevice(c)
        yield dev.write('?'.encode("ASCII", "ignore"))
        iden = yield dev.read()
        return iden

    @setting(19, returns='b')
    def get_state(self, c):
        '''
        Returns the state of the server
        '''
        return self.state

    @setting(20, returns='?')
    def abort_ramp(self, c):
        self.abort = True
        return self.abort

    @setting(21, returns='?')
    def unlock(self, c):
        self.abort = False
        return self.abort

    def sleep(self,secs):
        d = defer.Deferred()
        reactor.callLater(secs,d.callback,'Sleeping')
        return d

__server__ = PowerSupplyServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
