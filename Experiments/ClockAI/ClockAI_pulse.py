# -*- coding: utf-8 -*-
"""
Created on Sat Jul  9 12:04:05 2022

@author: sr
"""



from artiq.experiment import EnvExperiment, kernel, NumberValue, delay, parallel, us, ms, ns, EnumerationValue
from ClockAIClass import _ClockAI

class ClockAI_pulse(EnvExperiment):


    def build(self):
        self.setattr_device("core")
        self.ai=_ClockAI(self)
        self.setattr_device("ttl5")
        
        self.setattr_argument("Arm",EnumerationValue(['1', '2']),"parameters")
        self.setattr_argument("pulses", NumberValue(5,min=0, max=100), "parameters")
        self.setattr_argument("pulse_time", NumberValue(1.0*1e-6,min=0.0*1e-6,max=1000.00*1e-6,scale=1e-6,
                      unit="us"),"parameters")
        self.setattr_argument("wait_time", NumberValue(1.0*1e-3,min=0.0*1e-3,max=1000.00*1e-3,scale=1e-3,
                      unit="ms"),"parameters")

    def prepare(self):
        self.ai.prepare_aoms()
        self.arm_num = int(self.Arm)

    @kernel
    def run(self):
        self.core.reset()
        self.ai.init_aoms(on=False)
        
        for _ in range(int(self.pulses)):
            self.ttl5.on()
            self.ai.AI_pulse(self.pulse_time, 0)
            self.ttl5.off()
            delay(500*ns)
            self.ttl5.on()
            self.ai.AI_pulse(self.pulse_time, 1)
            self.ttl5.off()
            
            delay(self.wait_time)
                
