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
name = Power Supply Server
version = 1.0
description = Controller for Evaporator Valves and Relays

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
from labrad.devices import DeviceServer,DeviceWrapper
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet import reactor, defer
from labrad.types import Value
import time

TIMEOUT = Value(2,'s')
BAUD    = 9600
BYTESIZE = 8
STOPBITS = 1
PARITY = 0

class PowerSupplyWrapper(DeviceWrapper):

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
        #Set timeout to 0
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
        p=self.packet()
        p.read_line()
        ans=yield p.send()
        returnValue(ans.read_line)

    @inlineCallbacks
    def query(self, code):
        """ Write, then read. """
        p = self.packet()
        p.write_line(code)
        p.read_line()
        ans = yield p.send()
        returnValue(ans.read_line)


class PowerSupplyServer(DeviceServer):
    name             = 'Power_supply_server'
    deviceName       = 'TDK Power Supply'
    deviceWrapper    = PowerSupplyWrapper

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
        yield reg.cd(['', 'Servers', 'Power Supply', 'Links'], True)
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

    @setting(100,input = 's',returns = 's')
    def read(self,c, input):
        """This piece of equipment doesn't use carriage returns, so the serial port cannot recognize
        the end of a message. The timeout parameter is set to be 0 and this function
        loops until the message from the Power Supply has completely arrived or two seconds
        have elapsed. Also ensures that only one message is sent / being received at a time."""

        tzero = time.perf_counter()
        input = input + '$' + self.checksum(input) + '\r'
        #print 'Attempting to write: ' + input

        while True:
            if self.busy == False:
                #print('Initiating Query: ' + input)
                self.busy = True
                dev=self.selectedDevice(c)
                #print('Writing: ' + input)
                yield dev.write(input)
                ans = ''
                tzero = time.perf_counter()
                while True:
                    temp_ans = yield dev.read()
                    ans = ans + temp_ans
                    #TDK power supply randomly inserts unimportant characters. Following loop removes them
                    ans_final = ''
                    for char in ans:
                        if ord(char) > 31 and ord(char) < 128:
                            ans_final = ans_final + char

                    ans = ans_final
                    #print(ans)
                    #print(len(ans))
                    # try:
                    #     print('Printing 3rd to last char: ' + ans[-3])
                    # except:
                    #     pass
                    if len(ans)>3 and ans[-3] == '$':
                        #print('Checking stuff')
                        #print(ans[-2:])
                        #print(self.checksum(ans[:-3]))
                        if ans[-2:] == self.checksum(ans[:-3]):
                            #print('Returning: ' + ans)
                            self.busy = False
                            returnValue(ans[:-3])
                        else:
                            ans_num = ''
                            for char in ans:
                                ans_num = ans_num + str(ord(char)) + ','
                            print('Checksum error: ' + ans + ', Length: ' + str(len(ans)) + ', ASCII: ' +  ans_num)
                            self.busy = False
                            returnValue('ChecksumError')
                    elif (time.perf_counter() - tzero) > 5:
                        ans_num = ''
                        for char in ans:
                            ans_num = ans_num + str(ord(char)) + ','
                        #print('Reading timeout: ' + ans + ', Length: ' + str(len(ans)) + ', ASCII: ' +  ans_num)
                        self.busy = False
                        returnValue('Timeout')
                    yield self.sleep(0.005)
            elif (time.perf_counter() - tzero) > 2:
                #print('Connection timed out while writing')
                self.busy = False
                returnValue("Timeout")
            yield self.sleep(0.01)

    def sleep(self,secs):
        d = defer.Deferred()
        reactor.callLater(secs,d.callback,'Sleeping')
        return d

    def checksum(self,string):
        val = 0
        for sub in string:
            val = val + ord(sub)
        ans = str(hex(val%256)[-2:]).upper()
        return ans

    @setting(304,out = 's',returns='s')
    def switch(self,c,out):
        """Switches the output on or off."""
        ans = yield self.read(c,"OUT " + out)
        returnValue(ans)

    @setting(305,returns='s')
    def onoff(self,c):
        """Returns the output on/off status."""
        ans = yield self.read(c,"OUT?")
        returnValue(ans)

    @setting(306,returns='s')
    def iden(self,c):
        """Returns the power supply model identification."""
        ans = yield self.read(c,"IDN?")
        returnValue(ans)

    @setting(307,volts = 'v',returns='s')
    def volt_set(self,c,volts):
        """Sets the output voltage value in Volts."""
        print("Setting Voltage to " + str(volts))
        ans = yield self.read(c,"PV " + str(volts))
        returnValue(ans)

    @setting(308,returns='s')
    def volt_read(self,c):
        """Reads the output voltage setting."""
        ans = yield self.read(c,"PV?")
        returnValue(ans)

    @setting(309,returns='s')
    def act_volt(self,c):
        """Returns the actual voltage output."""
        ans = yield self.read(c,"MV?")
        returnValue(ans)

    @setting(310,current = 'v',returns='s')
    def cur_set(self,c,current):
        """Sets the output current value in Amperes."""
        ans = yield self.read(c,"PC " + str(current))
        returnValue(ans)

    @setting(311,returns='s')
    def cur_read(self,c):
        """Reads the output current setting."""
        ans = yield self.read(c,"PC?")
        returnValue(ans)

    @setting(312,returns='s')
    def act_cur(self,c):
        """Returns the actual current output."""
        ans = yield self.read(c,"MC?")
        returnValue(ans)

    @setting(313, adr='s', returns='s')
    def adr(self,c,adr):
        """Address to access the power supply."""
        ans = yield self.read(c,"ADR " + adr)
        returnValue(ans)

    @setting(314,returns='s')
    def clear(self,c):
        """Clear status."""
        ans = yield self.read(c,"CLS")
        returnValue(ans)

    @setting(315,rmt = 's', returns='s')
    def rmt_set(self,c,rmt):
        """Sets the power supply to local or remote mode. Send LOC for local mode, REM for remote, and LLO for local lockout."""
        ans = yield self.read(c,"RMT " +rmt)
        returnValue(ans)

    @setting(316,returns='s')
    def rmt_read(self,c):
        """Returns the remote mode setting."""
        ans = yield self.read(c,"RMT?")
        returnValue(ans)

    @setting(317,fld = 's',returns='s')
    def fld_set(self,c,fld):
        """Turns foldback protection on or off. Send 1 for on or 0 for off."""
        ans = yield self.read(c,"FLD " +fld)
        returnValue(ans)

    @setting(318,returns='s')
    def fld_read(self,c):
        """Returns the foldback protection status."""
        ans = yield self.read(c,"FLD?")
        returnValue(ans)

    @setting(319,ovp = 's',returns='s')
    def ovp_set(self,c,ovp):
        """Sets the over-voltage protection level."""
        ans = yield self.read(c,"OVP " + ovp)
        returnValue(ans)

    @setting(320,returns='s')
    def ovp_read(self,c):
        """Returns the over-voltage protection setting."""
        ans = yield self.read(c,"OVP?")
        returnValue(ans)

    @setting(321,fbd = 's',returns='s')
    def fbd_set(self,c,fbd):
        """Adds the inputted number of seconds to the fold back delay."""
        ans = yield self.read(c,"FBD "+fbd)
        returnValue(ans)

    @setting(322,returns='s')
    def fbd_read(self,c):
        """Reads the number of seconds added to the fold back delay."""
        ans = yield self.read(c,"FBD?")
        returnValue(ans)

    @setting(323,returns='s')
    def fbd_rst(self,c):
        """Resets the fold back delay to zero."""
        ans = yield self.read(c,"FBDRST")
        returnValue(ans)

    @setting(324,uvl = 's',returns='s')
    def uvl_set(self,c,uvl):
        """Sets the under voltage limit."""
        ans = yield self.read(c,"UVL "+ uvl)
        returnValue(ans)

    @setting(325,returns='s')
    def uvl_read(self,c):
        """Reads the under voltage limit."""
        ans = yield self.read(c,"UVL?")
        returnValue(ans)

    @setting(326,ast = 's',returns='s')
    def ast_set(self,c,ast):
        """Turns auto-restart mode on or off. Input 1 to turn on or 0 to turn off."""
        ans = yield self.read(c,"AST "+ast)
        returnValue(ans)

    @setting(327,returns='s')
    def ast_read(self,c):
        """Reads the auto restart status."""
        ans = yield self.read(c,"AST?")
        returnValue(ans)

    @setting(328,returns='s')
    def sav(self,c):
        """Saves the present settings."""
        ans = yield self.read(c,"SAV")
        returnValue(ans)

    @setting(329,returns='s')
    def rcl(self,c):
        """Recalls the setting from either the last power-down or the last SAV command."""
        ans = yield self.read(c,"RCL")
        returnValue(ans)

    @setting(330,returns='s')
    def mode(self,c):
        """Returns the power supply operation mode. If the supply is ON it will reutrn either CV or CC (constant voltage/current). If the supply is OFF it will return OFF."""
        ans = yield self.read(c,"MODE?")
        returnValue(ans)

__server__ = PowerSupplyServer()
if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
