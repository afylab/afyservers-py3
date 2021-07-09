
#import stuff
from labrad.server import setting,Signal
from labrad.devices import DeviceServer,DeviceWrapper
from twisted.internet.defer import inlineCallbacks, returnValue
import labrad.units as units
from labrad.types import Value
from twisted.internet import reactor,defer
import time

BAUD = 19200 # assumed as default
TIMEOUT = Value(0.01,'s')


class serverInfo(object):
    def __init__(self):
        self.deviceName = 'Turbo450device'
        self.serverName = 'Turbo450server'

    def getDeviceName(self,comPort):
        return "%s (%s)"%(self.serverName,comPort)

class Turbo450deviceWrapper(DeviceWrapper):
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
        p.read() #clear out the read buffer
        p.timeout(None)
        print("Connected")
        yield p.send()

    def packet(self):
        """Create a packet in our private context."""
        return self.server.packet(context=self.ctx)

    @inlineCallbacks
    def write(self, code):
        """Write a data value to the heat switch."""
        yield self.packet().write(code).send()

    @inlineCallbacks
    def read(self):
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
    #
#

class Turbo450server(DeviceServer):
    name = 'Turbo450'
    deviceName = 'Turbo450device'
    deviceWrapper = Turbo450deviceWrapper

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
        """Load configuration information from the registry."""
        reg = self.reg
        yield reg.cd(['', 'Servers', 'Turbo450', 'Links'], True)
        dirs, keys = yield reg.dir()
        p = reg.packet()
        print(" created packet")
        print("printing all the keys",keys)
        for k in keys:
            print("k=",k)
            p.get(k, key=k)

        ans = yield p.send()
        print("ans=",ans)
        self.serialLinks = dict((k, ans[k]) for k in keys)

    @inlineCallbacks
    def findDevices(self):
        """Find available devices from list stored in the registry."""
        devs = []
        for name, (serServer, port) in list(self.serialLinks.items()):
            if serServer not in self.client.servers:
                continue
            server = self.client[serServer]
            print(server)
            print(port)
            ports = yield server.list_serial_ports()
            print(ports)
            if port not in ports:
                continue
            devName = '%s (%s)' % (serServer, port)
            devs += [(devName, (server, port))]

       # devs += [(0,(3,4))]
        returnValue(devs)

    @setting(100)
    def connect(self,c,server,port):
        dev=self.selectedDevice(c)
        yield dev.connect(server,port)  #not certain

    def sleep(self,secs):
        d=defer.Deferred()
        reactor.callLater(secs,d.callback,'Sleeping')
        return d


    @setting(202) #do I need mode here
    def temperature(self,c):
        """
        Get Temperture in degree Celcius.
        """
        print("Got Here")
        dev=self.selectedDevice(c)
        yield dev.write('\x02\x16\x00 %\x00\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x10')
    #Here, this code is a specific code that will give out all the parameter we want
        yield self.sleep(0.1)
        rep=yield dev.read()
        i= 0
        while len(rep)!=24:
            rep=rep+'\n'
            retd=yield dev.read()
            rep=rep+retd
            i = i + 1
            if i >24:
                break
    #we need such loop to get away from the fact that dev.read is a readline and it stop at \n
        aa=list(map(ord,rep))
    #convert hex and ascii to decimal
        ans=aa[15]*256+aa[16]
    #give the parameter
        returnValue(ans)

    @setting(203) #do I need mode here
    def mcurrent(self,c):
        """
        Get motor current in 0.1 Ampere.
        """
        dev=self.selectedDevice(c)
        yield dev.write('\x02\x16\x00 %\x00\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x10')
        yield self.sleep(0.1)
        rep=yield dev.read()
        i= 0
        while len(rep)!=24:
            rep=rep+'\n'
            retc=yield dev.read()
            rep=rep+retc
            i = i + 1
            if i >24:
                break
        bb=list(map(ord,rep))
        ans=bb[17]*256+bb[18]
        returnValue(ans)

    @setting(204) #do I need mode here
    def csfrequency(self,c):
        """
        Get current stator frequency in Hz.
        """
        dev=self.selectedDevice(c)
        yield dev.write('\x02\x16\x00 %\x00\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x10')
        yield self.sleep(0.1)
        rep=yield dev.read()
        i= 0
        while len(rep)!=24:
            rep=rep+'\n'
            reta=yield dev.read()
            rep=rep+reta
            i = i + 1
            if i >24:
                break
        cc=list(map(ord,rep))
        ans=cc[13]*256+cc[14]
        returnValue(ans)

    @setting(205) #do I need mode here
    def voltage(self,c):
        """
        Get Current intermediate circuit voltage in 0.1V.
        """
        dev=self.selectedDevice(c)
        yield dev.write('\x02\x16\x00 %\x00\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x10')
        yield self.sleep(0.1)
        rep=yield dev.read()
        i= 0
        while len(rep)!=24:
            rep=rep+'\n'
            retb=yield dev.read()
            rep=rep+retb
            i = i + 1
            if i >24:
                break
        dd=list(map(ord,rep))
        ans=dd[21]*256+dd[22]
        returnValue(ans)

    @setting(9001,v='v')
    def do_nothing(self,c,v):
        pass

    @setting(9002)
    def read(self,c):
        dev=self.selectedDevice(c)
        ret=yield dev.read()
        returnValue(ret)

    @setting(9012)
    def reac(self,c):
        dev=self.selectedDevice(c)
        ret=yield dev.read()
        returnValue(ret)

    @setting(9003)
    def write(self,c,phrase):
        dev=self.selectedDevice(c)
        yield dev.write(phrase)

    @setting(9004)
    def query(self,c,phrase):
        dev=self.selectedDevice(c)
        yield dev.write(phrase)
        ret = yield dev.read()
        returnValue(ret)

__server__ = Turbo450server()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
