# Copyright []
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
### BEGIN NODE INFO
[info]
name = BK 9103
version = 1.0
description = BK 9103 Power Supply

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""

import platform
global serial_server_name
serial_server_name = (platform.node() + '_serial_server').replace('-','_').lower()

from labrad.server import setting
from labrad.devices import DeviceWrapper, DeviceServer
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet import reactor, defer
#import labrad.units as units
from labrad.types import Value
import time

TIMEOUT = Value(1,'s')
BAUD = 9600
BYTESIZE = 8
STOPBITS = 1
PARITY = 0

def formatNum(v):
    '''
    The BK supply wants values in a specific format 0000 where the first two
    digits are before the decimal point and the second two are after, as if it
    was displayed on the supply's screen. I.e. 12.02 = 1202
    '''
    if v < 0:
        v = -1.0*v
        print("Warning BK power supply does not allow negative inputs, sign changed to positive.")
    if v >= 100.0:
        raise ValueError("Values over 100 not supported by BK power supply")
    s = "{:04.2f}".format(v)
    if v < 10:
        s = "0" + s
    return s.replace('.','')
#

class BK9103Wrapper(DeviceWrapper):
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
        p.read()
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
        p=self.packet()
        p.read()
        ans=yield p.send()
        returnValue(ans.read)

    @inlineCallbacks
    def query(self, code):
        """ Write, then read. """
        p = self.packet()
        p.write_line(code)
        p.read()
        ans = yield p.send()
        returnValue(ans.read)

class BK9103Server(DeviceServer):
    name             = 'BK_9103'
    deviceName       = 'BK 9103 Power Supply'
    deviceWrapper    = BK9103Wrapper

    @inlineCallbacks
    def initServer(self):
        print('loading config info...', end=' ')
        self.reg = self.client.registry()
        yield self.loadConfigInfo()
        print('done.')
        print(self.serialLinks)
        yield DeviceServer.initServer(self)
        self.busy = False
        self.output_on = False

    @inlineCallbacks
    def loadConfigInfo(self):
        reg = self.reg
        yield reg.cd(['', 'Servers', 'BK 9103', 'Links'], True)
        dirs, keys = yield reg.dir()
        p = reg.packet()
        print("Created packet")
        print("printing all the keys",keys)
        for k in keys:
            print("k=",k)
            p.get(k, key=k)
        ans = yield p.send()
        print("ans=",ans)
        self.serialLinks = dict((k, ans[k]) for k in keys)

    @inlineCallbacks
    def findDevices(self):
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
        returnValue(devs)

    def sleep(self,secs):
        d = defer.Deferred()
        reactor.callLater(secs,d.callback,'Sleeping')
        return d

    @setting(100, input='s', returns='s')
    def read(self, c, input):
        '''
        The power supply always returns "OK" before the final carriage return, i.e.
        a function might respond "<value>\rOK\r" or just "OK\r" this function will
        write some input then read until it gets the OK and the final return.
        '''
        while True:
            if self.busy == False:
                self.busy = True
                dev=self.selectedDevice(c)
                yield dev.write(input+"\r\n")
                tzero = time.perf_counter()
                ans = ''
                while True:
                    a = yield dev.read()
                    ans = ans + a
                    if ans.endswith("\rOK\r"):
                        self.busy = False
                        returnValue(ans.replace("\rOK\r",""))
                    elif ans.endswith("OK\r"):
                        self.busy = False
                        returnValue(ans.replace("OK\r",""))
                    elif (time.perf_counter() - tzero) > 1:
                        self.busy = False
                        returnValue("Timeout")
                    yield self.sleep(0.005)


    @setting(101, returns='b')
    def output_status(self, c):
        """Checks the status of the supply output (On or Off)."""
        ans = yield self.read(c,"GOUT")
        if int(ans) == 1:
            self.output_on = True
        elif int(ans) == 0:
            self.output_on = False
        else:
            print("Error invalid output status")
        returnValue(self.output_on)

    @setting(102, returns='b')
    def toggle_output(self, c):
        """
        Checks the status of the supply output (On or Off).
        Returns the current status of the output
        """
        yield self.output_status(c)
        if self.output_on:
            yield self.read(c, "SOUT0")
            self.output_on = False
        else:
            yield self.read(c, "SOUT1")
            self.output_on = True
        returnValue(self.output_on)

    @setting(103, volts='v', returns='b')
    def set_voltage(self, c, volts):
        """
        Sets the output voltage
        Returns True if the output is currently on, False otherwise
        """
        yield self.read(c, "VOLT3"+formatNum(volts))
        returnValue(self.output_on)

    @setting(104, amps='v', returns='b')
    def set_current(self, c, amps):
        """
        Sets the output current
        Returns True if the output is currently on, False otherwise
        """
        yield self.read(c, "CURR3"+formatNum(amps))
        returnValue(self.output_on)

    @setting(105, volts='v', returns='b')
    def set_voltage_limit(self, c, volts):
        """
        Sets the upper limit of output voltage. If you attempt to set the value above
        this limit it will turn off and display a voltage error
        Returns True if the output is currently on, False otherwise
        """
        yield self.read(c, "SOVP"+formatNum(volts))
        returnValue(self.output_on)

    @setting(106, amps='v', returns='b')
    def set_current_limit(self, c, amps):
        """
        Sets the upper limit of output voltage
        Returns True if the output is currently on, False otherwise
        """
        yield self.read(c, "SOCP"+formatNum(amps))
        returnValue(self.output_on)

    @setting(200, returns='s')
    def get_output_values(self, c):
        """
        Get the actual output voltage, current and mode (CC or CV).
        Returns the raw serial output from the power supply
        """
        ans = yield self.read(c, "GETD")
        try:
            self.volts = float(ans[0:4])/100.0
            self.amps = float(ans[4:8])/100.0
            if int(ans[8]) == 0:
                self.mode = "CV"
            else:
                self.mode = "CC"
        except Exception as e:
            print(e)
            print("invalid response from unit, unable to read output values")
        returnValue(ans)

    @setting(201, returns='v')
    def get_voltage(self, c):
        '''
        Get the actual output voltage
        '''
        yield self.get_output_values(c)
        returnValue(self.volts)

    @setting(202, returns='v')
    def get_current(self, c):
        '''
        Get the actual output current
        '''
        yield self.get_output_values(c)
        returnValue(self.amps)

    @setting(203, returns='s')
    def get_mode(self, c):
        '''
        Get the output mode (CC or CV).
        '''
        yield self.get_output_values(c)
        returnValue(self.mode)

    @setting(204, returns='v')
    def get_voltage_limit(self, c):
        """
        Get the output voltage limit
        """
        ans = yield self.read(c, "GOVP")
        try:
            returnValue(float(ans)/100.0)
        except Exception as e:
            print(e)
            print("invalid response from unit, unable to read voltage limit")
            returnValue(0.0)

    @setting(205, returns='v')
    def get_current_limit(self, c):
        """
        Get the output current limit
        """
        ans = yield self.read(c, "GOCP")
        try:
            returnValue(float(ans)/100.0)
        except Exception as e:
            print(e)
            print("invalid response from unit, unable to read current limit")
            returnValue(0.0)

__server__ = BK9103Server()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
