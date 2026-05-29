# -*- coding: utf-8 -*-
"""
Created on Thu Mar 13 13:02:17 2025

@author: sr
"""


from scan_framework import Scan1D, TimeScan
from artiq.experiment import EnvExperiment, BooleanValue, kernel, ms, delay, now_mu, s # pyright: ignore[reportMissingImports]
import numpy as np


from CoolingClass import _Cooling
from CameraClass import _Camera 
from repository.models.scan_models import LoadingModel # pyright: ignore[reportMissingImports]

class BlueMOTLoading_exp(Scan1D, TimeScan, EnvExperiment):

    def build(self, **kwargs):
        # required initializations

        super().build(**kwargs)

        self.enable_pausing = True
        self.enable_auto_tracking = False
        self.enable_profiling = False

        # import classes for experiment control
        self.MOTs = _Cooling(self)
        self.Camera = _Camera(self)

        # scan settings
        self.scan_arguments(times = {'start':0,
            'stop':2,
            'npoints':20,
            'unit':"s",
            'scale':s,
            'global_step':1*ms,
            'ndecimals':2},
            nbins = {'default':1000},
            nrepeats = {'default':1},
            npasses = {'default':1},
            fit_options = {'default':"Fit and Save"}
            )
        self.setattr_argument("lifetime",BooleanValue(False),"Params")



    def prepare(self):
        #prepare/initialize mot hardware and camera
        self.MOTs.prepare_aoms()
        self.MOTs.prepare_coils()
        self.Camera.camera_init()
        # register model with scan framework
        self.enable_histograms = True
        self.model = LoadingModel(self)
        self.register_model(self.model, measurement=True, fit=True)






    @kernel
    def before_scan(self):
        # runs before experiment take place

        #initialize devices on host
        self.core.reset()
        self.MOTs.init_coils()
        self.MOTs.init_aoms(on=False)  # initializes whiling keeping them off

        delay(10*ms)

        self.MOTs.take_background_image_exp(self.Camera)
        delay(10*ms)
        self.MOTs.atom_source_on()
        delay(100*ms)
        self.MOTs.AOMs_on_all()
        delay(200*ms)
        self.MOTs.AOMs_off_all()
        self.MOTs.atom_source_off()




    @kernel
    def measure(self, point):
        if self.lifetime:
            t_delay = point
            self.core.wait_until_mu(now_mu())
            self.core.reset()
            self.Camera.arm()
            delay(200*ms)
    
            self.MOTs.AOMs_off_all()
            delay(10*ms)
    
            #self.MOTs.rMOT_pulse()
           #delay(self.load_time)
    
            self.MOTs.bMOT_load()
            self.MOTs.atom_source_off()
            delay(t_delay)

            self.Camera.trigger_camera()
            delay(self.Camera.Exposure_Time)

            self.MOTs.AOMs_off_all()
            self.MOTs.Blackman_ramp_down()
            delay(5*ms)
            self.Camera.process_image(bg_sub=True)
            delay(100*ms)
            
            return self.Camera.get_totalcount_stats()
            
        else:
            t_delay = point
            self.core.wait_until_mu(now_mu())
            self.core.reset()
            self.Camera.arm()
            delay(200*ms)
    
            self.MOTs.AOMs_off_all()
            delay(10*ms)
    
            #self.MOTs.rMOT_pulse()
           #delay(self.load_time)
    
            self.MOTs.atom_source_on()
            self.MOTs.AOMs_on_all()
            self.MOTs.set_current_dir(0)
            self.MOTs.Blackman_ramp_up()
    
            delay(t_delay)
            
            self.Camera.trigger_camera()
            delay(self.Camera.Exposure_Time)
            
            self.MOTs.atom_source_off()
            delay(5*ms)
            self.MOTs.AOMs_off_all()
            #self.MOTs.take_MOT_image(self.Camera)
    
            self.MOTs.Blackman_ramp_down()
            
            delay(5*ms)
    
            self.Camera.process_image(bg_sub=True)
    
            delay(100*ms)
            
            return self.Camera.get_totalcount_stats()

    def after_fit(self, fit_name, valid, saved, model):
            self.set_dataset('current_scan.plots.error', model.errors, broadcast=True, persist=True)
    
