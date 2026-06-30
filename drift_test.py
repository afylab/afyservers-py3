import numpy as np
import matplotlib.pyplot as plt
from scipy import signal
from scipy.signal import butter, sosfiltfilt
import time
import labrad

def lowpass(data, fs, cutoff_hz, order=6):
    sos = butter(order, cutoff_hz, btype='low', fs=fs, output='sos')
    return sosfiltfilt(sos, data)

def main():
	cxn = labrad.connect()
	da = cxn.dac_adc_giga
	da.select_device()

	for i in range(8):
		da.set_voltage(i, 0)

	da.set_voltage(0,0.05) #on channell

	print('waiting for voltages to settle')
	time.sleep(30)

	print('setting conversion time')
	set_convtime = 2600
	true_convtime = da.set_conversiontime(0, set_convtime)
	print(true_convtime)
	print('set conversion time')

	drift_data = []
	time_data = []
	sample_rate = 10 #sample rate in seconds
	total_time = 5 #number of minutes
	avgs = 100

	time_start = time.time()
	while (time.time() - time_start) < total_time * 60.0:
		time_data.append(time.time() - time_start)

		data_pt = 0
		for i in range(avgs):
			data_pt += da.read_voltage(0) / 100.0
		data_pt = data_pt / avgs
		print(data_pt*1e6)
		drift_data.append(data_pt)
		time.sleep(sample_rate)

	plt.plot(time_data, (drift_data - np.mean(drift_data)) * 1e6, 'ro-')
	#plt.loglog(freqs_sig[0], np.sqrt(avg_pspec_bg)*1e9)
	#plt.loglog(freqs_sig[0], np.sqrt(avg_pspec_sig)*1e9)
	#plt.semilogx(freqs_sig[0], avg_coh)
	plt.xlabel('time (s)', size = 15)
	plt.ylabel(' $\\Delta V_{DAC}$ Voltage [$\\mu$V]', size=15)
	plt.title('DAC Output = 50mV', size=15)
	plt.ylim((-2, 2))
	plt.show()

	#np.savetxt('/Users/liamcohen/Documents/sp2_Quantum/DAC_Testing_Data/DA_001_2026/ch2_psd.txt ', np.column_stack([freqs_sig[0], avg_pspec_sig, avg_pspec_bg]),
    #       header='freq_Hz  psd_sig  psd_bg',
    #       fmt='%.8e')

if __name__ == "__main__":
	main()