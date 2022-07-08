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
#
# midas.py - Communication server for the MIDAS, based on
#            gpib_server.py.
#

"""
### BEGIN NODE INFO
[info]
name = midas
version = 1.0
description = 
[startup]
cmdline = %PYTHON% %FILE%
timeout = 20
[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""

from labrad.devices import DeviceServer, DeviceWrapper
from labrad.server import setting
from gpib_server import GPIBBusServer
from twisted.internet.defer import inlineCallbacks, returnValue
import struct
import numpy as np
from time import sleep
from warnings import warn

HEADER = 0xFADCFADCFADCFADC

class CmdNums():
	"""
	Represents the 'command' sent to the midas_server program.
	A matching enum is maintained within the c++.
	"""
	SET_CHANNEL_FREQUENCY = 1
	SET_NUM_RASTER_POINTS = 2
	SET_RASTER_RATE = 3
	SET_AVG_NUM_SWEEPS_1D = 4
	SET_NUM_SWEEPS_2D = 5
	SET_OFDM_MUX = 6
	SET_OFDM_MASK_REG = 7
	CAPTURE_1D_TRACE = 15
	SET_SW_MODE = 16
	SW_TRIGGER_CAPTURE = 17
	CAPTURE_2D_TRACE = 18
	SET_RASTER_HZ = 19
	SET_CLK_MODE = 20
	RESET_UNIT = 21
	SET_FILTER_MODE = 22
	SET_ATTEN_VALUE = 23
	SET_CHAN_ATTEN = 24
	RT_CAL_ENABLE = 25
	RT_CAL_SW_LATENCY = 26
	RT_CAL_DB_LVL = 27
	POINT_AVG_NUM = 28
	DEBUG_WRITE_REG = 29
	MANUAL_ARM_TRIGGER = 30
	FLUSH_FIFO_GET_DATA = 31
	RESET_FIFOS = 32
	GIVE_UP_MISSED_TRIG = 33
	SEND_FMC160_DATA = 34
	REPEAT_OFFSET = 35
	REPEAT_EXT_TRIG = 36
	REPEAT_ARM = 37
	REPEAT_BURST_SIZE = 38
	GET_CHANNEL_FREQUENCY = 100
	GET_NUM_RASTER_POINTS = 101
	GET_AVG_NUM_SWEEPS_1D = 102
	GET_NUM_SWEEPS_2D = 103
	GET_SW_MODE = 104
	GET_RASTER_HZ = 105
	GET_CLK_MODE = 106
	GET_FILTER_MODE = 107
	GET_FINAL_ATTEN = 108
	GET_CHANNEL_ATTEN = 109
	GET_RT_LATENCY = 110
	GET_RT_NOISE_FIR = 111
	GET_POINT_AVG_NUM = 112
	GET_MISSED_TRIG = 113
	DEBUG_READ_REG = 114
	GET_VERSION_NUM = 115

'''class MIDASWrapper(DeviceWrapper):
	@inlineCallbacks
	def send_msg(self, cmd, data1=0, data2=0):
		"""
		Send a protocol command to the server using the visa.
		data1 and data2 are optional and will default to
		0. The protocol message structure consists of 4 64bit numbers.
		"""
		raw = struct.pack("4Q", HEADER, cmd, data1, data2)
		yield self.write_raw(raw)

	@inlineCallbacks
	def read_parameter(self):
		"""
		The "GET_" protocol commands return a single 64-bit reply
		containing the query result. This function parses the
		reply and returns the result.
		"""
		size = struct.calcsize('Q')
		raw = yield self.read_bytes(size)
		data = struct.unpack('Q', raw)
		returnValue(data[0])

	@inlineCallbacks
	def read_trace(self):
		"""
		The "SOFT_TRIGGER_1D_TRACE" and the "CAPTURE_" protocol
		commands return an array of 32765 32-bit int replies
		representing the 2048 complex measurements on the 8
		channels. This function parses the replies and returns
		the results.
		"""
		sweep_size = 2048 * 2 * 8
		full_len = struct.calcsize("%d")
		recv_bytes = 0
		message = bytes()
		while recv_bytes < full_len:
			raw = self.read_bytes(full_len - recv_bytes)
			recv_bytes += len(raw)
			message += raw

		cint64 = np.dtype([("re", np.int32), ("im", np.int32)])
		reply = np.frombuffer(message, dtype=cint64)
		#turn into complex double
		reply = reply.view(np.int32).astype(np.float64).view(np.complex128)
		returnValue(reply)'''

class MIDASServer(GPIBBusServer):
	"""Provide access to the MIDAS using the gpib_server"""
	name = "MIDAS"

	#@inlineCallbacks
	#def initServer(self):
		#print "loading config info...",
		#self.reg = self.client.registry()
		#yield self.loadConfigInfo()
		#print("done")
		#yield super().initServer()

	connected = False
	num_sweeps_2d = 1

	traces = np.zeros([8, 2048], np.complex128)

	@inlineCallbacks
	def send_msg(self, c, cmd, data1=0, data2=0):
		"""
		Send a protocol command to the server using the visa.
		data1 and data2 are optional and will default to
		0. The protocol message structure consists of 4 64bit numbers.
		"""
		raw = struct.pack("4Q", HEADER, cmd, data1, data2)
		yield self.write_raw(c, raw)

	@inlineCallbacks
	def read_parameter(self, c):
		"""
		The "GET_" protocol commands return a single 64-bit reply
		containing the query result. This function parses the
		reply and returns the result.
		"""
		size = struct.calcsize('Q')
		raw = yield self.read_bytes(c, size)
		data = struct.unpack('Q', raw)
		returnValue(data[0])

	@inlineCallbacks
	def read_trace(self, c):
		"""
		The "SW_TRIGGER_CAPTURE" and the "CAPTURE_" protocol
		commands return an array of 32768 32-bit int replies
		representing the 2048 complex measurements on the 8
		channels. This function parses the entirety of the
		replies and returns the results.
		"""
		sweep_size = 2048 * 2 * 8
		full_len = struct.calcsize("{}i".format(sweep_size))
		recv_bytes = 0
		message = bytes()
		while recv_bytes < full_len:
			raw = yield self.read_bytes(c, full_len - recv_bytes)
			recv_bytes += len(raw)
			message += raw

		#print(message)
		cint64 = np.dtype([("re", np.int32), ("im", np.int32)])
		reply = np.frombuffer(message, dtype=cint64)
		#print(reply)
		#turn into complex double
		reply = reply.view(np.int32).astype(np.float64).view(np.complex128)
		print(reply)
		returnValue(reply)

	@setting(2000, midas_ip='s', midas_port='s', n_tries='w', returns='')
	def midas_connect(self, c, midas_ip="169.231.175.92", midas_port="27016", n_tries=5, separation=1):
		"""
		Make attempts to connect to the MIDAS until commands
		can be successfully sent.

		If unspecified, make 5 attempts separated by 1s at ip
		169.231.175.92 and port 27016.

		Parameters:
		midas_ip, midas_port, n_tries, separation
		"""
		midas_address = "TCPIP::%s::%s::SOCKET"%(midas_ip, midas_port)
		if midas_address in self.list_devices(c):
			self.address(c, midas_address)
			print("MIDAS already connected.")
			return
		i = 0
		while i < n_tries:
			try:
				self.add_gpib_device(c, midas_address, '', '')
				#print("add passed")
				self.address(c, midas_address)
				#print("address passed")
				yield self.send_msg(c, CmdNums.GET_VERSION_NUM)
				#print("send passed")
				ver = yield self.read_parameter(c)
				#print("read passed")
				major = ver >> 8
				minor = ver & 15
				i = n_tries
				self.connected = True
			except:
				print(("Connection attempt failed(%d/%d)" % (i+1, n_tries)))
				i += 1
				#if midas_address in self.list_devices(c):
				#	self.close_connection(c, midas_address)
				if i != n_tries:
					sleep(separation)
		if not self.connected:
			print("Unable to reach the MIDAS, please check the connections and try again.")
		else:
			print(("Connection successful, MIDAS version %d.%d" % (major, minor)))

	@setting(2001, midas_ip='s', midas_port='s', returns='')
	def midas_close(self, c, midas_ip="169.231.175.92", midas_port="27016"):
		"""
		Close the connection to the MIDAS, and delete
		it from the GPIB device list.
		"""
		if not self.connected:
			print("MIDAS already disconnected.")
			return
		self.close_connection(c)
		self.connected = False
		print("MIDAS connection closed.")

	@setting(2002, returns='b')
	def midas_status(self, c):
		"""
		Return a boolean corresponding to the MIDAS
		connection status.
		"""
		return self.connected

	@setting(2100, chan = 'w', phase_offset='v', returns='*c')
	def get_trace_i(self, c, chan=None, phase_offset=0):
		"""
		Calculate and return the I measurements of an individual
		channel from the previous capture.

		If unspecified, assume 0 phase offset.

		Parameters:
		channel, phase_offset (rad)
		"""
		rot = self.traces[chan-1] * (1*np.cos(-phase_offset) + 1j*np.sin(-phase_offset))
		return np.real(rot)

	@setting(2101, chan='w', phase_offset='v', returns='*c')
	def get_trace_q(self, c, chan=None, phase_offset=0):
		"""
		Calculate and return the Q measurements of an individual
		channel from the previous capture.

		If unspecified, assume 0 phase offset.

		Parameters:
		channel, phase_offset (rad)
		"""
		rot = self.traces[chan-1] * (1*np.cos(-phase_offset) + 1j*np.sin(-phase_offset))
		return np.imag(rot)

	@setting(2102, chan='w', returns='*c')
	def get_trace_mag(self, c, chan=None):
		"""
		Calculate and return the magnitude measurements of an
		individual channel from the previous capture.

		Parameter:
		channel
		"""
		return np.abs(self.traces[chan-1])

	@setting(2103, chan='w', phase_offset='v', returns='*c')
	def get_trace_phase(self, c, chan, phase_offset=0):
		"""
		Calculate and return the phase measurements of an
		individual channel from the previous capture.

		If unspecified, assume 0 phase offset.

		Parameters:
		channel, phase_offset (rad)
		"""
		phases = np.angle(self.traces[chan-1]) - phase_offset
		phases = (phases+np.pi)%(2*np.pi) - np.pi
		return phases

	@setting(2150, chan='w', returns='*c')
	def get_trace(self, c, chan):
		"""
		Get the trace of an individual channel in the previous
		capture.

		Parameter:
		channel
		"""
		return self.traces[chan-1]


	@setting(1001, chan='w', freq='v', returns='s')
	def set_chan_freq(self, c, chan, freq):
		"""
		Set the frequency on a MIDAS channel.

		Parameters:
		channel, frequency
		"""
		if not self.connected:
			returnValue("Error: MIDAS not connected.")
			return
		if chan < 1 or chan > 8:
			returnValue("Error: invalid channel number, must be 1-8.")
			return
		yield self.send_msg(c, CmdNums.SET_CHANNEL_FREQUENCY, int(chan), int(freq))
		returnValue("MIDAS channel %d set to frequency %e Hz." % (chan, freq))

	@setting(1002, pts='w', returns='s')
	def set_num_raster_points(self, c, pts):
		"""
		Set the number of raster points. In raster mode this value
		should be set to the number of required raster points.

		Parameter:
		points
		"""
		if not self.connected:
			returnValue("Error: MIDAS not connected.")
			return
		if pts < 1 or pts > 2048:
			returnValue("Error: raster point out of range, must be 1-2048.")
			return
		yield self.send_msg(c, CmdNums.SET_NUM_RASTER_POINTS, pts)
		returnValue("Number of raster points set to %d" % pts)

	@setting(1004, num='w', returns='s')
	def set_avg_num_sweeps_1d(self, c, num):
		"""
		Set the number of traces averaged together during a capture

		Parameter:
		number
		"""
		if not self.connected:
			returnValue("Error: MIDAS not connected.")
			return
		if num < 1 or num > 100000:
			returnValue("Error: number out of range, must be between 1-100,000")
			return
		yield self.send_msg(c, CmdNums.SET_AVG_NUM_SWEEPS_1D, num)
		returnValue("Number of traces to be averaged in a capture set to %d." % num)

	@setting(1005, num='w', returns='s')
	def set_num_sweeps_2d(self, c, num):
		"""
		Set the number of captures performed by the
		"capture_2d_trace" function.

		Parameter:
		number
		"""
		if not self.connected:
			returnValue("Error: MIDAS not connected.")
			return
		if num < 1 or num > 100000:
			returnValue("Error: number out of range, must be 1-100,000")
			return
		yield self.send_msg(c, CmdNums.SET_NUM_SWEEPS_2D, num)
		self.num_sweeps_2d = num
		returnValue("Number of captures performed by \"capture_2d_trace\" set to %d" % num)

	@setting(1015, returns="*2c")
	def capture_1d_trace(self, c):
		"""
		Perform a capture using the hardware trigger.
		"""
		if not self.connected:
			returnValue("Error: MIDAS not connected.")
			return
		yield self.send_msg(c, CmdNums.CAPTURE_1D_TRACE)
		ans = yield self.read_trace(c)
		if ans is not None:
			result = ans.reshape(2048, 8).T
		else:
			result = np.zeros([8, 2048], dtype=np.complex128)

		self.traces = result    #Store traces for later calculations
		returnValue(result)

	@setting(1016, mode='w', returns='s')
	def set_sw_mode(self, c, mode):
		"""
		Set the MIDAS software trigger mode.

		Modes:
		Raster = 0 (default), Single Shot = 1,
		Single Point = 2

		Raster mode will spread samples out over the period set in
		the "set_raster_hz" function.
		Single shot mode will return 2048 samples directly after
		the trigger event.
		Single point mode will result in a single point being placed
		in the FIFO per trigger. A variable number of samples can be
		averaged together to create this single point.

		Parameter:
		mode
		"""
		if not self.connected:
			returnValue("Error: MIDAS not connected.")
			return
		if mode != 0 or mode != 1 or mode != 2:
			returnValue("Error: invalid mode, must be 0, 1, or 2.")
			return
		yield self.send_msg(c, CmdNums.SET_SW_MODE, mode)
		returnValue("MIDAS software set to mode %d." % mode)

	@setting(1017, returns="*2c")
	def sw_trigger_capture(self, c):
		"""
		Perform a capture using the software trigger.
		(soft_trigger_1d_trace in QCoDeS)
		"""
		if not self.connected:
			returnValue("Error: MIDAS not connected.")
			return
		yield self.send_msg(c, CmdNums.SW_TRIGGER_CAPTURE)
		ans = yield self.read_trace(c)
		if ans is not None:
			result = ans.reshape(2048, 8).T
		else:
			result = np.zeros([8, 2048], dtype=np.complex128)

		self.traces = result    #Store traces for later calculations
		returnValue(result)

	@setting(1018, returns="*3c")
	def capture_2d_trace(self, c):
		"""
		Perform a number of captures set by the
		"set_num_sweeps_2d" function.
		"""
		if not self.connected:
			returnValue("Error: MIDAS not connected.")
			return
		yield self.send_msg(c, CmdNums.CAPTURE_2D_TRACE)

		results = np.zeros([self.num_sweeps_2d, 8, 2048], dtype=np.complex128)
		for i in range(0, self.num_sweeps_2d):
			try:
				ans = yield self.read_trace(c)
				if reply is not None:
					tmp = ans.reshape(2048, 8).T
				else:
					tmp = np.zeros([8, 2048], dtype=np.complex128)
				results[i] = tmp
			except KeyboardInterrupt:
				left = self.num_sweeps_2d - i - 1
				print(("waiting out %d traces" % left))
				for _ in range(left):
					self.read_trace(c)
				raise
			except VisaIOError:
				#The capture timed out waiting for a trigger
				warn("Timeout ocurred waiting for trigger")
				#Give up and return the data that we have so far
				break

		#Read the number of missed triggers out
		yield self.send_msg(c, CmdNums.GET_MISSED_TRIG)
		missed = yield self.read_parameter(c)
		if missed > 0:
			warn("Missed %d triggers during capture."
				"Consider reducing trigger rate." % missed)

		returnValue(results)


	@setting(1019, rate='w', returns='s')
	def set_raster_hz(self, c, rate):
		"""
		Set the MIDAS raster rate in Hz.

		Parameter:
		rate
		"""
		if not self.connected:
			returnValue("Error: MIDAS not connected.")
			return
		yield self.send_msg(c, CmdNums.SET_RASTER_HZ, rate)
		returnValue("MIDAS raster rate set to %e Hz." % rate)

	@setting(1020, mode='i', returns='s')
	def set_clk_mode(self, c, mode):
		"""
		Set the clock mode on the MIDAS, toggling the ability to
		use a 10 MHz external reference.

		Modes:
		Internal Clock = 0 (default),
		External Clock Enable = 2

		Parameter:
		mode
		"""
		if not self.connected:
			returnValue("Error: MIDAS not connected.")
			return
		if mode != 0 and mode != 2:
			returnValue("Error: invalid mode, must be 0 or 2.")
			return
		yield self.send_msg(c, CmdNums.SET_CLK_MODE, mode)
		returnValue("MIDAS clock mode set to %d." % mode)

	@setting(1021, returns='s')
	def reset_unit(self, c):
		"""
		Reinitialize the unit. This may take a few minutes.
		"""
		if not self.connected:
			returnValue("Error: MIDAS not connected.")
			return
		yield self.send_msg(c, CmdNums.RESET_UNIT)
		returnValue("Reinitializing the unit, this may take a few minutes.")

	@setting(1022, mode='i', returns='s')
	def set_filter_mode(self, c, mode):
		"""
		Set the MIDAS filter mode.

		Modes:
		5kHz = 0, 10kHz = 1, 30kHz = 2, 100kHz = 3,
		1MHz = 4, 1.7MHz = 5

		Parameter:
		mode
		"""
		if not self.connected:
			returnValue("Error: MIDAS not connected.")
			return
		if mode != 0 and mode != 1 and mode != 2 and mode != 3 and mode != 4 and mode != 5:
			returnValue("Error: invalid mode, must be 0, 1, 2, 3, 4, or 5.")
			return
		yield self.send_msg(c, CmdNums.SET_FILTER_MODE, mode)
		returnValue("MIDAS filter mode set to %d." % mode)

	@setting(1023, atten='v', returns='s')
	def set_final_atten(self, c, atten):
		"""
		Set the attenuation of the overall MIDAS DAC output power in dB.

		Parameter:
		attenuation
		"""
		if not self.connected:
			returnValue("Error: MIDAS not connected.")
			return
		if atten > 0:
			returnValue("Error: dB level out of range, must be <= 0.0")
			return
		power = int(round(10**(atten/20) * 0xFFF))
		yield self.send_msg(c, CmdNums.SET_ATTEN_VALUE, power)
		returnValue("MIDAS DAC overall attenuation set to %f dB." % atten)

	@setting(1024, chan='w', atten='v', returns='s')
	def set_chan_atten(self, c, chan, atten):
		"""
		Set the attenuation of an individual MIDAS channel output power
		in dB.

		Parameters:
		channel, attenuation
		"""
		if not self.connected:
			returnValue("Error: MIDAS not connected.")
			return
		if atten > 0:
			returnValue("Error: dB level out of range, must be <= 0.0")
			return
		power = int(round(10**(atten/20) * 0xFFF))
		yield self.send_msg(c, CmdNums.SET_CHAN_ATTEN, chan, power)
		returnValue("MIDAS channel %d attenuation set to %f dB" % (chan, atten))

	@setting(1025, returns='s')
	def calibrate_latency(self, c):
		"""
		Trigger the round trip latency calibration operation in the FPGA.
		The calculated value will be used internally to delay the trigger.
		"""
		if not self.connected:
			returnValue("Error: MIDAS not connected.")
			return
		yield self.send_msg(c, CmdNums.RT_CAL_ENABLE)
		returnValue("MIDAS trigger latency calibration started.")

	@setting(1026, pts = 'w', returns='s')
	def rt_cal_sw_latency(self, c, pts):
		"""
		Set the number of points to delay the trigger by inside the
		FPGA. This overwrites the value calculated by the
		"calibrate_latency" function.

		Parameter:
		point
		"""
		if not self.connected:
			returnValue("Error: MIDAS not connected.")
			return
		yield self.send_msg(CmdNums.RT_CAL_SW_LATENCY, pts)
		returnValue("MIDAS trigger latency set to %d points" % pts)

	@setting(1027, returns='s')
	def rt_cal_db_lvl(self, c):
		"""
		Set the signal level above the calculated noise floor where
		the latency calibration will detect a signal.
		"""
		if not self.connected:
			returnValue("Error: MIDAS not connected.")
			return
		yield self.send_msg(CmdNums.RT_CAL_DB_LVL)
		returnValue("Signal level for MIDAS latency calibration set.")

	@setting(1028, num='w', returns='s')
	def set_point_avg_num(self, c, num):
		"""
		Set the number of samples to average together per trigger
		in single points mode. This number needs to be a power of
		two, and allows the effective "integration time" to be
		changed.

		Parameter:
		number
		"""
		if not self.connected:
			returnValue("Error: MIDAS not connected.")
			return
		if np.log2(num) != round(np.log2(num)) or np.log2(num) < 0 or np.log2(num) > 12:
			returnValue("Error: invalid number of points, must be power of 2 from 1 to 4096")
			return
		yield self.send_msg(CmdNums.POINT_AVG_NUM, num)
		returnValue("Number of samples to average together per trigger in single point mode set to %d" % pts)

	@setting(1030, returns='s')
	def manual_arm_trigger(self, c):
		"""
		Enable the trigger manually. Time domain measurements can
		be done by
		manual_arm_trigger() -> AWG -> flush_fifo_get_data()
		"""
		if not self.connected:
			returnValue("Error: MIDAS not connected.")
			return
		yield self.send_msg(c, CmdNums.MANUAL_ARM_TRIGGER)
		returnValue("MIDAS trigger enabled.")

	@setting(1031, returns='*2c')
	def flush_fifo_get_data(self, c):
		"""
		Flush out buffer and return 2048 data points per channel.
		This function disarms the trigger internally. Time domain
		measurements can be done by
		manual_arm_trigger() -> AWG -> flush_fifo_get_data().
		"""
		if not self.connected:
			returnValue("Error: MIDAS not connected.")
			return
		yield self.send_msg(c, CmdNums.FLUSH_FIFO_GET_DATA)
		ans = yield self.read_trace(c)
		if ans is not None:
			result = ans.reshape(2048, 8).T
		else:
			result = np.zeros([8, 2048], dtype=np.complex128)

		self.traces = result    #Store traces for later calculations
		returnValue(result)

	@setting(1100, chan='w', returns='v')
	def get_chan_freq(self, c, chan):
		"""
		Get the frequency on a MIDAS channel.

		Parameter:
		channel
		"""
		if not self.connected:
			returnValue("Error: MIDAS not connected.")
			return
		if chan < 1 or chan > 8:
			returnValue("Error: invalid channel number, must be 1-8.")
			return
		yield self.send_msg(c, CmdNums.GET_CHANNEL_FREQUENCY, chan)
		ans = yield self.read_parameter(c)
		returnValue(ans)

	@setting(1101, returns='w')
	def get_num_raster_points(self, c):
		"""
		Get the number of raster points in raster mode.
		"""
		if not self.connected:
			returnValue("Error: MIDAS not connected.")
			return
		yield self.send_msg(c, CmdNums.GET_NUM_RASTER_POINTS)
		ans = yield self.read_parameter(c)
		returnValue(ans)

	@setting(1102, returns='w')
	def get_avg_num_sweeps_1d(self, c):
		"""
		Get the number of traces averaged together during a capture.
		"""
		if not self.connected:
			returnValue("Error: MIDAS not connected.")
			return
		yield self.send_msg(c, CmdNums.GET_AVG_NUM_SWEEPS_1D)
		ans = yield self.read_parameter(c)
		returnValue(ans)


	@setting(1103, returns='v')
	def get_num_sweeps_2d(self, c):
		"""
		Get the number of captures performed by "capture_2d_trace".
		"""
		if not self.connected:
			returnValue("Error: MIDAS not connected.")
			return
		yield self.send_msg(c, Cmd.GET_NUM_SWEEPS_2D)
		ans = yield self.read_parameter(c)
		returnValue(ans)

	@setting(1104, returns='w')
	def get_sw_mode(self, c):
		"""
		Get the MIDAS software trigger mode.

		Modes:
		Distributed = 0 (default), Single Shot = 1,
		Single Point = 2

		Raster mode will spread samples out over the period set in
		the "set_raster_hz" function.
		Single shot mode will return 2048 samples directly after
		the trigger event.
		Single point mode will result in a single point being placed
		in the FIFO per trigger. A variable number of samples can be
		averaged together to create this single point.
		"""
		if not self.connected:
			returnValue("Error: MIDAS not connected.")
			return
		yield self.send_msg(c, CmdNums.GET_SW_MODE)
		ans = yield self.read_parameter(c)
		returnValue(ans)

	@setting(1105, returns='v')
	def get_raster_hz(self, c):
		"""
		Get the MIDAS raster rate in Hz.
		"""
		if not self.connected:
			returnValue("Error: MIDAS not connected.")
			return
		yield self.send_msg(c, CmdNums.GET_RASTER_HZ)
		ans = yield self.read_parameter(c)
		returnValue(ans)

	@setting(1106, returns='w')
	def get_clk_mode(self, c):
		"""
		Get the clock mode on the MIDAS.

		Modes:
		Internal Clock = 0 (default),
		External Clock Enable = 2
		"""
		if not self.connected:
			returnValue("Error: MIDAS not connected.")
			return
		yield self.send_msg(c, CmdNums.GET_CLK_MODE)
		ans = yield self.read_parameter(c)
		returnValue(ans)

	@setting(1107, returns='w')
	def get_filter_mode(self, c):
		"""
		Get the MIDAS filter mode.

		Modes:
		5kHz = 0, 10kHz = 1, 30kHz = 2, 100kHz = 3,
		1MHz = 4, 1.7MHz = 5
		"""
		if not self.connected:
			returnValue("Error: MIDAS not connected.")
			return
		yield self.send_msg(c, CmdNums.GET_FILTER_MODE)
		ans = yield self.read_parameter(c)
		returnValue(ans)

	@setting(1108, returns='v')
	def get_final_atten(self, c):
		"""
		Get the overall attenuation of the MIDAS DAC in dB.
		"""
		if not self.connected:
			returnValue("Error: MIDAS not connected.")
			return
		yield self.send_msg(c, CmdNums.GET_FINAL_ATTEN)
		ans = yield self.read_parameter(c)
		atten = 20*np.log10(ans/0xFFF)
		returnValue(atten)

	@setting(1109, chan='w', returns='v')
	def get_chan_atten(self, c, chan):
		"""
		Get the attenuation of an individual MIDAS channel in dB.

		parameter:
		channel
		"""
		if not self.connected:
			returnValue("Error: MIDAS not connected.")
			return
		yield self.send_msg(c, CmdNums.GET_CHANNEL_ATTEN, chan)
		ans = yield self.read_parameter(c)
		atten = 20*np.log10(ans/0xFFF)
		returnValue(atten)

	@setting(1110, returns='w')
	def get_rt_latency(self, c):
		"""
		Get the number of points the trigger is delayed by.
		"""
		if not self.connected:
			returnValue("Error: MIDAS not connected.")
			return
		yield self.send_msg(c, CmdNums.GET_RT_LATENCY)
		ans = yield self.read_parameter(c)
		returnValue(ans)

	@setting(1111, returns='i')
	def get_rt_noise_fir(self, c):
		"""
		Get the noise average FIR.
		"""
		if not self.connected:
			returnValue("Error: MIDAS not connected.")
			return
		yield self.send_msg(c, CmdNums.GET_RT_LATENCY)
		ans = yield self.read_parameter(c)
		returnValue(ans)

	@setting(1112, returns='w')
	def get_point_avg_num(self, c):
		"""
		Get the number of samples to average together per trigger
		in single point mode. This number needs to be a power of
		two, and allows the effective "integration time" to be
		changed.
		"""
		if not self.connected:
			returnValue("Error: MIDAS not connected.")
			return
		yield self.send_msg(c, CmdNums.GET_POINT_AVG_NUM)
		ans = yield self.read_parameter(c)
		returnValue(ans)




__server__ = MIDASServer()

if __name__ == "__main__":
	from labrad import util
	util.runServer(__server__)