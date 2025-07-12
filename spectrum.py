import numpy as np

def get_spectrum(adc_ch, conv_time, num_avgs):
    data = []
    for i in range(num_avgs):
        x = da.time_series_adc_read([adc_ch], conv_time, 1e6)
        if i == 0:
            data = x[0]
        else:
            data += x[0]
    
    data = 1.0/num_avgs * np.array(data)
    N = len(data)
    sample_time = int(da.get_conversion_time(adc_ch) * 1.5) * 1e-6
    
    fft = np.sqrt(N * sample_time) * np.fft.rfft(data, norm='forward')
    fftfreqs = np.fft.rfftfreq(N, d=sample_time)
    
    return fft, fftfreqs
    