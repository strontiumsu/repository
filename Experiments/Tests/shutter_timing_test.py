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

        self.setattr_device("ttl5")
        self.setattr_device("zotino0")
        # self.dac_0=self.get_device("zotino0")
        self.MOTs = _Cooling(self)

    @kernel    
    def run(self):
        self.core.reset()
        self.zotino0.init()
        delay(10*ms)
        
        self.open_461()
        delay(10*ms)        
        
        self.ttl5.on()
        self.close_461()
        delay(5*ms)
        self.ttl5.off()
        self.open_461()
        
        
    @kernel
    def open_461(self):
        delay(-3.0*ms)
        self.dac_set(4, 4.0)
        delay(3.0*ms)
        delay(10*us)

    # 
    @kernel
    def close_461(self):
        delay(-2.5*ms)
        self.dac_set(4, 0.0)
        delay(2.5*ms)
        delay(10*us)
        
    @kernel
    def dac_set(self, ch, val):
        self.zotino0.set_dac([val], [ch])
        #delay(10*us)
        #self.dac_0.write_dac(ch, val)
        #self.dac_0.load()
 

       