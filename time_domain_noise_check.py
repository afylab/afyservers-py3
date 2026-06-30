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

	da.set_voltage(7,0.05) #on channell

	print('waiting for voltages to settle')
	time.sleep(20)

	print('setting conversion time')
	set_convtime = 500
	true_convtime = da.set_conversiontime(0, set_convtime)
	print(true_convtime)
	print('set conversion time')
	
	out = da.time_series_adc_read([0], set_convtime, 25000*true_convtime)
	sig = out[0]/100.0 - np.mean(out[0])/100.0
	sig = 1e6 * lowpass(sig, 1.0/true_convtime*1e6, 0.5 * 1.0/true_convtime*1e6 * 0.8)
	time_data = 1/0.75 * true_convtime * np.linspace(0, len(sig)-1, len(sig)) * 1e-6
	plt.plot(time_data, sig)
	#plt.loglog(freqs_sig[0], np.sqrt(avg_pspec_bg)*1e9)
	#plt.loglog(freqs_sig[0], np.sqrt(avg_pspec_sig)*1e9)
	#plt.semilogx(freqs_sig[0], avg_coh)
	plt.xlabel('time (s)', size = 15)
	plt.ylabel(' $\\Delta V_{DAC}$ Voltage [$\\mu$V]', size=15)
	plt.title('DAC Output = 50mV', size=15)
	plt.ylim((-15, 15))
	plt.show()

	#np.savetxt('/Users/liamcohen/Documents/sp2_Quantum/DAC_Testing_Data/DA_001_2026/ch2_psd.txt ', np.column_stack([freqs_sig[0], avg_pspec_sig, avg_pspec_bg]),
    #       header='freq_Hz  psd_sig  psd_bg',
    #       fmt='%.8e')

if __name__ == "__main__":
	main()