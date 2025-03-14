# -*- coding: utf-8 -*-
"""
Created on Fri Jan 17 13:51:02 2025

@author: sr
"""


from artiq.experiment import EnvExperiment, kernel, BooleanValue, us
from STIRAPClass import _STIRAP

class STIRAP_set(EnvExperiment):


    def build(self):
        self.setattr_device("core")
        self.STIRAP=_STIRAP(self)
        self.setattr_device("ttl5")
        
        self.setattr_argument("ch_689",BooleanValue(False),"Params")
        self.setattr_argument("ch_Push",BooleanValue(False),"Params")
        self.setattr_argument("ch_688",BooleanValue(False),"Params")
        self.setattr_argument("ch_679",BooleanValue(False),"Params")


    def prepare(self):
        self.STIRAP.prepare_aoms()

    @kernel
    def run(self):
        self.core.reset()
        self.STIRAP.init_aoms(on=False)
        if self.ch_689: self.STIRAP.AOMs_on(["689"])
        if self.ch_Push: self.STIRAP.AOMs_on(["Push"])
        if self.ch_688: self.STIRAP.AOMs_on(["688"])
        if self.ch_679: self.STIRAP.AOMs_on(["679"])
        
        self.ttl5.pulse(100*us)
        
