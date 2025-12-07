# -*- coding: utf-8 -*-
"""
Created on Tue Aug 26 15:39:30 2025

@author: sr
"""

from artiq.experiment import *
from scan_framework import Scan1D
import numpy as np
from artiq.coredevice import ad9910

from CoolingClass import _Cooling
from BraggClass import _Bragg
from CameraClass import _Camera
from StateControlClass import _state_control

import time

class VRS_scan_calib_exp(Scan1D, EnvExperiment):
    
    def build(self, **kwargs):
        
        super().build(**kwargs)
        
        # hardware and class objects
        self.setattr_device("ttl5")
        self.MOTs = _Cooling(self)
        self.Bragg = _Bragg(self)
        self.State_Control = _state_control(self)
        self.Camera = _Camera(self)
        
        
        # cavity offset freqs (must be set by hand from comb)
        self.setattr_argument('offset_freqs', Scannable(default=RangeScan(start=0*kHz,stop=500*kHz,npoints=6),scale=1*kHz,ndecimals=1,unit="kHz"))
        
        self.scan_arguments(
                            nbins = {'default':1000}, 
                            nrepeats = {'default':1},
                            npasses = {'default':1},
                            fit_options = {'default':"No Fits"} 
                            )
        
        #parameters
        self.setattr_argument("B_field", NumberValue(0.21,min=0.0,max=2,scale=1, unit="V", ndecimals=3),"parameters")
        self.setattr_argument("pi_time_689", NumberValue(1.0*1e-6,min=0.0*1e-6,max=1000.00*1e-6,scale=1e-6, unit="us"),"parameters")
        self.setattr_argument("pi_time_Ramsey", NumberValue(1.0*1e-6,min=0.0*1e-6,max=1000.00*1e-6,scale=1e-6,unit="us"),"parameters")
        self.setattr_argument("dipole_load_time", NumberValue(20.0*1e-3,min=0.0*1e-3,max=9000.00*1e-3,scale=1e-3, unit="ms"),"parameters")
        
        # VRS Scan args
        self.setattr_argument("freq_center", NumberValue( 3*1e6,min=0.1*1e6, max=200.0*1e6,scale=1e6, unit="MHz",ndecimals = 3),"parameters")
        self.setattr_argument("freq_width", NumberValue( 1*1e6,min=-10*1e6, max=50.0*1e6,scale=1e6, unit="MHz",ndecimals = 3),"parameters")     
        self.setattr_argument("scan_time", NumberValue( 100*1e-6,min=1*1e-6, max=100000.0*1e-6,scale=1e-6, unit="us",ndecimals = 3),"parameters")
        
        
        # boolean args
        self.setattr_argument("Pre_measure", BooleanValue(True), "parameters")
        self.setattr_argument("Cavity_clear", BooleanValue(True), "parameters")
        self.setattr_argument("Calibrate", BooleanValue(True), "parameters")
        self.setattr_argument("Image", BooleanValue(False), "parameters")
        
        
        # Prep DDS scan
        self.freq_list= np.linspace(0.0*MHz, 0.0*MHz, 1024)
        self.freq_list_ram = np.full(1024, 1)
        self.step_size=0
        self.scan_dds = self.Bragg.urukul_channels[1]
        

    def get_scan_points(self):
        return list(self.offset_freqs)
    
    def prepare(self):
        self.MOTs.prepare_aoms()
        self.MOTs.prepare_coils()
        self.Bragg.prepare_aoms()
        self.State_Control.prepare_aoms()
        if self.Image:
            self.Camera.camera_init()
            
        if self.freq_width/2 > self.freq_center: raise Exception("Bad Range...")
        if self.Calibrate and self.Image: raise Exception("Cannot Image Cloud and Calibrate Bare Cavity Simultaneously...")
        if not( self.Cavity_clear or self.Pre_measure): raise Exception("Must Include Either Pre-Measure or Cavity Clear Measurement...")
        
        
    
    @kernel
    def before_scan(self):
        self.core.reset()

        # set hardware in known states and initialize
        self.ttl5.off()
        self.MOTs.init_coils()
        self.MOTs.init_ttls()
        self.MOTs.init_aoms(on=False)
        self.State_Control.init_aoms(on=False)
        self.Bragg.init_aoms(switches=0x9)
        delay(10*ms)
        
        if self.Image:

            self.MOTs.take_background_image_exp(self.Camera)
            self.core.break_realtime()
            delay(5*ms)
        
        self.MOTs.set_current_dir(0)
        delay(10*ms)



        self.core.wait_until_mu(now_mu())
    
    def before_measure(self, point, measurement):
        if self.Image:self.Camera.arm()
    
    @kernel
    def measure(self, point):
        
        offset = point / (1*kHz)
        #offset = 0 * ms
        self.core.reset()
        delay(1*ms)
        
        ##### PREP EXP ################
        self.MOTs.init_rmot_dds(self.MOTs.rmot_freq_i, self.MOTs.rmot_freq_f,  self.MOTs.rmot_freq_depth_i, self.MOTs.rmot_freq_depth_f, self.MOTs.freq_3D_red)
        delay(1*ms)
        
        self.load_scan()
        delay(1*ms)
        
        
        ##### ENSURE KNOWN STATES ################
        self.MOTs.AOMs_off_all()
        self.State_Control.AOMs_off_all()
        delay(1*ms)
         
        self.State_Control.aom_689.set(frequency=self.State_Control.freq_689, amplitude=0.8)
        self.State_Control.aom_688.set(frequency=self.State_Control.freq_688, amplitude=0.8)
        self.State_Control.aom_679.set(frequency=self.State_Control.freq_679, amplitude=0.8)
        
        delay(1*ms)
        
        self.Bragg.aom_bragg1.set_att(self.Bragg.atten_Bragg1)
        self.Bragg.aom_bragg2.set_att(self.Bragg.atten_Bragg2)
        self.MOTs.aom_3D_blue.set_att(self.MOTs.atten_3D)
        delay(1*ms)
        
        
        
        ##### FORM ATOM SAMPLE ################
        
        # generate red mot
        self.MOTs.close_688() # close 688 shutter to prevent leakage from optical pumping
        self.MOTs.rMOT_pulse_new()
        self.MOTs.open_688() # open shutter after 689 rMOT light turns off to be prepare for Raman pulse
        if self.MOTs.molasses:
               with parallel:
                   self.MOTs.set_current_dir(1) 
                   self.MOTs.molasses_pulse(freq=self.MOTs.molasses_frequency, amp=0.1, t = self.dipole_load_time)
        else:
            with parallel:
                delay(self.dipole_load_time) # Needs to by >~ 40 ms for cavity shaking to stop.
                self.MOTs.set_current_dir(1) # let MOT field go to zero and switch H-bridge, 5ms        
     
        self.MOTs.Blackman_ramp(0.0, self.B_field, 20*ms) # set bias field so 3P1 m=+1 is ~40MHz separated.
        
        
        ##### PREMEASURE ################
        if self.Pre_measure:                        
            self.scan_probe(self.scan_time)
         
            
        
                
        if self.Cavity_clear:
            delay(5*ms)
            ##### EXCITATION ################
            self.State_Control.pulse_689(self.pi_time_689)
            delay(0.15*us)
            with parallel:
                self.State_Control.pulse_679(self.pi_time_Ramsey)
                self.State_Control.pulse_688(self.pi_time_Ramsey)
        
            ##### CLEAR CAVITY AND PREP GROUND ################
            self.State_Control.cav_clear_pulse(2.5*ms)

            with parallel:
                self.State_Control.pulse_679(self.pi_time_Ramsey)
                self.State_Control.pulse_688(self.pi_time_Ramsey)
            self.MOTs.close_688() # turn off 688 nm
            self.MOTs.aom_3P0.sw.on()
            self.MOTs.aom_3P2.sw.on()
            delay(0.5*ms)
            self.MOTs.aom_3P0.sw.off()
            self.MOTs.aom_3P2.sw.off()

            ##### REMEASURE VRS ################
            # for i in range(60):
            #     self.ttl5.on()
            #     self.scan_probe(self.scan_time)
            #     self.ttl5.off()
                # delay(10*us)
            self.scan_probe(self.scan_time)

        
            
        ##### BARE CAVITY CALIB / IMAGE ################
        if self.Calibrate:
            with parallel:
                self.Bragg.aom_bragg1.set_att(17.0)
                self.State_Control.cav_clear_pulse(2.5*ms) 
            self.scan_probe(self.scan_time)
        elif self.Image:
            #self.readout(scheme="0")
            self.MOTs.take_MOT_image(self.Camera)
            delay(5*ms)
            
            
        ##### CLEAN UP ################
        self.scan_dds.set_cfr1(ram_enable=0)
        self.scan_dds.cpld.io_update.pulse_mu(8)
        delay(5*ms)
        self.MOTs.Blackman_ramp(self.B_field, 0.0, 30*ms)
        self.MOTs.set_current_dir(0)
        delay(5*ms)
        self.MOTs.AOMs_off_all()
        self.State_Control.AOMs_off_all()
        delay(1*ms)
        #delay(10*s)
        
        
        self.core.wait_until_mu(now_mu())        
        return 0
     
    def after_measure(self, point, measurement):
        if self.Image:     
            self.Camera.process_image(bg_sub=True)
        if self.Calibrate:
            print(f"Move Cavity: {np.round((point+np.mean(np.diff(list(self.offset_freqs))))*1e-6, 3)} MHz")
            time.sleep(1)

    #helpers           
        
    @kernel
    def scan_probe(self, time):
        with parallel:
            self.scan_dds.sw.on()
            self.Bragg.urukul_channels[2].sw.on()
            self.ttl5.on()
            self.scan_dds.cpld.io_update.pulse_mu(8)
            
        delay(time)
        
        with parallel:
            self.scan_dds.sw.off()
            self.Bragg.urukul_channels[2].sw.off()
            self.ttl5.off()
        
    
    @kernel
    def load_scan(self):
        self.step_size = int(self.scan_time/(1024*4*ns))
        f0 = self.freq_center + self.freq_width/2
        
    
        f_step = self.freq_width / 1023        
        for i in range(1024):
            self.freq_list[i] = f0 - f_step*i
            
        self.scan_dds.frequency_to_ram(self.freq_list, self.freq_list_ram)

        self.core.break_realtime()
        delay(10 * ms)


        self.scan_dds.set_cfr1(ram_enable=0)
        self.scan_dds.cpld.io_update.pulse_mu(8)

        delay(1*ms)
        self.scan_dds.set_profile_ram(start=0, end=1024-1, step=(self.step_size | (2**6 - 1 ) << 16),
                                  profile=0, mode=ad9910.RAM_MODE_RAMPUP)
        delay(5*ms)
        self.scan_dds.cpld.set_profile(0)
        self.scan_dds.cpld.io_update.pulse_mu(8)
        self.scan_dds.write_ram(self.freq_list_ram)
        # prepare to enable ram and set frequency as target
        delay(1*ms)
        self.scan_dds.set_cfr1(internal_profile=0, ram_enable=1, ram_destination=ad9910.RAM_DEST_FTW)
        delay(10*ms)

        self.core.wait_until_mu(now_mu())
    
    @kernel
    def readout(self, scheme):
        """
        reading out ports
        scheme 0 seperates 1S0 and 3P1, leaves metastable states dark
        scheme 1 seperates 1S0 and 3P1 and 3P1/2
        scheme 2 seperates 1S0+3P1 and 3P2 and 3P0
            note there is mixing of metstable ports in scheme 2

        """
        if scheme == "0":
            self.State_Control.push_pulse(self.MOTs.Push_pulse_time)            
            self.MOTs.aom_3P0.sw.on()
            self.MOTs.aom_3P2.sw.on()
            delay(self.MOTs.Delay_duration)
            self.MOTs.aom_3P0.sw.off()
            self.MOTs.aom_3P2.sw.off()

        elif scheme == "1":
            self.State_Control.push_pulse(self.MOTs.Push_pulse_time)
            delay(200*us)
            self.State_Control.push_pulse(self.MOTs.Push_pulse_time)
            delay(5*us)
            
            self.MOTs.aom_3P0.sw.on()
            self.MOTs.aom_3P2.sw.on()
            delay(self.MOTs.Delay_duration)
            self.MOTs.aom_3P0.sw.off()
            self.MOTs.aom_3P2.sw.off()
            
        elif scheme == "2":
            delay(200*us)
            self.State_Control.push_pulse(self.MOTs.Push_pulse_time)

            self.MOTs.aom_3P2.sw.on()
            delay(200*us)
            self.MOTs.aom_3P2.sw.off()
            
            delay(200*us)
            self.State_Control.push_pulse(self.MOTs.Push_pulse_time)
            delay(5*us)
            
            self.MOTs.aom_3P0.sw.on()
            self.MOTs.aom_3P2.sw.on()
            delay(self.MOTs.Delay_duration)
            self.MOTs.aom_3P0.sw.off()
            self.MOTs.aom_3P2.sw.off()
        else:
            raise Exception("Not a valid readout scheme...")