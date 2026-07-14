import os,sys,inspect
import time
import math
import numpy as np
import h5py
import labrad
import labrad.units as U
import yaml
import shutil

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0,parentdir)

#TODO: to implement gate voltage limits
X_MIN = -10.0
X_MAX = 10.0
Y_MIN = -10.0
Y_MAX = 10.0
    
def sweep_sim(sim,ch,vi,vf,rate):
    '''
    Step a SIM gate output on channel ch from vi to vf.
    
        Parameters:
            sim, labrad.connect.sim: sim module server
            ch, int: channel to sweep
            vi, float: initial voltage
            vf, float: final voltage
            rate, float: ramp rate in volts per second
        
        Returns:
            data_reshaped, np.array(float[][]): 
    '''
    sim.dc_output_on(ch)
    t = np.abs(vf-vi)/rate
    for v in np.linspace(vi, vf, 100):
        sim.dc_set_voltage(ch, v)
        time.sleep(float(t)/float(100))

def sweep_qdac(qdac,ch,vi,vf,rate):
    '''
    Step a QDAC gate output on channel ch from vi to vf.
    
        Parameters:
            qdac, labrad.connect.qdac: qdac server
            ch, int: channel to sweep
            vi, float: initial voltage
            vf, float: final voltage
            rate, float: ramp rate in volts per second
        
        Returns:
            data_reshaped, np.array(float[][]): 
    '''
    t = np.abs(vf-vi)/rate
    qdac.ramp([ch], [vi], [vf], 1000, float(t)/float(1000))
    #for v in np.linspace(vi, vf, 100):
    #    qdac.set_voltage(ch, v)
    #    time.sleep(float(t)/float(100))

def sweep_dac(dc,ch,vi,vf,rate):
    t = np.abs(vf-vi)/rate
    #dc.buffer_ramp([ch],[0],[vi],[vf],100,t*1e6/100, 1)
    dc.buffer_ramp([ch],[0],[vi],[vf],100,int(0.01*1e6))

