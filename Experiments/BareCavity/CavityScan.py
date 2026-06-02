# -*- coding: utf-8 -*-
"""
Created on Mon Nov  4 11:01:45 2024

@author: ejporter
"""


from artiq.experiment import Scannable, RangeScan, NumberValue, TArray,TInt32 # pyright: ignore[reportMissingImports]
from artiq.experiment import kernel, EnvExperiment, rpc, delay, ms, parallel, us, MHz, now_mu, ns # pyright: ignore[reportMissingImports]
from artiq.coredevice import ad9910 # pyright: ignore[reportMissingImports]
from scan_framework import Scan1D
import numpy as np

from BraggClass import _Bragg

class bare_cavity_scan_exp(Scan1D, EnvExperiment):
    
    def build(self, **kwargs):

        super().build(**kwargs)
        self.Bragg = _Bragg(self)
        self.enable_auto_tracking = False
        self.setattr_device("ttl5") # triggering pulse
        
        self.scan_dds = self.Bragg.urukul_channels[2]
        
        # Arguments 
        
        self.setattr_argument('pulse_spacing', Scannable(default=RangeScan(
            start=10*us,
            stop=10.01*us,
            npoints=10),
            scale=1e-6,
            ndecimals=4,
            unit="us"))
        
        self.scan_arguments(nbins={'default':1000},
                    nrepeats={'default':1},
                    npasses={'default':1},
                    fit_options={'default':"No Fits"})
   
        self.setattr_argument("freq_center", 
                              NumberValue(
                                  3*1e6,
                                  min=0.1*1e6,
                                  max=360.0*1e6,
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
        self.setattr_argument("pulses", 
                              NumberValue(
                                  10,
                                  min=1,
                                  max=1000,
                                  scale=1,),
                              "parameters")
        self.setattr_argument("scan_time", 
                              NumberValue(
                                  100*1e-6,
                                  min=1*1e-6,
                                  max=50000*1e-6,
                                  scale=1e-6,
                                  unit='us'),
                              "parameters")
        
        self.setattr_argument("pause_time", 
                              NumberValue(
                                  1.0,
                                  min=0.1,
                                  max=20.0,
                                  scale=1e0,
                                  unit='s'),
                              "parameters")

        self.freq_list= np.linspace(80.0*MHz, 80.0*MHz, 1024)
        self.freq_list_ram = np.full(1024, 1)
        self.step_size=0
        
    def get_scan_points(self):
        # return the set of scan points to the framework
        return self.pulse_spacing
     
        
    def prepare(self):
        self.Bragg.prepare_aoms()       
    

    @kernel 
    def before_scan(self):
        self.core.reset()
        self.ttl5.off()
        self.Bragg.init_aoms()
        delay(1*ms)

    @kernel
    def before_measure(self, point, measurement):
        delay(1*ms)
        self.load_mod(self.scan_dds)

     
        
    @kernel
    def measure(self, point):
        self.core.break_realtime()
        delay(10 * ms)
   
        self.Bragg.aom_sideband.sw.on()
        self.scan_dds.sw.on()
        delay(1*ms)  
        for _ in range(int(self.pulses)):    
            self.ttl5.on()
            self.scan_dds.cpld.io_update.pulse_mu(8)             
            delay(self.scan_time)               
            self.ttl5.off()      
            delay(point)
            
        delay(1*ms)
        

        self.scan_dds.set(self.freq_center, amplitude=self.Bragg.scale_Carrier)
        self.scan_dds.sw.on()
        self.Bragg.aom_sideband.sw.on()
        
        delay(self.pause_time)
        self.core.wait_until_mu(now_mu())
        return 0
     
    @kernel
    def load_mod(self, dds):
        # one host round-trip, table arrives prepacked
        step = int(self.scan_time/(1024*4*ns))
        ram_data = self._build_ram_table(dds, self.freq_center, self.freq_weidth)
        self.core.break_realtime()  # RPC ate ~ms of wall clock
        delay(1*ms)
        
        # turn off RAM mode
        dds.set_cfr1(ram_enable=0)
        dds.cpld.io_update.pulse_mu(8)
        delay(100*us)

        # set profile registers
        dds.set_profile_ram(start=0, end=1023, step=step,
                            profile=0, mode=ad9910.RAM_MODE_CONT_RAMPUP)
        delay(100*us)

        # write sweep
        dds.cpld.set_profile(0)
        dds.cpld.io_update.pulse_mu(8)
        delay(100*us)
        dds.write_ram(ram_data)
        delay(100*us)
        
        # ram enable
        dds.set_cfr1(internal_profile=0, ram_enable=1,
                     ram_destination=ad9910.RAM_DEST_ASF)
        delay(1000*us)
        self.core.wait_until_mu(now_mu())

    @rpc
    def _build_ram_table(self, dds, fc, fw) -> TArray(TInt32):  # pyright: ignore[reportInvalidTypeForm]
        f0 = fc + fw/2     
        f_step = fw / 1023     
        table =  f0 - np.arange(1024)*f_step  
        ram = np.zeros(1024, dtype=np.int32)
        dds.frequency_to_ram(table, ram)
        return ram
            
        
        
    
   
    