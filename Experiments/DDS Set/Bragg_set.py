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

        self.setattr_argument("Dipole", BooleanValue(False))
        self.setattr_argument("Bragg1", BooleanValue(False))
        self.setattr_argument("Bragg2", BooleanValue(False))
        self.setattr_argument("Lattice", BooleanValue(False))

        

    def prepare(self):
        self.bragg.prepare_aoms()

    @kernel
    def run(self):
        switch_state = ((1<<0 if self.Dipole  else 0) |
                       (1<<1 if self.Bragg1  else 0) |
                       (1<<2 if self.Bragg2  else 0) |
                       (1<<3 if self.Lattice else 0) )
        self.core.reset()
        self.bragg.init_aoms(switches=switch_state) 
        delay(1*ms)
        
        
        
        
        
        
        
        

        # if not self.Dipole: self.bragg.AOMs_off(["Dipole"])
        # if not self.Bragg1: self.bragg.AOMs_off(["Bragg1"])
        # if not self.Bragg2: self.bragg.AOMs_off(["Bragg2"])
        # if not self.Lattice: self.bragg.AOMs_off(["Lattice"])
# self.aoms_off = []
        # if not self.Dipole:self.aoms_off.append('Dipole')
        # if not self.Bragg1:self.aoms_off.append('Bragg1')
        # if not self.Bragg2:self.aoms_off.append('Bragg2')
        # if not self.Lattice:self.aoms_off.append('Lattice')