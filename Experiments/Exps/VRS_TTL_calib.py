# -*- coding: utf-8 -*-
"""
Created on Wed Aug 27 12:17:35 2025

@author: sr
"""

from artiq.experiment import *
from scan_framework import Scan1D, TimeScan
import numpy as np

from CoolingClass import _Cooling
from CameraClass import _Camera
from BraggClass import _Bragg
from StateControlClass import _state_control

from artiq.coredevice import ad9910
from artiq.coredevice.ad9910 import PHASE_MODE_TRACKING


class VRS_TTL_calib_exp(Scan1D, TimeScan, EnvExperiment):
    
    def build(self, **kwargs):
        
        super().build(**kwargs)
        
        # hardware and class objects
        self.setattr_device("ttl5")
        self.setattr_device("ttl0") 
        self.setattr_device("ttl4") 
        self.MOTs = _Cooling(self)
        self.Camera = _Camera(self)
        self.State_Control = _state_control(self)
        self.Bragg = _Bragg(self)
        
        
        
        self.enable_pausing = True # disable to speed up by not checking scheduler
        self.enable_auto_tracking=False

        
        #scan parameters
        self.scan_arguments(times = {'start':1*1e-6,
            'stop':10*1e-6,
            'npoints':20,
            'unit':"us",
            'scale':us,
            'global_step':1*us,
            'ndecimals':2},
            nbins = {'default':1000},
            nrepeats = {'default':1},
            npasses = {'default':1},
            fit_options = {'default':"Fit and Save"}
            )
        
        
        
        #parameters
        self.setattr_argument("B_field", NumberValue(0.21,min=0.0,max=2,scale=1, unit="V", ndecimals=3),"parameters")
        self.setattr_argument("pi_time_689", NumberValue(1.0*1e-6,min=0.0*1e-6,max=1000.00*1e-6,scale=1e-6, unit="us"),"parameters")
        self.setattr_argument("pi_time_Ramsey", NumberValue(1.0*1e-6,min=0.0*1e-6,max=1000.00*1e-6,scale=1e-6,unit="us"),"parameters")
        self.setattr_argument("dipole_load_time", NumberValue(20.0*1e-3,min=0.0*1e-3,max=9000.00*1e-3,scale=1e-3, unit="ms"),"parameters")
        
        #self.setattr_argument("probe_atten", NumberValue(12.0,min=1.0, max=30,scale=1, unit="dB",ndecimals = 2),"parameters")
        self.setattr_argument("probe_atten", NumberValue(0.8,min=0.01, max=0.8,scale=1, ndecimals = 2),"parameters")
        self.setattr_argument("probe_time", NumberValue(2.0*1e-3,min=0.05*1e-3,max=100.00*1e-3,scale=1e-3, unit="ms"),"parameters")
        
        # VRS Scan args
        # Arguments   
        self.setattr_argument("freq_center", 
                              NumberValue(
                                  3*1e6,
                                  min=0.1*1e6,
                                  max=200.0*1e6,
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
    
        self.setattr_argument("scan_time", 
                              NumberValue(
                                  100*1e-6,
                                  min=1*1e-6,
                                  max=50000*1e-6,
                                  scale=1e-6,
                                  unit='us'),
                              "parameters")
        
        # boolean args
        self.setattr_argument("Cavity_clear", BooleanValue(True), "parameters")
        self.setattr_argument("Image", BooleanValue(False), "parameters")
        
        # Prep DDS scan
        self.freq_list= np.linspace(0.0*MHz, 0.0*MHz, 1024)
        self.freq_list_ram = np.full(1024, 1)
        self.step_size=0
        self.scan_dds = self.Bragg.urukul_channels[1]
        
        self.t0 = np.int64(0)
        
    
        
        
    def prepare(self):
        #prepare/initialize mot hardware and camera
        self.MOTs.prepare_aoms()
        self.Bragg.prepare_aoms()
        self.State_Control.prepare_aoms()
        
        self.MOTs.prepare_coils()
        
        if self.Image:
            self.Camera.camera_init()
            
        # if self.probe_type != "Constant": raise Exception("Scanning Probe Not Implemented...")
        if self.freq_width/2 > self.freq_center: raise Exception("Bad Range...")
        
    @kernel
    def before_scan(self):
        self.core.reset()

        # set hardware in known states and initialize
        self.ttl0.input()
        self.ttl4.off()
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
        if self.Image: self.Camera.arm()
    
    @kernel
    def measure(self, point):
        probe_delay = point     
        
        self.core.reset()
        delay(1*ms)
        
        self.ttl4.off() ## TURN OFF RF switch (DELETE when we redo scanning!)
        
        
        
        ##### PREP EXP ################
        self.MOTs.init_rmot_dds(self.MOTs.rmot_freq_i, self.MOTs.rmot_freq_f,  self.MOTs.rmot_freq_depth_i, self.MOTs.rmot_freq_depth_f, self.MOTs.freq_3D_red)
        delay(1*ms)
        
        
        ##### ENSURE KNOWN STATES ################
        self.MOTs.AOMs_off_all()
        self.State_Control.AOMs_off_all()
        delay(1*ms)
         
        self.State_Control.aom_689.set(frequency=self.State_Control.freq_689, amplitude=0.8)
        self.State_Control.aom_688.set(frequency=self.State_Control.freq_688, amplitude=0.8)
        self.State_Control.aom_679.set(frequency=self.State_Control.freq_679, amplitude=0.8)
        
        self.ttl5.off()
        self.scan_dds.sw.off()
        self.State_Control.aom_carrier.set_att(9.0)
        delay(1*ms)
        self.load_scan()
        step_mu  = self.core.seconds_to_mu(self.step_size * 4*ns)
        delay(1*ms)
        
                
        
        ##### FORM ATOM SAMPLE ################
        self.MOTs.close_688()
        self.MOTs.rMOT_pulse_new()
        self.MOTs.open_688()
        
        with parallel:
            delay(self.dipole_load_time)
            self.MOTs.set_current_dir(1) 
                
        self.MOTs.Blackman_ramp(0.0, self.B_field, 20*ms)
            
                
            
        if self.Cavity_clear:        
            delay(2*ms)
            ##### EXCITATION ################
            self.State_Control.pulse_689(self.pi_time_689)
            delay(0.15*us)
            with parallel:
                self.State_Control.pulse_679(self.pi_time_Ramsey)
                self.State_Control.pulse_688(self.pi_time_Ramsey)
        
            ##### CLEAR CAVITY AND PREP GROUND ################
            self.Bragg.cav_clear_pulse(2.5*ms)

            with parallel:
                self.State_Control.pulse_679(self.pi_time_Ramsey)
                self.State_Control.pulse_688(self.pi_time_Ramsey)
            self.MOTs.close_688() # turn off 688 nm
            self.MOTs.aom_3P0.sw.on()
            self.MOTs.aom_3P2.sw.on()
            delay(0.5*ms)
            self.MOTs.aom_3P0.sw.off()
            self.MOTs.aom_3P2.sw.off()
        
        # phase crossing verification
        # self.ttl5.on()
        # self.scan_dds.sw.on()
        # self.scan_dds.cpld.io_update.pulse_mu(8)  
        # delay(self.scan_time)
        # self.scan_dds.sw.off()
        # self.ttl5.off()
        # delay(100*us)
        # delay(point)
            
        # ##### PROBE FOR RESONANCE ################
        
        t_start = now_mu() + self.core.seconds_to_mu(20*us)        
        at_mu(t_start) 
        
        
        self.ttl5.on()
        with parallel:   
            t_end = self.ttl0.gate_rising(self.scan_time + 2*ms)
            self.State_Control.aom_carrier.sw.on()
            self.scan_dds.sw.on()
            self.scan_dds.cpld.io_update.pulse_mu(8)

            
        t_edge = self.ttl0.timestamp_mu(t_end)
        
        if t_edge >= 0: # timestamp found
            at_mu(t_edge) # set the timeline cursor to time where first edge was found + margin 
            delay(5*us)
            
            # turn off probe
            self.ttl5.off()
            delay(5*us)
            self.scan_dds.sw.off()
            self.State_Control.aom_carrier.sw.off()
            
            idx = int((t_edge - t_start) // step_mu)
            delay(100*us)
            self.freeze_RAM(idx-10)
            #self.freeze_RAM(idx + int(point/(1*us)) - 200 )
            #
            
            #delay(point)
            
            self.ttl4.on()
            self.ttl5.on()
            self.scan_dds.sw.on()
            #delay(self.scan_time)
            delay(1*ms)
            self.freeze_RAM(idx-20)
            delay(1*ms)
            self.scan_dds.sw.off()
            self.ttl5.off()


                  
        delay(10*us)
        self.ttl5.off()
        self.ttl4.off()
        self.scan_dds.sw.off()
        
        delay(5*ms)
        if self.Image:
            self.MOTs.take_MOT_image(self.Camera)
            delay(5*ms)
            
        delay(5*ms)
        self.MOTs.Blackman_ramp(self.B_field, 0.0, 30*ms)
        self.MOTs.set_current_dir(0)
        delay(5*ms)
        self.MOTs.AOMs_off_all()
        self.State_Control.AOMs_off_all()
        delay(1*ms)

        self.ttl5.off()
        self.ttl0.count(t_end) 
        
        delay(1*s)
 
        self.core.wait_until_mu(now_mu())        
        return 0
        
    
  
        
    def after_measure(self, point, measurement):
        if self.Image: self.Camera.process_image(bg_sub=True)
        
        
    @kernel
    def probe(self, time, SCAN_MODE):
        raise Exception('Changed this method make sure to fix inputs')
        
        if SCAN_MODE == 0:
            with parallel:
                self.Bragg.aom_sideband.sw.on()
                self.Bragg.aom_sideband.cpld.io_update.pulse_mu(8) 
        else:
            self.Bragg.aom_sideband.sw.on()
            self.State_Control.aom_carrier.sw.on()
            
        delay(time)
        self.Bragg.aom_sideband.sw.off()
        self.State_Control.aom_carrier.sw.off()
        
    
    @kernel
    def load_scan(self):
        self.step_size = int(self.scan_time/(1024*4*ns))
        
        f0 = self.freq_center + self.freq_width/2
        if self.freq_width/2 > self.freq_center: raise Exception("Bad Range")
        
        #continuous       
        f_step = self.freq_width / 1023        
        for i in range(1024):
            self.freq_list[i] = f0 - f_step*i

            
        self.scan_dds.frequency_to_ram(self.freq_list, self.freq_list_ram)

        self.core.break_realtime()
        delay(10 * ms)

        self.scan_dds.set_cfr1(ram_enable=0)
        self.scan_dds.cpld.io_update.pulse_mu(8)

        self.scan_dds.set_profile_ram(start=0, end=1024-1, step=(self.step_size | (2**6 - 1 ) << 16),
                                  profile=0, mode=ad9910.RAM_MODE_RAMPUP)
        
        delay(5*ms)
        self.scan_dds.cpld.set_profile(0)
        self.scan_dds.cpld.io_update.pulse_mu(8)
        self.scan_dds.write_ram(self.freq_list_ram)

  

        
        delay(1*ms)
        self.scan_dds.cpld.set_profile(0)
        delay(50*ms)
    
        
        # prepare to enable ram and set frequency as target
        delay(10 * us)
        self.scan_dds.set_cfr1(internal_profile=0, ram_enable=1, ram_destination=ad9910.RAM_DEST_FTW)
        delay(10*ms)

        self.core.wait_until_mu(now_mu())
        
    @kernel
    def freeze_RAM(self, idx):
        self.scan_dds.set_profile_ram(start=idx,end=idx, 
            step=(self.step_size | (2**6 - 1) << 16),profile=0,mode=ad9910.RAM_MODE_RAMPUP)
        self.scan_dds.cpld.io_update.pulse_mu(8)
        
    @kernel 
    def load_profiles(self, freq, probe_atten=0.8):
        self.Bragg.aom_dipole.set(frequency=self.Bragg.freq_Dipole, phase=0.0, phase_mode=PHASE_MODE_TRACKING, ref_time_mu=self.t0, profile=0)
        self.Bragg.aom_lattice.set(frequency=self.Bragg.freq_Lattice, phase=0.0, phase_mode=PHASE_MODE_TRACKING, ref_time_mu=self.t0, profile=0)
        self.Bragg.aom_sideband.set(frequency=self.Bragg.freq_Sideband, phase=0.0, phase_mode=PHASE_MODE_TRACKING, ref_time_mu=self.t0, profile=0)
        self.Bragg.aom_push.set(frequency=2*self.Bragg.freq_Push, phase=0.0, phase_mode=PHASE_MODE_TRACKING, ref_time_mu=self.t0, profile=0)
        
        self.Bragg.aom_dipole.set(frequency=self.Bragg.freq_Dipole, phase=0.0, phase_mode=PHASE_MODE_TRACKING, ref_time_mu=self.t0, profile=1)
        self.Bragg.aom_lattice.set(frequency=self.Bragg.freq_Lattice, phase=0.0, phase_mode=PHASE_MODE_TRACKING, ref_time_mu=self.t0, profile=1)
        self.Bragg.aom_sideband.set(frequency=freq, phase=0.0, phase_mode=PHASE_MODE_TRACKING, ref_time_mu=self.t0, profile=1)
        self.Bragg.aom_push.set(frequency=2*freq, phase=0.0, phase_mode=PHASE_MODE_TRACKING, ref_time_mu=self.t0, profile=1)
