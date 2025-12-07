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
        self.setattr_device("ttl5")
        self.setattr_device("ttl6")
        
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
        
        if self.ch_688: self.StateControl.urukul_channels[0].sw.on()
        if self.ch_Push: 
            self.ttl6.on()
            self.StateControl.urukul_channels[1].sw.on()
        if self.ch_679: self.StateControl.urukul_channels[2].sw.on()
        if self.ch_689: self.StateControl.urukul_channels[3].sw.on()
        
        self.ttl5.pulse(100*us)
        
