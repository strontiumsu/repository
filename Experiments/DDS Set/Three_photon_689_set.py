# -*- coding: utf-8 -*-
"""
Created on Sat Jul  9 12:04:05 2022

@author: sr
"""

# -*- coding: utf-8 -*-
"""
Created on Tue Feb 15 21:19:34 2022

@author: sr
"""


from artiq.experiment import EnvExperiment, kernel
from ThreePhotonClass import _ThreePhoton

class Three_photon_689_set(EnvExperiment):


    def build(self):
        self.setattr_device("core")
        self.th_ph=_ThreePhoton(self)

    def prepare(self):
        self.th_ph.prepare_aoms()

    @kernel
    def run(self):
        self.core.reset()
        self.th_ph.init_aoms(on=False)
        self.th_ph.AOMs_on(self.th_ph.AOMs)
