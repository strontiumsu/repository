# -*- coding: utf-8 -*-
"""
Created on Thu Aug  7 15:29:14 2025

@author: sr
"""

from artiq.experiment import EnvExperiment, kernel, ms,us, NumberValue, delay, parallel, sequential, now_mu,BooleanValue
from artiq.coredevice import ad9910


# imports
from scan_framework import Scan1D
from scan_framework.scans import *

import numpy as np
from CoolingClass import _Cooling
from CameraClass import _Camera




######## imports for rigol (some unnecessary)
import pyvisa

####################################


class Red_MOT_pulse_1Dscan_exp(Scan1D, EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.setattr_device("scheduler")
        self.MOTs = _Cooling(self)
        self.Camera = _Camera(self)


        # attributes for this experiment
        self.setattr_argument("pulses", NumberValue(5,min=0, max=100), "parameters")
        self.setattr_argument("wait_time", NumberValue(10.0*1e-3,min=0.0*1e-3,max=9000.00*1e-3,scale=1e-3,
                      unit="ms"),"parameters")
        self.setattr_argument("broadband",BooleanValue(False),"parameters")


        self.setattr_argument('scan_var_freq', Scannable(
                default=RangeScan(
                    start=178 * MHz,
                    stop=180.6 * MHz,
                    npoints=10
                ),
                unit='MHz',
                scale= 1*MHz,
                ndecimals=4
            ), group='Scan Range')
        
        
        self.setattr_argument('scan_var_freq_2', Scannable(
                default=RangeScan(
                    start=0 * MHz,
                    stop=2 * MHz,
                    npoints=10
                ),
                unit='MHz',
                scale= 1*MHz,
                ndecimals=4
            ), group='Scan Range')
        
        self.setattr_argument('scan_var_int', Scannable(
                default=RangeScan(
                    start=0.0,
                    stop=250,
                    npoints=10
                ),
                #unit='MHz',
                #scale= 1*MHz,
                #ndecimals=4
            ), group='Scan Range')
                
        
        self.scan_arguments(nbins={'default':1000},
                        nrepeats={'default':1},
                        npasses={'default':1},
                        fit_options={'default':"No Fits"})

        self.rigol = 0
        
        
    def get_scan_points(self):
        #A, B = np.meshgrid(list(self.scan_var_freq_2), list(self.scan_var_int)) # changes names if you want
        #tuple_list_points = list(zip(A.flatten(),B.flatten()))
        #return tuple_list_points # check if this is right
        return self.scan_var_int
    
    def prepare(self):
        # initial datasets for the aoms and mot coils, does not run on core
        self.MOTs.prepare_aoms()
        self.MOTs.prepare_coils()

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
        delay(500*ms)
        
        
        self.core.wait_until_mu(now_mu())
        

    @kernel     
    def measure(self, point):    
        self.core.reset()
        delay(1*ms)
        self.MOTs.init_rmot_dds(self.MOTs.rmot_freq_i, self.MOTs.rmot_freq_f,  self.MOTs.rmot_freq_depth_i, self.MOTs.rmot_freq_depth_f, self.MOTs.freq_3D_red)

        delay(1*ms)
        
        self.core.break_realtime()
        delay(10*ms)
            
        self.MOTs.rMOT_pulse_new(sf=not self.broadband,atten_scale_factor=2.67)
        delay(self.wait_time)
        self.MOTs.take_MOT_image(self.Camera)
        delay(10*ms)
        self.Camera.process_image(bg_sub=True)
        delay(300*ms)
        self.core.wait_until_mu(now_mu())
        delay(200*ms)
        self.MOTs.AOMs_off(['3P0_repump', '3P2_repump', '3D'])
        delay(self.wait_time)
            
        return 0
        
 
        
    def before_measure(self, point, measurement):
        self.Camera.arm()

    
    @kernel
    def after_scan(self):
        self.core.reset()
        delay(50*ms)
        for i in range(3):
            self.MOTs.urukul_channels[i].sw.on()
        self.MOTs.atom_source_on()    
    