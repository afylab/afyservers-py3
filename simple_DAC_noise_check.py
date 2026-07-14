import numpy as np
import matplotlib.pyplot as plt
from scipy import signal
from scipy.signal import butter, sosfiltfilt

def lowpass(data, fs, cutoff_hz, order=8):
    sos = butter(order, cutoff_hz, btype='low', fs=fs, output='sos')
    return sosfiltfilt(sos, data)

def main():
	import labrad
	cxn = labrad.connect()
	da = cxn.dac_adc_giga
	da.select_device()

	da.set_voltage(0, 0.05)
	true_convtime = da.set_conversiontime(0, 2602)

	Pspecs = []
	freqs = []

	for i in range(5):
		print(i)
		out = da.dac_led_buffer_ramp([0], [0], [0.05], [0.05], 5000, 4000, 1000, 1)
		out_sub = out[0]/100.0 - np.mean(out[0])/100.0
		f, P_den = signal.welch(out_sub, 1.0/4000.0*1e6, nperseg=1024, scaling='density') 
		Pspecs.append(np.array(P_den))
		freqs.append(np.array(f))

	avg_pspec = []
	for i in range(len(Pspecs)):
		if i == 0:
			avg_pspec = Pspecs[i]
		else:
			avg_pspec += Pspecs[i]

	avg_pspec = 1.0/len(Pspecs) * avg_pspec
	cutoff = 1.0/4000.0*1e6 / 2.0 * 0.8
	avg_pspec = lowpass(avg_pspec, 1.0/4000.0*1e6, cutoff)
	plt.loglog(freqs[0], np.sqrt(avg_pspec)*1e9)
	plt.xlabel('frequency (Hz)', size = 15)
	plt.ylabel('Spectral Density [nV/$\\sqrt{Hz}$]')
	plt.show()

if __name__ == "__main__":
	main()