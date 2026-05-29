# -*- coding: utf-8 -*-
"""
Created on Thu Feb 27 10:43:13 2025

@author: sr
"""

import numpy as np


from artiq.experiment import EnvExperiment, kernel, ms, delay, us, s # pyright: ignore[reportMissingImports]               

class lineTriggerTest_Exp(EnvExperiment):
    def build(self): #This code runs on the host device

        self.setattr_device("core")
        self.setattr_device("ttl1")    # line trigger in          
        self.setattr_device("ttl5") # start of experiment
        
        self.output_list = np.zeros(50)
    
        
    @kernel 
    def run(self):                          
        self.core.reset()   

        self.ttl1.input()
        self.ttl5.output() 
        self.ttl5.off()
                    
        delay(50*ms)    

        t_flush = self.ttl1.gate_rising(1*us)
        n_flush = self.ttl1.count(t_flush)
        for _ in range(n_flush):
            self.ttl1.timestamp_mu(t_flush)                
        
        
        delay(100*ms)
        self.check_delay_jitter()
        
        delay(200*ms)


        
   
    @kernel
    def check_delay_jitter(self, offset=1*ms):
        
        


        

        ts_mu = [0]*3000
        gate = 16.7*ms
        
        for i in range(3000):
        
            
            t_end = self.ttl1.gate_rising(gate)
            delay(2*ms)
            t_first = self.ttl1.timestamp_mu(t_end)  # oldest→newest
            self.ttl1.timestamp_mu(t_end)  # flush
            delay(20*ms)
            
            t_end = self.ttl1.gate_rising(gate)
            t_second = self.ttl1.timestamp_mu(t_end)  # oldest→newest
            delay(1*ms)
            ts_mu[i] = t_second-t_first
            self.ttl1.timestamp_mu(t_end)  # flush
            
   

        
        

        ts_s = [self.core.mu_to_seconds(x) for x in ts_mu]
        ts_rel_s = [self.core.mu_to_seconds(x - ts_mu[0]) for x in ts_mu]

        self.set_dataset("timestamps_mu", ts_mu, broadcast=True)
        self.set_dataset("timestamps_s", ts_s, broadcast=True)
        self.set_dataset("timestamps_rel_s", ts_rel_s, broadcast=True)

        # Quick summary in the log:
        # print("Captured", n, "edges in 500 ms")
        # if n > 1:
        #     print("Mean period (ms):", 1000*(ts_s[-1]-ts_s[0])/(len(ts_s) - 1)
        
        # t0 = now_mu()
        # t_end1 = self.ttl1.gate_rising(500*ms)
        
        
        # out1 = self.ttl1.timestamp_mu(t_end1)
        # ind = -1
        # while out1 != -1:
        #     ind += 1
        #     out1 = self.ttl1.timestamp_mu(t_end1)
            # self.output_list[ind] = out1
            # print(type(out1))
            # print(out1-t0)
        # print(self.output_list)
        # t1 = self.ttl1.timestamp_mu(t_end1)
        # n1 = self.ttl1.count(t_end1)   # how many edges landed in the gate
        # for _ in range(n1):                     # discard the rest from this gate
        
        # print(t1)
            
            

        
        
        # N=30
        # t_end1 = self.ttl1.gate_rising(25*ms) # ensures we only gate for one cycle
        # t_edge1 = self.ttl1.timestamp_mu(t_end1)
    
        # if t_edge1 > 0:
        #     at_mu(t_edge1+self.core.seconds_to_mu(offset))  # Add a tiny buffer to prevent underflow
        #     self.ttl5.on()
            
        # delay((N-1)/60-10*ms) # delay the number of cycles desired
            
        # t_end2 = self.ttl1.gate_rising(25*ms) # ensures we only gate for one cycle
        # t_edge2 = self.ttl1.timestamp_mu(t_end2)
    
        # if t_edge2 > 0:
        #     at_mu(t_edge2+self.core.seconds_to_mu(offset))  # Add a tiny buffer to prevent underflow
        #     self.ttl5.off() 
            
        
        # delay(1*ms)
      
        # print(self.core.mu_to_seconds(t_edge2-t_edge1)*1000)
        
        
     # @kernel
    # def line_trigger(self, offset=5*ms):
    #     # sets start of exp relative to linetrigger
    #     t_end = self.ttl1.gate_rising(1/60) # ensures we only gate for one cycle
    #     t_edge = self.ttl1.timestamp_mu(t_end)
    
    #     if t_edge > 0:
    #         at_mu(t_edge+self.core.seconds_to_mu(offset))  # Add a tiny buffer to prevent underflow
        
    #     delay(1*ms)
    #     # self.ttl1.count(t_end) # clears cache
    #     # delay(1*ms)
        