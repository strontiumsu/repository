# -*- coding: utf-8 -*-
"""
Created on Wed Jun 11 17:22:54 2025

@author: ejporter
"""

from artiq.experiment import *
from scan_framework import Scan1D
import numpy as np
from artiq.coredevice import ad9910

from CoolingClass import _Cooling
from BraggClass import _Bragg
from repository.models.scan_models import LinearModel

from time import sleep

class cavity_calib_exp(Scan1D, EnvExperiment):

    def build(self, **kwargs):
        
        super().build(**kwargs)
        self.setattr_device("ttl5") # triggering pulse

        # import classes for experiment control
        self.MOTs = _Cooling(self)
        self.Bragg = _Bragg(self)

        self.enable_auto_tracking=False

        self.setattr_argument('offsets_freqs', 
            Scannable(default=RangeScan(
            start=0*kHz,
            stop=500*kHz,
            npoints=6),
            scale=100*kHz,
            ndecimals=1,
            unit="kHz"))
        self.setattr_argument("freq_center", 
                              NumberValue(
                                  3*1e6,
                                  min=0.1*1e6,
                                  max=200.0*1e6,
                                  scale=1e6,
                                  unit="MHz",
                                  ndecimals = 3),
                              "parameters")     
        self.setattr_argument("freq_width", 
                              NumberValue(
                                  1*1e6,
                                  min=-10.0*1e6,
                                  max=10.0*1e6,
                                  scale=1e6,
                                  unit="MHz"),
                              "parameters")
        self.setattr_argument("scan_time", 
                              NumberValue(
                                  100*1e-6,
                                  min=1*1e-6,
                                  max=50000*1e-6,
                                  scale=1e-6,
                                  unit='us'),
                              "parameters")

        # create GUI arguments for configuring the scan
        self.scan_arguments(
            nbins = {'default':1000},
            nrepeats = {'default':1},
            npasses = {'default':1},
            fit_options = {'default':"Fit and Save"}
            )
        
        self.freq_list= np.linspace(0.0*MHz, 0.0*MHz, 1024)
        self.freq_list_ram = np.full(1024, 1)
        self.step_size=0


    def get_scan_points(self):
        # return the set of scan points to the framework
        return self.offsets_freqs

    def prepare(self):
        self.MOTs.prepare_aoms()
        self.MOTs.prepare_coils()
        self.Bragg.prepare_aoms()

        self.model = LinearModel()
        self.register_model(self.model, measurement=False, fit=True)

    @kernel
    def load_scan(self, freqs, dds):
        self.step_size = int(self.scan_time/(1024*4*ns))
        f0 = self.freq_center + self.freq_width/2
        if self.freq_width/2 > self.freq_center: raise Exception("Bad Range")
        

        self.freq_list = freqs[::-1]
            
        dds.frequency_to_ram(self.freq_list, self.freq_list_ram)

        self.core.break_realtime()
        delay(10 * ms)

        dds.set(self.freq_center - self.freq_width/2, amplitude=self.Bragg.scale_Bragg1)

        delay(1 * ms)



        dds.set_cfr1(ram_enable=0)
        dds.cpld.io_update.pulse_mu(8)

        dds.set_profile_ram(start=0, end=1024-1, step=(self.step_size | (2**6 - 1 ) << 16),
                                  profile=0, mode=ad9910.RAM_MODE_RAMPUP)
        dds.cpld.set_profile(0)

        delay(100*us) # needs 2x delays here not to throw RTIOUnderflow Error?????
        delay(100*us)

        dds.cpld.io_update.pulse_mu(8)
        delay(100*us)
        dds.write_ram(self.freq_list_ram)
        # prepare to enable ram and set frequency as target
        delay(10 * us)
        dds.set_cfr1(internal_profile=0, ram_enable=1, ram_destination=ad9910.RAM_DEST_FTW)
        delay(10*ms)

        self.core.wait_until_mu(now_mu())


    def measure(self, point):
        pass
    

    @kernel
    def before_scan(self):


    @kernel
    def run_exp()