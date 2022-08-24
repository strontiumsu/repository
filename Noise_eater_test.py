# -*- coding: utf-8 -*-
"""
Created on Fri Aug 12 10:44:00 2022

@author: sr
"""

# -*- coding: utf-8 -*-
"""
Created on Wed Mar 30 18:37:28 2022

@author: sr
"""

from artiq.experiment import *
import numpy as np
from fit_image import Fit2DGaussParabola


class Noise_eater_test(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.setattr_device("ttl5")
        self.setattr_device("urukul2_cpld")



        self.setattr_argument("Hp688_AOM_frequency",NumberValue(80*1e6,min=25*1e6,max=250*1e6,scale=1e6,unit='MHz'),"AOM")
        self.setattr_argument("Hp688_DDS_amplitude_scale",NumberValue(0.8,min=0.0,max=0.8),"AOM")
        self.setattr_argument("Hp688_Urukul_attenuation",NumberValue(13,min=1.0,max=30.0),"AOM")

        self.urukul_hmc_ref_test = self.get_device("urukul2_ch3")

        self.urukul_meas =  self.get_device("urukul2_ch3")


    def set_atten(self):

        #

        # self.test_dds_scale=
        self.test_iatten=self.Hp688_Urukul_attenuation


    @kernel
    def init_aoms(self):

        delay(1*ms)
        self.urukul2_cpld.init()

        #self.urukul_hmc_ref_Red_MOT.init()
        #self.urukul_hmc_ref_Red_MOT.set_mu(0x40000000, asf=self.urukul_hmc_ref_Red_MOT.amplitude_to_asf(self.Red_MOT_dds_scale))
        #self.urukul_hmc_ref_Red_MOT.set_att(self.Red_MOT_iatten)
        #self.urukul_hmc_ref_Red_MOT.sw.on()

        delay(10*ms)
        self.urukul_hmc_ref_3P0_repumper.init()
        self.urukul_hmc_ref_3P0_repumper.set_mu(0x40000000, asf=self.urukul_hmc_ref_3P0_repumper.amplitude_to_asf(self.repumper_3P0_dds_scale))
        self.urukul_hmc_ref_3P0_repumper.set_att(self.repumper_3P0_iatten)
        self.urukul_hmc_ref_3P0_repumper.sw.on()
        delay(10*ms)
        self.urukul_hmc_ref_3P2_repumper.init()
        self.urukul_hmc_ref_3P2_repumper.set_mu(0x40000000, asf=self.urukul_hmc_ref_3P2_repumper.amplitude_to_asf(self.repumper_3P2_dds_scale))
        self.urukul_hmc_ref_3P2_repumper.set_att(self.repumper_3P2_iatten)
        self.urukul_hmc_ref_3P2_repumper.sw.on()
        delay(10*ms)

        self.urukul_hmc_ref_Hp688.init()
        self.urukul_hmc_ref_Hp688.set_mu(0x40000000, asf=self.urukul_hmc_ref_Hp688.amplitude_to_asf(self.Hp688_dds_scale))
        self.urukul_hmc_ref_Hp688.set_att(self.Hp688_iatten)
        self.urukul_hmc_ref_Hp688.sw.on()
        delay(10*ms)

        urukul_ch =self.urukul_meas[0]
        urukul_ch.init()
        dds_ftw_3P0_repumper=self.urukul_meas[0].frequency_to_ftw(self.repumper_3P0_frequency)
        urukul_ch.set_mu(dds_ftw_3P0_repumper, asf=urukul_ch.amplitude_to_asf(self.repumper_3P0_dds_scale))
        urukul_ch.set_att(self.repumper_3P0_iatten)
        urukul_ch.sw.on()
        delay(10*ms)

        urukul_ch =self.urukul_meas[1]
        urukul_ch.init()
        dds_ftw_3P2_repumper=self.urukul_meas[1].frequency_to_ftw(self.repumper_3P2_frequency)
        urukul_ch.set_mu(dds_ftw_3P2_repumper, asf=urukul_ch.amplitude_to_asf(self.repumper_3P2_dds_scale))
        urukul_ch.set_att(self.repumper_3P2_iatten)
        urukul_ch.sw.on()
        delay(10*ms)

        urukul_ch =self.urukul_meas[2]
        urukul_ch.init()
        dds_ftw_Hp688=self.urukul_meas[2].frequency_to_ftw(self.Hp688_AOM_frequency)
        urukul_ch.set_mu(dds_ftw_Hp688, asf=urukul_ch.amplitude_to_asf(self.Hp688_dds_scale))
        urukul_ch.set_att(self.Hp688_iatten)
        urukul_ch.sw.on()
        delay(10*ms)


    ####################################################
    ############### Red MOT methods ####################
    ####################################################
    @kernel
    def set_Red_MOT_aom_frequency(self, freq):

        urukul_ch =self.urukul_meas[0]
        dds_ftw_Red_MOT_AOM=self.urukul_meas[0].frequency_to_ftw(freq)
        urukul_ch.set_mu(dds_ftw_Red_MOT_AOM, asf=urukul_ch.amplitude_to_asf(self.Red_MOT_dds_scale))


    @kernel
    def shift_Red_MOT_aom_frequency(self, df):


        urukul_ch =self.urukul_meas[0]
        dds_ftw_Red_MOT_AOM=self.urukul_meas[0].frequency_to_ftw(self.Red_MOT_AOM_frequency+df*1e6)
        urukul_ch.set_mu(dds_ftw_Red_MOT_AOM, asf=urukul_ch.amplitude_to_asf(self.Red_MOT_dds_scale))

    @kernel
    def reinit_Red_MOT_aom(self, user_atten, user_freq):

        urukul_ch = self.urukul_meas[0]
        urukul_ch.set_att(user_atten)
        urukul_ch.set_mu(urukul_ch.frequency_to_ftw(user_freq), asf=urukul_ch.amplitude_to_asf(self.Red_MOT_dds_scale))

    @kernel
    def Red_MOT_aom_off(self):
        urukul_ch =self.urukul_meas[0]
        urukul_ch.sw.off()

    @kernel
    def Red_MOT_aom_on(self):
        urukul_ch =self.urukul_meas[0]
        urukul_ch.sw.on()


    ####################################################
    ############# Repumper MOT methods #################
    ####################################################

    @kernel
    def set_3P0_repumper_frequency(self, freq):

        urukul_ch =self.urukul_meas[0]
        dds_ftw_3P0_repumper_AOM=self.urukul_meas[0].frequency_to_ftw(freq)
        urukul_ch.set_mu(dds_ftw_3P0_repumper_AOM, asf=urukul_ch.amplitude_to_asf(self.repumper_3P0_dds_scale))

    @kernel
    def set_3P2_repumper_frequency(self, freq):

        urukul_ch =self.urukul_meas[1]
        dds_ftw_3P2_repumper_AOM=self.urukul_meas[1].frequency_to_ftw(freq)
        urukul_ch.set_mu(dds_ftw_3P2_repumper_AOM, asf=urukul_ch.amplitude_to_asf(self.repumper_3P2_dds_scale))


    @kernel
    def shift_3P0_repumper_frequency(self, df):   # df in MHz

        urukul_ch =self.urukul_meas[0]
        dds_ftw_3P0_repumper_AOM=self.urukul_meas[0].frequency_to_ftw(self.repump_3P0_frequency+df*1e6)
        urukul_ch.set_mu(dds_ftw_3P0_repumper_AOM, asf=urukul_ch.amplitude_to_asf(self.repumper_3P0_dds_scale))

    @kernel
    def shift_3P2_repumper_frequency(self, df):   # df in MHz

        urukul_ch =self.urukul_meas[1]
        dds_ftw_3P2_repumper_AOM=self.urukul_meas[1].frequency_to_ftw(self.repump_3P2_frequency+df*1e6)
        urukul_ch.set_mu(dds_ftw_3P2_repumper_AOM, asf=urukul_ch.amplitude_to_asf(self.repumper_3P2_dds_scale))


    @kernel
    def reinit_3P0_repumper_aom(self, user_atten, user_freq):

        urukul_ch = self.urukul_meas[0]
        urukul_ch.set_att(user_atten)
        urukul_ch.set_mu(urukul_ch.frequency_to_ftw(user_freq), asf=urukul_ch.amplitude_to_asf(self.repumper_3P0_dds_scale))

    @kernel
    def reinit_3P2_repumper_aom(self, user_atten, user_freq):

        urukul_ch = self.urukul_meas[1]
        urukul_ch.set_att(user_atten)
        urukul_ch.set_mu(urukul_ch.frequency_to_ftw(user_freq), asf=urukul_ch.amplitude_to_asf(self.repumper_3P2_dds_scale))

    @kernel
    def repumper_3P0_off(self):
        urukul_ch =self.urukul_meas[0]
        urukul_ch.sw.off()

    @kernel
    def repumper_3P2_off(self):
        urukul_ch =self.urukul_meas[1]
        urukul_ch.sw.off()

    @kernel
    def repumpers_off(self):
        self.repumper_3P0_off()
        self.repumper_3P2_off()

    @kernel
    def repumper_3P0_on(self):
        urukul_ch =self.urukul_meas[0]
        urukul_ch.sw.on()

    @kernel
    def repumper_3P2_on(self):
        urukul_ch =self.urukul_meas[1]
        urukul_ch.sw.on()

    @kernel
    def repumpers_on(self):
        self.repumper_3P0_on()
        self.repumper_3P2_on()


    ####################################################
    ############ High Power 688 methods ################
    ####################################################

    @kernel
    def set_Hp688_aom_frequency(self, freq):

        urukul_ch =self.urukul_meas[2]
        dds_ftw_Hp688_AOM=self.urukul_meas[2].frequency_to_ftw(freq)
        urukul_ch.set_mu(dds_ftw_Hp688_AOM, asf=urukul_ch.amplitude_to_asf(self.Hp688_dds_scale))


    @kernel
    def shift_Hp688_aom_frequency(self, df):


        urukul_ch =self.urukul_meas[2]
        dds_ftw_Hp688_AOM=self.urukul_meas[2].frequency_to_ftw(self.Hp688_AOM_frequency+df*1e6)
        urukul_ch.set_mu(dds_ftw_Hp688_AOM, asf=urukul_ch.amplitude_to_asf(self.Hp688_dds_scale))

    @kernel
    def reinit_Hp688_aom(self, user_atten, user_freq):

        urukul_ch = self.urukul_meas[2]
        urukul_ch.set_att(user_atten)
        urukul_ch.set_mu(urukul_ch.frequency_to_ftw(user_freq), asf=urukul_ch.amplitude_to_asf(self.Hp688_dds_scale))

    @kernel
    def Hp688_aom_off(self):
        urukul_ch =self.urukul_meas[2]
        urukul_ch.sw.off()

    @kernel
    def Hp688_aom_on(self):
        urukul_ch =self.urukul_meas[2]
        urukul_ch.sw.on()
