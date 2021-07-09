# Copyright (C) 2015  Brunel Odegard
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
This LabRAD client identifies active serial COM ports.
For each port available, it queries the port with known
identification commands. If the port responds, the Serial
Device Manager will write an entry in the LabRAD registry
identifying the port as corresponding to a particular
type of device.
"""
import time
import platform
import labrad
from labrad.types import Value

# names of server types (for classification of device type in registry)
global serverNameAD5764_DCBOX; serverNameAD5764_DCBOX = "ad5764_dcbox" # ad5764 dcbox
global serverNameAD5764_ACBOX; serverNameAD5764_ACBOX = "ad5764_acbox" # ad5764 acbox
global serverNameAD5780_DCBOX; serverNameAD5780_DCBOX = "ad5780_dcbox" # ad5780 dcbox quad

#Following servers are associated with the evaporator
global serverNameRVC300; serverNameRVC300 = "RVC_server" # RVC Pressure Controller (Pressure read out and leak valve)
global serverNameFTM2400; serverNameFTM2400 = "FTM_server" # Deposition Controller
global serverNameValveRelayController; serverNameValveRelayController = "valve_relay_server" # Valve and Relay Controller
global serverNameStepperController; serverNameStepperController = "stepper_server" # Stepper Motor Controller
global serverNamePowerSupply; serverNamePowerSupply = "power_supply_server" # TDK Power Supply

global IO_DELAY  ;IO_DELAY   = 0.1 # delay between read and write
global PORT_DELAY;PORT_DELAY = 2.0 # delay after opening serial port

global TIMEOUT; TIMEOUT = Value(1,'s') # timeout for reading 

# ports that the manager will always ignore.
global blacklistedPorts
blacklistedPorts = ['COM1']



class serialDeviceManager(object):
    def __init__(self):
        self.serialConnect()

    def serialConnect(self):
        """Initializes connection to LabRAD, the serial server, and the registry"""

        self.cxn = labrad.connect()    # connect to labrad
        computerName = platform.node() # get computer name

        # LabRAD prefaces the serial server name with the computer name
        # after shifting to lower case and replaceing spaces with underscores.
        self.serialServerName = computerName.lower().replace(' ','_').replace('-','_') + '_serial_server'

        self.ser = self.cxn.servers[self.serialServerName] # connect to serial server
        self.reg = self.cxn.registry                       # connect to the registry

    def run(self):
        """Tries to identify any ports found"""
        serialPorts = self.ser.list_serial_ports()                                      # all serial ports found
        activePorts = [port for port in serialPorts if (port not in blacklistedPorts)]  # filter out ports present in blacklistedPorts
        print('\n')                                                                     #
        print(("Found %i active serial port(s): %s"%(len(activePorts),str(activePorts)))) # Print out number, names of ports found
        print('\n')                                                                     #

        for port in activePorts:
            self.identifyPort(port)
            print('\n\n\n')

        # Also ensure that the "Servers" folder exists, even if there aren't any devices identified.
        self.reg.cd([''])
        if not ("Servers" in self.reg.dir()[0]):
            self.reg.mkdir("Servers")
            print('Folder "Servers" does not exist in registry. Creating it.')

    def getPortDevices(self,port):
        """Gets a list of all registry entries that point to COM port 'port'"""

        regEntries = []

        self.reg.cd([''])                      # If there's no Servers folder,
        if not 'Servers' in self.reg.dir()[0]: # there are no device entries.
            return regEntries                  # Note that this function should never be called if there is no "Servers" folder.

        self.reg.cd(['','Servers'])
        serverTypes = self.reg.dir()[0]

        for sType in serverTypes:
            self.reg.cd(['','Servers',sType,'Links'])
            entries = self.reg.dir()[1]
            for entry in entries:
                contents = self.reg.get(entry)
                if contents[1] == port:
                    regEntries.append([['','Servers',sType],entry])

        return regEntries


    def regWrite(self,serverType,deviceName,port):
        """Writes an entry in the registry linking 'port' to 'data'"""

        # If 'Servers' folder doesn't exist in registry root, make it.
        self.reg.cd([''])
        if not ('Servers' in self.reg.dir()[0]):
            self.reg.mkdir('Servers')
            print('Folder "Servers" does not exist in registry. Creating it.')

        # In folder "Servers," create the folder serverType if it doesn't exist.
        self.reg.cd(['','Servers'])
        if not (serverType in self.reg.dir()[0]):
            self.reg.mkdir(serverType)
            print(('Folder "%s" does not exist in "Servers." Creating it.'%serverType))

        # In the server specific folder, make sure there is a folder named "Links"
        self.reg.cd(['','Servers',serverType])
        if not ('Links' in self.reg.dir()[0]):
            self.reg.mkdir('Links')
            print('Folder "Links" missing from server directory. Creating it.')

        self.reg.cd(['','Servers',serverType,'Links']) # Finally, go the the pre-existing or newly created location
        keys = self.reg.dir()[1]                       # Fetch list of existing keys

        if not (deviceName in keys):                              # If this device (deviceName) doesn't have a key already, make it.
            self.reg.set(deviceName,(self.serialServerName,port)) # Write the port info.
            print(("Device %s of type %s not in registry. Adding it (port %s)..."%(deviceName,serverType,port)))

        else:                                          # If this device already has an entry
            existingPort = self.reg.get(deviceName)[1] # Get the port that supposedly corresponds to this device

            if port == existingPort: # Device already in registry, port number agree.
                print(("Device %s of type %s is already in the registry with port %s"%(deviceName,serverType,port)))

            else: # Device already in registry, port numbers disagree.
                print(("Device %s of type %s is already in registry. Ports disagree. (OLD:%s, NEW:%s). Overwriting..."%(deviceName,serverType,existingPort,port)))
                self.reg.set(deviceName,(self.serialServerName,port)) # Write the port info.

        # [!!!!] ADD THIS FUNCTIONALITY
        # search for other entries linked to the same port (not including this result. This should only happen if a port changes device.)
        # If none: do nothing
        # If one : prompt user - delete?
        # If many: prompt delete (a/s/n) all / selective / none

    def identifyPort(self,port):
        """Attempts to idenfiy any given port"""

        print("")                              # 
        print(("Connecting to port %s..."%port)) # 
        self.ser.open(port)                    # connect to the given port
        time.sleep(PORT_DELAY)
        
        self.ser.bytesize(8)
        self.ser.parity('N')
        self.ser.stopbits(1)
        self.ser.timeout(TIMEOUT)
        
        #####################
        ## ACbox and DCbox ##
        #####################
        print("\tTrying device type: AC/DC box") # 
        acdcBoxBaudrates = [115200]      # values of baudrates for this type of device
        for rate in acdcBoxBaudrates:
            time.sleep(IO_DELAY)
            self.ser.baudrate(rate)                # set the baudrate
            self.ser.write('NOP\r\n')              # 
            time.sleep(IO_DELAY); self.ser.read_line()  # flush the interface
            self.ser.write("*IDN?\r\n")            # query identification command
            time.sleep(IO_DELAY)                   # delay for processing
            response = self.ser.read_line()        # get response from device
            if response:
                print(("\tGot response: <%s>"%response))
                break # if we got a non-empty response, don't try any more baudrates.

        if response.startswith('DCBOX_DUAL_AD5764'):                         # For a DCBOX, the response to *IDN? will be "DCBOX_DUAL_AD5764(NAME)"
            print(("\tPort %s identified as a DCBOX_DUAL_AD5764 device."%port))  # Print info that port has been identified
            self.regWrite(serverNameAD5764_DCBOX,response,port)              # Write a registry entry identifying this port as corresponding to a DCBOX_DUAL_AD5764 device
            self.ser.close() # close the port
            return True                                                      # Returning True tells the run() function that the port has been identified.

        elif response.startswith('ACBOX_DUAL_AD5764'):                       # For an ACBOX, the response to *IDN? will be "ACBOX_DUAL_AD5764(NAME)"
            print(("\tPort %s identified as an ACBOX_DUAL_AD5764 device."%port)) # Print info that port has been identified
            self.regWrite(serverNameAD5764_ACBOX,response,port)              # Write a registry entry identifying this port as corresponding to an ACBOX_DUAL_AD5764 device.
            self.ser.close() # close the port
            return True                                                      #

        elif response.startswith('DCBOX_QUAD_AD5780'):
            print(('\tPort %s identified as a DCBOX_QUAD_AD5780 device.'%port))
            self.regWrite(serverNameAD5780_DCBOX,response,port)
            self.ser.close() # close the port
            return True

        else:                                                                # no response
            print(("\tPort %s cannot be identified as an AC/DC box."%port))      # or unrecognized response
            print(("\tResponded with <%s>"%response))

        time.sleep(1) # sleep 1 second between attempts to identify. This prevents flooding the port with signals too quickly.
        
        #########################
        ## next device type(s) ##
        #########################

        self.ser.close() # close the port       
    


if __name__ == '__main__':
    sdm = serialDeviceManager()
    sdm.run()
    input("Finished. Press enter to exit.")