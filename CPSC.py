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
name = CPSC Server
version = 1.0
description = Communicates with the CPSC which controls the JPE piezo stacks. Must be placed in the same directory as cacli.exe in order to work. 

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""

import subprocess
import re

from labrad.server import LabradServer, setting
from twisted.internet.defer import inlineCallbacks, returnValue
import labrad.units as units
from labrad.types import Value
import time
import numpy as np
from math import floor

import sys
import os

class CPSCServer(LabradServer):
    name = "CPSC Server"    # Will be labrad name of server

    @inlineCallbacks
    def initServer(self):  # Do initialization here
        yield os.chdir(sys.path[0])
        self.device_detected = False
        
        #Distance between pivot point and top of sample given in mm. 
        #This value changes with geometry of sample loaded on piezos. 
        self.h = 33.9
        #radius given in mm. This value should be constant.
        self.R = 15.0
        
        #The relative step sizes of each of the knobs with everything else held constant
        #1 everywhere means everything is stepping the same
        #0.5 means that it steps half the distance
        #2 means it steps twice the distance
        #Forward is moving in direction 0, backwards is moving in direction 1
        self.weight_for =[1,1,1]
        self.weight_back =[1,1,1]
        
        #Matrix T1 goes from xyz coordinates to channel 1, 2, 3 coordinates. This does not take into account the relative weight of steps
        self.T1 = [[-self.R * np.sqrt(3) / (2*self.h), self.R / (2*self.h), 1],[0,-self.R/(self.h),1],[self.R * np.sqrt(3) / (2*self.h), self.R / (2*self.h), 1]]
        
        #Matrix T2 goes from channel coordinates back to xyz coordinates. Apparently never implemented
        
        yield self.detect_device()
        #print "Server initialization complete"
        
    @setting(100,returns = 'b')
    def detect_device(self, c = 1, d = 1):
        #no idea how or why this sometimes takes three inputs, but it does. None of them are important. 
        resp = yield subprocess.check_output("cacli modlist")
        if resp.startswith("STATUS : INQUIRY OF INSTALLED MODULES"):
            print("CPSC detected. Communication active.")
            self.device_detected = True
            returnValue(True)
        else:
            print("CPSC not detected. Ensure controller is connected to computer and channel is set to EXT, then run detect device method.") 
            self.device_detected = False
            self.device_list = ['ADDR','CHANNEL','DEVICE NAME','TAG', 'TYPE INFO']
            returnValue(False)
            
    @setting(101, returns='s')
    def get_module_list(self, c):
        """Command to list the automatically detected modules in the controller."""
        if self.device_detected == True:
            resp = yield subprocess.check_output("cacli modlist")
        else:
            resp = "Device not connected."
            print("Device not connected. ")
            #Eventually make this actually throw an error instead of printing something
        returnValue(resp)
            
    @setting(102, ADDR='i', returns='s')
    def get_module_info(self, c, ADDR):
        """Requests the module description and available output channels.
        Input ADDR is the module location (integer 1 through 6). """
        if self.device_detected == True:
            resp = yield subprocess.check_output("cacli DESC "+str(ADDR))
        else:
            resp = "Device not connected."
            print("Device not connected. ")
            #Eventually make this actually throw an error instead of printing something
        returnValue(resp)
        
    @setting(103, ADDR='i', CH = 'i', returns='*s')
    def get_actuator_info(self, c, ADDR, CH):
        """Requests information about a user defined Tags (name) or set actuator Types. 
        Input ADDR is the module location (integer 1 through 6). 
        Input CH is the module channel, integer 1 through 3.
        Returns array of strings. First element is the Type. Second element is the Tag."""
        if self.device_detected == True:
            resp = yield subprocess.check_output("cacli INFO "+str(ADDR) + " " + str(CH))
            type = self.find_between(resp,"TYPE :","\r\n")
            tag = self.find_between(resp,"TAG  :","\r\n")
            info = [type, tag]
        else:
            resp = "Device not connected."
            info = [resp, resp]
            #Eventually make this actually throw an error instead of printing something
        returnValue(info)
        
    @setting(104, ADDR='i', CH = 'i', TYPE = 's', TEMP = 'i', DIR = 'i', FREQ = 'i',
                REL = 'i', STEPS = 'i', TORQUE = 'i', returns='s')
    def move(self, c, ADDR, CH, TYPE, TEMP, DIR, FREQ, REL, STEPS, TORQUE = None):
        """Moves specified actuator with specified parameters. ADDR and CH specify the 
        module address (1 through 6) and channel (1 through 3). 
        TYPE specifies the cryo actuator model. TEMP is the nearest integer temperature
        (0 through 300). DIR determines CW (1) vs CWW (0) stack rotation. 
        FREQ is the interger frequency of operation input in Hertz. 
        REL is the piezo step size parameter input. Value is a percentage (0-100%).
        STEPS is the number of actuation steps. Range is 0 to 50000, where 0 is used for
        infinite movement. 
        TORQUE corresponds to an optional torque factor, between 1 and 30. Larger values
        can be useful for unsticking the JPE. 
        """
        if self.device_detected == True:
            #Add input checks
            if TORQUE == None:
                resp = yield subprocess.check_output("cacli MOV "+str(ADDR) + " " + str(CH)
                 + " " + TYPE + " " + str(TEMP) + " " + str(DIR) + " " + str(FREQ) + " " +
                 str(REL) + " " + str(STEPS))
            else:
                resp = yield subprocess.check_output("cacli MOV "+str(ADDR) + " " + str(CH)
                 + " " + TYPE + " " + str(TEMP) + " " + str(DIR) + " " + str(FREQ) + " " +
                 str(REL) + " " + str(STEPS) + " " + str(TORQUE))
        else:
            resp = "Device not connected."
            print("Device not connected. ")
            #Eventually make this actually throw an error instead of printing something
        returnValue(resp)
        
    @setting(105, ADDR = 'i', returns = 's')
    def stop(self,c,ADDR):
        """Stops movement of the actuator at the specified address."""
        if self.device_detected == True:
            resp = yield subprocess.check_output("cacli STP " + str(ADDR))
            #print resp
        else:
            resp = "Device not connected."
            print("Device not connected. ")
        returnValue(resp)
        
    @setting(106, ADDR = 'i', returns = '*s')
    def status(self,c,ADDR):
        """Requests the status of the amplifier at provided address. Returns Moving
        or Stop in the first element of array. In addition, amplifier Failsage State
        is shown. If any error of the amplifier occurs (red status LED on front panel)
        the cause of the error may be requested via this command."""
        if self.device_detected == True:
            resp = yield subprocess.check_output("cacli STS " + str(ADDR))
            #print resp
        else:
            resp = "Device not connected."
            print("Device not connected. ")
        returnValue(resp)
        
    @setting(107, returns = 'v[]')
    def get_height(self,c):
        """Returns the height from the sample to the pivot location. Units of mm"""
        return self.h
        
    @setting(108, h = 'v[]', returns = 'v[]')
    def set_height(self,c, h):
        """Sets and returns the height from the sample to the pivot location. Units of mm"""
        self.h = h
        self.T1 = [[-self.R * np.sqrt(3) / (2*self.h), self.R / (2*self.h), 1],[0,-self.R/(self.h),1],[self.R * np.sqrt(3) / (2*self.h), self.R / (2*self.h), 1]]
        return self.h
        
    @setting(109, ADDR = 'i', returns = 's')
    def center(self,c, ADDR):
        """Centers the piezos specified by ADDR in order to keep track of position. This will run the piezos through their
        full movement range. Make sure this is only called with no sensitive sample and be destroyed."""
        #FIGURE OUT HOW TO DO THIS
        #Actually pretty sure this is impossible to do from software
        returnValue('Success!')
    
    @setting(110, ADDR = 'i', TEMP = 'i', FREQ = 'i', REL = 'i', XYZ = '*v[]', TORQUE = 'i', returns = 's')
    def move_xyz(self,c, ADDR, TEMP, FREQ, REL, XYZ, TORQUE = None):
        """Request CADM move sample in the according to the arbitrary vector XYZ. XYZ should be a 3 element list 
        with the number of steps to be taken in the x, y, and z direction respectively. Intergers not necessary because
        the xyz coordinates need to be transformed into other coordinates first, after which they will be rounded. 
        Output not yet implememnted. Output returns the true number of steps taken in the x, y, and z directions 
        (not necessarily equal), and the number of steps taken in radial directions."""
        try:
            VEC = np.dot(self.T1,XYZ)
            VEC = self.adjustForWeight(VEC)
            VEC = [round(x) for x in VEC]
            print(VEC)
            
            #have each cycle take ~1 second
            cycle_size = int(FREQ/2)
            
            if VEC[0] > 0:
                dir_chn_1 = 1
            else:
                dir_chn_1 = 0

            if VEC[1] > 0:
                dir_chn_2 = 1
            else:
                dir_chn_2 = 0
                
            if VEC[2] > 0:
                dir_chn_3 = 1
            else:
                dir_chn_3 = 0
                
            #Find the largest number of steps that need to be taken
            max = np.max(np.abs(VEC))
            #Determine the number of cycles based on the max number of step taken in a cycle (cycle_size)
            num_cycles  = floor(max / cycle_size)
            #Determine the amount to move each cycle in each channel 
            
            VEC_cycle = [int(x) for x in np.multiply(VEC, cycle_size / max)]
            remainder  = [int(x) for x in np.subtract(VEC, np.multiply(VEC_cycle, num_cycles))]
            
            print("Taking " + str(VEC) +  " steps in channel 1, 2 and 3 respectively.")
            print("This will be done over " + str(num_cycles) + " cycles of " + str(VEC_cycle) + " steps.")
            print("And a final cycle with the remainder of " + str(remainder) + " steps.")

            VEC_cycle = np.abs(VEC_cycle)
            remainder = np.abs(remainder)
            
            for i in range (0,int(num_cycles)):
                if VEC_cycle[0] > 0:
                    yield self.move(c, ADDR, 1, 'CA1801', TEMP, dir_chn_1, FREQ, REL, VEC_cycle[0], TORQUE)
                    yield self.pause_while_moving(c,ADDR)
                if VEC_cycle[1] > 0:
                    yield self.move(c, ADDR, 2, 'CA1801', TEMP, dir_chn_2, FREQ, REL, VEC_cycle[1], TORQUE)
                    yield self.pause_while_moving(c,ADDR)
                if VEC_cycle[2] > 0:
                    yield self.move(c, ADDR, 3, 'CA1801', TEMP, dir_chn_3, FREQ, REL, VEC_cycle[2], TORQUE)
                    yield self.pause_while_moving(c,ADDR)
            
            tot_remain = 0
            for rem in remainder:
                tot_remain = tot_remain + rem
                
            if tot_remain != 0:
                if remainder[0] > 0:
                    yield self.move(c, ADDR, 1, 'CA1801', TEMP, dir_chn_1, FREQ, REL, remainder[0], TORQUE)
                    yield self.pause_while_moving(c,ADDR)
                if remainder[1] > 0:
                    yield self.move(c, ADDR, 2, 'CA1801', TEMP, dir_chn_2, FREQ, REL, remainder[1], TORQUE)
                    yield self.pause_while_moving(c,ADDR)
                if remainder[2] > 0:
                    yield self.move(c, ADDR, 3, 'CA1801', TEMP, dir_chn_3, FREQ, REL, remainder[2], TORQUE)
                    yield self.pause_while_moving(c,ADDR)
            
            returnValue('Success!')
        except Exception as inst:
            print(inst)
            
    @setting(111, ADDR = 'i', TEMP = 'i', FREQ = 'i', REL = 'i', X = 'v[]', TORQUE = 'i', returns = 's')
    def move_x(self,c, ADDR, TEMP, FREQ, REL, X, TORQUE = None):
        """Request CADM move sample in the according to the arbitrary vector XYZ. XYZ should be a 3 element list 
        with the number of steps to be taken in the x, y, and z direction respectively. Intergers not necessary because
        the xyz coordinates need to be transformed into other coordinates first, after which they will be rounded. 
        Output not yet implememnted. Output returns the true number of steps taken in the x, y, and z directions 
        (not necessarily equal), and the number of steps taken in radial directions."""
        
        VEC = np.dot(self.T1,[X,0,0])
        VEC = self.adjustForWeight(VEC)
        VEC = [round(x) for x in VEC]
        print(VEC)
        print('Knob 2 should always need to move 0 for this. If it is not showing 0, then something went werd')
        #have each cycle take ~1 second
        cycle_size = int(FREQ/2)
        
        #TODO, just implement these cycles into the move XYZ general command
        #Direction should just be positive is 1, negative is 0
        if VEC[0] > 0:
            dir_chn_1 = 1
            dir_chn_3 = 0
        else:
            dir_chn_1 = 0
            dir_chn_3 = 1
        
        #Find the largest number of steps that need to be taken
        max = np.max(np.abs(VEC))
        #Determine the number of cycles based on the max number of step taken in a cycle (cycle_size)
        num_cycles  = floor(max / cycle_size)
        #Determine the amount to move each cycle in each channel 
        VEC_cycle = [int(x) for x in np.multiply(VEC, cycle_size / max)]
        remainder  = [int(x) for x in np.subtract(VEC, np.multiply(VEC_cycle, num_cycles))]
        
        print("Taking " + str(VEC) +  " steps in channel 1, 2 and 3 respectively.")
        print("This will be done over " + str(num_cycles) + " cycles of " + str(VEC_cycle) + " steps.")
        print("And a final cycle with the remainder of " + str(remainder) + " steps.")
        
        VEC_cycle = np.abs(VEC_cycle)
        remainder = np.abs(remainder)
        
        for i in range (0,int(num_cycles)):
            if VEC_cycle[0] > 0:
                yield self.move(c, ADDR, 1, 'CA1801', TEMP, dir_chn_1, FREQ, REL, VEC_cycle[0], TORQUE)
                yield self.pause_while_moving(c,ADDR)
            if VEC_cycle[2] > 0:
                yield self.move(c, ADDR, 3, 'CA1801', TEMP, dir_chn_3, FREQ, REL, VEC_cycle[2], TORQUE)
                yield self.pause_while_moving(c,ADDR)
            
        tot_remain = 0
        for rem in remainder:
            tot_remain = tot_remain + rem
            
        if tot_remain != 0:
            if remainder[0] > 0:
                yield self.move(c, ADDR, 1, 'CA1801', TEMP, dir_chn_1, FREQ, REL, remainder[0], TORQUE)
                yield self.pause_while_moving(c,ADDR)
            if remainder[2] > 0:
                yield self.move(c, ADDR, 3, 'CA1801', TEMP, dir_chn_3, FREQ, REL, remainder[2], TORQUE)
                yield self.pause_while_moving(c,ADDR)
        
        returnValue('Success!')
        
    @setting(112, ADDR = 'i', TEMP = 'i', FREQ = 'i', REL = 'i', Y = 'v[]', TORQUE = 'i', returns = 's')
    def move_y(self,c, ADDR, TEMP, FREQ, REL, Y, TORQUE = None):
        """Request CADM move sample in the according to the arbitrary vector XYZ. XYZ should be a 3 element list 
        with the number of steps to be taken in the x, y, and z direction respectively. Intergers not necessary because
        the xyz coordinates need to be transformed into other coordinates first, after which they will be rounded. 
        Output not yet implememnted. Output returns the true number of steps taken in the x, y, and z directions 
        (not necessarily equal), and the number of steps taken in radial directions."""
        
        VEC = np.dot(self.T1,[0,Y,0])
        VEC = self.adjustForWeight(VEC)
        VEC = [round(x) for x in VEC]
        print(VEC)
        
        #Have each cycle take ~1.5 seconds
        cycle_size = int(FREQ/2)
        
        #Determine the direction
        if VEC[0] >0:
            dir_chn_1 = 1
            dir_chn_2 = 0
            dir_chn_3 = 1
        else:
            dir_chn_1 = 0
            dir_chn_2 = 1
            dir_chn_3 = 0
        
        #Find the largest number of steps that need to be taken
        max = np.max(np.abs(VEC))
        #Determine the number of cycles based on the max number of step taken in a cycle (cycle_size)
        num_cycles  = floor(max / cycle_size)
        #Determine the amount to move each cycle in each channel 
        VEC_cycle = [int(x) for x in np.multiply(VEC, cycle_size / max)]
        remainder  = [int(x) for x in np.subtract(VEC, np.multiply(VEC_cycle, num_cycles))]
        
        print("Taking " + str(VEC) +  " steps in channel 1, 2 and 3 respectively.")
        print("This will be done over " + str(num_cycles) + " cycles of " + str(VEC_cycle) + " steps.")
        print("And a final cycle with the remainder of " + str(remainder) + " steps.")

        VEC_cycle = np.abs(VEC_cycle)
        remainder = np.abs(remainder)
        
        for i in range (0,int(num_cycles)):
            if VEC_cycle[0] > 0:
                yield self.move(c, ADDR, 1, 'CA1801', TEMP, dir_chn_1, FREQ, REL, VEC_cycle[0], TORQUE)
                yield self.pause_while_moving(c,ADDR)
            if VEC_cycle[1] > 0:
                yield self.move(c, ADDR, 2, 'CA1801', TEMP, dir_chn_2, FREQ, REL, VEC_cycle[1], TORQUE)
                yield self.pause_while_moving(c,ADDR)
            if VEC_cycle[2] > 0:
                yield self.move(c, ADDR, 3, 'CA1801', TEMP, dir_chn_3, FREQ, REL, VEC_cycle[2], TORQUE)
                yield self.pause_while_moving(c,ADDR)
        
        tot_remain = 0
        for rem in remainder:
            tot_remain = tot_remain + rem
            
        if tot_remain != 0:
            if remainder[0] > 0:
                yield self.move(c, ADDR, 1, 'CA1801', TEMP, dir_chn_1, FREQ, REL, remainder[0], TORQUE)
                yield self.pause_while_moving(c,ADDR)
            if remainder[1] > 0:
                yield self.move(c, ADDR, 2, 'CA1801', TEMP, dir_chn_2, FREQ, REL, remainder[1], TORQUE)
                yield self.pause_while_moving(c,ADDR)
            if remainder[2] > 0:
                yield self.move(c, ADDR, 3, 'CA1801', TEMP, dir_chn_3, FREQ, REL, remainder[2], TORQUE)
                yield self.pause_while_moving(c,ADDR)
        
        returnValue('Success!')
        
    @setting(113, ADDR = 'i', TEMP = 'i', FREQ = 'i', REL = 'i', Z = 'v[]', TORQUE = 'i', returns = 's')
    def move_z(self,c, ADDR, TEMP, FREQ, REL, Z, TORQUE = None):
        """Request CADM move sample in the according to the arbitrary vector XYZ. XYZ should be a 3 element list 
        with the number of steps to be taken in the x, y, and z direction respectively. Intergers not necessary because
        the xyz coordinates need to be transformed into other coordinates first, after which they will be rounded. 
        Output not yet implememnted. Output returns the true number of steps taken in the x, y, and z directions 
        (not necessarily equal), and the number of steps taken in radial directions."""
        
        #Calculate steps in knobs 1 2 and 3
        VEC = np.dot(self.T1,[0.0,0.0,Z])
        VEC = self.adjustForWeight(VEC)
        VEC = [round(x) for x in VEC]
        print(VEC)
        
        #Have each cycle take ~1.5 seconds
        cycle_size = float(FREQ/2)
                
        #Determine the direction
        if VEC[0] >0:
            dir_chn_1 = 1
            dir_chn_2 = 1
            dir_chn_3 = 1
        else:
            dir_chn_1 = 0
            dir_chn_2 = 0
            dir_chn_3 = 0
        
        #Find the largest number of steps that need to be taken
        max = np.max(np.abs(VEC))
        #Determine the number of cycles based on the max number of step taken in a cycle (cycle_size)
        num_cycles  = floor(max / cycle_size)
        #Determine the amount to move each cycle in each channel 
        VEC_cycle = [int(x) for x in np.multiply(VEC, cycle_size / max)]
        remainder  = [int(x) for x in np.subtract(VEC, np.multiply(VEC_cycle, num_cycles))]
        
        print("Taking " + str(VEC) +  " steps in channel 1, 2 and 3 respectively.")
        print("This will be done over " + str(num_cycles) + " cycles of " + str(VEC_cycle) + " steps.")
        print("And a final cycle with the remainder of " + str(remainder) + " steps.")
        
        VEC_cycle = np.abs(VEC_cycle)
        remainder = np.abs(remainder)
        
        for i in range (0,int(num_cycles)):
            if VEC_cycle[0] > 0:
                yield self.move(c, ADDR, 1, 'CA1801', TEMP, dir_chn_1, FREQ, REL, VEC_cycle[0], TORQUE)
                yield self.pause_while_moving(c,ADDR)
            if VEC_cycle[1] > 0:
                yield self.move(c, ADDR, 2, 'CA1801', TEMP, dir_chn_2, FREQ, REL, VEC_cycle[1], TORQUE)
                yield self.pause_while_moving(c,ADDR)
            if VEC_cycle[2] > 0:
                yield self.move(c, ADDR, 3, 'CA1801', TEMP, dir_chn_3, FREQ, REL, VEC_cycle[2], TORQUE)
                yield self.pause_while_moving(c,ADDR)
        
        tot_remain = 0
        for rem in remainder:
            tot_remain = tot_remain + rem
            
        if tot_remain != 0:
            if remainder[0] > 0:
                yield self.move(c, ADDR, 1, 'CA1801', TEMP, dir_chn_1, FREQ, REL, remainder[0], TORQUE)
                yield self.pause_while_moving(c,ADDR)
            if remainder[1] > 0:
                yield self.move(c, ADDR, 2, 'CA1801', TEMP, dir_chn_2, FREQ, REL, remainder[1], TORQUE)
                yield self.pause_while_moving(c,ADDR)
            if remainder[2] > 0:
                yield self.move(c, ADDR, 3, 'CA1801', TEMP, dir_chn_3, FREQ, REL, remainder[2], TORQUE)
                yield self.pause_while_moving(c,ADDR)
        
        returnValue('Success!')
        
    @setting(114, ADDR = 'i', returns = 's')
    def pause_while_moving(self,c, ADDR):
        """Returns 'Success' once the server is no longer actively stepping. Function should be called
        immediately after a cpsc.move(...) command to avoid sending more commands while the move is
        being executed. move_x, move_y, move_z, and move_xyz already have this function built into them."""

        while True:
            status = yield self.status(c,ADDR)
            if status.startswith("STATUS : STOP"):
                break
        returnValue('Success!')
        
    @setting(115, Weight_for = '*v[]',Weight_back = '*v[]')
    def setRelativeStepSize(self, c, Weight_for, Weight_back):
        #Direction 0 is forward
        self.weight_for  = Weight_for
        #Direction 1 is backwards
        self.weight_back = Weight_back
        
    def adjustForWeight(self, vec):
        #Vec value greater than 0 corresponds to direction 1, which is moving "backward" (the tip moves away from the sample)
        #vec values less than 0 corresponds to direction 0, which is moving "forward" (the tip moves closer to the sample)
        for i in range(0,3):
            if vec[i] > 0:
                vec[i] = vec[i] / self.weight_back[i]
            elif vec[i] < 0:
                vec[i] = vec[i] / self.weight_for[i]
        return vec
        
    @setting(116, returns = 'b')
    def checkWeights(self, c):
        #Returns True if all the weights are set to something reasonable and positive
        #Returns False if one or more weights are set to 0 or something negative
        num = 0
        for weight in self.weight_for:
            if weight <= 0:
                num += 1
            
        for weight in self.weight_back:
            if weight <= 0:
                num += 1
                
        if num >0:
            return False
        else:
            return True
        
    def find_between(self, s, start, end):
        try:
            result = re.search('%s(.*)%s' % (start, end), s).group(1)
        except:
            result = ""
        return result
        
__server__ = CPSCServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)