# -*- coding: utf-8 -*-
"""
Created on Fri Jan 17 13:44:41 2025

@author: sr
"""


from artiq.experiment import EnvExperiment, NumberValue, delay, ms, kernel, TInt32, parallel, ns
import numpy as np

from artiq.coredevice.ad9910 import PHASE_MODE_TRACKING

class _state_control(EnvExperiment):


    def build(self):
        self.setattr_device("core")
        self.setattr_device("urukul0_cpld")
        
        

        # names for all our AOMs
        self.AOMs = ["688", 'PCarrier', '679', "689"]


        # default values for all params for all AOMs
        self.scales = [0.8, 0.8, 0.8, 0.8]

        self.attens = [8.0, 6.0, 10.0, 8.0]

        self.freqs = [80.0, 80.0, 200.0, 220.0]

        self.urukul_channels = [self.get_device("urukul0_ch0"),
                                self.get_device("urukul0_ch1"), 
                                self.get_device("urukul0_ch2"),
                                self.get_device("urukul0_ch3")]
        
        self.aom_688 = self.urukul_channels[0]
        self.aom_carrier = self.urukul_channels[1]
        self.aom_679 = self.urukul_channels[2]
        self.aom_689 = self.urukul_channels[3]

        # setting attributes to controll all AOMs
        for i in range(len(self.AOMs)):
            AOM = self.AOMs[i]
            self.setattr_argument(f"scale_{AOM}", NumberValue(self.scales[i], min=0.0, max=0.9), f"{AOM}_AOMs")
            self.setattr_argument(f"atten_{AOM}", NumberValue(self.attens[i], min=1.0, max=30), f"{AOM}_AOMs")
            self.setattr_argument(f"freq_{AOM}", NumberValue(self.freqs[i]*1e6, min=0.1000*1e6, max=350.0000*1e6, scale=1e6, unit='MHz'),  f"{AOM}_AOMs")


    def prepare_aoms(self):
        self.scales = [self.scale_688, self.scale_PCarrier, self.scale_679, self.scale_689]
        self.attens = [self.atten_688, self.atten_PCarrier, self.atten_679, self.atten_689]
        self.freqs = [self.freq_688, self.freq_PCarrier, self.freq_679, self.freq_689]

    @kernel
    def init_aoms(self, on=False):
        delay(50*ms)
        self.urukul0_cpld.init()
        for i in range(len(self.AOMs)):
            delay(2*ms)

            ch = self.urukul_channels[i]
            ch.init()

            set_f = ch.frequency_to_ftw(self.freqs[i])
            set_asf = ch.amplitude_to_asf(self.scales[i])
            ch.set_mu(set_f, asf=set_asf)
            ch.set_att(self.attens[i])
            if on:
                ch.sw.on()
            else:
                ch.sw.off()
        delay(50*ms)


   


                
    @kernel 
    def AOMs_off_all(self):
        for i in range(4):            
            self.urukul_channels[i].sw.off()
            
    @kernel 
    def AOMs_on_all(self):
        for i in range(4):            
            self.urukul_channels[i].sw.on()
            
            
            
            


    @kernel
    def set_AOM_freq(self, ind, freq): # takes in a list of tuples
        self.freqs[ind] = freq
        ch = self.urukul_channels[ind]
        set_freq = ch.frequency_to_ftw(freq)
        set_asf = ch.amplitude_to_asf(self.scales[ind])
        ch.set_mu(set_freq, asf=set_asf)

    @kernel 
    def set_AOM_freq_689(self,freq, amp=0.8):
        self.urukul_channels[3].set(frequency=freq,amplitude=amp)    
        
    @kernel 
    def set_AOM_freq_679(self, freq, amp=0.8):
        self.urukul_channels[2].set(frequency=freq,amplitude=amp)    
        
    @kernel 
    def set_AOM_freq_688(self, freq, amp=0.8):
        self.urukul_channels[0].set(frequency=freq,amplitude=amp)    


    @kernel
    def set_AOM_atten(self, ind, atten):
        self.attens[ind] = atten
        self.urukul_channels[ind].set_att(atten)


    @kernel
    def set_AOM_scale(self, ind, scale):
        self.scales[ind] = scale
        ch = self.urukul_channels[ind]
        set_freq = ch.frequency_to_ftw(self.freqs[ind])
        set_asf = ch.amplitude_to_asf(scale)
        ch.set_mu(set_freq, asf=set_asf)

    @kernel
    def set_AOM_phase(self, ind, freq, ph, t, prof=0):
        self.freqs[ind] = freq
        ch = self.urukul_channels[ind]
        ch.set(freq, phase=ph, phase_mode=PHASE_MODE_TRACKING, amplitude=0.8, ref_time_mu=t, profile=prof)
        
        
    @kernel
    def set_phase_mode(self, mode):
        for i in range(4):
            self.urukul_channels[i].set_phase_mode(mode)


    @kernel
    def switch_profile(self, prof=0):
        self.urukul_channels[0].cpld.set_profile(prof)
        

    @kernel 
    def shelf_pulse(self,t):
        self.pulse_688(t)
    
    @kernel 
    def pulse_688(self,t):
        
        rewind=450*ns
        added=130*ns
        
        delay(-rewind)
        self.pulse(self.aom_688, t, added)
        delay(rewind-added)
        
        
        
    @kernel 
    def pulse_679(self,t):
        rewind=450*ns
        added=100*ns
        
        delay(-rewind)
        self.pulse(self.aom_679, t, added)
        delay(rewind-added)
        
    @kernel 
    def pulse_689(self,t):
        rewind=400*ns
        added=100*ns
        
        delay(-rewind)
        self.pulse(self.aom_689, t, added)
        delay(rewind-added)     
    
    
    
    @kernel
    def pulse(self, dds, t, d=0.0):
        dds.sw.on()
        delay(t+d)
        dds.sw.off()
        




