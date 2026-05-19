
"""
Created on Mon Feb 14 15:48:49 2022

@author: sr


"""

from artiq.experiment import EnvExperiment, NumberValue, delay, ms, kernel, TInt32, parallel, us
from artiq import *
import numpy as np

from artiq.coredevice.ad9910 import PHASE_MODE_TRACKING

class _Bragg(EnvExperiment):


    def build(self):
        self.setattr_device("core")
        self.setattr_device("urukul2_cpld")
        



        # names for all our AOMs
        self.AOMs = ["Dipole", 'Sideband', 'Carrier', "Lattice"]



        # default values for all params for all AOMs
        self.scales = [0.8, 0.8, 0.8, 0.8]
        self.attens = [12.0, 9.0, 6.0, 3.0]
        self.freqs = [80.0, 3.0, 80.0, 80.0]


        self.urukul_channels = [self.get_device("urukul2_ch0"),
                                self.get_device("urukul2_ch1"), 
                                self.get_device("urukul2_ch2"),
                                self.get_device("urukul2_ch3")]
        
        self.aom_dipole = self.urukul_channels[0]
        self.aom_sideband = self.urukul_channels[1]
        self.aom_carrier = self.urukul_channels[2]
        self.aom_lattice = self.urukul_channels[3]

        # setting attributes to controll all AOMs
        for i in range(len(self.AOMs)):
            AOM = self.AOMs[i]
            self.setattr_argument(f"scale_{AOM}", NumberValue(self.scales[i], min=0.0, max=0.9, ndecimals=3), f"{AOM}_AOMs")
            self.setattr_argument(f"atten_{AOM}", NumberValue(self.attens[i], min=1.0, max=30, ndecimals=3), f"{AOM}_AOMs")
            self.setattr_argument(f"freq_{AOM}", NumberValue(self.freqs[i]*1e6, min=0.1000*1e6, max=351.0000*1e6, scale=1e6, unit='MHz', ndecimals=3),  f"{AOM}_AOMs")


    def prepare_aoms(self):
        self.scales = [self.scale_Dipole, self.scale_Sideband, self.scale_Carrier, self.scale_Lattice]
        self.attens = [self.atten_Dipole, self.atten_Sideband, self.atten_Carrier, self.atten_Lattice]
        self.freqs = [self.freq_Dipole, self.freq_Sideband, self.freq_Carrier, self.freq_Lattice]

    @kernel
    def init_aoms(self, switches=0x9):
        delay(1*ms)     
        self.urukul2_cpld.init()
        
        for i in range(4):
            ch = self.urukul_channels[i]
            ch.init()
            if ( switches >> i ) & 0b1 == 1:
                ch.sw.on()
            else:
                ch.sw.off()               
            ch.set_att(self.attens[i])
            ch.set(self.freqs[i], 0.0, self.scales[i])
            delay(1*ms)

        delay(1*ms)
        
        
    # basic AOM methods
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
        self.aom_dipole.cpld.set_profile(prof)



    @kernel
    def lattice_rampdown(self, end, time):
        dt = time/31
        for step in range(int(31)):
            atten = self.atten_Lattice + ((end-self.atten_Lattice)/time)*step*dt
            self.aom_lattice.set_att(atten)
            delay(dt)
        #self.atten[3] = end

    @kernel
    def dipole_rampdown(self, end, time):
        dt = time/31
        for step in range(int(31)):
            atten = self.atten_Dipole + ((end-self.atten_Dipole)/time)*step*dt
            self.aom_dipole.set_att(atten)
            delay(dt)
        #self.atten[3] = end
        
    @kernel
    def dipole_lattice_rampdown(self, end, time):
        dt = time/101
        for step in range(int(31)):
            atten = self.atten_Dipole + ((end-self.atten_Dipole)/time)*step*dt
            self.aom_dipole.set_att(atten)
            delay(dt/2)
            atten = self.atten_Lattice + ((end-self.atten_Lattice)/time)*step*dt
            self.aom_lattice.set_att(atten)
            delay(dt/2)

    


