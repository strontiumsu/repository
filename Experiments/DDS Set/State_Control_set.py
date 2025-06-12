# -*- coding: utf-8 -*-
"""
Created on Fri Jan 17 13:51:02 2025

@author: sr
"""


from artiq.experiment import EnvExperiment, kernel, BooleanValue, us
from StateControlClass import _STATE_CONTROL

class State_Control_set(EnvExperiment):


    def build(self):
        self.setattr_device("core")
        self.StateControl=_STATE_CONTROL(self)
        self.setattr_device("ttl5")
        
        self.setattr_argument("ch_689",BooleanValue(False),"Params")
        self.setattr_argument("ch_Push",BooleanValue(False),"Params")
        self.setattr_argument("ch_688",BooleanValue(False),"Params")
        self.setattr_argument("ch_679",BooleanValue(False),"Params")


    def prepare(self):
        self.StateControl.prepare_aoms()

    @kernel
    def run(self):
        self.core.reset()
        self.StateControl.init_aoms(on=False)
        if self.ch_689: self.StateControl.AOMs_on(["689"])
        if self.ch_Push: self.StateControl.AOMs_on(["Push"])
        if self.ch_688: self.StateControl.AOMs_on(["688"])
        if self.ch_679: self.StateControl.AOMs_on(["679"])
        
        self.ttl5.pulse(100*us)
        
