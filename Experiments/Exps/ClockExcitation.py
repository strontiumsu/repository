# -*- coding: utf-8 -*-
"""
Created on Tue Jan 21 13:37:31 2025

@author: sr
"""

from scan_framework import Scan1D, TimeFreqScan
from artiq.experiment import *
import numpy as np
import pyvisa



from CoolingClass import _Cooling
from CameraClass import _Camera

from StateControlClass import _state_control
from BraggClass import _Bragg
from repository.models.scan_models import AI_Rabi_Model as myModel


class ClockExcitation_exp(Scan1D, TimeFreqScan, EnvExperiment):
    
    def build(self, **kwargs):
        # required initializations
        
        super().build(**kwargs)
        
        self.setattr_device("ttl5") # triggering pulse
        self.setattr_device("ttl1")
        # import classes for experiment control
        self.MOTs = _Cooling(self)
        self.Camera = _Camera(self)
        self.State_Control = _state_control(self)
        self.Bragg = _Bragg(self)
        
        self.enable_pausing = True # disable to speed up by not checking scheduler
        self.enable_auto_tracking=False
        self.enable_profiling = False # enable to print runtime statistics to find bottlenecks

        self.scan_arguments(times = {'start':0*us,'stop':1.5*us,'npoints':20,'unit':"us",'scale':us,'global_step':0.1*us,'ndecimals':4},
             frequencies={'start':-3*MHz,'stop':3*MHz,'npoints':50,'unit':"MHz",'scale':MHz,'global_step':0.1*MHz,'ndecimals':4},
            frequency_center={'default':100*MHz}, pulse_time= {'default':0*us},nbins = {'default':1000},nrepeats = {'default':1},npasses = {'default':1},fit_options = {'default': "No Fits"} )
        
        self.setattr_argument("dipole_load_time", NumberValue(40.0*1e-3,min=0.0*1e-3,max=9000.00*1e-3,scale=1e-3,
                      unit="ms"),"Params")
        
        self.setattr_argument("pi_time_689", NumberValue(0.15*1e-6,min=0.0*1e-6,max=1000.00*1e-6,scale=1e-6,ndecimals=3,
                      unit="us"),"Params")
        self.setattr_argument("pi_time_Raman", NumberValue(0.55*1e-6,min=0.0*1e-6,max=1000.00*1e-6,scale=1e-6,ndecimals=3,
                      unit="us"),"Params")
        
        self.setattr_argument("excited_state", EnumerationValue(['3P1', "3P0"], default='3P1'), "Params")
        self.setattr_argument("readout_scheme", EnumerationValue(["0","1","2"], default="0"), "Params")
        self.setattr_argument("cavity_clear",BooleanValue(False),"Params")
        self.setattr_argument("free_space",BooleanValue(False),"Params")
        self.setattr_argument("B_field", NumberValue(0.88,min=0.0,max=2,scale=1,
                      unit="V", ndecimals=3),"Params")
        
        
        
    def prepare(self):
        #prepare/initialize mot hardware and camera
        self.MOTs.prepare_aoms()
        self.Bragg.prepare_aoms()
        self.State_Control.prepare_aoms()
        
        self.MOTs.prepare_coils()
        
        self.Camera.camera_init(scheme = 0)
        
        
        self.enable_histograms = True
        self.model = myModel(self)
        self.register_model(self.model, measurement=True, fit=True)
        
    @kernel
    def before_scan(self):
        # runs before experiment take place
        
        self.core.reset()
        delay(10*ms)
        self.ttl5.off()
        self.MOTs.init_coils()
        self.MOTs.init_ttls()
        
        #init AOMs
        self.MOTs.init_aoms(on=False)  
        self.State_Control.init_aoms(on=False)
        self.Bragg.init_aoms()
        
        delay(10*ms)
        
        #MOT Config
        self.MOTs.set_current_dir(0)
        delay(10*ms)
        
        self.MOTs.take_background_image_exp(self.Camera)
        
        # Warm up before exp
        delay(50*ms)
        self.core.wait_until_mu(now_mu())
        
    def before_measure(self, point, measurement):
        self.Camera.arm()
 
    @kernel
    def measure(self, time, frequency):        
        
        
        #prepare
        self.core.wait_until_mu(now_mu())
        self.core.reset()
        
        self.MOTs.init_rmot_dds(self.MOTs.rmot_freq_i, self.MOTs.rmot_freq_f,  self.MOTs.rmot_freq_depth_i, self.MOTs.rmot_freq_depth_f, self.MOTs.freq_3D_red)

        delay(1*ms)
        
        self.core.break_realtime()
        delay(10*ms)

        
        self.MOTs.AOMs_off_all()
        self.State_Control.AOMs_off_all()
        delay(1*ms)
        
        if self.excited_state=='3P1':
            self.State_Control.set_AOM_freq_689(frequency, self.State_Control.scale_689)
        
        elif self.excited_state=='3P0':   
            self.State_Control.set_AOM_freq_689(self.State_Control.freq_689, self.State_Control.scale_689)
            self.State_Control.set_AOM_freq_688(self.State_Control.freq_688, self.State_Control.scale_688)
            self.State_Control.set_AOM_freq_679(frequency, self.State_Control.scale_679)
            delay(1*ms)
        else:
            raise Exception('Not Valid State')
            
        
        delay(35*ms)
        
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
        delay(5*ms)
        
        if self.free_space:
            self.Bragg.aom_dipole.set_att(30.0 )
            self.Bragg.aom_lattice.sw.off()
        
        delay(100*us)
       
        # experiment        
        # -----  3P1 EXCITATION -----------------------
        if self.excited_state=='3P1':
            self.ttl5.on() 
            self.State_Control.pulse_689(time)
            self.readout(scheme="0")
            self.ttl5.off()


        # -----  3P0 EXCITATION -----------------------
        elif self.excited_state=='3P0':
            
            if self.cavity_clear:
                self.ttl5.on()       # for triggering start
                # prepare in 3P0
                self.State_Control.pulse_689(self.pi_time_689)
                delay(0.15*us)
                with parallel:
                    self.State_Control.pulse_679(self.pi_time_Raman)
                    self.State_Control.pulse_688(self.pi_time_Raman)
                # clear cavity
                self.Bragg.cav_clear_pulse(2.5*ms)
                self.ttl5.off()
                
                
                
                ### Repeated lasing
                # for i in range(10):
                #     delay(5*us)
                #     self.ttl5.on()
                #     self.MOTs.aom_3P2.sw.on()
                #     self.MOTs.aom_3P0.sw.on()
                #     delay(10*us)
                #     self.MOTs.aom_3P2.sw.off()
                #     self.MOTs.aom_3P0.sw.off()
                #     with parallel:
                #         self.State_Control.pulse_679(self.pi_time_Raman)
                #         self.State_Control.pulse_688(self.pi_time_Raman)
                #     delay(50*us)

                #     self.ttl5.off()       # for triggering start
                #     # prepare in 3P0
                #     self.State_Control.pulse_689(self.pi_time_689)
                #     delay(0.15*us)
                #     with parallel:
                #         self.State_Control.pulse_679(self.pi_time_Raman)
                #         self.State_Control.pulse_688(self.pi_time_Raman)
                #     # clear cavity
                #     self.Bragg.cav_clear_pulse(100*us)
                #     delay(100*us)
                    

                ### Rabi flop from 3P0
                with parallel: # Raman pulse
                    self.State_Control.pulse_679(time)
                    self.State_Control.pulse_688(time)
                delay(0.3*us)
                self.State_Control.pulse_689(self.pi_time_689)
                delay(200*us) # let 3P1 decay to 1S0
                
                ### Cheap Ramsey time scan
                # with parallel: # Raman pulse
                #     self.State_Control.pulse_679(0.374*us)
                #     self.State_Control.pulse_688(0.374*us)
                # delay(0.3*us)
                # self.State_Control.pulse_689(self.pi_time_689)
                
                # delay(time)
                
                # self.State_Control.pulse_689(self.pi_time_689)
                # delay(0.15*us)
                # with parallel:
                #     self.State_Control.pulse_679(0.374*us)
                #     self.State_Control.pulse_688(0.374*us)
                # delay(200*us) # let 3P1 decay to 1S0
                
            
                
            else:    
                
                self.ttl5.on()       # for triggering start
                self.State_Control.pulse_689(self.pi_time_689)
                delay(0.15*us)
                with parallel:
                    self.State_Control.pulse_679(time)
                    self.State_Control.pulse_688(time)
                
                # delay(2*ms)
                # self.ttl5.on()       # for triggering start
                # self.State_Control.pulse_689(self.pi_time_689/2)
                # delay(0.15*us)
                # with parallel:
                #     self.State_Control.pulse_679(self.pi_time_Raman)
                #     self.State_Control.pulse_688(self.pi_time_Raman)
                    
                # delay(time)
                
                # with parallel:
                #     self.State_Control.pulse_679(self.pi_time_Raman)
                #     self.State_Control.pulse_688(self.pi_time_Raman)
                # delay(0.35*us)
                # self.State_Control.pulse_689(self.pi_time_689/2)
                
            
            self.ttl5.off()
            
            self.readout(scheme=self.readout_scheme)
                
 
        else:
            raise Exception('Not Valid State')

        
        
        
        # image and reset for next shot
        self.MOTs.take_MOT_image(self.Camera)  
        self.Bragg.aom_dipole.set_att(self.Bragg.atten_Dipole)
        self.Bragg.aom_lattice.sw.on()
        delay(15*ms)
        
        self.MOTs.set_current(0.0)
        delay(20*ms)
        self.MOTs.set_current_dir(0)
        delay(5*ms)  
        
        #process and output
        self.MOTs.AOMs_on_all() # just keeps AOMs warm
        self.Camera.process_image(save=True, name='', bg_sub=True)
        delay(400*ms)
        
        return self.Camera.get_push_stats()
        

    
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
            self.Bragg.push_pulse(self.MOTs.Push_pulse_time)            
            self.MOTs.aom_3P0.sw.on()
            self.MOTs.aom_3P2.sw.on()
            delay(self.MOTs.Delay_duration)
            self.MOTs.aom_3P0.sw.off()
            self.MOTs.aom_3P2.sw.off()

        elif scheme == "1":
            self.Bragg.push_pulse(self.MOTs.Push_pulse_time)
            delay(200*us)
            self.Bragg.push_pulse(self.MOTs.Push_pulse_time)
            delay(5*us)
            
            self.MOTs.aom_3P0.sw.on()
            self.MOTs.aom_3P2.sw.on()
            delay(self.MOTs.Delay_duration)
            self.MOTs.aom_3P0.sw.off()
            self.MOTs.aom_3P2.sw.off()
            
        elif scheme == "2":
            delay(200*us)
            self.Bragg.push_pulse(self.MOTs.Push_pulse_time)

            self.MOTs.aom_3P2.sw.on()
            delay(200*us)
            self.MOTs.aom_3P2.sw.off()
            
            delay(200*us)
            self.Bragg.push_pulse(self.MOTs.Push_pulse_time)
            delay(5*us)
            
            self.MOTs.aom_3P0.sw.on()
            self.MOTs.aom_3P2.sw.on()
            delay(self.MOTs.Delay_duration)
            self.MOTs.aom_3P0.sw.off()
            self.MOTs.aom_3P2.sw.off()
        else:
            raise Exception("Not a valid readout scheme...")
            
            
        
                
    @kernel
    def after_scan(self):
        self.core.reset()
        delay(50*ms)
        for i in range(3):
            self.MOTs.urukul_channels[i].sw.on()
        self.MOTs.atom_source_on()    
  