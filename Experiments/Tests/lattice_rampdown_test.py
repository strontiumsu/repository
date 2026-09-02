# -*- coding: utf-8 -*-
"""
Quick test for _Bragg.lattice_rampdown.

Ramps the lattice AOM off (attenuation ramped up to ramp_end_atten) and back on
(attenuation snapped back to atten_Lattice) a few times so the ramp can be viewed
on a scope / photodiode. ttl5 is pulsed high around each cycle as a scope trigger.
Nothing else.
"""


from artiq.experiment import *




class LatticeRampdownTest(EnvExperiment):

    def build(self):
        self.setattr_device("core")
        self.setattr_device("zotino0")
        self.setattr_device("ttl5")          # scope trigger

        self.setattr_argument("volt",
                            NumberValue(9.9, ndecimals=2, step=0.01, min=0.01, max=9.99))



    @kernel
    def run(self):
        self.core.reset()
        self.zotino0.init()
        delay(100*ms)
        self.ttl5.pulse(10*us)
        self.zotino0.write_dac(6, self.volt)  # write values without updating
        self.zotino0.load()  # update all at once

        delay(100*ms)
        self.zotino0.write_dac(6, 9.99)  # write values without updating
        self.zotino0.load()  # update all at once
        

        