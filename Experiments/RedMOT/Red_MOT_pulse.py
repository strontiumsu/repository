# -*- coding: utf-8 -*-
"""
Created on Thu Feb  2 11:17:41 2023

@author: E. Porter
"""

# make available artiq classes for us

from artiq.experiment import EnvExperiment, kernel, ms,us, MHz, NumberValue, delay, parallel, sequential, now_mu,BooleanValue # pyright: ignore[reportMissingImports]

# imports
from CoolingClass import _Cooling
from CameraClass import _Camera
from BraggClass import _Bragg


class Red_MOT_pulse_exp(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.setattr_device("scheduler")

        self.MOTs = _Cooling(self)
        self.Bragg = _Bragg(self)  # dipole/lattice beam AOMs in here
        self.Camera = _Camera(self)
        
        self.setattr_device("ttl5") # timing pulse


        # attributes for this experiment
        self.setattr_argument("pulses", NumberValue(5,min=0, max=100), "parameters")
        self.setattr_argument("wait_time", NumberValue(50.0*1e-3,min=0.0*1e-3,max=9000.00*1e-3,scale=1e-3,
                      unit="ms"),"parameters")




    def prepare(self):
        self.MOTs.prepare_cooling()
        self.Bragg.prepare_aoms()
        self.Camera.camera_init(N=int(self.pulses) + 1)
              
        
    @kernel
    def run(self):
        self.core.reset()
        self.MOTs.init_cooling()
        self.Bragg.init_aoms(switches=0x9)
        delay(10*ms)

        self.MOTs.take_background_image_exp(self.Camera)


        for _ in range(int(self.pulses)):
            self.MOTs.rmot_pulse()
            delay(self.wait_time)
            self.MOTs.take_MOT_image(self.Camera)
            

            # always use this block to readout images
            delay(10*ms)
            self.core.wait_until_mu(now_mu())
            self.Camera.process_image(bg_sub=True)
            self.core.break_realtime()

            delay(10*ms)


        self.MOTs.AOMs_on_all()
        self.MOTs.atom_source_on()


        
        
         
    
       