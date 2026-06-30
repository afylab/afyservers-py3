import numpy as np
import matplotlib.pyplot as plt
from scipy import signal
from scipy.signal import butter, sosfiltfilt
import time

def lowpass(data, fs, cutoff_hz, order=6):
    sos = butter(order, cutoff_hz, btype='low', fs=fs, output='sos')
    return sosfiltfilt(sos, data)

def main():
	import labrad
	cxn = labrad.connect()
	da = cxn.dac_adc_giga
	da.select_device()

	for i in range(8):
		da.set_voltage(i, 0)

	da.set_voltage(0,0.05) #on channell

	print('waiting for voltages to settle')
	time.sleep(20)

	#Begin Averaging spectrum for 0V and 50mV

	Pspecs_sig = []
	freqs_sig = []

	Pspecs_bg = []
	freqs_bg = []

	cohs = []
	csds = []

	print('setting conversion time')
	set_convtime = 500
	true_convtime = da.set_conversiontime(0, set_convtime)
	print('set conversion time')

	fs = 1.0/(true_convtime)*1e6
	cutoff = fs / 2.0
	
	print('start data acquisition for background 0V')
	for i in range(10):
		print(i)
		out = da.time_series_adc_read([0], set_convtime, 50000*true_convtime + 500)
		print('finished adc read')
		#bg = out[1]/100.0 - np.mean(out[1])/100.0
		sig = out[0]/100.0 - np.mean(out[0])/100.0

		#bg = lowpass(bg, fs, cutoff)
		sig = lowpass(sig, fs, cutoff)
		#f_bg, P_den_bg = signal.welch(bg, fs, nperseg=10000, scaling='density') 
		f_sig, P_den_sig = signal.welch(sig, fs, nperseg=2000, scaling='density') 
		#_, csd_gnd_sig = signal.csd(sig, bg, fs, nperseg=10000, scaling='density')
		#_, coherence = signal.coherence(sig, bg, fs, nperseg=500)

		#Pspecs_bg.append(np.array(P_den_bg))
		Pspecs_sig.append(np.array(P_den_sig))
		#cohs.append(np.array(coherence))
		#csds.append(np.array(csd_gnd_sig))
		#freqs_bg.append(np.array(f_bg))
		freqs_sig.append(np.array(f_sig))

	#avg_pspec_bg = []
	avg_pspec_sig = []
	#avg_csd = []
	#avg_coh = []

	for i in range(len(Pspecs_sig)):
		if i == 0:
			#avg_pspec_bg = Pspecs_bg[i]
			avg_pspec_sig = Pspecs_sig[i]
			#avg_csd = csds[i]
			#avg_coh = cohs[i]

		else:
			#avg_pspec_bg += Pspecs_bg[i]
			avg_pspec_sig += Pspecs_sig[i]
			#avg_csd += csds[i]
			#avg_coh += cohs[i]

	#avg_pspec_bg = 1.0/len(Pspecs_bg) * avg_pspec_bg
	avg_pspec_sig = 1.0/len(Pspecs_sig) * np.array(avg_pspec_sig)
	#avg_csd = 1.0/len(avg_csd) * avg_csd
	#avg_coh = 1.0/len(avg_coh) * avg_coh

	#added_noise = avg_pspec_sig - avg_pspec_bg  #+ 2*np.real(avg_csd)
	#added_noise[added_noise < 0] = np.mean(added_noise)

	#plt.loglog(freqs_sig[0], np.sqrt(avg_pspec_bg)*1e9)
	plt.loglog(freqs_sig[0], np.sqrt(avg_pspec_sig)*1e9)
	#plt.semilogx(freqs_sig[0], avg_coh)
	plt.xlabel('frequency (Hz)', size = 15)
	plt.ylabel('Spectral Density [nV/$\\sqrt{Hz}$]')
	plt.show()

	#np.savetxt('/Users/liamcohen/Documents/sp2_Quantum/DAC_Testing_Data/DA_001_2026/ch2_psd.txt ', np.column_stack([freqs_sig[0], avg_pspec_sig, avg_pspec_bg]),
    #       header='freq_Hz  psd_sig  psd_bg',
    #       fmt='%.8e')

if __name__ == "__main__":
	main()