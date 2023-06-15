# -*- coding: utf-8 -*-
"""
Created on Mon Feb  6 10:54:54 2023

@author: sr
"""

# -*- coding: utf-8 -*-
"""
Created on Mon Feb 14 16:39:41 2022

@author: sr
"""

# -*- coding: utf-8 -*-
"""
Created on Mon Feb 14 15:48:49 2022

@author: sr

Functions:

Controls some aspects of the HCDL lock setup    
Sets the parameters of the HCDL MTS AOM and double-pass AOM before the HDCL setup

"""

from artiq.experiment import EnvExperiment, NumberValue, delay, ms, kernel, TInt32, parallel
import numpy as np

from artiq.coredevice.ad9910 import PHASE_MODE_TRACKING

class _Bragg(EnvExperiment):
      
    
    def build(self):
        self.setattr_device("core")        
        self.setattr_device("urukul0_cpld")
        
        
        # names for all our AOMs
        self.AOMs = ['Bragg1', 'Bragg2']

        
        # default values for all params for all AOMs
        self.scales = [0.8, 
                       0.8]
        
        self.attens = [18.0, 
                       5.0]
        
        self.freqs = [110.0, 
                      110.0]  
        
        self.urukul_channels = [self.get_device("urukul0_ch0"),
                                self.get_device("urukul0_ch1")]

        # setting attributes to controll all AOMs       
        for i in range(len(self.AOMs)):
            AOM = self.AOMs[i]
            self.setattr_argument(f"scale_{AOM}", NumberValue(self.scales[i], min=0.0, max=0.9), f"{AOM}_AOMs")
            self.setattr_argument(f"atten_{AOM}", NumberValue(self.attens[i], min=1.0, max=30), f"{AOM}_AOMs")
            self.setattr_argument(f"freq_{AOM}", NumberValue(self.freqs[i]*1e6, min=50*1e6, max=350*1e6, scale=1e6, unit='MHz'),  f"{AOM}_AOMs")
        
        
    def prepare_aoms(self):
        self.scales = [self.scale_Bragg1, self.scale_Bragg2]
        
        self.attens = [self.atten_Bragg1, self.atten_Bragg2]
        
        self.freqs = [self.freq_Bragg1, self.freq_Bragg2]
    @kernel
    def init_aoms(self, on=True):
   
        delay(10*ms)
        self.urukul0_cpld.init()

        for i in range(len(self.AOMs)):
            delay(10*ms)
           
            ch =  self.urukul_channels[i]
            
            ch.init()            
            set_f = ch.frequency_to_ftw(self.freqs[i])
            set_asf = ch.amplitude_to_asf(self.scales[i])
            ch.set_mu(set_f, asf=set_asf)
            ch.set_att(self.attens[i])
            if on:
                ch.sw.on()
            else:                
                ch.sw.off()
        delay(10*ms)
            
        
    # basic AOM methods, maybe turn these into parallel?
    @kernel
    def AOMs_on(self, AOMs):
        for aom in AOMs:
            ch = self.urukul_channels[self.index_artiq(aom)]
            ch.sw.on()
            delay(0.05*ms)
    @kernel
    def AOMs_off(self, AOMs):
        for aom in AOMs:
            self.urukul_channels[self.index_artiq(aom)].sw.off()
            delay(2*ms)
    @kernel        
    def set_AOM_freqs(self, freq_list): # takes in a list of tuples
        for aom, freq in freq_list:
            self.index_artiq(aom)
            self.freqs[self.index] = freq
            ch = self.urukul_channels[self.index]
            set_freq = ch.frequency_to_ftw(freq)
            set_asf = ch.amplitude_to_asf(self.scales[self.index])
            ch.set_mu(set_freq, asf=set_asf)

    def get_AOM_freqs(self):
        return self.freqs
    
    @kernel        
    def set_AOM_attens(self, atten_list):
        for aom, atten in atten_list:
            self.index_artiq(aom)
            self.attens[self.index] = atten
            self.urukul_channels[self.index].set.att(atten)

    def get_AOM_attens(self):
        return self.attens
    
    @kernel        
    def set_AOM_scales(self, scale_list):
        for aom, scale in scale_list.items():
            self.index_artiq(aom)
            self.scales[self.index] = scale
            ch = self.urukul_channels[self.index]
            set_freq = ch.frequency_to_ftw(self.freqs[self.index])
            set_asf = ch.amplitude_to_asf(self.scales[self.index])
            ch.set_mu(set_freq, asf=set_asf)

    def get_AOM_scales(self):
        return self.scales
    
    
    @kernel
    def bragg_pulse(self,time):
        self.AOMs_on(self.AOMs)
        self.hold(time)
        self.AOMs_off(self.AOMs)
        
    # @kernel    
    # def init_aoms_phase(self,t):
        
    #     delay(1*ms)
    #     self.urukul0_cpld.init()

    #     self.urukul_hmc_ref_switch1_689_3nu.init()
    #     self.urukul_hmc_ref_switch1_689_3nu.set_mu(0x40000000, asf=self.urukul_hmc_ref_switch1_689_3nu.amplitude_to_asf(self.switch1_689_3nu_dds_scale))
    #     self.urukul_hmc_ref_switch1_689_3nu.set_att(self.switch1_689_3nu_iatten)
    #     self.urukul_hmc_ref_switch1_689_3nu.set(self.switch1_689_3nu_frequency,phase=0.0, ref_time_mu=t)
            
    #     self.urukul_hmc_ref_switch2_689_3nu.init()
    #     self.urukul_hmc_ref_switch2_689_3nu.set_mu(0x40000000, asf=self.urukul_hmc_ref_switch2_689_3nu.amplitude_to_asf(self.switch2_689_3nu_dds_scale))
    #     self.urukul_hmc_ref_switch2_689_3nu.set_att(self.switch2_689_3nu_iatten)
    #     self.urukul_hmc_ref_switch2_689_3nu.set(self.switch2_689_3nu_frequency,phase=0.0, ref_time_mu=t)
            
    #     self.urukul_hmc_ref_switch3_689_3nu.init()
    #     self.urukul_hmc_ref_switch3_689_3nu.set_mu(0x40000000, asf=self.urukul_hmc_ref_switch3_689_3nu.amplitude_to_asf(self.switch3_689_3nu_dds_scale))
    #     self.urukul_hmc_ref_switch3_689_3nu.set_att(self.switch3_689_3nu_iatten)
    #     self.urukul_hmc_ref_switch3_689_3nu.set(self.switch3_689_3nu_frequency,phase=0.0, ref_time_mu=t)
    #     #self.urukul_hmc_ref_switch3_689_3nu.sw.on()
        
    # @kernel    
    # def set_switch1_phase_freq_profile(self,freq,ph,t,prof=0):
    #     self.urukul_meas[0].set(freq,phase=ph,phase_mode = PHASE_MODE_TRACKING, ref_time_mu=t, profile = prof)
    # @kernel    
    # def set_switch2_phase_freq_profile(self,freq,ph,t,prof=0):
    #     self.urukul_meas[1].set(freq,phase=ph,phase_mode = PHASE_MODE_TRACKING, ref_time_mu=t, profile = prof)
    # @kernel    
    # def set_switch3_phase_freq_profile(self,freq,ph,t,prof=0):
    #     self.urukul_meas[2].set(freq,phase=ph,phase_mode = PHASE_MODE_TRACKING, ref_time_mu=t, profile = prof)
          
    # @kernel 
    # def set_switch1_689_3nu_frequency(self): 
        
    #     fswitch1 = self.switch1_689_3nu_frequency
    #     urukul_ch =self.urukul_meas[0]
    #     dds_ftw_switch1_689_3nu=self.urukul_meas[0].frequency_to_ftw(fswitch1)
    #     urukul_ch.set_mu(dds_ftw_switch1_689_3nu, asf=urukul_ch.amplitude_to_asf(self.switch1_689_3nu_DDS_amplitude_scale))   
        
    # @kernel 
    # def set_switch1_689_3nu_freq(self,f): 
        
    #     fswitch1 = f
    #     urukul_ch =self.urukul_meas[0]
    #     dds_ftw_switch1_689_3nu=self.urukul_meas[0].frequency_to_ftw(fswitch1)
    #     urukul_ch.set_mu(dds_ftw_switch1_689_3nu, asf=urukul_ch.amplitude_to_asf(self.switch1_689_3nu_DDS_amplitude_scale))        
    
    # @kernel 
    # def set_switch1_phase(self,ph,t):
    #     self.urukul_meas[0].set(self.switch1_689_3nu_frequency,phase=ph, ref_time_mu=t)
        
    # @kernel 
    # def set_switch1_phase_freq(self,freq,ph,t):
    #     self.urukul_meas[0].set(freq,phase=ph, ref_time_mu=t)
        
    # @kernel 
    # def set_switch1_phase_freq_mu(self,freq,ph,t):
    #     dds_ftw_switch1_689_3nu=self.urukul_meas[0].frequency_to_ftw(freq)
    #     phpow = self.urukul_meas[0].turns_to_pow(ph)
    #     self.urukul_meas[0].set_mu(dds_ftw_switch1_689_3nu, pow_ = phpow, 
    #                                asf=self.urukul_meas[0].amplitude_to_asf(self.switch1_689_3nu_DDS_amplitude_scale),
    #                                ref_time_mu = t) 
    
    
    def index_artiq(self, aom) -> TInt32:
        if aom == 'Bragg1':
            return  0
        elif aom == 'Bragg2':
            return  1
        else:
            raise Exception("No AOM with that name")