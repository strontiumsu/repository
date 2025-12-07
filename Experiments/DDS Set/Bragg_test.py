# -*- coding: utf-8 -*-
"""
Created on Thu Sep 11 19:04:17 2025

@author: sr
"""


from artiq.experiment import *
import numpy as np

from BraggClass import _Bragg
from artiq.coredevice.ad9910 import PHASE_MODE_TRACKING

class Bragg_test(EnvExperiment):


    def build(self):
        self.setattr_device("core")
        self.bragg=_Bragg(self)

        self.setattr_argument("Dipole", BooleanValue(False))
        self.setattr_argument("Bragg1", BooleanValue(False))
        self.setattr_argument("Bragg2", BooleanValue(False))
        self.setattr_argument("Lattice", BooleanValue(False))

        self.t0 = np.int64(0)
        self.setattr_device("ttl5") # triggering pulse


    def prepare(self):
        self.bragg.prepare_aoms()

    @kernel
    def run(self):
        self.t0 = now_mu()

        switch_state = ((1<<0 if self.Dipole  else 0) |
                       (1<<1 if self.Bragg1  else 0) |
                       (1<<2 if self.Bragg2  else 0) |
                       (1<<3 if self.Lattice else 0) )
        self.core.reset()
        self.bragg.init_aoms(switches=switch_state) 
        delay(1*ms)
        
        self.bragg.aom_bragg1.set(2*MHz, phase=0.0, phase_mode=PHASE_MODE_TRACKING, ref_time_mu=self.t0, profile=0);
        self.bragg.aom_bragg2.set(4*MHz, phase=0.5, phase_mode=PHASE_MODE_TRACKING, ref_time_mu=self.t0, profile=0)
        self.ttl5.on()       # for triggering start
        
        self.bragg.aom_bragg1.sw.on()
        self.bragg.aom_bragg2.sw.on()
        delay(1*ms)
        self.bragg.aom_bragg1.sw.off()
        self.bragg.aom_bragg2.sw.off()
        self.ttl5.off()       # for triggering start
