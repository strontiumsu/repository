# -*- coding: utf-8 -*-
"""
Created on Tue Oct  7 09:30:14 2025

@author: ejporter
"""



from artiq.experiment import *
from scan_framework import Scan1D, TimeScan
import numpy as np
from artiq.coredevice import ad9910


from BraggClass import _Bragg



class pause_scan_test_exp(Scan1D, TimeScan, EnvExperiment):
    
    def build(self, **kwargs):
        
        super().build(**kwargs)
        self.setattr_device("ttl5") # triggering pulse
        self.setattr_device("ttl0")             #sets drivers of TTL0 as attributes

        # import classes for experiment control
        self.Bragg = _Bragg(self)

        # attributes here
        self.enable_pausing = True # disable to speed up by not checking scheduler
        self.enable_auto_tracking=False
        self.enable_profiling = False # enable to print runtime statistics to find bottlenecks
        
        self.scan_dds = self.Bragg.urukul_channels[1]
        
        self.scan_arguments(times = {'start':1*1e-6,
            'stop':10*1e-6,
            'npoints':20,
            'unit':"us",
            'scale':us,
            'global_step':1*us,
            'ndecimals':2},
            nbins = {'default':1000},
            nrepeats = {'default':1},
            npasses = {'default':1},
            fit_options = {'default':"Fit and Save"}
            )

        # Arguments   
        self.setattr_argument("freq_center", 
                              NumberValue(
                                  3*1e6,
                                  min=0.1*1e6,
                                  max=200.0*1e6,
                                  scale=1e6,
                                  unit="MHz",
                                  ndecimals = 3),
                              "parameters")     
        self.setattr_argument("freq_width", 
                              NumberValue(
                                  1*1e6,
                                  min=-10.0*1e6,
                                  max=10.0*1e6,
                                  scale=1e6,
                                  unit="MHz"),
                              "parameters")
    
        self.setattr_argument("scan_time", 
                              NumberValue(
                                  100*1e-6,
                                  min=1*1e-6,
                                  max=50000*1e-6,
                                  scale=1e-6,
                                  unit='us'),
                              "parameters")
        
       

        self.freq_list= np.linspace(80.0*MHz, 80.0*MHz, 1024)
        self.freq_list_ram = np.full(1024, 1)
        self.step_size=0
        
        
        
    def prepare(self):
        self.Bragg.prepare_aoms()

        
        
        
    @kernel
    def load_scan(self):
        self.step_size = int(self.scan_time/(1024*4*ns))
        
        f0 = self.freq_center + self.freq_width/2
        if self.freq_width/2 > self.freq_center: raise Exception("Bad Range")
        
        #continuous       
        f_step = self.freq_width / 1023        
        for i in range(1024):
            self.freq_list[i] = f0 - f_step*i

            
        self.scan_dds.frequency_to_ram(self.freq_list, self.freq_list_ram)

        self.core.break_realtime()
        delay(10 * ms)

        self.scan_dds.set_cfr1(ram_enable=0)
        self.scan_dds.cpld.io_update.pulse_mu(8)

        self.scan_dds.set_profile_ram(start=0, end=1024-1, step=(self.step_size | (2**6 - 1 ) << 16),
                                  profile=0, mode=ad9910.RAM_MODE_RAMPUP)
        
        delay(5*ms)
        self.scan_dds.cpld.set_profile(0)
        self.scan_dds.cpld.io_update.pulse_mu(8)
        self.scan_dds.write_ram(self.freq_list_ram)

  

        
        delay(1*ms)
        self.scan_dds.cpld.set_profile(0)
        delay(50*ms)
    
        
        # prepare to enable ram and set frequency as target
        delay(10 * us)
        self.scan_dds.set_cfr1(internal_profile=0, ram_enable=1, ram_destination=ad9910.RAM_DEST_FTW)
        delay(10*ms)

        self.core.wait_until_mu(now_mu())

   

    @kernel 
    def before_scan(self):
        self.core.reset()
        self.ttl0.input()
        self.ttl5.off()
        self.Bragg.init_aoms(switches=0x9)
        self.core.wait_until_mu(now_mu())
     

    @kernel
    def measure(self, point):
        self.core.reset()
        delay(1 * ms)
        self.scan_dds.sw.off()
        self.load_scan()
        step_mu  = self.core.seconds_to_mu(self.step_size * 4*ns)
        delay(1*ms)
        
                
        t_start = now_mu() + self.core.seconds_to_mu(200*us)        
        at_mu(t_start)       



        with parallel:   
            t_end = self.ttl0.gate_rising(10*ms)
            self.scan_dds.sw.on()
            self.scan_dds.cpld.io_update.pulse_mu(8)

            
        t_edge = self.ttl0.timestamp_mu(t_end)
        
        if t_edge > 0:
            at_mu(t_edge)                       
            delay(5*us)
            self.scan_dds.sw.off()
            idx = (t_edge - t_start) // step_mu
            delay(30*us)
            self.freeze_RAM(idx)
            
            
            self.ttl5.on()
            
            self.scan_dds.sw.on()
            delay(1*ms)
            self.scan_dds.sw.off()
            
            self.ttl5.off()
            
            
        delay(1*s)
        self.core.wait_until_mu(now_mu())
        return 0
     
    @kernel
    def freeze_RAM(self, idx):
        self.scan_dds.set_profile_ram(start=idx,end=idx, 
            step=(self.step_size | (2**6 - 1) << 16),profile=0,mode=ad9910.RAM_MODE_RAMPUP)
        self.scan_dds.cpld.io_update.pulse_mu(8)
            
    