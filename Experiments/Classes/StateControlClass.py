# -*- coding: utf-8 -*-
"""
Created on Fri Jan 17 13:44:41 2025

@author: sr
"""


from artiq.experiment import EnvExperiment, NumberValue, delay, ms, kernel, TInt32, parallel, ns
import numpy as np

from artiq.coredevice.ad9910 import PHASE_MODE_TRACKING

class _STATE_CONTROL(EnvExperiment):


    def build(self):
        self.setattr_device("core")
        self.setattr_device("urukul0_cpld")
        
        self.setattr_device("ttl7") # for general triggering

        # names for all our AOMs
        self.AOMs = ["688", 'Push', '679', "689"]


        # default values for all params for all AOMs
        self.scales = [0.8, 0.8, 0.8, 0.8]

        self.attens = [8.0, 6.0, 6.0, 12.0]

        self.freqs = [80.0, 205.0, 200.14, 190.0]

        self.urukul_channels = [self.get_device("urukul0_ch0"),
                                self.get_device("urukul0_ch1"), 
                                self.get_device("urukul0_ch2"),
                                self.get_device("urukul0_ch3")]

        # setting attributes to controll all AOMs
        for i in range(len(self.AOMs)):
            AOM = self.AOMs[i]
            self.setattr_argument(f"scale_{AOM}", NumberValue(self.scales[i], min=0.0, max=0.9), f"{AOM}_AOMs")
            self.setattr_argument(f"atten_{AOM}", NumberValue(self.attens[i], min=1.0, max=30), f"{AOM}_AOMs")
            self.setattr_argument(f"freq_{AOM}", NumberValue(self.freqs[i]*1e6, min=0.1000*1e6, max=350.0000*1e6, scale=1e6, unit='MHz'),  f"{AOM}_AOMs")


    def prepare_aoms(self):
        self.scales = [self.scale_688, self.scale_Push, self.scale_679, self.scale_689]
        self.attens = [self.atten_688, self.atten_Push, self.atten_679, self.atten_689]
        self.freqs = [self.freq_688, self.freq_Push, self.freq_679, self.freq_689]

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


    # basic AOM methods
    @kernel
    def AOMs_on(self, AOMs):
        with parallel:
            for aom in AOMs:
                self.urukul_channels[self.index_artiq(aom)].sw.on()


    @kernel
    def AOMs_off(self, AOMs):
        with parallel:
            for aom in AOMs:
                self.urukul_channels[self.index_artiq(aom)].sw.off()

    @kernel
    def set_AOM_freqs(self, freq_list): # takes in a list of tuples
        with parallel:
            for aom, freq in freq_list:
                ind = self.index_artiq(aom)
                self.freqs[ind] = freq
                ch = self.urukul_channels[ind]
                set_freq = ch.frequency_to_ftw(freq)
                set_asf = ch.amplitude_to_asf(self.scales[ind])
                ch.set_mu(set_freq, asf=set_asf)


    @kernel
    def set_AOM_attens(self, atten_list):
        with parallel:
            for aom, atten in atten_list:
                ind = self.index_artiq(aom)
                self.attens[ind] = atten
                self.urukul_channels[ind].set_att(atten)


    @kernel
    def set_AOM_scales(self, scale_list):
        with parallel:
            for aom, scale in scale_list:
                ind = self.index_artiq(aom)
                self.scales[ind] = scale
                ch = self.urukul_channels[ind]
                set_freq = ch.frequency_to_ftw(self.freqs[ind])
                set_asf = ch.amplitude_to_asf(self.scales[ind])
                ch.set_mu(set_freq, asf=set_asf)

    @kernel
    def set_AOM_phase(self, aom_name, freq, ph, t, prof=0):
        ind = self.index_artiq(aom_name)
        self.freqs[ind] = freq
        ch = self.urukul_channels[ind]
        ch.set(freq, phase=ph, phase_mode=PHASE_MODE_TRACKING, ref_time_mu=t, profile=prof)

    @kernel
    def set_phase_mode(self, mode):
        for i in range(4):
            self.urukul_channels[i].set_phase_mode(mode)


    @kernel
    def switch_profile(self, prof=0, dds_num=2):
        self.urukul_channels[dds_num].cpld.set_profile(prof)

    @kernel 
    def pulse(self, time, dds):
        dds.sw.on()
        delay(time)
        dds.sw.off()
    
    @kernel 
    def shelf_pulse(self,t):
        self.urukul_channels[0].sw.on()
        delay(t)
        self.urukul_channels[0].sw.off()
        
    @kernel 
    def push_pulse(self,t):
        self.urukul_channels[1].sw.on()
        delay(t)
        self.urukul_channels[1].sw.off()
        

        
    @kernel 
    def pulse_688(self,t):
        
        rewind=550*ns
        added=130*ns
        
        delay(-rewind)
        self.pulse(t, 0, added)
        delay(rewind-added)
        
    @kernel 
    def pulse_679(self,t):
        rewind=450*ns
        added=100*ns
        
        delay(-rewind)
        self.pulse(t, 2, added)
        delay(rewind-added)
        

        
    @kernel 
    def pulse_689(self,t):
        rewind=700*ns
        added=100*ns
        
        delay(-rewind)
        self.pulse(t, 3, added)
        delay(rewind-added)     
    
    @kernel
    def pulse(self, t, ch, d):
        self.urukul_channels[ch].sw.on()
        delay(t+d)
        self.urukul_channels[ch].sw.off()
        

    def index_artiq(self, aom) -> TInt32:
        for i in range(len(self.AOMs)):
            if self.AOMs[i] == aom:
                return i
        raise Exception("No AOM with that name")
        


