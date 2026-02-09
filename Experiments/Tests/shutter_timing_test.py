# -*- coding: utf-8 -*-
"""
Created on Thu Feb  2 11:17:41 2023

@author: E. Porter
"""

# make available artiq classes for us

from artiq.experiment import EnvExperiment, kernel, ms,us,s, NumberValue, delay, parallel, sequential, now_mu,BooleanValue

# imports
import numpy as np
from CoolingClass import _Cooling


class shutter_timing_test_exp(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.setattr_device("scheduler")
        self.setattr_device("ttl5")
        self.MOTs = _Cooling(self)
        
        self.setattr_argument("pulses", NumberValue(5,min=0, max=100), "parameters")


    def prepare(self):
        # initial datasets for the aoms and mot coils, does not run on core
        self.MOTs.prepare_aoms()
        self.MOTs.prepare_coils()

        
    def run(self):
        # initial devices
        self.init_exp()     
        self.run_exp()
        self.cleanup()


    @kernel 
    def init_exp(self):
        self.core.reset()
        delay(10*ms)
        self.MOTs.init_coils()
        self.MOTs.init_ttls()
        self.MOTs.init_aoms(on=False)
        delay(10*ms)
        
        self.core.wait_until_mu(now_mu())
        
        
    @kernel
    def run_exp(self):
        self.core.reset()
        delay(10*ms)
        self.MOTs.close_repumpers()
        delay(10*ms)
        self.MOTs.aom_3P0.sw.on()
        self.MOTs.aom_3P2.sw.on()
        delay(10*ms)
        for i in range(int(self.pulses)):            
            
            self.ttl5.on()
            self.MOTs.open_repumpers()
            delay(5*ms)
            
            self.ttl5.off()
            self.MOTs.close_repumpers() 
            delay(10*ms)
            
    @kernel
    def cleanup(self):
        self.core.reset()
        delay(20*ms)
        for i in range(3):
            self.MOTs.urukul_channels[i].sw.on()
        self.MOTs.atom_source_on()
        
         
    
       