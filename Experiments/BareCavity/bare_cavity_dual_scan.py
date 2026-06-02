# -*- coding: utf-8 -*-
"""
Created on Mon Nov  4 11:01:45 2024

@author: ejporter
"""


#imports
from artiq.experiment import EnvExperiment, RangeScan, Scannable, kernel, ms, NumberValue, delay, now_mu, us # pyright: ignore[reportMissingImports]
from scan_framework import Scan1D
import numpy as np

from BraggClass import _Bragg
from repository.models.scan_models import RabiModel # pyright: ignore[reportMissingImports]


class bare_cavity_dual_scan_exp(Scan1D, EnvExperiment):
    
    def build(self, **kwargs):
        
        super().build(**kwargs)
        self.Bragg = _Bragg(self)
        self.enable_auto_tracking = False
        
        # Arguments 
        self.setattr_argument('pulse_spacing', Scannable(default=RangeScan(
            start=10*us,
            stop=10.01*us,
            npoints=10),
            scale=1e-6,
            ndecimals=4,
            unit="us"))
        
        self.scan_arguments(nbins={'default':1000},
                    nrepeats={'default':1},
                    npasses={'default':1},
                    fit_options={'default':"No Fits"})
                  
        
        self.setattr_argument("probe_time", 
                              NumberValue(
                                  100*1e-6,
                                  min=1*1e-6,
                                  max=5000*1e-6,
                                  scale=1e-6,
                                  unit='us'),
                              "parameters")
        
        self.setattr_argument("delay_time", 
                              NumberValue(
                                  100*1e-6,
                                  min=1*1e-6,
                                  max=50000*1e-6,
                                  scale=1e-6,
                                  unit='us'),
                              "parameters")
        
        self.setattr_argument("pause_time", 
                              NumberValue(
                                  2.0,
                                  min=0.1,
                                  max=5.0,
                                  scale=1e0,
                                  unit='s'),
                              "parameters")


        
    def get_scan_points(self):
        return self.pulse_spacing
        
        
    def prepare(self):
        self.Bragg.prepare_aoms()       
        
    @kernel 
    def before_scan(self):
        self.core.reset()
        self.MOTs.ttl5.off()

        self.Bragg.init_aoms(on=True)
        self.Bragg.aom_sideband.sw.off()
        self.Bragg.aom_carrier.sw.off()
        delay(15*ms)

        
        
    @kernel
    def measure(self, point):
        self.core.wait_until_mu(now_mu())
        delay(10 * ms)

        self.Bragg.aom_sideband.set_att(self.Bragg.atten_Sideband)      
        delay(1 * ms)


        # probe cavity once with sideband AOM
        self.MOTs.ttl5.on()    
        self.Bragg.self.aom_sideband.sw.on()
        delay(self.probe_time)
        self.Bragg.aom_sideband.sw.off()

        delay(self.delay_time)

        # probe second time with sideband AOM
        self.Bragg.aom_sideband.sw.on()
        delay(self.probe_time)
        self.Bragg.aom_sideband.sw.off()    
        self.MOTs.ttl5.off()
   
        return 0
     

        
            
        
    