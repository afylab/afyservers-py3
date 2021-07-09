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
name = RVC Server
version = 1.0
description = RVC Pressure Gauge and Leak Valve Controller

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
serial_server_name = (platform.node() + '_serial_server').replace('-', '_').lower()

global port_to_int, int_to_port
port_to_int = {'X1': 0, 'Y1': 1, 'X2': 2, 'Y2': 3}
int_to_port = ['X1', 'Y1', 'X2', 'Y2']

from labrad.server import setting
from labrad.devices import DeviceServer, DeviceWrapper
from twisted.internet.defer import inlineCallbacks, returnValue
from labrad.types import Value

from traceback import format_exc

TIMEOUT = Value(2, 's')
BAUD = 9600
BYTESIZE = 8
STOPBITS = 1
PARITY = 0


class RVCWrapper(DeviceWrapper):

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
        p.read()  # clear out the read buffer
        p.timeout(TIMEOUT)
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
    def query(self, code):
        """ Write, then read. """
        p = self.packet()
        p.write_line(code)
        p.read_line()
        ans = yield p.send()
        returnValue(ans.read_line)


class RVCServer(DeviceServer):
    name = 'RVC_Server'
    deviceName = 'RVC 300 Pressure Controller'
    deviceWrapper = RVCWrapper

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

    @inlineCallbacks
    def loadConfigInfo(self):
        reg = self.reg
        yield reg.cd(['', 'Servers', 'RVC 300', 'Links'], True)
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

    @setting(205, returns='s')
    def get_ver(self, c):
        """Queries the VER? command and returns the response. Usage is get_ver()"""
        dev = self.selectedDevice(c)
        yield dev.write("VER?\r\n")
        ans = yield dev.read()
        returnValue(ans)

    @setting(206, returns='s')
    def get_nom_prs(self, c):
        """Queries the PRS? command and returns the response. Response is nominal pressure. Usage is get_nom_prs()"""
        dev = self.selectedDevice(c)
        yield dev.write("PRS?\r\n")
        ans = yield dev.read()
        returnValue(ans)

    @setting(207, nom_prs='?', returns='s')
    def set_nom_prs(self, c, nom_prs):
        """Queries the PRS=x.xxEsxx command and returns the response. Input requires string
        of the form x.xxEsxx, where x are digits and s is either + or -. Usage is set_nom_prs('1.00E+01')"""
        dev = self.selectedDevice(c)
        nom_prs = "{:.2E}".format(float(nom_prs))
        yield dev.write("PRS=" + nom_prs + "\r\n")
        ans = yield dev.read()
        self.state = True
        returnValue(ans)

    @setting(208, returns='s')
    def get_nom_flo(self, c):
        """Queries the PRS? command and returns the response. Response is nominal pressure. Usage is get_nom_flo()"""
        dev = self.selectedDevice(c)
        yield dev.write("FLO?\r\n")
        ans = yield dev.read()
        returnValue(ans)

    @setting(209, nom_flo='s', returns='s')
    def set_nom_flo(self, c, nom_flo):
        """Queries the FLO=xxx.x command and returns the response. Input requires string
        of the form xxx.x, where x are digits. This sets flow to a percentage. Usage is set_nom_flo('012.5')"""
        dev = self.selectedDevice(c)
        yield dev.write("FLO=" + nom_flo + "\r\n")
        ans = yield dev.read()
        self.state = True
        returnValue(ans)

    @setting(210, returns='*s')
    def close_valve(self, c):
        """Queries the PRS=5.01E-09 and FLO=0000.0 commands and returns the responses. Sets nominal pressure to minimum and
        sets nominal flow to 0, closing the valve in either pressure or flow mode. Usage close_valve()"""
        dev = self.selectedDevice(c)
        yield dev.write("FLO=000.0\r\n")
        ans1 = yield dev.read()
        yield dev.write("PRS=5.01E-09\r\n")
        ans2 = yield dev.read()
        self.state = False
        returnValue([ans1, ans2])

    @setting(211, returns='s')
    def get_mode(self, c):
        """Queries the MOD? command and returns the response. Usage get_mode()"""
        dev = self.selectedDevice(c)
        yield dev.write("MOD?\r\n")
        ans = yield dev.read()
        returnValue(ans)

    @setting(212, returns='s')
    def set_mode_prs(self, c):
        """Queries the MOD=P command and returns the response. Usage set_mode_prs()"""
        dev = self.selectedDevice(c)
        yield dev.write("MOD=P\r\n")
        ans = yield dev.read()
        returnValue(ans)

    @setting(213, returns='s')
    def set_mode_flo(self, c):
        """Queries the MOD=F command and returns the response. Usage set_mode_flo()"""
        dev = self.selectedDevice(c)
        yield dev.write("MOD=F\r\n")
        ans = yield dev.read()
        returnValue(ans)

    @setting(214, returns='s')
    def keys_lock(self, c):
        """Queries the TAS=D command and returns the response. Disables usage of keys on RVC screen. Usage keys_lock(
        ) """
        dev = self.selectedDevice(c)
        yield dev.write("TAS=D\r\n")
        ans = yield dev.read()
        returnValue(ans)

    @setting(215, returns='s')
    def keys_enable(self, c):
        """Queries the TAS=E command and returns the response. Enables usage of keys on RVC screen. Usage
        keys_enable() """
        dev = self.selectedDevice(c)
        yield dev.write("TAS=E\r\n")
        ans = yield dev.read()
        returnValue(ans)

    @setting(216, returns='s')
    def get_prs(self, c):
        """Queries the PRI? command and returns the response. Gets current pressure. Usage get_prs()"""
        dev = self.selectedDevice(c)
        yield dev.write("PRI?\r\n")
        ans = yield dev.read()
        returnValue(ans)

    @setting(316, returns='?')
    def get_pressure_mbar(self, c):
        """
        Queries the PRI? command and returns the response. Gets current pressure
        and returns a floating point value of the pressure in mbar.
        """
        dev = self.selectedDevice(c)
        yield dev.write("PRI?\r\n")
        ans = yield dev.read()
        ans = ans.replace("PRI=", "").replace("mbar", "")
        try:
            #returnValue(float(ans))
            return float(ans)
        except:
            print(format_exc())


    @setting(217, returns='s')
    def get_unit(self, c):
        """Queries the UNT? command and returns the response. Gets measurement unit. Usage get_unit()"""
        dev = self.selectedDevice(c)
        yield dev.write("UNT?\r\n")
        ans = yield dev.read()
        returnValue(ans)

    @setting(218, returns='s')
    def get_prs_sensor(self, c):
        """Queries the RTP? command and returns the response. Gets pressure sensor name. Usage get_prs_sensor()"""
        dev = self.selectedDevice(c)
        yield dev.write("PRS?\r\n")
        ans = yield dev.read()
        returnValue(ans)

    @setting(219, returns='s')
    def get_valve_type(self, c):
        """Queries the VEN? command and returns the response. Gets valve type name. Usage get_valve_type()"""
        dev = self.selectedDevice(c)
        yield dev.write("VEN?\r\n")
        ans = yield dev.read()
        returnValue(ans)

    @setting(220, auto='s', returns='s')
    def select_auto_controller(self, c, auto):
        """Queries the RAS=xx command and returns the response. auto should be a string of two positive integers.
           This sets the PID to automatic paramter where auto = '01' is the slowest response, and auto = '99' is
           the fastest. An example query would be RAS=05. Usage is set_auto_controller('05')."""
        dev = self.selectedDevice(c)
        yield dev.write("RAS=" + auto + "\r\n")
        ans = yield dev.read()
        returnValue(ans)

    @setting(221, auto='s', returns='s')
    def select_PID(self, c, auto):
        """Queries the RAS=_0 command and returns the response. auto should be a string of two positive integers.
            This sets the PID to automatic paramter where auto = '01' is the slowest response, and auto = '99' is
            the fastest. An example query would be RAS=05. Usage is set_auto_controller('05')."""
        dev = self.selectedDevice(c)
        yield dev.write("RAS=" + auto + "\r\n")
        ans = yield dev.read()
        returnValue(ans)

    @setting(222, Kp='s', returns='s')
    def set_Kp(self, c, Kp):
        """Queries the RSP=xxx.x command and returns the response. Kp should be a string of xxx.x, where x is an integer.
            This sets the PID proportional term to the provided input value. Accepts values 0.1 through 100.0."""

        dev = self.selectedDevice(c)
        yield dev.write("RSP=" + Kp + "\r\n")
        ans = yield dev.read()
        returnValue(ans)

    @setting(223, Tv='s', returns='s')
    def set_Tv(self, c, Tv):
        """Queries the RSD=xxxx.x command and returns the response. Tv should be a string of xxxx.x, where x is an integer.
            This sets the PID derivative time Tv to the provided input value. Accepts values 0.0 through 3600.0."""

        dev = self.selectedDevice(c)
        yield dev.write("RSD=" + Tv + "\r\n")
        ans = yield dev.read()
        returnValue(ans)

    @setting(224, on='s', returns='s')
    def set_auto_reset(self, c, on):
        """Queries the RAR=x command and returns the response. on should be a string of either 0 or 1, where 0 is off and 1
        is on. This turns the auto reset function off and on."""

        dev = self.selectedDevice(c)
        yield dev.write("RAR=" + on + "\r\n")
        ans = yield dev.read()
        returnValue(ans)

    @setting(225, returns='s')
    def get_PID_setting(self, c):
        """Queries the RAS? command and returns the response. Returns the PID setting number. 0 corresponds to manual PID
        parameter entry, 1-99 is slow to fast automatic settings."""

        dev = self.selectedDevice(c)
        yield dev.write("RAS?\r\n")
        ans = yield dev.read()
        returnValue(ans)

    @setting(226, returns='s')
    def get_Kp(self, c):
        """Queries the RSP? command and returns the response, which is the manual PID proportional gain."""

        dev = self.selectedDevice(c)
        yield dev.write("RSP?\r\n")
        ans = yield dev.read()
        returnValue(ans)

    @setting(227, returns='s')
    def get_Tn(self, c):
        """Queries the RSI? command and returns the response, which is the manual PID reset time."""

        dev = self.selectedDevice(c)
        yield dev.write("RSI?\r\n")
        ans = yield dev.read()
        returnValue(ans)

    @setting(228, returns='s')
    def get_Tv(self, c):
        """Queries the RSD? command and returns the response, which is the manual PID derivative time."""

        dev = self.selectedDevice(c)
        yield dev.write("RSD?\r\n")
        ans = yield dev.read()
        returnValue(ans)

    @setting(229, returns='s')
    def get_auto_reset(self, c):
        """Queries the RAR? command and returns the response. RAR=0 corresponds to auto reset function is off
            whereas RAR=1 corresponds to it being on."""

        dev = self.selectedDevice(c)
        yield dev.write("RAR?\r\n")
        ans = yield dev.read()
        returnValue(ans)

    @setting(230, returns='s')
    def get_deviation(self, c):
        """Queries the RVA? command and returns the response. Returns the deviation."""

        dev = self.selectedDevice(c)
        yield dev.write("RVA?\r\n")
        ans = yield dev.read()
        returnValue(ans)

    @setting(231, returns='s')
    def get_P_comp(self, c):
        """Queries the RVP? command and returns the response. Returns the P component."""

        dev = self.selectedDevice(c)
        yield dev.write("RVA?\r\n")
        ans = yield dev.read()
        returnValue(ans)

    @setting(232, returns='s')
    def get_I_comp(self, c):
        """Queries the RVI? command and returns the response. Returns the I component."""

        dev = self.selectedDevice(c)
        yield dev.write("RVI?\r\n")
        ans = yield dev.read()
        returnValue(ans)

    @setting(233, returns='s')
    def get_D_comp(self, c):
        """Queries the RVD? command and returns the response. Returns the D component."""

        dev = self.selectedDevice(c)
        yield dev.write("RVD?\r\n")
        ans = yield dev.read()
        returnValue(ans)

    @setting(234, returns='s')
    def get_manipulating_variable(self, c):
        """Queries the RVO? command and returns the response. Returns the manipulating variable."""
        dev = self.selectedDevice(c)
        yield dev.write("RVO?\r\n")
        ans = yield dev.read()
        returnValue(ans)

    @setting(235, returns='b')
    def returnstate(self, c):
        return self.state


__server__ = RVCServer()
if __name__ == '__main__':
    from labrad import util

    util.runServer(__server__)
