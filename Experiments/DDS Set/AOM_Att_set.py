# -*- coding: utf-8 -*-
"""
Created on Fri Apr  4 12:40:23 2025

@author: sr
"""

# -*- coding: utf-8 -*-
"""
Created on Thu Jun 15 13:50:24 2023

@author: sr
"""


from artiq.experiment import *
import numpy as np

from BraggClass import _Bragg

class AOM_Att_set(EnvExperiment):


    def build(self):
        self.setattr_device("core")
        self.setattr_device("ttl5") # triggering pulse
        self.bragg=_Bragg(self)

        self.setattr_argument("Dipole", BooleanValue(False))
        self.setattr_argument("Bragg1", BooleanValue(False))
        self.setattr_argument("Bragg2", BooleanValue(False))
        self.setattr_argument("Lattice", BooleanValue(False))

        self.aoms_off = []
        if not self.Dipole:self.aoms_off.append('Dipole')
        if not self.Bragg1:self.aoms_off.append('Bragg1')
        if not self.Bragg2:self.aoms_off.append('Bragg2')
        if not self.Lattice:self.aoms_off.append('Lattice')
        
        self.Npts = 10
        
        self.atten_list =  np.linspace(2,30.0,60)


    def prepare(self):
        self.bragg.prepare_aoms()

    @kernel
    def run(self):
        self.core.reset()
        self.bragg.init_aoms(on=True)
        
        if self.Dipole: self.bragg.AOMs_on(["Dipole"])
        if self.Bragg1: self.bragg.AOMs_on(["Bragg1"])
        if self.Bragg2: self.bragg.AOMs_on(["Bragg2"])
        if self.Lattice: self.bragg.AOMs_on(["Lattice"])
        
        self.bragg.AOMs_off(["Bragg1"])
                
        delay(2000*ms)
        self.ttl5.on()
        delay(500*ms)
        self.ttl5.off()
        
        delay(100*ms)
        self.bragg.AOMs_on(["Bragg1"])
        
        for att in self.atten_list:
            self.bragg.set_AOM_attens([("Bragg1", att)])
       
            delay(2000*ms)
            self.ttl5.on()
            delay(1*ms)
            self.ttl5.off()
            
        
        
        
