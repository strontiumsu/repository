
    
    # -*- coding: utf-8 -*-
"""
Created on Wed Aug 27 12:17:35 2025

@author: sr
"""

from artiq.experiment import *
from scan_framework import Scan1D, TimeScan
import numpy as np

from CoolingClass import _Cooling
from CameraClass import _Camera
from BraggClass import _Bragg
from StateControlClass import _state_control

from artiq.coredevice import ad9910
from artiq.coredevice.ad9910 import PHASE_MODE_TRACKING


class TTL_VRS(Scan1D, TimeScan, EnvExperiment):
    
    def build(self, **kwargs):
        
        super().build(**kwargs)
        
        # hardware and class objects
        self.setattr_device("ttl5")
        self.setattr_device("ttl0")
        self.Bragg = _Bragg(self)
        
        
        
        self.enable_pausing = True # disable to speed up by not checking scheduler
        self.enable_auto_tracking=False

        
        #scan parameters
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
        
        
        
        
        # VRS Scan args
        # Arguments   
        self.setattr_argument("freq_center_trigg", 
                              NumberValue(
                                  3*1e6,
                                  min=0.1*1e6,
                                  max=200.0*1e6,
                                  scale=1e6,
                                  unit="MHz",
                                  ndecimals = 3),
                              "scans")     
        self.setattr_argument("freq_width_trigg", 
                              NumberValue(
                                  1*1e6,
                                  min=-50.0*1e6,
                                  max=50.0*1e6,
                                  scale=1e6,
                                  unit="MHz"),
                              "scans")
    
        self.setattr_argument("scan_time_trigg", 
                              NumberValue(
                                  1000*1e-6,
                                  min=1*1e-6,
                                  max=50000*1e-6,
                                  scale=1e-6,
                                  unit='us'),
                              "scans")
        
        self.setattr_argument("freq_center_meas", 
                              NumberValue(
                                  80*1e6,
                                  min=0.1*1e6,
                                  max=200.0*1e6,
                                  scale=1e6,
                                  unit="MHz",
                                  ndecimals = 3),
                              "scans")     
        self.setattr_argument("freq_width_meas", 
                              NumberValue(
                                  1*1e6,
                                  min=-50.0*1e6,
                                  max=50.0*1e6,
                                  scale=1e6,
                                  unit="MHz"),
                              "scans")
    
        self.setattr_argument("scan_time_meas", 
                              NumberValue(
                                  1000*1e-6,
                                  min=1*1e-6,
                                  max=50000*1e-6,
                                  scale=1e-6,
                                  unit='us'),
                              "scans")
        
        self.setattr_argument("idx_offset", NumberValue(0, min=-500, max=500, scale=1), 'scans')
        self.setattr_argument("Meas_type", EnumerationValue(['Scan', "Probe"], default='Scan'), "scans")

        
        
        # Prep DDS scan
        self.freq_list= np.linspace(0.0*MHz, 0.0*MHz, 1024)
        self.freq_list_ram = np.full(1024, 1)
        self.step_size = 0
        
        self.scan_dds_trigg = self.Bragg.urukul_channels[1]
        self.scan_dds_meas = self.Bragg.urukul_channels[2]
        

        
        

        
    
        
        
    def prepare(self):

        self.Bragg.prepare_aoms()
        
    @kernel
    def before_scan(self):
        self.core.reset()

        # set hardware in known states and initialize
        self.ttl0.input()
        self.ttl5.off()
        self.Bragg.init_aoms(switches=0x9)
        
        delay(1*ms)
        self.core.wait_until_mu(now_mu())

    
    @kernel
    def measure(self, point):  
 
        self.core.reset()

        # make sure everything is off
        self.ttl5.off()
        self.scan_dds_trigg.sw.off()
        self.scan_dds_meas.sw.off()
        
        
        delay(1*ms)
        self.Bragg.aom_sideband.set(frequency=self.freq_center_trigg-self.freq_width_trigg/2, amplitude=0.8)
        self.Bragg.aom_push.set(frequency=self.freq_center_meas, amplitude=0.8)
        delay(1*ms)
        self.load_scan(self.scan_dds_trigg, self.freq_center_trigg, self.freq_width_trigg, self.scan_time_trigg)
        self.load_scan(self.scan_dds_meas, self.freq_center_meas, self.freq_width_meas, self.scan_time_meas)
        delay(1*ms)
        self.scan_dds_trigg.set_cfr1(internal_profile=0, ram_enable=1, ram_destination=ad9910.RAM_DEST_FTW)
        delay(10*ms)
        
        self.scan_dds_trigg.set_att(self.Bragg.atten_sideband)
        self.scan_dds_meas.set_att(self.Bragg.atten_push)  
        self.Bragg.aom_push.set(frequency=self.freq_center_meas, amplitude=0.8)
        delay(1*ms)
                
        
        with parallel:   
            self.ttl5.on()
            self.scan_dds_trigg.sw.on()
            self.scan_dds_meas.sw.on()
            self.scan_dds_trigg.cpld.io_update.pulse_mu(8)
            
        delay(self.scan_time_trigg)
        
        with parallel:
            self.ttl5.off()
            self.scan_dds_trigg.sw.off()
            self.scan_dds_meas.sw.off()
            
        with parallel:
            delay(50*us)
            with sequential:
                self.freeze_RAM(900)
                self.scan_dds_trigg.cpld.io_update.pulse_mu(8)  # apply start=end=900 once
                
                # Now turn RAM OFF on trig so it just holds that FTW
                self.scan_dds_trigg.set_cfr1(ram_enable=0)
                self.scan_dds_trigg.cpld.io_update.pulse_mu(8)
                
                self.scan_dds_meas.cpld.set_profile(0)
                self.scan_dds_meas.cpld.io_update.pulse_mu(8)
                
                self.scan_dds_meas.set_cfr1(internal_profile=0, ram_enable=1, ram_destination=ad9910.RAM_DEST_FTW)
                
                
            
        self.ttl5.on()   
        with parallel:   
            
            self.scan_dds_trigg.sw.on()
            self.scan_dds_meas.sw.on()
            self.scan_dds_meas.cpld.io_update.pulse_mu(8)
            
        delay(self.scan_time_meas)
        
        with parallel:
            
            self.scan_dds_trigg.sw.off()
            self.scan_dds_meas.sw.off()
        self.ttl5.off()
        

        return 0
        
    
    @kernel
    def freeze_RAM(self, idx):
        self.scan_dds_trigg.set_profile_ram(start=idx,end=idx, 
            step=(self.step_size | (2**6 - 1) << 16),profile=0,mode=ad9910.RAM_MODE_RAMPUP)
        self.scan_dds_trigg.cpld.io_update.pulse_mu(8)
        
  
    
    @kernel
    def load_scan(self, dds, f_center, f_width, scan_time):
        
        step_size = int(scan_time/(1024*4*ns)  )
        f0 = f_center + f_width/2
        
        #continuous       
        f_step = f_width /1023        
        for i in range(1024):
            self.freq_list[i] = f0 - f_step*i
        
            
        dds.frequency_to_ram(self.freq_list, self.freq_list_ram)

        self.core.break_realtime()
        delay(10 * ms)

        dds.set_cfr1(ram_enable=0)
        dds.cpld.io_update.pulse_mu(8)

        dds.set_profile_ram(start=0, end=1023, step=(step_size | (2**6 - 1 ) << 16),
                                  profile=0, mode=ad9910.RAM_MODE_RAMPUP)
        
        delay(5*ms)
        dds.cpld.set_profile(0)
        dds.cpld.io_update.pulse_mu(8)
        dds.write_ram(self.freq_list_ram)

  

        
        delay(1*ms)
        dds.cpld.set_profile(0)
        delay(50*ms)
    
        
        # prepare to enable ram and set frequency as target
        delay(10 * us)


        self.core.wait_until_mu(now_mu())
        
    @kernel
    def freeze_RAM(self, idx):
        self.scan_dds_trigg.set_profile_ram(start=idx,end=idx, 
            step=(self.step_size | (2**6 - 1) << 16),profile=0,mode=ad9910.RAM_MODE_RAMPUP)
        # self.scan_dds_trigg.cpld.io_update.pulse_mu(8)
   
