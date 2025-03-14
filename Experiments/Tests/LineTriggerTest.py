# -*- coding: utf-8 -*-
"""
Created on Thu Feb 27 10:43:13 2025

@author: sr
"""




from artiq.experiment import *                

class lineTriggerTest_Exp(EnvExperiment):
    def build(self): #This code runs on the host device

        self.setattr_device("core")
        self.setattr_device("ttl1")    # line trigger in          
        self.setattr_device("ttl5") # start of experiment
    
        
    @kernel 
    def run(self):   
        self.before_scan()                         
        self.core.reset()                       
        
        
        for _ in range(50):
            self.line_trigger()
            delay(2000*ms)
            self.ttl5.pulse(1*ms) 
            delay(100*ms)    







    @kernel
    def before_scan(self):
        self.core.reset()                      
        
        delay(50*ms)
        
        self.ttl1.input()
        self.ttl5.output()  
                    
        delay(200*ms)
        
    @kernel
    def line_trigger(self, offset=5*ms):
        # sets start of exp relative to linetrigger
        t_end = self.ttl1.gate_rising(1/60) # ensures we only gate for one cycle
        t_edge = self.ttl1.timestamp_mu(t_end)
    
        if t_edge > 0:
            at_mu(t_edge+self.core.seconds_to_mu(offset))  # Add a tiny buffer to prevent underflow
        
        delay(1*ms)
        # self.ttl1.count(t_end) # clears cache
        # delay(1*ms)