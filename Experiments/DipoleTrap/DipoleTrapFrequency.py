# -*- coding: utf-8 -*-
"""
Created on Thu Mar 13 17:26:44 2025

@author: sr
"""

from scan_framework import Scan1D, TimeScan
from artiq.experiment import *
import numpy as np


from CoolingClass import _Cooling
from CameraClass import _Camera
from BraggClass import _Bragg
from repository.models.scan_models import DipoleFreqModel
from scipy.optimize import curve_fit
from scipy import constants

class DipoleTrapFrequency_exp(Scan1D, TimeScan, EnvExperiment):

    def build(self, **kwargs):
        # required initializations

        super().build(**kwargs)

        self.enable_pausing = True
        self.enable_auto_tracking = False
        self.enable_profiling = False

        # import classes for experiment control
        self.MOTs = _Cooling(self)
        self.Camera = _Camera(self)
        self.Bragg = _Bragg(self)

        # scan settings
        self.scan_arguments(times = {'start':0.1*1e-3,
            'stop':100*1e-3,
            'npoints':20,
            'unit':"ms",
            'scale':ms,
            'global_step':1*us,
            'ndecimals':2},
            nbins = {'default':1000},
            nrepeats = {'default':1},
            npasses = {'default':1},
            fit_options = {'default':"Fit and Save"}
            )


        self.setattr_argument("load_time", NumberValue(15*1e-3,min=0.0*1e-3,max=5000.00*1e-3,scale=1e-3,
                     unit="ms"),"parameters")
        self.setattr_argument("wait_time", NumberValue(15*1e-3,min=0.0*1e-3,max=5000.00*1e-3,scale=1e-3,
                     unit="ms"),"parameters")

    def prepare(self):
        #prepare/initialize mot hardware and camera
        self.MOTs.prepare_aoms()
        self.MOTs.prepare_coils()
        self.Camera.camera_init()
        self.Bragg.prepare_aoms()
        # register model with scan framework
        self.enable_histograms = True
        self.model = DipoleFreqModel(self)
        self.register_model(self.model, measurement=True, fit=True)

        self.Camera.prep_temp_datasets(len(list(self.get_scan_points())))




    @kernel
    def before_scan(self):
        # runs before experiment take place

        #initialize devices on host
        self.core.reset()
        self.MOTs.init_coils()
        self.MOTs.init_aoms(on=False)  # initializes whiling keeping them off
        self.Bragg.init_aoms(on=True)

        delay(10*ms)

        self.MOTs.take_background_image_exp(self.Camera)
        delay(100*ms)
        self.MOTs.atom_source_on()
        delay(100*ms)
        self.MOTs.AOMs_on(['3D', "3P0_repump", "3P2_repump"])
        delay(200*ms)
        self.MOTs.AOMs_off(['3D', "3P0_repump", "3P2_repump"])
        self.MOTs.atom_source_off()




    @kernel
    def measure(self, point):
        t_delay = point
        self.core.wait_until_mu(now_mu())
        self.core.reset()
        self.Camera.arm()
        delay(200*ms)

        self.MOTs.AOMs_off(self.MOTs.AOMs)
        delay(10*ms)

        self.MOTs.rMOT_pulse()
        delay(self.load_time)


        self.Bragg.set_AOM_attens([("Dipole",30.0 )])
        self.Bragg.AOMs_off(["Lattice"])


        delay(self.wait_time)  # drop time
        
        self.Bragg.set_AOM_attens([("Dipole",self.Bragg.atten_Dipole)])
        #self.Bragg.AOMs_on(["Lattice"])
        
        
        delay(t_delay)
        
        self.Bragg.set_AOM_attens([("Dipole",30.0 )])
        #self.Bragg.AOMs_off(["Lattice"])


        delay(self.wait_time)  # drop time
        
        self.Bragg.set_AOM_attens([("Dipole",self.Bragg.atten_Dipole)])
        #self.Bragg.AOMs_on(["Lattice"])
        
        delay(1*ms)
        
        
        self.MOTs.take_MOT_image(self.Camera) # image after variable drop time
        
        

        delay(10*ms)
        self.MOTs.AOMs_on(self.MOTs.AOMs)
        delay(1*ms)
        self.Bragg.AOMs_on(["Lattice"])
        self.Bragg.set_AOM_attens([("Dipole",self.Bragg.atten_Dipole)])

        delay(50*ms)
        self.Camera.process_image(bg_sub=True)
        delay(400*ms)
        return 0
    
    def after_fit(self, fit_name, valid, saved, model):
        self.set_dataset('current_scan.plots.error', model.errors, broadcast=True, persist=True)