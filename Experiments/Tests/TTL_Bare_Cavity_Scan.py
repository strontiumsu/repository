# -*- coding: utf-8 -*-
"""
Created on Mon Aug 11 11:54:49 2025

@author: sr
"""

from artiq.experiment import *                  #imports everything from artiq experiment library
from BraggClass import _Bragg
import numpy as np
from artiq.coredevice import ad9910

#This code demonstrates how to use a TTL pulse(channel0) to trigger another event.
#In this code the event being triggered is another ttl pulse 
#however the same principle can be used to trigger an experimental sequence.

#pulses occur 5.158us appart with about 1ns jitter

class TTL_Bare_Cavity_Scan(EnvExperiment):
    def build(self): #Adds the device drivers as attributes and adds the keys to the kernel invarients     

        self.setattr_device("core")             #sets drivers of core device as attributes
        self.setattr_device("ttl0")             #sets drivers of TTL0 as attributes
        self.setattr_device("ttl5")             #sets drivers of TTL6 as attributes
        
        self.Bragg = _Bragg(self)
        
        self.scan_dds = self.Bragg.urukul_channels[1]
        
        self.freq_list= np.linspace(80.0*MHz, 80.0*MHz, 1024)
        self.freq_list_ram = np.full(1024, 1)
        self.step_size=0
        
        self.scan_time = 10*ms
        self.freq_center = 80.7*MHz
        self.freq_width = 3*MHz
        
    def prepare(self):
        self.Bragg.prepare_aoms()
        
    @kernel
    def load_scan(self):
        self.step_size = int(self.scan_time/(1024*4*ns))
        f0 = self.freq_center + self.freq_width/2
        f_step = self.freq_width/1023
        if self.freq_width/2 > self.freq_center: raise Exception("Bad Range")
        for i in range(1024):
            self.freq_list[i] = f0 - f_step*i
        self.scan_dds.frequency_to_ram(self.freq_list, self.freq_list_ram)

        self.core.break_realtime()
        delay(10 * ms)

        self.scan_dds.set(self.freq_center - self.freq_width/2, amplitude=self.Bragg.scale_sideband)

        delay(1 * ms)



        self.scan_dds.set_cfr1(ram_enable=0)
        self.scan_dds.cpld.io_update.pulse_mu(8)

        self.scan_dds.set_profile_ram(start=0, end=1024-1, step=(self.step_size | (2**6 - 1 ) << 16),
                                  profile=0, mode=ad9910.RAM_MODE_RAMPUP)
        self.scan_dds.cpld.set_profile(0)

        delay(100*us) # needs 2x delays here not to throw RTIOUnderflow Error?????
        delay(100*us)

        self.scan_dds.cpld.io_update.pulse_mu(8)
        delay(10000*us)
        self.scan_dds.write_ram(self.freq_list_ram)
        # prepare to enable ram and set frequency as target
        delay(10 * us)
        self.scan_dds.set_cfr1(internal_profile=0, ram_enable=1, ram_destination=ad9910.RAM_DEST_FTW)
        delay(10*ms)

        self.core.wait_until_mu(now_mu())

    @kernel #this code runs on the FPGA
    def run(self):                              
        self.core.reset()                       #resets core device
        delay(10*ms)
        self.Bragg.init_aoms(on=True)
        delay(10*ms)
        self.scan_dds.sw.off()
        delay(10*ms)

        self.load_scan()
        delay(10*ms)
        self.core.break_realtime()
        delay(10*ms)
        
        self.ttl0.input()                       #sets TTL0 as an input
        self.ttl5.output()                      #sets TTL6 as an output
                
        delay(1*us)                             #1us delay, necessary for using trigger, no error given if removed

        delay(10*us)
               
        
        with parallel:
            t_end = self.ttl0.gate_rising(10*ms)    #opens gate for rising edges to be detected on TTL0 for 10ms
                                                    #sets variable t_end as time(in MUs) at which detection stops
            with sequential:
                self.scan_dds.sw.on()
                self.ttl5.on()
                self.scan_dds.cpld.io_update.pulse_mu(8)
                #delay(self.scan_time)

                
        t_edge = self.ttl0.timestamp_mu(t_end)  #sets variable t_edge as time(in MUs) at which first edge is detected
                                                #if no edge is detected, sets t_edge to -1

        if t_edge > 0:                          #runs if an edge has been detected
            at_mu(t_edge)                       #set time cursor to position of edge
            delay(10*us)
            self.scan_dds.sw.off()
            self.ttl5.off()            
            delay(1*ms)                         #5us delay, to prevent underflow

            self.scan_dds.sw.on()
            self.ttl5.on()
            self.scan_dds.cpld.io_update.pulse_mu(8)
            delay(self.scan_time)
        delay(10*us)
        self.ttl5.off()            
        self.scan_dds.set_cfr1(ram_enable=0)
        self.scan_dds.cpld.io_update.pulse_mu(8)
        self.ttl0.count(t_end)                  #discard remaining edges and close gate