# -*- coding: utf-8 -*-
"""
Created on Thu Feb  2 11:17:41 2023

@author: E. Porter
"""

# make available artiq classes for us

from artiq.experiment import EnvExperiment, kernel, ms, NumberValue, delay, parallel, sequential, now_mu,BooleanValue # pyright: ignore[reportMissingImports]

# imports
import numpy as np
from CoolingClass import _Cooling
from CameraClass import _Camera


class Red_MOT_pulse_exp(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.setattr_device("scheduler")

        self.MOTs = _Cooling(self)
        self.Camera = _Camera(self)


        # attributes for this experiment
        self.setattr_argument("pulses", NumberValue(5,min=0, max=100), "parameters")
        self.setattr_argument("wait_time", NumberValue(1000.0*1e-3,min=0.0*1e-3,max=9000.00*1e-3,scale=1e-3,
                      unit="ms"),"parameters")
        self.setattr_argument("broadband",BooleanValue(False),"parameters")




    def prepare(self):
        # initial datasets for the aoms and mot coils, does not run on core
        self.MOTs.prepare_aoms()
        self.MOTs.prepare_coils()

        # Initialize camera
        self.Camera.camera_init(N=int(self.pulses) + 1)
        
     
    @kernel 
    def run(self):
        # initial devices
        self.init_exp()     
        self.run_exp()
        self.cleanup()




    @kernel
    def init_exp(self):
        self.core.reset()

        self.MOTs.init_coils()
        self.MOTs.init_ttls()
        self.MOTs.init_aoms(on=False)
        delay(10*ms)

        self.MOTs.take_background_image_exp(self.Camera)

        self.MOTs.AOMs_off_all()
        self.MOTs.atom_source_off()

        

        
        
    @kernel
    def run_exp(self):
        delay(10*ms)
        self.MOTs.init_rmot_dds(self.MOTs.rmot_freq_i, 
                                self.MOTs.rmot_freq_f, 
                                self.MOTs.rmot_freq_depth_i,
                                self.MOTs.rmot_freq_depth_f, 
                                self.MOTs.freq_3D_red)
        
        self.core.break_realtime()
        delay(10*ms)

        for _ in range(int(self.pulses)):
            self.MOTs.rMOT_pulse_new()
            delay(self.wait_time)

            self.MOTs.take_MOT_image(self.Camera)
            delay(10*ms)

            # always use this block to readout images
            self.core.wait_until_mu(now_mu())
            self.Camera.process_image(bg_sub=True)
            self.core.break_realtime()

            delay(10*ms)

            # turn off aoms
            self.MOTs.AOMs_off_all()
            delay(50*ms)

            
    @kernel
    def cleanup(self):
        delay(20*ms)
        self.MOTs.AOMs_on_all()
        self.MOTs.atom_source_on()
        
         
    
       