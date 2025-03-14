# -*- coding: utf-8 -*-
"""
Created on Thu Feb  6 15:30:32 2025

@author: sr
"""

from artiq.experiment import *                  #imports everything from artiq experiment library
from BraggClass import _Bragg
#This code takes a single read from TTL0 and prints the voltage 

class sandbox_exp(EnvExperiment):
    def build(self): #This code runs on the host device

        self.setattr_device("core")             #sets drivers for core device as attributes
        self.setattr_device("ttl5") # represents output event
        
        self.Bragg = _Bragg(self)
     
        
    def prepare(self):
        self.Bragg.prepare_aoms()
        
        
    @kernel #this code runs on the FPGA
    def run(self):                              
        self.core.reset()                       #resets core device
        self.ttl5.output()                      #TTL5 output is to represent the input signal triggering the even 
        self.Bragg.init_aoms(on=True)
        
        delay(100*ms)
        
        # self.ttl5.on()
        # self.Bragg.AOMs_off(["Dipole"])
        # delay(20*us)
        # self.Bragg.AOMs_on(["Dipole"])
        # self.ttl5.off()
        
        # atten_list = [12.0,14.0,16.0,18.0,20.0,22.0,24.0,26.0]
        atten_list = [12.0]
        
        for att in atten_list:
            self.ring_down(att)
        self.Bragg.set_AOM_attens([("Dipole", 12.0)])
        
    @kernel
    def ring_down(self, atten):
        # self.Bragg.set_AOM_attens([("Bragg1", atten)])
        # self.Bragg.AOMs_on(["Bragg1"])
        # delay(10*ms)
        # self.ttl5.on()
        # delay(5*us)
        # self.Bragg.AOMs_off(["Bragg1"])
        # delay(30*us)
        # self.ttl5.off()
        self.Bragg.set_AOM_attens([("Dipole", atten)])
        delay(1000*ms)
        self.ttl5.on()
        self.Bragg.AOMs_off(["Dipole"])
        delay(20*us)
        self.Bragg.AOMs_on(["Dipole"])
        self.ttl5.off()
        