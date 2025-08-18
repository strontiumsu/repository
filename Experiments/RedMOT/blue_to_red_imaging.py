# -*- coding: utf-8 -*-
"""
Created on Wed Jul 30 16:11:04 2025

@author: sr
"""

# make available artiq classes for us

from artiq.experiment import EnvExperiment, kernel, ms,us, NumberValue, delay, parallel, sequential, now_mu,BooleanValue

# imports
import numpy as np
from CoolingClass import _Cooling
from CameraClass import _Camera


class Blue_to_Red_Imaging(EnvExperiment):
    """
    blue_to_red_imaging
    This experiment uses the CoolingClass to control the relevant AOMs and MOT
    coils to pulse the Red MOT off and on, taking an image each time to display to the user
    at detection.images.current_image.

    parameters:
        <all parameters inherited from CoolingClass>
        <all parameters inherited from Detection2>
        pulses: number of times to pulse the red MOT
        wait_time: how long to wait between pulses

    """

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
        self.Camera.camera_init()


    @kernel
    def run(self):
        
        # initial devices
        self.core.reset()
        self.MOTs.init_coils()
        self.MOTs.init_ttls()
        self.MOTs.init_aoms(on=False)
        delay(100*ms)
        
        # take image for bg sub
        self.MOTs.take_background_image_exp(self.Camera)
        delay(500*ms)
        
        for m in range(int(self.pulses)):
            self.Camera.arm()
            delay(200*ms)
            
            self.MOTs.atom_source_on()
            self.MOTs.AOMs_on(["3D", "3P0_repump", "3P2_repump"])
            self.MOTs.set_current_dir(0)
    
            self.MOTs.Blackman_ramp_up()
            self.MOTs.hold(self.MOTs.bmot_load_duration)
            
           
            self.MOTs.ttl6.off() #start in broadband mode
            tramp = 25*ms
            binc = 1.0
            dt = tramp/int(self.MOTs.Npoints)
            for step in range(1, int(self.MOTs.Npoints)):
                self.MOTs.dac_0.write_dac(0, self.MOTs.bmot_current + binc/tramp*step*dt)
                self.MOTs.dac_0.load()
                self.MOTs.set_AOM_attens([("3D",6+24*step/int(self.MOTs.Npoints))])
                delay(dt)
            self.MOTs.dac_0.write_dac(0, self.MOTs.bmot_current + binc)
            self.MOTs.dac_0.load()
            
            ##########################
    
            self.MOTs.atom_source_off()
            self.MOTs.AOMs_off(['3D'])
            delay(0.5*us)
            
            if m==0:
                self.MOTs.take_MOT_image(self.Camera)
                delay(2*ms)
                self.MOTs.Blackman_ramp(self.MOTs.bmot_current + binc, self.MOTs.rmot_bb_current, 20*ms)
                
            else:              
                #self.MOTs.Blackman_ramp(self.MOTs.bmot_current + binc, self.MOTs.rmot_bb_current, 20*ms)
                self.MOTs.set_current(self.MOTs.rmot_bb_current)
                with sequential:
                    delay(10*ms)
                  # self.MOTs.take_MOT_image(self.Camera)
                  
                self.MOTs.AOMs_on(["3D_red"])
                self.MOTs.linear_ramp(self.MOTs.rmot_bb_current, self.MOTs.rmot_sf_current, self.MOTs.rmot_ramp_duration, self.MOTs.Npoints)

                self.MOTs.ttl6.on() #switch to single frequency with RF switch
                delay(m/int(self.pulses)*self.MOTs.rmot_sf_duration)
                self.MOTs.take_MOT_image(self.Camera)

            delay(10*ms)
            self.Camera.process_image(bg_sub=True)
            delay(300*ms)
            self.core.wait_until_mu(now_mu())
            delay(200*ms)
            self.MOTs.AOMs_off(['3P0_repump', '3P2_repump', '3D'])

            self.MOTs.set_current(0.0)
