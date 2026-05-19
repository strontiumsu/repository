# -*- coding: utf-8 -*-
"""
Created on Fri May 15 14:05:59 2026

@author: sr
"""

from scan_framework import Scan1D, FreqScan
from artiq.experiment import *
import numpy as np
from artiq.coredevice import ad9910


from CoolingClass import _Cooling
from BraggClass import _Bragg
from scipy import constants

class amp_ramp_test_exp(Scan1D, FreqScan, EnvExperiment):

    def build(self, **kwargs):
        # required initializations

        super().build(**kwargs)
        self.setattr_device("ttl5")
    

        self.enable_pausing = True
        self.enable_auto_tracking = False
        self.enable_profiling = False

        self.Bragg = _Bragg(self)

        # scan settings
        self.scan_arguments(frequencies = {'start':0.5e3,
            'stop':250*1e3,
            'npoints':20,
            'unit':"kHz",
            'scale':kHz,
            'global_step':0.1*kHz,
            'ndecimals':2},
            nbins = {'default':1000},
            nrepeats = {'default':1},
            npasses = {'default':1},
            fit_options = {'default':"Fit and Save"}
            )

        self.atten_list= np.full(1024, 10.0)
        self.atten_list_ram = np.full(1024, 1)
    def prepare(self):
        self.Bragg.prepare_aoms()

    @kernel
    def before_scan(self):

        self.core.reset()
        self.Bragg.init_aoms(switches=0x9)
        
        delay(50*ms)
        self.Bragg.aom_lattice.sw.off()
        
    @kernel
    def before_measure(self, point, measurement):
        self.load_mod(self.Bragg.aom_lattice, 0.1, 0.8, point)
        delay(100*ms)
        self.core.wait_until_mu(now_mu())
        
    @kernel
    def measure(self, point):
        self.core.reset()
        delay(100*ms)
        self.ttl5.on()
        self.Bragg.aom_lattice.cpld.io_update.pulse_mu(8)
        self.Bragg.aom_lattice.sw.on()
        delay(1*ms)
        self.Bragg.aom_lattice.sw.off()
        self.ttl5.off()
        delay(50*ms)
        return 0
    
    @kernel
    def load_mod(self, dds, ai, af, freq):  
        N_CYCLES_IN_RAM = 8   # was 2
        
        PERIOD_TICKS = int(N_CYCLES_IN_RAM / freq / (4*ns) + 0.5)  # round, not truncate
        N_words = 1024
        step = (PERIOD_TICKS + N_words // 2) // N_words            # round
        if step < 1:
            step = 1
        if step > 65535:
            step = 65535
        
        n_cycles = N_CYCLES_IN_RAM
        mean      = 0.5 * (ai + af)
        half_diff = 0.5 * (ai - af)
        two_pi    = 6.283185307179586
        dphi      = two_pi * n_cycles / N_words
        for i in range(N_words):
            self.atten_list[i] = mean + half_diff * np.sin(dphi * i)
        # PERIOD_TICKS = int(2/freq/(4*ns))  
        
        # # Use the full 1024-word table, choose step so N_words * step = PERIOD_TICKS
        # N_words = 1024
        # step = PERIOD_TICKS // N_words   # = 488 ticks -> 2.0014 ms total
        # if step < 1:
        #     step = 1
        # if step > 65535:
        #     step = 65535
        
        # # Number of sine cycles to fit into the 2 ms window
        # # freq=500 Hz -> 1 cycle; freq=250 kHz -> 500 cycles
        # n_cycles = 2   # float; non-integer is fine, phase just won't wrap cleanly
        
        # # Build the table: phase advances by (2*pi * n_cycles / N_words) per entry
        # mean      = 0.5 * (ai + af)
        # half_diff = 0.5 * (ai - af)
        # two_pi    = 6.283185307179586
        # dphi      = two_pi * n_cycles / N_words
        # for i in range(N_words):
        #     self.atten_list[i] = mean + half_diff * np.sin(dphi * i)
        # (No unused tail; N_words = 1024)
        
                      

        dds.amplitude_to_ram(self.atten_list, self.atten_list_ram)
        
        self.core.break_realtime()
        delay(10*ms)

        # Disable RAM before programming
        dds.set_cfr1(ram_enable=0)
        dds.cpld.io_update.pulse_mu(8)
        
        delay(5*ms)

        # RAM sweep from index 0 to 1023, profile 0
        dds.set_profile_ram(
            start=0,
            end=1023,
            step=(step | (2**6 - 1) << 16),
            profile=0,
            mode=ad9910.RAM_MODE_CONT_RAMPUP
        )

        delay(25*ms)
        dds.cpld.set_profile(0)
        dds.cpld.io_update.pulse_mu(8)
        
        
        self.core.break_realtime()
        delay(10*ms)
        dds.write_ram(self.atten_list_ram)
 
        delay(10*ms)

        dds.set_cfr1(
            internal_profile=0,
            ram_enable=1,
            ram_destination=ad9910.RAM_DEST_ASF
        )
        delay(5*ms)
        dds.set_frequency(80*MHz)
        
        
        self.core.wait_until_mu(now_mu())
        