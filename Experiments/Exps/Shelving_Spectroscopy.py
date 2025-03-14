# -*- coding: utf-8 -*-
"""
Created on Tue Jan 21 13:37:31 2025

@author: sr
"""

from scan_framework import Scan1D, TimeFreqScan
from artiq.experiment import *
import numpy as np



from CoolingClass import _Cooling
from CameraClass import _Camera
from STIRAPClass import _STIRAP
from BraggClass import _Bragg
from repository.models.scan_models import AI_Rabi_Model as myModel


class Shelving_Spectroscopy_exp(Scan1D, TimeFreqScan, EnvExperiment):
    
    def build(self, **kwargs):
        # required initializations
        
        super().build(**kwargs)
        
        self.setattr_device("ttl5") # triggering pulse
        
        # import classes for experiment control
        self.MOTs = _Cooling(self)
        self.Camera = _Camera(self)
        self.STIRAP = _STIRAP(self)
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
        
        self.setattr_argument("pi_time", NumberValue(1.0*1e-6,min=0.0*1e-6,max=1000.00*1e-6,scale=1e-6,
                      unit="us"),"Params")
        self.setattr_argument("shelf_time", NumberValue(10.0*1e-6,min=0.0*1e-6,max=1000.00*1e-6,scale=1e-6,
                      unit="us"),"Params")
        self.setattr_argument("Shelf",BooleanValue(False),"Params")


        self.setattr_argument("B_field", NumberValue(0.88,min=0.0,max=2,scale=1,
                      unit="V", ndecimals=3),"Params")
        
        
        
    def prepare(self):
        #prepare/initialize mot hardware and camera
        self.MOTs.prepare_aoms()
        self.MOTs.prepare_coils()
        self.Bragg.prepare_aoms()
        self.Camera.camera_init()
        self.STIRAP.prepare_aoms()

        # register model with scan framework
        
        
        self.enable_histograms = True
        self.model = myModel(self)
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
        self.STIRAP.init_aoms(on=False)
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
        
        pi_pulse_freq = frequency if not self.Shelf else self.STIRAP.freq_689
        pi_pulse_time = time if not self.Shelf else self.pi_time
        
        shelf_freq = frequency # unused if self.shelf=False


        delay(100*ms)
        self.Camera.arm()
        delay(200*ms)
        
        
        self.STIRAP.set_AOM_freqs([('689', pi_pulse_freq)])
        if self.Shelf:
            self.STIRAP.set_AOM_freqs([('688', frequency)])

        delay(10*ms)
        
        # perform experiment
        self.MOTs.AOMs_off(self.MOTs.AOMs)
        self.STIRAP.AOMs_off(self.STIRAP.AOMs)
        delay(15*ms)
        self.MOTs.rMOT_pulse()  # generates the red MOT
        

        # if self.B_field>0:
        
        # delay(5*ms)
        with parallel:
            delay(self.dipole_load_time)
            with sequential:
                self.MOTs.set_current_dir(1) # XXX let MOT field go to zero and switch H-bridge, 5ms
                self.MOTs.set_current(self.B_field)
        #delay(30*ms)

        #delay(self.dipole_load_time)
        
        self.Bragg.set_AOM_attens([("Dipole",25.0 )])
        self.Bragg.AOMs_off(["Lattice"])
        delay(20*us)
        
        
        self.ttl5.on()
        
        self.STIRAP.pulse(pi_pulse_time, self.STIRAP.urukul_channels[self.STIRAP.index_artiq("689")])
        delay(0.5*us)
        
        if self.Shelf:
            
            self.STIRAP.AOMs_on(['688'])
            delay(self.shelf_time)
            self.STIRAP.AOMs_off(['688'])
            self.STIRAP.pulse(self.shelf_time, self.STIRAP.urukul_channels[self.STIRAP.index_artiq("679")])
            
        self.ttl5.off()

        self.STIRAP.push_pulse(self.MOTs.Push_pulse_time) #seperate for readout
        delay(200*us)
        self.STIRAP.push_pulse(self.MOTs.Push_pulse_time) #seperate for readout
        delay(5*us)

        
        self.MOTs.AOMs_on(['3P0_repump'])
        #self.MOTs.AOMs_on(['3P0_repump', '3P2_repump'])
        delay(self.MOTs.Delay_duration)
        self.MOTs.AOMs_on(['3P0_repump'])
        #self.MOTs.AOMs_off(['3P0_repump', '3P2_repump'])
        
               
        
        self.Bragg.set_AOM_attens([("Dipole",12.0 )])
        self.Bragg.AOMs_on(["Lattice"])
        
        
        

        self.MOTs.take_MOT_image(self.Camera)  
        delay(15*ms)
        self.MOTs.set_current(0.0)
        delay(20*ms)
        self.MOTs.set_current_dir(0)
        delay(5*ms)  
        
        #process and output
        self.MOTs.AOMs_on(self.MOTs.AOMs) # just keeps AOMs warm

        self.Camera.process_image(save=True, name='', bg_sub=True)

        delay(400*ms)
        
        
        return self.Camera.get_push_stats()
                
        
    