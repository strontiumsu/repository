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

        # relevant ramp variables
        self.setattr_argument("ramp_end_atten",
            NumberValue(30.0, min=1.0, max=31.5, unit="dB", ndecimals=1),
            "Lattice ramp")                  # attenuation ramped to = lattice "off"
        self.setattr_argument("ramp_time",
            NumberValue(5.0*ms, min=0.1*ms, max=200.0*ms, scale=ms, unit="ms", ndecimals=2),
            "Lattice ramp")                  # duration of each ramp-down
        self.setattr_argument("hold_time",
            NumberValue(20.0*ms, min=1.0*ms, max=500.0*ms, scale=ms, unit="ms", ndecimals=1),
            "Lattice ramp")                  # dwell at each end
        self.setattr_argument("n_cycles",
            NumberValue(3, min=1, max=20, ndecimals=0, step=1),
            "Lattice ramp")                  # number of off/on cycles

    def prepare(self):
        self.Bragg.prepare_aoms()

    @kernel
    def run(self):
        self.core.reset()
        self.Bragg.dac_0.init()

        # init Bragg AOMs with just the lattice (bit 3) switched on
        self.Bragg.init_aoms(switches=0x9)
        delay(10*ms)

        for i in range(int(self.n_cycles)):
            self.ttl5.on()      
            self.Bragg.dipole_ramp(3.7, 0.0, self.ramp_time, pts=100)  # ramp dipole off

            delay(self.hold_time)
            self.Bragg.dipole_ramp(0.0, 3.7, self.ramp_time, pts=100)  # ramp dipole off
            self.ttl5.off()

            delay(2*ms)