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


class Red_MOT_pulse_2Dscan_exp(Scan2D, EnvExperiment):
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

        # self.setattr_argument("detuning_i", NumberValue(-1.5*1e6,min=0.1*1e6, max=200.0*1e6, scale=1e6, unit="MHz", ndecimals = 3), "parameters")
        # self.setattr_argument("detuning_f", NumberValue(-0.5*1e6,min=0.1*1e6, max=200.0*1e6, scale=1e6, unit="MHz", ndecimals = 3), "parameters")
        # self.setattr_argument("deviation_i", NumberValue(5*1e6,min=0.1*1e6, max=200.0*1e6, scale=1e6, unit="MHz", ndecimals = 3), "parameters")
        # self.setattr_argument("deviation_f", NumberValue(1*1e6,min=0.1*1e6, max=200.0*1e6, scale=1e6, unit="MHz", ndecimals = 3), "parameters")

        # self.setattr_argument("n_profiles",NumberValue(7,min=2,max=8),"parameters")


        self.setattr_argument('rmot_freq_i_scanvar', Scannable(
                default=RangeScan(
                    start=178 * MHz,
                    stop=180.6 * MHz,
                    npoints=20
                ),
                unit='MHz',
                scale=1 * MHz,
                ndecimals=4
            ), group='Scan Range')
        self.setattr_argument('rmot_freq_depth_i_scanvar', Scannable(
                default=RangeScan(
                    start = 8 * MHz,
                    stop = 2 * MHz,
                    npoints=50
                ),
                unit='MHz',
                scale=1 * MHz,
                ndecimals=4
            ), group='Scan Range')

        # scan arguments
        self.scan_arguments()
    
    
    def get_scan_points(self):
        return [self.rmot_freq_i_scanvar, self.rmot_freq_depth_i_scanvar]
    
    @kernel
    def set_scan_point(self, i_point, point):
        rmot_freqi = point[0]
        rmot_freq_depthi = point[1]
                           
        self.core.break_realtime()
        if i_point[1] == 0:
            self.rmot_freq = rmot_freqi
            delay(3*us)
            
        self.rmot_freq_depth = rmot_freq_depthi
        delay(3*us)
    
    def prepare(self):
        # initial datasets for the aoms and mot coils, does not run on core
        self.MOTs.prepare_aoms()
        self.MOTs.prepare_rmot_dds() # with arguments
        self.MOTs.prepare_coils()

        # Initialize camera
        self.Camera.camera_init()

    @kernel 
    def init_exp(self):
        self.core.reset()
        delay(10*ms)
        self.MOTs.init_coils()
        self.MOTs.init_ttls()
        self.MOTs.init_aoms(on=False)
        delay(100*ms)

        self.MOTs.take_background_image_exp(self.Camera)
        delay(500*ms)
        
        self.core.wait_until_mu(now_mu())
        
    @kernel
    def setup_scans(self):
         self.core.reset()
         delay(10*ms)
         self.MOTs.init_scans() #can include nprofiles arg
         self.core.wait_until_mu(now_mu())
         
         
        
    @kernel
    def run_exp(self):
        self.core.reset()
        delay(10*ms)
        for _ in range(int(self.pulses)):
            delay(10*ms)
            self.Camera.arm()
            delay(500*ms)            
            self.MOTs.rMOT_pulse_new(sf=not self.broadband)
            delay(self.wait_time)
            self.MOTs.take_MOT_image(self.Camera)
            delay(10*ms)
            self.Camera.process_image(bg_sub=True)
            delay(300*ms)
            self.core.wait_until_mu(now_mu())
            delay(200*ms)
            self.MOTs.AOMs_off(['3P0_repump', '3P2_repump', '3D'])
            delay(self.wait_time)
            
    @kernel
    def cleanup(self):
        self.core.reset()
        delay(50*ms)
        for i in range(3):
            self.MOTs.urukul_channels[i].sw.on()
        self.MOTs.atom_source_on()
        
         
    def run(self):
        # initial devices
        self.init_exp()
        self.setup_scans()
        self.run_exp()
        self.cleanup()
       
    def calculate_dim0(self, dim1_model):
        ###make it simple: total photons in camera image
        img = np.array(self.get_dataset("detection.images.current_image"))
        param = sum(sum(img))
        
        ###fraction of pixel counts outside 10% of max  
        mask = np.abs(img-np.max(img)) < 0.1*np.max(img)
        dist = 1-np.sum(mask)/img.size
        return param, dist