# -*- coding: utf-8 -*-
"""
Created on Thu Aug  7 12:36:44 2025

@author: sr
"""

# make available artiq classes for us

from artiq.experiment import EnvExperiment, kernel, ms,us, NumberValue, delay, parallel, sequential, now_mu,BooleanValue

# imports
from scan_framework import Scan2D
from scan_framework.scans import *

import numpy as np
from CoolingClass import _Cooling
from CameraClass import _Camera
from BraggClass import _Bragg


class Red_MOT_pulse_2Dscan_exp(Scan2D, EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.setattr_device("scheduler")
        self.MOTs = _Cooling(self)
        self.Camera = _Camera(self)
        self.Bragg = _Bragg(self)

        self.setattr_device("ttl5") # triggering pulse


        # attributes for this experiment
        self.setattr_argument("dipole_load_time", NumberValue(60.0*1e-3,min=0.0*1e-3,max=1000.00*1e-3,scale=1e-3,
                      unit="ms"),"parameters")
        self.setattr_argument("B_field", NumberValue(0.36,min=0.0,max=2,scale=1,
                      unit="V", ndecimals=3),"parameters")


        self.setattr_argument('freq_scanvar', Scannable(
                default=RangeScan(
                    start=178 * MHz,
                    stop=180.6 * MHz,
                    npoints=20
                ),
                unit='MHz',
                scale=1 * MHz,
                ndecimals=4
            ), group='Scan Range')
        self.setattr_argument('pow_scanvar', Scannable(
                default=RangeScan(
                    start = 0.1,
                    stop = 0.8,
                    npoints=20
                ),
                scale=1,
                ndecimals=4
            ), group='Scan Range')
        
        self.freq = 180*MHz
        self.pow = 0.8

        # scan arguments
        self.scan_arguments()
    
    
    def get_scan_points(self):
        return [self.freq_scanvar, self.pow_scanvar]
    
    @kernel
    def set_scan_point(self, i_point, point):
        self.freq = point[0]
        self.pow = point[1]
                           
        self.core.break_realtime()
    
    def prepare(self):
        # initial datasets for the aoms and mot coils, does not run on core
        self.MOTs.prepare_aoms()
        self.MOTs.prepare_coils()
        self.Bragg.prepare_aoms()


        # Initialize camera
        self.Camera.camera_init()
         
    @kernel 
    def before_scan(self):
        self.core.reset()
        delay(10*ms)
        self.MOTs.init_coils()
        self.MOTs.init_aoms(on=False)
        self.MOTs.init_ttls()
        delay(100*ms)

        self.MOTs.take_background_image_exp(self.Camera)
        self.core.break_realtime()
        delay(5*ms)
        self.MOTs.set_current_dir(0)
        delay(10*ms)
        self.Bragg.init_aoms()

        
        
        self.core.wait_until_mu(now_mu())
        
    @kernel
    def run_exp(self, freq = 180*MHz, amp = 0.8, drop_time=0*ms):
        self.core.reset()
        delay(10*ms)
        
        self.Camera.arm()
        delay(500*ms)  

        #self.MOTs.init_rmot_dds(self.MOTs.rmot_freq_i, self.MOTs.rmot_freq_f, self.MOTs.rmot_freq_depth_i,self.MOTs.rmot_freq_depth_f, self.MOTs.freq_3D_red)
        self.MOTs.init_rmot_dds(self.MOTs.rmot_freq_i, self.MOTs.rmot_freq_f,  self.MOTs.rmot_freq_depth_i, self.MOTs.rmot_freq_depth_f, freq)
        delay(1*ms)

        #self.MOTs.bMOT_pulse_shield(shield_freq = freq, shield_scale= amp)
        #self.MOTs.rMOT_pulse_shield(shield_amp = amp)
        #self.MOTs.rMOT_pulse_new(sf=False, sf_amp = 0.3)
        self.MOTs.rMOT_pulse_new(sf=True, atten_scale_factor=3.0, sf_amp = amp, dipole_on = True)

        self.Bragg.aom_dipole.set_att(30.0)
        self.Bragg.aom_lattice.sw.off()
        delay(drop_time)

        self.MOTs.take_MOT_image(self.Camera)
        self.Bragg.aom_dipole.set_att(self.Bragg.atten_Dipole)
        self.Bragg.aom_lattice.sw.on()

        delay(10*ms)
        self.Camera.process_image(bg_sub=True)
        delay(500*ms)
        self.core.wait_until_mu(now_mu())
        delay(50*ms)

        
    @kernel  
    def measure(self, point):
        self.run_exp(freq=self.freq,amp=self.pow, drop_time=0*ms)
        self.run_exp(freq=self.freq,amp=self.pow, drop_time=5*ms)

        return 0
       
    def calculate_dim0(self, dim1_model):
        ###make it simple: total photons in camera image
        img = np.array(self.get_dataset("detection.images.current_image"))
        param = sum(sum(img))
        
        ###fraction of pixel counts outside 10% of max  
        mask = np.abs(img-np.max(img)) < 0.1*np.max(img)
        dist = 1-np.sum(mask)/img.size
        return param, dist