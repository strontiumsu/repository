# -*- coding: utf-8 -*-
"""
Created on 
@author: sr
"""



from artiq.experiment import EnvExperiment, kernel, BooleanValue
from ClockAIClass import _ClockAI

class ClockAI_set(EnvExperiment):


    def build(self):
        self.setattr_device("core")
        self.AI=_ClockAI(self)
        
        self.setattr_argument("Push",BooleanValue(False),"Params")
        self.setattr_argument("Arm1",BooleanValue(False),"Params")
        self.setattr_argument("Arm2",BooleanValue(False),"Params")

    def prepare(self):
        self.AI.prepare_aoms()

    @kernel
    def run(self):
        self.core.reset()
        self.AI.init_aoms(on=False)
        if self.Push: self.AI.AOMs_on(["Push"])
        if self.Arm1: self.AI.AOMs_on(["AI1"])
        if self.Arm2: self.AI.AOMs_on(["AI2"])
        
