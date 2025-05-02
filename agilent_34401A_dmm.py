# Copyright (C) 2007  Matthew Neeley
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
name = Agilent 34401A DMM
version = 1.4
description = LabRAD server for Agilent/HP 34401A digital multimeter, updated for Python 3.

[startup]
cmdline = %PYTHON% %FILE%
timeout = 50

[shutdown]
message = 987654321
timeout = 50
### END NODE INFO
"""

from labrad.server import setting
from labrad.gpib import GPIBManagedServer
from twisted.internet.defer import returnValue


class AgilentDMMServer(GPIBManagedServer):
    name = 'Agilent 34401A DMM'
    deviceName = 'HEWLETT-PACKARD 34420A'

    # Voltage -----------------------------------------------------------------
    @setting(10, AC='b', returns='v[]')
    def voltage(self, c, AC=False):
        """Measure voltage. Defaults to DC unless *AC* is True."""
        dev = self.selectedDevice(c)
        ans = yield dev.query('MEAS:VOLT:{}?'.format('AC' if AC else 'DC'))
        returnValue(float(ans))

    # Current ------------------------------------------------------------------
    @setting(11, AC='b', returns='v[]')
    def current(self, c, AC=False):
        """Measure current. Defaults to DC unless *AC* is True."""
        dev = self.selectedDevice(c)
        ans = yield dev.query('MEAS:CURR:{}?'.format('AC' if AC else 'DC'))
        returnValue(float(ans))

    # Resistance ---------------------------------------------------------------
    @setting(12, fourWire='b', returns='v[]')
    def resistance(self, c, fourWire=False):
        """Measure resistance. Defaults to 2‑wire unless *fourWire* is True."""
        dev = self.selectedDevice(c)
        mode = 'FRES' if fourWire else 'RES'
        ans = yield dev.query('MEAS:{}?'.format(mode))
        returnValue(float(ans))

    # Configuration ------------------------------------------------------------
    @setting(13, vRange='v[]', resolution='v[]')
    def configure_voltage(self, c, vRange=10, resolution=0.0001):
        """Configure voltage mode with the specified *vRange* and *resolution*."""
        dev = self.selectedDevice(c)
        yield dev.write('CONF:VOLT:DC {}, {}'.format(vRange, resolution))

    # Read ---------------------------------------------------------------------
    @setting(14, returns='v[]')
    def read_voltage(self, c):
        """Perform a READ? after the meter has been configured to voltage mode."""
        dev = self.selectedDevice(c)
        ans = yield dev.query('READ?')
        returnValue(float(ans))


__server__ = AgilentDMMServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
