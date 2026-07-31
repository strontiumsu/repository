# -*- coding: utf-8 -*-
"""
Quick test for _Bragg.lattice_rampdown.

Ramps the lattice AOM off (attenuation ramped up to ramp_end_atten) and back on
(attenuation snapped back to atten_Lattice) a few times so the ramp can be viewed
on a scope / photodiode. ttl5 is pulsed high around each cycle as a scope trigger.
Nothing else.
"""


from artiq.experiment import *

from BraggClass import _Bragg


class LatticeRampdownTest(EnvExperiment):

    def build(self):
        self.setattr_device("core")
        
        self.setattr_device("ttl5")          # scope trigger
        self.Bragg = _Bragg(self)

    def prepare(self):
        self.Bragg.prepare_aoms()


    @kernel
    def run(self):
        self.core.reset()
        self.Bragg.dac_0.init()
        self.Bragg.init_aoms(switches=0x9)  # Dipole + Lattice on

        delay(1*ms)

        self.ttl5.on()
        self.Bragg.dipole_rampdown()
        self.ttl5.off()
        delay(1*ms)
        self.ttl5.on()
        self.Bragg.dipole_rampup()
        delay(1*ms)
        self.ttl5.off()
        




        self.Bragg.dac_set(6, 9.99)

        