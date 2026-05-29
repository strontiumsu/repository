# -*- coding: utf-8 -*-
"""
Created on Mon Nov  4 11:01:45 2024

@author: ejporter
"""


from artiq.experiment import Scannable, RangeScan, NumberValue # pyright: ignore[reportMissingImports]
from artiq.experiment import kernel, EnvExperiment, kHz, delay, ms, parallel, us, MHz, now_mu, ns # pyright: ignore[reportMissingImports]
from artiq.coredevice import ad9910 # pyright: ignore[reportMissingImports]
from scan_framework import Scan1D
import numpy as np


from CoolingClass import _Cooling
from CameraClass import _Camera
from BraggClass import _Bragg
from repository.models.scan_models import RabiModel # pyright: ignore[reportMissingImports]


class bare_cavity_scan_exp(Scan1D, EnvExperiment):
    
    def build(self, **kwargs):
        
        super().build(**kwargs)
        self.setattr_device("ttl5") # triggering pulse

        # import classes for experiment control

        self.Bragg = _Bragg(self)

        
                # attributes here
        self.enable_pausing = True # disable to speed up by not checking scheduler
        self.enable_auto_tracking=False
        self.enable_profiling = False # enable to print runtime statistics to find bottlenecks
        
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
        self.enable_histograms = True
        
        
    @kernel
    def load_scan(self):
        self.step_size = int(self.scan_time/(1024*4*ns))
        f0 = self.freq_center + self.freq_width/2
        if self.freq_width/2 > self.freq_center: raise Exception("Bad Range")
        
        #continuous       
        f_step = self.freq_width / 1023        
        for i in range(1024):
            self.freq_list[i] = f0 - f_step*i
            
        ## discrete:
        # f_step = self.freq_width / 15
        # for i in range(1024):
        #     self.freq_list[i] = f0 - int(i/16) * f_step
            
            
        self.scan_dds.frequency_to_ram(self.freq_list, self.freq_list_ram)

        self.core.break_realtime()
        delay(10 * ms)

        self.scan_dds.set(self.freq_center - self.freq_width/2, amplitude=self.Bragg.scale_Carrier)

        delay(1 * ms)



        self.scan_dds.set_cfr1(ram_enable=0)
        self.scan_dds.cpld.io_update.pulse_mu(8)

        self.scan_dds.set_profile_ram(start=0, end=1024-1, step=(self.step_size | (2**6 - 1 ) << 16),
                                  profile=0, mode=ad9910.RAM_MODE_RAMPUP)
        self.scan_dds.cpld.set_profile(0)

        delay(100*us) # needs 2x delays here not to throw RTIOUnderflow Error?????
        delay(100*us)

        self.scan_dds.cpld.io_update.pulse_mu(8)
        delay(100*us)
        self.scan_dds.write_ram(self.freq_list_ram)
        # prepare to enable ram and set frequency as target
        delay(10 * us)
        self.scan_dds.set_cfr1(internal_profile=0, ram_enable=1, ram_destination=ad9910.RAM_DEST_FTW)
        delay(10*ms)

        self.core.wait_until_mu(now_mu())



    @kernel 
    def before_scan(self):
        self.core.reset()
        self.ttl5.off()


        self.Bragg.init_aoms(switches=0x9)
        self.Bragg.aom_sideband.sw.off()
        self.Bragg.aom_carrier.sw.off()
        

        delay(1*ms)
        
        
        self.Bragg.aom_sideband.set_att(self.Bragg.atten_Sideband)  
        self.Bragg.aom_carrier.set_att(self.Bragg.atten_Carrier)  
        delay(100*ms)

        
        self.core.wait_until_mu(now_mu())
     
        
    @kernel
    def measure(self, point):
        self.core.reset()
        delay(1 * ms)
        self.load_scan()
        # delay(10*ms)
   
        # before this point is just for preparing the RAM and RIGOL
        self.core.break_realtime()
        delay(10*ms)
        self.Bragg.aom_sideband.set_att(self.Bragg.atten_Sideband)  
        self.Bragg.aom_carrier.set_att(self.Bragg.atten_Carrier)      
        delay(10 * ms)




        self.run_exp(point)
        

        self.scan_dds.set(self.freq_center, amplitude=self.Bragg.scale_Carrier)
        self.scan_dds.sw.on()
        self.Bragg.aom_sideband.sw.on()
        
        #resets scan to prepapre for next scan
        #self.scan_dds.set_cfr1(ram_enable=0)
        #self.scan_dds.cpld.io_update.pulse_mu(8)
        
        
        
        # simulate experiment shot rate
        delay(self.pause_time)
        self.core.wait_until_mu(now_mu())
        return 0
     
    
    @kernel
    def run_exp(self, pspace):
        self.Bragg.aom_sideband.sw.on()
        self.scan_dds.sw.on()

        delay(1*ms)
        
        for _ in range(int(self.pulses)):
            
            
            
            with parallel:
                
                self.ttl5.on()
                
                self.scan_dds.cpld.io_update.pulse_mu(8)
                
                
            delay(self.scan_time)
            
            with parallel:
                
                self.ttl5.off()      

            delay(pspace)
            
        # self.freeze_RAM(self.scan_dds, 0, 1023, 1*self.scan_time)
        # self.ttl5.on()
        # delay(1*self.scan_time)
        # self.ttl5.off()

        delay(1*ms)
       
        
        
    
    @kernel
    def freeze_RAM(self, dds, start_idx, end_idx, scan_time):
        """
        Modify the trigger DDS RAM so that profile 0 consists of a single
        index (idx), effectively "freezing" the DDS at the frequency
        corresponding to the detection time.

        This is called after pulse 1, before pulse 2.
        """
        step_size = int(scan_time/(1024*4*ns))


        dds.set_profile_ram(
            start=start_idx,
            end=end_idx,
            step=(step_size | (2**6 - 1) << 16),
            profile=0,
            mode=ad9910.RAM_MODE_RAMPUP
        )
        dds.cpld.io_update.pulse_mu(8)
        
    