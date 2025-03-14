# -*- coding: utf-8 -*-
"""
Created on Tue Feb  7 11:48:20 2023

@author: G. Panelli & E. Porter
"""

from scan_framework import Scan1D, TimeFreqScan
from artiq.experiment import *
import numpy as np



from CoolingClass import _Cooling
from CameraClass import _Camera
from ClockAIClass import _ClockAI
from BraggClass import _Bragg
from repository.models.scan_models import AI_Rabi_Model as myModel

class Spectroscopy_689_exp(Scan1D, TimeFreqScan, EnvExperiment):
    
    def build(self, **kwargs):
        # required initializations
        
        super().build(**kwargs)
        
        self.setattr_device("ttl5") # triggering pulse
        
        # import classes for experiment control
        self.MOTs = _Cooling(self)
        self.Camera = _Camera(self)
        self.AI = _ClockAI(self)
        self.Bragg = _Bragg(self)
        
        self.enable_pausing = True # disable to speed up by not checking scheduler
        self.enable_auto_tracking=False
        self.enable_profiling = False # enable to print runtime statistics to find bottlenecks

        self.scan_arguments(times = {'start':0*us,
            'stop':1.5*us,
            'npoints':20,
            'unit':"us",
            'scale':us,
            'global_step':0.1*us,
            'ndecimals':2},
             frequencies={
            'start':-3*MHz,
            'stop':3*MHz,
            'npoints':50,
            'unit':"MHz",
            'scale':MHz,
            'global_step':0.1*MHz,
            'ndecimals':4},
            frequency_center={'default':100*MHz},
            pulse_time= {'default':0*us},
            nbins = {'default':1000},
            nrepeats = {'default':1},
            npasses = {'default':1},
            fit_options = {'default': "No Fits"}
        
            )
        
        self.setattr_argument("dipole_load_time", NumberValue(20.0*1e-3,min=0.0*1e-3,max=9000.00*1e-3,scale=1e-3,
                      unit="ms"),"Params")
        self.setattr_argument("No_Scan",BooleanValue(False),"Params")
        self.setattr_argument("No_Scan_Val",NumberValue(0*1e-6,min=0.0*1e-6,max=10000.00*1e-6,scale = 1e-6,
                      unit="us"),"Params")
        self.setattr_argument("Arm",EnumerationValue(['1', '2']),"Params")
        self.setattr_argument("B_field", NumberValue(0.88,min=0.0,max=2,scale=1,
                      unit="V", ndecimals=3),"Params")
        
        
    def prepare(self):
        #prepare/initialize mot hardware and camera
        self.MOTs.prepare_aoms()
        self.MOTs.prepare_coils()
        self.Bragg.prepare_aoms()
        self.Camera.camera_init()
        self.AI.prepare_aoms()
        self.arm_num = int(self.Arm)
        self.pulse_dds = self.AI.urukul_channels[1+int(self.Arm)] # indexes into urukul ch array 
        # register model with scan framework
        
        
        self.enable_histograms = True
        self.model = myModel(self, arm=f"Arm {self.arm_num}")
        self.register_model(self.model, measurement=True, fit=True)

    @kernel
    def before_scan(self):
        # runs before experiment take place
        
        #initialize devices on host
        self.core.reset()
        delay(10*ms)
        self.ttl5.off()
        self.MOTs.init_coils()
        self.MOTs.init_ttls()
        self.MOTs.init_aoms(on=False)  
        self.AI.init_aoms(on=False)
        self.Bragg.init_aoms(on=True)
        delay(10*ms)
        
        self.MOTs.set_current_dir(0)
        delay(10*ms)
        
        self.MOTs.take_background_image_exp(self.Camera)
        
        delay(5*ms)
        self.MOTs.AOMs_on(['3D', "3P0_repump", "3P2_repump", "3D_red"])
        delay(2000*ms)
        self.MOTs.AOMs_off(['3D', "3P0_repump", "3P2_repump", "3D_red"])   
                   

    @kernel
    def measure(self, time, frequency):        
        
        
        #prepare
        self.core.wait_until_mu(now_mu())
        self.core.reset()
        
        pulse_time = time
        if self.No_Scan: pulse_time = self.No_Scan_Val 
        
        delay(100*ms)
        self.Camera.arm()
        delay(200*ms)
        
        
        self.AI.set_AOM_freqs([('AI' + self.Arm, frequency)])
        
        # for checking power
        # self.AI.pulse(10*ms, self.pulse_dds)
        delay(10*ms)
        
        # perform experiment
        self.MOTs.AOMs_off(self.MOTs.AOMs)
        delay(15*ms)
        self.MOTs.rMOT_pulse()  # generates the red MOT
        delay(5*ms)
        self.MOTs.AOMs_on(['3P0_repump', '3P2_repump']) #make sure all atoms go to ground state
        self.MOTs.set_current_dir(1) # XXX let MOT field go to zero and switch H-bridge, 5ms
        self.MOTs.set_current(self.B_field)
        self.MOTs.AOMs_off(['3P0_repump', '3P2_repump']) 
        delay(self.dipole_load_time)
        
        #self.Bragg.set_AOM_attens([("Dipole",25.0 )])
        #self.Bragg.AOMs_off(["Lattice"])
        delay(20*us)
        self.AI.AI_pulse(pulse_time, self.arm_num-1)
        #self.AI.AI_pulse(1*us, self.arm_num-1)
        
        self.AI.push_pulse(self.MOTs.Push_pulse_time) #seperate for readout
        delay(self.MOTs.Delay_duration)
        
        
        self.Bragg.set_AOM_attens([("Dipole",12.0 )])
        self.Bragg.AOMs_on(["Lattice"])
        
        
        

        self.MOTs.take_MOT_image(self.Camera)  
        delay(15*ms)
        self.MOTs.set_current(0.0)
        delay(5*ms)
        self.MOTs.set_current_dir(0)
        delay(5*ms)  
        
        #process and output
        self.MOTs.AOMs_on(self.MOTs.AOMs) # just keeps AOMs warm

        self.Camera.process_image(save=True, name='', bg_sub=True)

        delay(400*ms)
        
        
        return self.Camera.get_push_stats()
            
    
    def after_fit(self, fit_name, valid, saved, model):
        self.set_dataset('current_scan.plots.error', model.errors, broadcast=True, persist=True)

