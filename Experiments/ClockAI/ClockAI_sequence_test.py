# -*- coding: utf-8 -*-
"""
Created on Sat Jul  9 12:04:05 2022

@author: sr
"""



from artiq.experiment import EnvExperiment, kernel, NumberValue, delay, parallel, us
from ClockAIClass import _ClockAI

class ClockAI_sequence_test(EnvExperiment):


    def build(self):
        self.setattr_device("core")
        self.ai=_ClockAI(self)
        
        self.setattr_argument("pulses", NumberValue(10,min=0, max=100), "parameters")
        self.setattr_argument("pulse_time", NumberValue(1.0*1e-6,min=0.0*1e-6,max=1000.00*1e-6,scale=1e-6,
                      unit="us"),"parameters")
        self.setattr_argument("wait_time", NumberValue(1.0*1e-6,min=0.0*1e-6,max=1000.00*1e-6,scale=1e-6,
                      unit="us"),"parameters")

    def prepare(self):
        self.ai.prepare_aoms()

    @kernel
    def run(self):
        self.core.reset()
        self.ai.init_aoms(on=False)
        
        self.ai.ttl7.off()
        delay(5*us)
           
        
        self.ai.AI1_bs(self.pulse_time)
        self.ai.ttl7.on() 
        
        self.ai.AI_accel(self.pulse_time, self.pulses, 2)
        delay(2*us)
        self.ai.AI_accel(self.pulse_time, self.pulses, 2)
        self.ai.AI1_pulse(self.pulse_time)
        delay(self.pulse_time)
        self.ai.AI_accel(self.pulse_time, self.pulses, 2)
        delay(2*us)
        self.ai.AI_accel(self.pulse_time, self.pulses, 2)
        
        self.ai.ttl7.off() 
        self.ai.AI1_bs(self.pulse_time)
        
        
        #self.ai.AI_accel(self.pulse_time, self.pulses, 1)
        #self.ai.AI_mirror(self.pulse_time,self.pulses,1)
        #self.ai.AI1_bs(self.pulse_time)
        
        
        # self.ai.ttl7.on()
        # delay(1*us)
        # #self.ai.ttl7.off()
        # for m in range(int(self.pulses)):
        #     self.ai.AI1_pulse(self.pulse_time)
        #     delay(self.wait_time)
        #     if m==0:
        #         self.ai.ttl7.off()
        # delay(1*us)
        self.ai.ttl7.off()
