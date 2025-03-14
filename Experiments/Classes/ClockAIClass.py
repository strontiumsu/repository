
"""
Created on Mon Feb 14 15:48:49 2022

@author: sr


"""

from artiq.experiment import EnvExperiment, NumberValue, delay, ms, kernel, TInt32, parallel, ns
import numpy as np

from artiq.coredevice.ad9910 import PHASE_MODE_TRACKING

class _ClockAI(EnvExperiment):


    def build(self):
        self.setattr_device("core")
        self.setattr_device("urukul0_cpld")
        
        self.setattr_device("ttl7") # for general triggering
        self.setattr_device("ttl5") 

        # names for all our AOMs
        self.AOMs = ["Unused", 'Push', 'AI1', "AI2"]


        # default values for all params for all AOMs
        self.scales = [0.8, 0.8, 0.8, 0.8]

        self.attens = [12.0, 6.0, 10.0, 10.0]
        # self.attens = [18.0, 5.0, 20.0, 20.0]

        self.freqs = [3.0, 205.0, 80.0, 80.0]
        
        self.AOM_SWITCH_TIME = 150*ns


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
        self.scales = [self.scale_Unused, self.scale_Push, self.scale_AI1, self.scale_AI2]
        self.attens = [self.atten_Unused, self.atten_Push, self.atten_AI1, self.atten_AI2]
        self.freqs = [self.freq_Unused, self.freq_Push, self.freq_AI1, self.freq_AI2]

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
        self.urukul_channels[0].set_phase_mode(mode)
        self.urukul_channels[1].set_phase_mode(mode)
        self.urukul_channels[2].set_phase_mode(mode)
        self.urukul_channels[3].set_phase_mode(mode)

    @kernel
    def switch_profile(self, prof=0, dds_num=2):
        self.urukul_channels[dds_num].cpld.set_profile(prof)

    @kernel 
    def pulse(self, time, dds):
        dds.sw.on()
        delay(time)
        dds.sw.off()
     
    @kernel
    def AI_pulse(self, time, arm):
        if time >= 50*ns:  
            self.ttl5.on()
            if arm == 0: self.AI1_pulse(time)
            if arm == 1: self.AI2_pulse(time)
            self.ttl5.off()
     
    ## fixed delays set 1/8/24, AOMs not yet focused
    @kernel
    def AI1_pulse(self, time):
        delay(-450*ns)
        self.urukul_channels[2].sw.on()
        delay(time-50*ns)
        self.urukul_channels[2].sw.off()
        delay(500*ns)
    
    @kernel
    def AI2_pulse(self, time):
            delay(-600*ns)
            self.urukul_channels[3].sw.on()
            delay(time-50*ns)
            self.urukul_channels[3].sw.off()
            delay(650*ns)
    
    # old AOM delay times
    # @kernel
    # def AI1_pulse(self, time):
    #     delay(-380*ns)
    #     self.urukul_channels[2].sw.on()
    #     delay(time+70*ns)
    #     self.urukul_channels[2].sw.off()
    #     delay(310*ns)
    
    # @kernel
    # def AI2_pulse(self, time):
    #     delay(-740*ns)
    #     self.urukul_channels[3].sw.on()
    #     delay(time+70*ns)
    #     self.urukul_channels[3].sw.off()
    #     delay(670*ns)
        
    @kernel
    def AI_pulse_pair1(self, time):
        self.urukul_channels[2].sw.on()
        delay(time)
        self.urukul_channels[2].sw.off()
        delay(self.AOM_SWITCH_TIME)
        self.urukul_channels[3].sw.on()
        delay(time)
        self.urukul_channels[3].sw.off()
        delay(self.AOM_SWITCH_TIME)
        
    @kernel
    def AI_pulse_pair2(self, time):
        self.urukul_channels[3].sw.on()
        delay(time)
        self.urukul_channels[3].sw.off()
        delay(self.AOM_SWITCH_TIME)
        self.urukul_channels[2].sw.on()
        delay(time)
        self.urukul_channels[2].sw.off()
        delay(self.AOM_SWITCH_TIME)
        
    @kernel
    def AI1_bs(self, time):
        
        self.urukul_channels[2].sw.on()
        delay(time)
        self.urukul_channels[2].sw.off()        
        delay(self.AOM_SWITCH_TIME)
        
    @kernel
    def AI_accel(self, pitime, numpulses, arm=1):
        if arm == 1:
            for i in range(int(numpulses)):
                self.AI_pulse_pair1(pitime)
            self.AI1_pulse(pitime)
            delay(self.AOM_SWITCH_TIME)
            
        else:
            for i in range(int(numpulses)):
                self.AI_pulse_pair2(pitime)
            self.AI2_pulse(pitime)
            delay(self.AOM_SWITCH_TIME)
            #self.AI1_pulse(pitime)
            #delay(pitime)
            #self.AI2_pulse(pitime)
            #delay(pitime)
    
    @kernel
    def AI_mirror(self, pitime, numpulses, arm=1):
        #self.ttl7.off()
        #if arm == 1:
        for i in range(int(numpulses/2)):
            self.AI_pulse_pair1(pitime)
            # self.AI2_pulse(pitime)
            # delay(pitime)
            # self.AI1_pulse(pitime)
            # delay(pitime)
        #self.AI2_pulse(pitime)
        #delay(pitime)

    @kernel 
    def push_pulse(self,t):
        self.urukul_channels[1].sw.on()
        delay(t)
        self.urukul_channels[1].sw.off()

    def index_artiq(self, aom) -> TInt32:
        for i in range(len(self.AOMs)):
            if self.AOMs[i] == aom:
                return i
        raise Exception("No AOM with that name")
