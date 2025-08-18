from artiq.experiment import *
import numpy as np
from artiq.coredevice import ad9910

from CoolingClass import _Cooling
import matplotlib.pyplot as plt

class dds_scan_test(EnvExperiment):
    
    def build(self):
        self.setattr_device("core")
        self.setattr_device("scheduler")
        self.setattr_device("ttl5") # triggering pulse
        self.MOTs = _Cooling(self)
                
        self.setattr_argument("freq_start", 
                              NumberValue(
                                  20*1e6,
                                  min=0.1*1e6,
                                  max=200.0*1e6,
                                  scale=1e6,
                                  unit="MHz",
                                  ndecimals = 3),
                               "parameters")     
        self.setattr_argument("freq_depth", 
                              NumberValue(
                                  10*1e6,
                                  min=0.0*1e6,
                                  max=20.0*1e6,
                                  scale=1e6,
                                  unit="MHz"),
                              "parameters")
        self.setattr_argument("scan_time", 
                              NumberValue(
                                  33*1e-6,
                                  min=1*1e-6,
                                  max=5000*1e-6,
                                  scale=1e-6,
                                  unit='us'),
                              "parameters")
        self.num_profiles = 7
        self.freq_list= np.linspace(21.0*MHz, 21.0*MHz, int(1024/self.num_profiles)*self.num_profiles)
        self.freq_list_ram = np.full(int(1024/self.num_profiles)*self.num_profiles, 1)
        self.step_size = 0
        self.scan_dds = self.MOTs.scan_dds
        
        self.flength = int(1024/self.num_profiles)
        self.fstep = 1*MHz
        
        
        
    def prepare(self):        
        self.MOTs.prepare_aoms()
        
        self.step_size = int(self.scan_time/(self.flength*4*ns))
        for profile_idx in range(int(self.num_profiles)):
            scale = (self.num_profiles - profile_idx)/self.num_profiles
            start_idx = self.flength*profile_idx
            f0 = self.freq_start
            fend = self.freq_start-self.freq_depth*scale
            flist = self.fstep*profile_idx + np.linspace(fend, f0, self.flength) # reverse order due to RAM reading
            self.freq_list[start_idx:start_idx+self.flength] = flist

        self.scan_dds.frequency_to_ram(self.freq_list, self.freq_list_ram)
            

    def run(self):
        self.init_exp()
        self.prepare_scan()
        self.run_exp()

  
        
    @kernel
    def init_exp(self):     
        self.core.reset()

        self.MOTs.init_aoms(on=False)
        self.scan_dds.sw.off()
        self.core.wait_until_mu(now_mu())
        
        
        
    @kernel
    def run_exp(self):
        self.core.reset()
        delay(100*ms)
        
        

        self.scan_dds.set_att(5.0)
        delay(50*us)
        
        with parallel:
            self.scan_dds.sw.on()
            self.scan_dds.cpld.io_update.pulse_mu(8)
            
        
        for profile_idx in range(int(self.num_profiles)):
            self.ttl5.pulse(0.1*us)
            self.scan_dds.cpld.set_profile(profile_idx)      
            self.scan_dds.set_att(5.0 + 2.0*profile_idx)

            
            delay(50*us)
         
            
        

        self.scan_dds.sw.off()
        self.ttl5.off()            
        delay(2*ms)
        
        self.scan_dds.set_cfr1(ram_enable=0)
        self.scan_dds.cpld.io_update.pulse_mu(8)
        delay(5*ms)
        
        
        self.core.wait_until_mu(now_mu())

    @kernel
    def prepare_scan(self):
        self.core.reset()
        delay(1*ms)
        
        # turn off RAM mode to prepare to write
        self.scan_dds.set_cfr1(ram_enable=0)
        self.scan_dds.cpld.io_update.pulse_mu(8)
        
        # set profile ranges
        for profile_idx in range(self.num_profiles):
            delay(1*ms)
            start_idx = self.flength*profile_idx
            
            self.scan_dds.set_profile_ram(
                start=start_idx, end=start_idx+self.flength-1, step=(int(self.step_size) | (2**6 - 1 ) << 16),
                profile=profile_idx, mode=ad9910.RAM_MODE_CONT_RAMPUP)
        
        for profile_idx in range(self.num_profiles):
            delay(5*ms)
            start_idx = self.flength*profile_idx
            self.scan_dds.cpld.set_profile(profile_idx)
            self.scan_dds.cpld.io_update.pulse_mu(8)
            self.scan_dds.write_ram(self.freq_list_ram[start_idx: start_idx+self.flength])   


        delay(1*ms)
        self.scan_dds.cpld.set_profile(0)
        delay(50*ms)
        
        self.scan_dds.set_cfr1(ram_enable=1, ram_destination=ad9910.RAM_DEST_FTW)
        self.core.wait_until_mu(now_mu())


  