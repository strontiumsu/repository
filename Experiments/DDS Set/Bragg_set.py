# -*- coding: utf-8 -*-
"""
Created on Thu Jun 15 13:50:24 2023

@author: sr
"""


from artiq.experiment import *
import numpy as np

from BraggClass import _Bragg

class Bragg_set(EnvExperiment):


    def build(self):
        self.setattr_device("core")
        self.bragg=_Bragg(self)
        self.setattr_device("ttl6") # triggering pulse

        self.setattr_argument("Dipole", BooleanValue(False))
        self.setattr_argument("Sideband", BooleanValue(False))
        self.setattr_argument("Push", BooleanValue(False))
        self.setattr_argument("Lattice", BooleanValue(False))

        

    def prepare(self):
        self.bragg.prepare_aoms()

    @kernel
    def run(self):
        switch_state = ((1<<0 if self.Dipole  else 0) |
                       (1<<1 if self.Sideband  else 0) |
                       (1<<2 if self.Push  else 0) |
                       (1<<3 if self.Lattice else 0) )
        
        
        self.core.reset()
        
        if self.Push: self.ttl6.on()
        self.bragg.init_aoms(switches=switch_state) 
        delay(1*ms)
        
        
        
        
        
        
        