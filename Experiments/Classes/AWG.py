# -*- coding: utf-8 -*-
"""
Created on Fri Aug 23 10:16:17 2024

@author: ejporter


Class for generating AWG pulses for Bragg experiments
"""


import numpy as np
from scipy.signal import gaussian
import matplotlib.pyplot as plt
import pyvisa

class WaveformGenerator:
    def __init__(self, sample_rate=10e6):
        self.sample_rate = sample_rate  # Samples per second
        self.time_array = np.array([])
        self.amplitude_array = np.array([])
        self.max = 1

    def add_square_pulse(self, start_time, duration, amplitude):
        t = np.arange(start_time, start_time + duration, 1/self.sample_rate)
        pulse = np.full_like(t, amplitude)
        self._append_pulse(t, pulse)

    def add_gaussian_pulse(self, start_time, duration, amplitude, std_dev):
        t = np.arange(start_time, start_time + duration, 1/self.sample_rate)
        t_centered = t - (start_time + duration / 2)
        pulse = amplitude * np.exp(-t_centered**2 / (2 * std_dev**2))
        self._append_pulse(t, pulse)
        
    def add_sigmoid_pulse(self, start_time, duration, amplitude, sigma, sign):
        t = np.arange(start_time, start_time + duration, 1/self.sample_rate)
        t_offset = start_time+duration/2  
        pulse = amplitude/(1 + np.exp(-sign*(t-t_offset)/sigma))
        pulse[0] = 0
        self._append_pulse(t, pulse)
        
    def add_point(self, t, V):
        self._append_pulse(np.array([t]), np.array([V]))
        
        

    def _append_pulse(self, t, pulse):
        if len(self.time_array) == 0:           
            # gap = np.arange(0, t[0], 1/self.sample_rate)
            # gap_amplitude = np.zeros_like(gap)
            
            self.time_array = t
            self.amplitude_array = pulse
        
        else:
            last_time = self.time_array[-1]
            if t[0] > last_time:
                # Fill in the gap with zeros if there's a delay
                gap = np.arange(last_time, t[0], 1/self.sample_rate)
                gap_amplitude = np.zeros_like(gap)
                self.time_array = np.concatenate([self.time_array, gap])
                self.amplitude_array = np.concatenate([self.amplitude_array, gap_amplitude])
            self.time_array = np.concatenate([self.time_array, t])
            self.amplitude_array = np.concatenate([self.amplitude_array, pulse])

    def get_waveform(self):
        self.max = np.max(self.amplitude_array)
        self.amplitude_array = self.amplitude_array/self.max
        return self.time_array, self.amplitude_array
        

    def reset_waveform(self):
        self.time_array = np.array([])
        self.amplitude_array = np.array([])