def main():
    time_start = time.time()
    
    #Load config
    scriptdir="C:\\Users\\afyla\\Young Lab Dropbox\\Young Group\\Oxford Proteox\\Measurement Code\\Noah\\RESTEST20\\"
    configname=scriptdir+"2gatesweep_config.yml"
    with open(configname, 'r') as ymlfile:
        cfg = yaml.full_load(ymlfile)

    #Connect to Each Instrument
    cxn = labrad.connect()
    dc = cxn.dac_adc_giga
    #sim = cxn.sim900
    #qdac = cxn.qdac
    dc.select_device()
    #sim.select_device()
    #qdac.select_device()

    # --- Begin Lockin Setup ---
    num_lockins = int(len(cfg['lockins']['type']))
    measurement = cfg['measurement']
    sweep_parameters = cfg['sweep_parameters']
    
    lockins_list = cxn.sr860
    if len(lockins_list.list_devices()) < num_lockins:
        sys.exit(['Required number of lockins not connected.'])
    lockin_list = lockins_list.list_devices()
    
    #Match the list of lockins given by labrad to the appropriate lockins by index
    lockin_addresses = [-1 for i in range(num_lockins)]
    for j in range(len(lockin_list)):
        lck_num = int(lockin_list[j][1].split("::")[-2])
        for i in range(num_lockins):
            if lck_num == int(cfg['lockins']['GPIB'][i]) :
                lockin_addresses[i] = j
    for i, a in enumerate(lockin_addresses):
        if a==-1:
            sys.exit("!!!\n\n Lockin not found at GPIB address %i. Please check GPIB addresses.\n\n!!!"%cfg['lockins']['GPIB'][i])
    lcks = []
    cxns=[]
    for i in range(num_lockins):
        cxns.append(labrad.connect())
        l = cxns[i].sr860
        lcks.append(l)
        lcks[i].select_device()
    for i in range(num_lockins):
        lcks[i].select_device(lockin_addresses[i])
        lcks[i].sensitivity(cfg['lockins']['sensitivity'][i])
        lcks[i].time_constant(cfg['lockins']['time_constant'][i])
    
    #TODO: Set the phase of current lockins to be -180deg
    
    #Set the output lockin (TODO: allow sourcing excitations on multiple lockins)
    lcks[cfg['measurement']['source_lockin']].sine_out_amplitude(cfg['measurement']['V_source'])
    lcks[cfg['measurement']['source_lockin']].frequency(cfg['measurement']['frequency'])
    #lcks[cfg['measurement']['hetero_lockin']].sine_out_amplitude(cfg['measurement']['hetero_source'])
    #lcks[cfg['measurement']['hetero_lockin']].frequency(cfg['measurement']['hetero_frequency'])
    # --- End Lockin Setup ---
    
    num_x = sweep_parameters['x_points']
    num_y = sweep_parameters['y_points']

    xgate_chs = sweep_parameters['x_channels']
    xranges = sweep_parameters['x_ranges']
    ygate_chs = sweep_parameters['y_dac_channels']
    yranges = sweep_parameters['y_dac_ranges']
    ysim_chs = sweep_parameters['y_sim_channels']
    ysimranges = sweep_parameters['y_sim_ranges']
    yqdac_chs = sweep_parameters['y_qdac_channels']
    yqdacranges = sweep_parameters['y_qdac_ranges']
    
    xvalues = np.array([np.linspace(xranges[i][0],xranges[i][1],num_x) for i in range(len(xgate_chs))])
    yvalues = np.array([np.linspace(yranges[i][0],yranges[i][1],num_y) for i in range(len(ygate_chs))])
    
    if ysim_chs != None:
        ysimvalues = np.array([np.linspace(ysimranges[i][0],ysimranges[i][1],num_y) for i in range(len(ysim_chs))])
    else:
        ysimvalues = None
    
   
    if yqdac_chs != None:
        yqdacvalues = np.array([np.linspace(yqdacranges[i][0],yqdacranges[i][1],num_y) for i in range(len(yqdac_chs))])
    else:
        yqdacvalues = None

    
    limits = sweep_parameters['gate_limits'][1]
    settling_time = float(cfg['sweep_parameters']['settling_time'])
    ramp_rate = float(cfg['sweep_parameters']['ramp_rate'])
    fixed_ramptime = 1.0
    
    dac_ch = xgate_chs + ygate_chs
    adc_ch = []
    for i in range(num_lockins):
        adc_ch.append(cfg['lockins']['ch_x'][i])
        adc_ch.append(cfg['lockins']['ch_y'][i])
    
    #Look through existing .h5 files in this folder and find max prefix
    h5file_indices = [int(f[:5]) for f in os.listdir(currentdir) if f.endswith('.h5')]
    filenumber=0
    if (len(h5file_indices)>0):
        filenumber=(np.max(h5file_indices))+1
    while filenumber < 99999:
        try:
            #Create the data file. IMPORTANT: Fail if it already exists!
            datafile = h5py.File(cfg['file']['data_directory']+"\\"+"%05d - "%filenumber+cfg['file']['file_name']+".hd5","x", libver='latest')
        except IOError:
            #If for some reason the file exists (shouldn't be possible), increment by one and try again
            filenumber+=1
            if filenumber>=99999:
                sys.exit("!!!\n\nYou've saved 100 thousand datasets in this folder. Are you okay?\n\n!!!")
            continue
        break
    
    shutil.copyfile(configname,cfg['file']['data_directory']+"\\configs\\"+"%05d"%filenumber+"_config.yml")
    
    #Create Dataset and Name the Columns
    n_columns = 3 + num_lockins*2 + len(xgate_chs) + len(ygate_chs) #nx, ny, Temp, Time, lockins (need both x and y quadratures), xgate values, ygate values
    if not ysim_chs is None:
        n_columns = n_columns + len(ysim_chs) #nx, ny, Temp, Time, lockins (need both x and y quadratures), xgate values, ygate values

    if not yqdac_chs is None:
        n_columns = n_columns + len(yqdac_chs) #nx, ny, Temp, Time, lockins (need both x and y quadratures), xgate values, ygate values

    
    dac_names = ["DAC %i [V]"%i for i in dac_ch]
    #TODO: Get string names from config file, only if provided
    lockin_names = []
    for i in range(num_lockins):
        gpib_addr = cfg['lockins']['GPIB'][i]
        lockin_names = lockin_names + ["Lockin (GPIB %i), X Quadrature [V]"%gpib_addr, "Lockin (GPIB %i), Y Quadrature [V]"%gpib_addr]
    nameslist = ["ix", "iy"] + dac_names + lockin_names + ["Probe Temperature [K]"]
    if not ysim_chs is None:
        for ch in ysim_chs:
            nameslist = nameslist + ["SIM " + str(ch) + " [V]"]

    if not yqdac_chs is None:
        for ch in yqdac_chs:
            nameslist = nameslist + ["QDAC " + str(ch) + " [V]"]

    dataset = datafile.create_dataset(cfg['file']['file_name'], (num_y*num_x,n_columns), dtype="f")
    dataset.attrs['column_names'] = nameslist
    dataset.attrs['comment'] = cfg['file']['comment']
    dataset.attrs['x_lim'] = cfg['sweep_parameters']['x_ranges']
    if cfg['sweep_parameters']['y_dac_ranges'] is not None:
        dataset.attrs['y_lim_dac'] = cfg['sweep_parameters']['y_dac_ranges']
    if cfg['sweep_parameters']['y_sim_ranges'] is not None:
        dataset.attrs['y_lim_sim'] = cfg['sweep_parameters']['y_sim_ranges']
    datafile.swmr_mode = True
    
    #check to see if gate limits exceeded during sweep:
    x_lims = sweep_parameters['x_lims']
    y_lims = sweep_parameters['y_lims']
    
    for lim, xrange in zip(x_lims, xranges):
        if np.min(xrange) < lim[0] or np.max(xrange) > lim[1]:
            raise Exception('MAXIMUM GATE RANGE EXCEEDED ON X-AXIS, PLEASE ADJUST SWEEP RANGE PARAMETERS')
    
    for lim, yrange in zip(y_lims, yranges):
        if np.min(yrange) < lim[0] or np.max(yrange) > lim[1]:
            raise Exception('MAXIMUM GATE RANGE EXCEEDED ON Y-AXIS, PLEASE ADJUST SWEEP RANGE PARAMETERS')
    
    #Set fixed SIM voltages
    if cfg['fixed_gates']['sim_channels'] != None:
        for i in range(len(cfg['fixed_gates']['sim_channels'])):
            ch = cfg['fixed_gates']['sim_channels'][i]
            if ch!=None:
                ch = int(ch)
                if (ch >=0) and (ch <=8):
                    print("Ramping SIM channel {} to {}V".format(ch,float(cfg['fixed_gates']['sim_voltages'][i])))
                    sweep_sim(sim,ch,0.0,float(cfg['fixed_gates']['sim_voltages'][i]),ramp_rate)

    """
    #Set fixed QDAC voltages
    if cfg['fixed_gates']['qdac_channels'] != None:
        for i in range(len(cfg['fixed_gates']['qdac_channels'])):
            ch = cfg['fixed_gates']['qdac_channels'][i]
            if ch!=None:
                ch = int(ch)
                if (ch >=1) and (ch <=24):
                    print("Ramping QDAC channel {} to {}V".format(ch,float(cfg['fixed_gates']['qdac_voltages'][i])))
                    sweep_qdac(qdac,ch,0.0,float(cfg['fixed_gates']['qdac_voltages'][i]),ramp_rate)                
    """
    
    #Set fixed DAC voltages
    if cfg['fixed_gates']['dac_channels'] != None:
        for i in range(len(cfg['fixed_gates']['dac_channels'])):
            ch = cfg['fixed_gates']['dac_channels'][i]
            if ch!=None:
                ch = int(ch)
                if (ch >=0) and (ch <=4):
                    print("Ramping DAC channel {} to {}V".format(ch,float(cfg['fixed_gates']['dac_voltages'][i])))
                    sweep_dac(dc,ch,0.0,float(cfg['fixed_gates']['dac_voltages'][i]),ramp_rate)
    
    print("Ramping DAC sweep channels to initial voltages")
    ramptime=float(np.max(np.abs(np.concatenate((xvalues[:,0],yvalues[:,0])))))/ramp_rate #set the ramp time based on largest voltage change on any given gate
    _ = dc.buffer_ramp(dac_ch,[0],np.zeros(len(dac_ch)),np.concatenate((xvalues[:,0],yvalues[:,0])),100,int(0.01*1e6), 1)
    
    #Ramp swept SIMs to initial voltage
    
    print("Ramping SIM sweep channels to initial voltages")
    if not ysim_chs is None:
        for j in range(len(ysim_chs)):
            sweep_sim(sim,ysim_chs[j],0.0,ysimvalues[j][0],ramp_rate)

    """
    print("Ramping QDAC sweep channels to initial voltages")
    if not yqdac_chs is None:
        for j in range(len(yqdac_chs)):
            sweep_qdac(qdac,yqdac_chs[j],0.0,yqdacvalues[j][0],ramp_rate)
    """
    
    DELAY_MEAS = float(sweep_parameters['delay_meas']) * cfg['lockins']['time_constant'][0] * 1e6
    print("")
    #TODO: Provide estimate of total time
    #TODO: Get Delay_Meas from Config
    
    cratio = 1.0
    
    #Alternate data-taking sweeps left-to-right then right-to-left to save time between them?
    # (True = Yes, alternate)
    
    
    for i in range(num_y):
        linetime = time.time()
        vstart = np.concatenate((xvalues[:,0],yvalues[:,i]))
        #vstart = np.concatenate(([xvalues[0,0]-(yvalues[0,i]-yvalues[0,0])],yvalues[:,i]))
        #vstart = np.concatenate(([xvalues[0,0]-cratio*(ysimvalues[0][i]-ysimvalues[0][0])],yvalues[:,i]))
        #vstart = np.concatenate(([(xvalues[0,0]-cratio*(yvalues[0][i]-yvalues[0][0]))], yvalues[:,i]))
        vstop = np.concatenate((xvalues[:,-1],yvalues[:,i]))
        #vstop = np.concatenate(([xvalues[0,-1]-(yvalues[0,i]-yvalues[0,0])],yvalues[:,i]))
        #vstop = np.concatenate(([xvalues[0,-1]-cratio*(ysimvalues[0][i]-ysimvalues[0][0])],yvalues[:,i]))
        #vstop = np.concatenate(([(xvalues[0,-1]-cratio*(yvalues[0][i]-yvalues[0][0]))],yvalues[:,i]))
        print("wait")
        time.sleep(settling_time)
        print("waited")
        print("{} of {}  --> Ramping. Points: {}".format(i + 1, num_y, num_x))
        temp1 = float(0.001)
        #temp1 = 1.5
        d_tmp = dc.buffer_ramp(dac_ch,adc_ch,vstart,vstop,int(num_x), DELAY_MEAS, int(sweep_parameters['avg_points'])) 
        dc.read()
        
        #flip the data so it goes into the file in the correct order
        #if (alternate and parity):
        #    d_tmp = np.flip(d_tmp)
        temp_avg=0.001
        
        #Rescale the data appropriately from each lockin channel using given gain settings
        data = d_tmp
        for k in range(num_lockins):
            sens = float(cfg['lockins']['sensitivity'][k])
            pa = float(cfg['lockins']['preamp_gain'][k])
            if cfg['lockins']['type'][k] == 'I':
                data[2*k] = data[2*k] * sens / 10.0 * 1e-6 / pa
                data[2*k+1] = data[2*k+1] * sens / 10.0 * 1e-6 / pa
            elif cfg['lockins']['type'][k] == 'V':
                data[2*k] = data[2*k] * sens / 10.0 / pa
                data[2*k+1] = data[2*k+1] * sens / 10.0 / pa
        
        
        #Ramp to start voltages of next sweep
        if (i<num_y-1):
            print('Ramping sweep channels to next point')
            vnext = np.concatenate((xvalues[:,0],yvalues[:,i+1]))
            ramptime=np.max(np.abs(vstop - vnext))/ramp_rate #set the ramp time based on largest voltage change on any given gate
            _ = dc.buffer_ramp(dac_ch,[0],vstop,np.concatenate((xvalues[:,0],yvalues[:,i+1])),100,int(0.01*1e6), 1)
            #_ = dc.buffer_ramp(dac_ch,[0],vstop,np.concatenate(([xvalues[0,0]-(yvalues[0,i+1]-yvalues[0,0])],yvalues[:,i+1])),100,int(ramptime*1e6/100.0), 1)
            #_ = dc.buffer_ramp(dac_ch,[0],vstop,np.concatenate(([xvalues[0,0]-cratio*(yvalues[0][i+1]-yvalues[0][0])],yvalues[:,i+1])),100,int(ramptime*1e6/100.0), 1)
            #_ = dc.buffer_ramp(dac_ch,[0],vstop,np.concatenate(([(xvalues[0,0]-cratio*(ysimvalues[0][i+1]-ysimvalues[0][0]))],yvalues[:,i+1])),100,int(ramptime*1e6/100.0), 1)
            if not ysim_chs is None:
                for j in range(len(ysim_chs)):
                    sweep_sim(sim,ysim_chs[j],ysimvalues[j][i],ysimvalues[j][i+1],ramp_rate)

            if not yqdac_chs is None:
                for j in range(len(yqdac_chs)):
                    sweep_qdac(qdac,yqdac_chs[j],yqdacvalues[j][i],yqdacvalues[j][i+1],ramp_rate)

        else:
            print('Ramping sweep channels back to 0.0V')
            ramptime=np.max(np.abs(vstop))/ramp_rate #set the ramp time based on largest voltage change on any given gate
            _ = dc.buffer_ramp(dac_ch,[0],vstop,np.zeros(len(dac_ch)),100,int(0.01*1e6), 1)
            if not ysim_chs is None:
                for j in range(len(ysim_chs)):
                    sweep_sim(sim,ysim_chs[j],ysimvalues[j][i],0.0,ramp_rate)

            if not yqdac_chs is None:
                for j in range(len(yqdac_chs)):
                    sweep_qdac(qdac,yqdac_chs[j],yqdacvalues[j][i],0.0,ramp_rate)

        
        n_y = np.linspace(0, num_x - 1, num_x)
        n_x = np.ones(num_x) * i
        probe_temp = temp_avg * np.ones(num_x)
        totdata = []
        if ysim_chs is None and yqdac_chs is None:
            totdata = np.array([n_y, n_x]+[xvalues[k] for k in range(len(xvalues))]+[yvalues[k,i]*np.ones(num_x) for k in range(len(yvalues))]+[data[k] for k in range(len(data))]+[probe_temp])
        elif ysim_chs is None and not yqdac_chs is None:
            totdata = np.array([n_y, n_x]+[xvalues[k] for k in range(len(xvalues))]+[yvalues[k,i]*np.ones(num_x) for k in range(len(yvalues))]+[data[k] for k in range(len(data))]+[probe_temp]+[yqdacvalues[k][i]*np.ones(num_x) for k in range(len(yqdacvalues))])
        elif not ysim_chs is None and yqdac_chs is None:
            totdata = np.array([n_y, n_x]+[xvalues[k] for k in range(len(xvalues))]+[yvalues[k,i]*np.ones(num_x) for k in range(len(yvalues))]+[data[k] for k in range(len(data))]+[probe_temp]+[ysimvalues[k][i]*np.ones(num_x) for k in range(len(ysimvalues))])
        else:
            totdata = np.array([n_y, n_x]+[xvalues[k] for k in range(len(xvalues))]+[yvalues[k,i]*np.ones(num_x) for k in range(len(yvalues))]+[data[k] for k in range(len(data))]+[probe_temp]+[ysimvalues[k][i]*np.ones(num_x) for k in range(len(ysimvalues))] + [yqdacvalues[k][i]*np.ones(num_x) for k in range(len(yqdacvalues))])
        
        #TODO: add a try loop here to make sure the file is able to be opened for live plotting
        dataset[i*num_x:(i+1)*num_x,:]=np.transpose(totdata)
        dataset.flush()
        
        print("%.1f s for line %i\n"% (time.time()-linetime,i+1))
        
        #parity = not parity
    
    #Set fixed SIM voltages back to 0
    if cfg['fixed_gates']['sim_channels'] != None:
        for i in range(len(cfg['fixed_gates']['sim_channels'])):
            ch = cfg['fixed_gates']['sim_channels'][i]
            if ch!=None:
                ch = int(ch)
                if (ch >=0) and (ch <=8):
                    print("Ramping SIM {} back to 0.0V".format(ch))
                    sweep_sim(sim,ch,float(cfg['fixed_gates']['sim_voltages'][i]),0.0,ramp_rate)

    """
    #Set fixed QDAC voltages back to 0
    if cfg['fixed_gates']['qdac_channels'] != None:
        for i in range(len(cfg['fixed_gates']['qdac_channels'])):
            ch = cfg['fixed_gates']['qdac_channels'][i]
            if ch!=None:
                ch = int(ch)
                if (ch >=1) and (ch <=24):
                    print("Ramping QDAC {} back to 0.0V".format(ch))
                    sweep_qdac(qdac,ch,float(cfg['fixed_gates']['qdac_voltages'][i]),0.0,ramp_rate)
    """

    #Set fixed dac voltages back to 0
    if cfg['fixed_gates']['dac_channels'] != None:
        for i in range(len(cfg['fixed_gates']['dac_channels'])):
            ch = cfg['fixed_gates']['dac_channels'][i]
            if ch!=None:
                ch = int(ch)
                if (ch >=0) and (ch <=4):
                    print("Ramping DAC channel {} back to 0".format(ch))
                    sweep_dac(dc,ch,float(cfg['fixed_gates']['dac_voltages'][i]),0.0,ramp_rate)

    print("Total time: {} minutes.".format((time.time() - time_start)/60.0))

if __name__ == '__main__':
    main()
