# -*- coding: utf-8 -*-
"""
Created on Wed Aug  2 10:59:20 2023

@author: E. Porter
"""

from scan_framework import Scan1D, TimeScan
from artiq.experiment import *
import numpy as np



from CoolingClass import _Cooling
from CameraClass import _Camera
from BraggClass import _Bragg
from repository.models.scan_models import DipoleTemperatureModel

class Red_MOT_Molasses_Scan_exp(Scan1D, TimeScan, EnvExperiment):

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

        # attrs for this exp
        # self.setattr_argument('ScanType', EnumerationValue(['CoM', 'Tx', 'Tz']) )

        self.setattr_argument("load_time", NumberValue(15*1e-3,min=1.0*1e-3,max=5000.00*1e-3,scale=1e-3,
                     unit="ms"),"parameters")


    def prepare(self):
        #prepare/initialize mot hardware and camera
        self.MOTs.prepare_aoms()
        self.MOTs.prepare_coils()
        self.Camera.camera_init()
        self.Bragg.prepare_aoms()
        # register model with scan framework
        self.enable_histograms = True
        self.model = DipoleTemperatureModel(self)
        self.register_model(self.model, measurement=False, fit=False)






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
        delay(500*ms)
        self.Camera.arm()
        delay(300*ms)
        # self.MOTs.molasses_power(0.0)
        # delay(100*ms)
        self.Bragg.set_AOM_attens([("Homodyne",3.0 )])
        self.MOTs.set_AOM_attens([("Probe",14.0)])
        self.MOTs.set_AOM_freqs([("Probe",self.MOTs.freq_Probe)])

        self.MOTs.AOMs_off(self.MOTs.AOMs)
        delay(10*ms)


        self.MOTs.rMOT_pulse()

        # molasses #
        self.MOTs.set_AOM_freqs([("Probe",self.MOTs.freq_Probe-600*kHz)])
        self.MOTs.set_AOM_attens([("Probe",23.5)])
        self.MOTs.AOMs_on(["Probe"])
        delay(10*ms)
        self.MOTs.AOMs_off(["Probe"])

        ###################


        delay(self.load_time) # load for fixed time

        #self.Bragg.lattice_rampdown(30.0, 1*ms)

        #delay(self.load_time) # load for fixed time


        self.Bragg.set_AOM_attens([("Dipole",30.0 )])
        self.Bragg.AOMs_off(["Homodyne"])


        delay(t_delay)  # drop time
        self.MOTs.take_MOT_image(self.Camera) # image after variable drop time
        self.Bragg.set_AOM_attens([("Dipole",self.Bragg.atten_Dipole)])
        self.Bragg.AOMs_on(["Homodyne"])

        delay(10*ms)
        self.MOTs.AOMs_on(self.MOTs.AOMs)

        delay(50*ms)
        self.Camera.process_image(bg_sub=True)
        delay(400*ms)
        # self.MOTs.molasses_power(0.0)
        # delay(50*ms)
        return 0  # return nothing for now, deal with in post
