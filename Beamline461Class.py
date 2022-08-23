# -*- coding: utf-8 -*-
"""
Created on Mon Feb 14 15:48:49 2022

@author: sr

Functions:
    
Set Zeeman slower aom amplitutde (scannable) and frequency
Set 2D mot aom
Set 3D mot aom


"""

from artiq.experiment import *
import numpy as np     

class Beamline461(EnvExperiment):
      
    
    def build(self):
        
        self.setattr_device("urukul1_cpld")
        
        
        # 3D MOT AOM  
        self.setattr_argument("MOT3DDP_AOM_frequency",
            Scannable(default=[NoScan(87*1e6), RangeScan(80*1e6, 100*1e6, 1, randomize=False)],scale=1e6,
                      unit="MHz"),"MOT3DDP")
        self.setattr_argument("MOT3DDP_DDS_amplitude_scale",NumberValue(0.8,min=0.0,max=0.8),"MOT3DDP")
        self.setattr_argument("MOT3DDP_Urukul_attenuation",NumberValue(6.0,min=1.0,max=30.0),"MOT3DDP")
        
        # Zeeman slower AOM
        self.setattr_argument("Zeeman_AOM_frequency",NumberValue(300*1e6,min=250*1e6,max=350*1e6,scale=1e6,unit='MHz'),"Zeeman")
        self.setattr_argument("Zeeman_DDS_amplitude_scale",NumberValue(0.8,min=0.0,max=0.95),"Zeeman")
        self.setattr_argument("Zeeman_Urukul_attenuation",NumberValue(18.0,min=0.0,max=30.0),"Zeeman")

        
        # 2D MOT AOM
        
        self.setattr_argument("MOT2D_AOM_frequency",NumberValue(194*1e6,min=170*1e6,max=250*1e6,scale=1e6,unit='MHz'),"MOT2D")
        self.setattr_argument("MOT2D_DDS_amplitude_scale",NumberValue(0.8,min=0.0,max=0.8),"MOT2D")
        self.setattr_argument("MOT2D_Urukul_attenuation",NumberValue(11.5,min=1.0,max=30.0),"MOT2D")
        
        
        # Probe AOM 
        #self.setattr_argument("Probe_AOM_frequency",
        #    Scannable(default=[RangeScan(30*1e6, 50*1e6, 1, randomize=False),NoScan(40*1e6)],scale=1e6,
        #              unit="MHz"),"Probe_AOM")
        self.setattr_argument("Probe_AOM_frequency",NumberValue(40*1e6,min=10*1e6,max=60*1e6,scale=1e6,unit='MHz'),"Probe_AOM")
        self.setattr_argument("Probe_AOM_DDS_amplitude_scale",NumberValue(0.8,min=0.0,max=0.99),"Probe_AOM")
        self.setattr_argument("Probe_AOM_Urukul_attenuation",NumberValue(11.5,min=0.0,max=30.0),"Probe_AOM")
        
        

        self.urukul_hmc_ref_MOT2D = self.get_device("urukul1_ch0")
        self.urukul_hmc_ref_MOT3DDP = self.get_device("urukul1_ch1")
        self.urukul_hmc_ref_Zeeman = self.get_device("urukul1_ch2")
        self.urukul_hmc_ref_Probe_AOM = self.get_device("urukul1_ch3")
        
        self.urukul_meas = [self.get_device("urukul1_ch0"),self.get_device("urukul1_ch1"),self.get_device("urukul1_ch2"),self.get_device("urukul1_ch3")]
        
        self.f_MOT3D_load=self.get_dataset('blue_MOT.f_load3D')
        self.f_MOT3D_detect=self.get_dataset('blue_MOT.f_detect')
        self.f_push=self.get_dataset('blue_MOT.f_push')
        
    def set_atten_ZS(self):   # set the DDS amplitude and attenuation for the Zeeman slower only
        self.Zeeman_dds_scale=self.Zeeman_DDS_amplitude_scale
        self.Zeeman_iatten=self.Zeeman_Urukul_attenuation
    
    def set_atten_MOT2D(self):
        self.MOT2D_dds_scale=self.MOT2D_DDS_amplitude_scale
        self.MOT2D_iatten=self.MOT2D_Urukul_attenuation
        
    def set_atten_MOT3DDP(self,user_atten):
        if user_atten >= 0.:
            self.MOT3DDP_dds_scale=self.MOT3DDP_DDS_amplitude_scale
            self.MOT3DDP_iatten=user_atten
        else:    
            self.MOT3DDP_dds_scale=self.MOT3DDP_DDS_amplitude_scale
            self.MOT3DDP_iatten=self.MOT3DDP_Urukul_attenuation
            
    def set_atten_Probe_AOM(self):   # set the DDS amplitude and attenuation for the Zeeman slower only
        self.Probe_AOM_dds_scale=self.Probe_AOM_amplitude_scale
        self.Probe_AOM_iatten=self.Probe_AOM_Urukul_attenuation
    
    def set_atten(self):
        self.Zeeman_dds_scale=self.Zeeman_DDS_amplitude_scale
        self.MOT2D_dds_scale=self.MOT2D_DDS_amplitude_scale
        self.MOT3DDP_dds_scale=self.MOT3DDP_DDS_amplitude_scale
        self.Probe_AOM_dds_scale=self.Probe_AOM_DDS_amplitude_scale
           
        self.Zeeman_iatten=self.Zeeman_Urukul_attenuation
        self.MOT2D_iatten=self.MOT2D_Urukul_attenuation
        self.MOT3DDP_iatten=self.MOT3DDP_Urukul_attenuation
        self.Probe_AOM_iatten=self.Probe_AOM_Urukul_attenuation
        
    @kernel    
    def init_aoms(self):
        
        delay(1*ms)
        self.urukul1_cpld.init()
        
        delay(10*ms)

        self.urukul_hmc_ref_MOT3DDP.init()
        self.urukul_hmc_ref_MOT3DDP.set_mu(0x40000000, asf=self.urukul_hmc_ref_MOT3DDP.amplitude_to_asf(self.MOT3DDP_dds_scale))
        self.urukul_hmc_ref_MOT3DDP.set_att(self.MOT3DDP_iatten)
        self.urukul_hmc_ref_MOT3DDP.sw.on()
        
        delay(10*ms)
            
        self.urukul_hmc_ref_Zeeman.init()
        self.urukul_hmc_ref_Zeeman.set_mu(0x40000000, asf=self.urukul_hmc_ref_Zeeman.amplitude_to_asf(self.Zeeman_dds_scale))
        self.urukul_hmc_ref_Zeeman.set_att(self.Zeeman_iatten)
        self.urukul_hmc_ref_Zeeman.sw.on()

        delay(10*ms)
            
        self.urukul_hmc_ref_MOT2D.init()
        self.urukul_hmc_ref_MOT2D.set_mu(0x40000000, asf=self.urukul_hmc_ref_MOT2D.amplitude_to_asf(self.MOT2D_dds_scale))
        self.urukul_hmc_ref_MOT2D.set_att(self.MOT2D_iatten)
        self.urukul_hmc_ref_MOT2D.sw.on()
            
        delay(10*ms)    
        self.urukul_hmc_ref_Probe_AOM.init()
        self.urukul_hmc_ref_Probe_AOM.set_mu(0x40000000, asf=self.urukul_hmc_ref_Probe_AOM.amplitude_to_asf(self.Probe_AOM_dds_scale))
        self.urukul_hmc_ref_Probe_AOM.set_att(self.Probe_AOM_iatten)
        self.urukul_hmc_ref_Probe_AOM.sw.on()
        
        
        
        urukul_ch =self.urukul_meas[2]
        urukul_ch.init()
        fZeeman = self.Zeeman_AOM_frequency
        dds_ftw_Zeeman=self.urukul_meas[2].frequency_to_ftw(fZeeman)
                
        urukul_ch.set_mu(dds_ftw_Zeeman, asf=urukul_ch.amplitude_to_asf(self.Zeeman_dds_scale))
        urukul_ch.set_att(self.Zeeman_iatten)
        urukul_ch.sw.on()
        
        delay(10*ms)                    
                
        urukul_ch =self.urukul_meas[0]
        urukul_ch.init()

        fMOT2D = self.MOT2D_AOM_frequency
        dds_ftw_MOT2D=self.urukul_meas[0].frequency_to_ftw(fMOT2D)
                
        urukul_ch.set_mu(dds_ftw_MOT2D, asf=urukul_ch.amplitude_to_asf(self.MOT2D_dds_scale))
        urukul_ch.set_att(self.MOT2D_iatten)
        urukul_ch.sw.on() 
            
        delay(10*ms)
        
        urukul_ch =self.urukul_meas[1]
        urukul_ch.init() 
        
       
        dds_ftw_MOT3DDP=self.urukul_meas[1].frequency_to_ftw(self.f_MOT3D_load)
            
        urukul_ch.set_mu(dds_ftw_MOT3DDP, asf=urukul_ch.amplitude_to_asf(self.MOT3DDP_dds_scale))
        urukul_ch.set_att(self.MOT3DDP_iatten)
        urukul_ch.sw.on()
        
        delay(10*ms)
        
        urukul_ch =self.urukul_meas[3]
        urukul_ch.init()

        fProbe_AOM = self.Probe_AOM_frequency
        dds_ftw_Probe_AOM=self.urukul_meas[3].frequency_to_ftw(fProbe_AOM)
                
        urukul_ch.set_mu(dds_ftw_Probe_AOM, asf=urukul_ch.amplitude_to_asf(self.Probe_AOM_dds_scale))
        urukul_ch.set_att(self.Probe_AOM_iatten)
        urukul_ch.sw.on() 
            
        delay(10*ms)
    @kernel    
    def reinit_MOT3DDP_aom(self, user_atten, user_freq):
        
        urukul_ch = self.urukul_meas[1]
        urukul_ch.set_att(user_atten) 
        urukul_ch.set_mu(urukul_ch.frequency_to_ftw(user_freq), asf=urukul_ch.amplitude_to_asf(self.MOT3DDP_dds_scale))
        
        # urukul_ch =self.urukul_meas[1]
        # urukul_ch.init() 

        # dds_ftw_MOT3DDP=self.urukul_meas[1].frequency_to_ftw(user_freq)
            
        # urukul_ch.set_mu(dds_ftw_MOT3DDP, asf=urukul_ch.amplitude_to_asf(self.MOT3DDP_dds_scale))
        # urukul_ch.set_att(user_atten)
        # urukul_ch.sw.on()   
         
        
    @kernel 
    def set_MOT3DDP_aom_frequency(self, freq): 
      
        urukul_ch =self.urukul_meas[1]
        dds_ftw_MOT3DDP_AOM=self.urukul_meas[1].frequency_to_ftw(freq)
        urukul_ch.set_mu(dds_ftw_MOT3DDP_AOM, asf=urukul_ch.amplitude_to_asf(self.MOT3DDP_dds_scale)) 
        
    @kernel 
    def set_MOT3DDP_aom_atten(self, user_atten): 
      
        #urukul_ch =self.urukul_meas[1]
        #urukul_ch.set_mu(dds_ftw_MOT3DDP, asf=urukul_ch.amplitude_to_asf(self.MOT3DDP_dds_scale))
        self.urukul_meas[1].set_att(user_atten) 
        
    @kernel    
    def reinit_Probe_aom(self, user_atten, user_freq):
        
        urukul_ch = self.urukul_meas[3]
        delay(100*ms)
        urukul_ch.set_att(user_atten) 
        delay(100*ms)
        urukul_ch.set_mu(urukul_ch.frequency_to_ftw(user_freq), asf=urukul_ch.amplitude_to_asf(self.Probe_AOM_dds_scale))
        delay(100*ms)
        
    @kernel 
    def set_Probe_aom_frequency(self, freq): 
      
        urukul_ch =self.urukul_meas[3]
        dds_ftw_Probe_AOM=self.urukul_meas[3].frequency_to_ftw(freq*1e6)
        urukul_ch.set_mu(dds_ftw_Probe_AOM, asf=urukul_ch.amplitude_to_asf(self.Probe_AOM_dds_scale)) 
        
    @kernel 
    def shift_MOT2D_aom_frequency(self,df): 
      
        
        urukul_ch =self.urukul_meas[0]
        dds_ftw_MOT2D_AOM=self.urukul_meas[0].frequency_to_ftw(self.MOT2D_AOM_frequency + df*1e6)
        urukul_ch.set_mu(dds_ftw_MOT2D_AOM, asf=urukul_ch.amplitude_to_asf(self.MOT2D_dds_scale)) 
        
    @kernel 
    def shift_MOT3DDP_aom_frequency(self, df): 
        
     
        urukul_ch =self.urukul_meas[1]
        dds_ftw_MOT3DDP_AOM=self.urukul_meas[1].frequency_to_ftw(self.MOT3DDP_AOM_frequency+df*1e6)
        urukul_ch.set_mu(dds_ftw_MOT3DDP_AOM, asf=urukul_ch.amplitude_to_asf(self.MOT3DDP_dds_scale)) 
        
    @kernel 
    def pulse_3D_MOT(self,t):     # Pulse the 3D MOT beams on for duration t
        urukul_ch =self.urukul_meas[1]
        urukul_ch.sw.on()  
        delay(t)
        urukul_ch.sw.off() 
        
    @kernel
    def MOT_on(self):    
        urukul_ch =self.urukul_meas[1]
        urukul_ch.sw.on()  
        
    @kernel
    def MOT_off(self):    
        urukul_ch =self.urukul_meas[1]
        urukul_ch.sw.off()        
        
    @kernel
    def MOT2D_on(self):    
        urukul_ch =self.urukul_meas[0]
        urukul_ch.sw.on()  
        
    @kernel
    def MOT2D_off(self):    
        urukul_ch =self.urukul_meas[0]
        urukul_ch.sw.off()
        
        
    @kernel
    def Zeeman_on(self):    
        urukul_ch =self.urukul_meas[2]
        urukul_ch.sw.on()  
        
    @kernel
    def Zeeman_off(self):    
        urukul_ch =self.urukul_meas[2]
        urukul_ch.sw.off()
 
        
    @kernel
    def Probe_AOM_on(self):    
        urukul_ch =self.urukul_meas[3]
        urukul_ch.sw.on()  
        
    @kernel
    def Probe_AOM_off(self):    
        urukul_ch =self.urukul_meas[3]
        urukul_ch.sw.off()    
        
        
        
    # def scan_probe(nreps):
        
    #     delay(1*ms)
    #     self.urukul1_cpld.init()
        
    #     urukul_ch =self.urukul_meas[3]
    #     urukul_ch.init()
    #     urukul_ch.set_att(self.probeDP_iatten)
    #     urukul_ch.sw.on()
            
    #     for kk in range(nreps):
    #         for ii in range(len(self.ProbeDP_AOM_frequency.sequence)):
                     
    #             fprobeDP = self.ProbeDP_AOM_frequency.sequence[ii]
    #             dds_ftw_probeDP=self.urukul_meas[3].frequency_to_ftw(fprobeDP)
    #             delay(2*ms)
    #             urukul_ch.set_mu(dds_ftw_probeDP, asf=urukul_ch.amplitude_to_asf(self.probeDP_dds_scale))
        
    