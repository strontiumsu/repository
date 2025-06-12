# -*- coding: utf-8 -*-
"""
Created on Mon Nov  4 11:01:45 2024

@author: ejporter
"""

from artiq.experiment import *
from scan_framework import Scan1D
import numpy as np

from BraggClass import _Bragg
from repository.models.scan_models import RabiModel


class bare_cavity_duak_scan_exp(Scan1D, EnvExperiment):
    
    def build(self, **kwargs):
        
        super().build(**kwargs)
        self.setattr_device("ttl5") # triggering pulse

        # import classes for experiment control

        self.Bragg = _Bragg(self)

        
                # attributes here
        self.enable_pausing = True # disable to speed up by not checking scheduler
        self.enable_auto_tracking=False
        self.enable_profiling = False # enable to print runtime statistics to find bottlenecks
        
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
        # return the set of scan points to the framework
        return self.pulse_spacing
        
        
        
    def prepare(self):
        self.Bragg.prepare_aoms()       
        self.enable_histograms = True
        


    @kernel 
    def before_scan(self):
        self.core.reset()
        self.ttl5.off()


        self.Bragg.init_aoms(on=True)
        self.Bragg.AOMs_off(["Bragg1", "Bragg2"])  
        delay(100*ms)

        
        self.core.wait_until_mu(now_mu())
     
        
    @kernel
    def measure(self, point):
        self.core.reset()
        delay(1 * ms)

        # before this point is just for preparing the RAM and RIGOL
        self.core.break_realtime()
        delay(10*ms)
        self.Bragg.set_AOM_attens([("Bragg1", self.Bragg.atten_Bragg1)])      
        delay(10 * ms)

        self.run_exp()
            
        
        delay(self.pause_time)
        self.core.wait_until_mu(now_mu())
        return 0
     
    
    @kernel
    def run_exp(self):
                        
        self.ttl5.on()
        
        self.Bragg.AOMs_on(["Bragg1"])
        delay(self.probe_time)
        self.Bragg.AOMs_off(["Bragg1"])
        delay(self.delay_time)
        self.Bragg.AOMs_on(["Bragg1"])
        delay(self.probe_time)
        self.Bragg.AOMs_off(["Bragg1"])
        
        self.ttl5.off()
            
        
    