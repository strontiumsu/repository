# -*- coding: utf-8 -*-
"""
Created on Fri Jan 17 13:51:02 2025

@author: sr
"""


from artiq.experiment import EnvExperiment, kernel, BooleanValue, us
from StateControlClass import _state_control

class State_Control_set(EnvExperiment):


    def build(self):
        self.setattr_device("core")
        self.StateControl=_state_control(self)

        
        self.setattr_argument("ch_689",BooleanValue(False),"Params")
        self.setattr_argument("ch_push",BooleanValue(False),"Params")
        self.setattr_argument("ch_688",BooleanValue(False),"Params")
        self.setattr_argument("ch_679",BooleanValue(False),"Params")


    def prepare(self):
        self.StateControl.prepare_aoms()

    @kernel
    def run(self):
        self.core.reset()
        self.StateControl.init_aoms(on=False)
        
        if self.ch_688:     self.StateControl.aom_688.sw.on()
        if self.ch_push:    self.StateControl.aom_push.sw.on()
        if self.ch_679:     self.StateControl.aom_679.sw.on()
        if self.ch_689:     self.StateControl.aom_689.sw.on()
        

