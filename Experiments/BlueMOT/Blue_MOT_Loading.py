# -*- coding: utf-8 -*-
"""
Created on Thu Mar 13 13:02:17 2025

@author: sr
"""


from scan_framework import Scan1D, TimeScan
from artiq.experiment import EnvExperiment, BooleanValue, kernel, ms, delay, now_mu, s # pyright: ignore[reportMissingImports]

from CoolingClass import _Cooling
from CameraClass import _Camera 
from repository.models.scan_models import LoadingModel # pyright: ignore[reportMissingImports]

class BlueMOTLoading_exp(Scan1D, TimeScan, EnvExperiment):

    def build(self, **kwargs):
        super().build(**kwargs)
        self.enable_auto_tracking = False

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
            fit_options = {'default':"No Fits"}
            )
        
        self.setattr_argument("lifetime",BooleanValue(False),"Params")



    def prepare(self):
        #prepare/initialize mot hardware and camera
        self.MOTs.prepare_aoms()
        self.MOTs.prepare_coils()
        self.Camera.camera_init(N=len(self.get_scan_points())*self.nrepeats * self.npasses + 10)
        
        # register model with scan framework
        self.model = LoadingModel(self)
        self.register_model(self.model, measurement=True, fit=True)


    @kernel
    def before_scan(self):
        self.core.reset()

        self.MOTs.init_coils()
        self.MOTs.init_ttls()
        self.MOTs.init_aoms(on=False) 
        delay(10*ms)

        self.MOTs.take_background_image_exp(self.Camera)

        self.MOTs.AOMs_off_all()
        self.MOTs.atom_source_off()




    @kernel
    def measure(self, point):
        self.core.break_realtime()
        delay(10*ms)
        t_delay = point

        # either full load or start loading bmot
        if self.lifetime:
            self.MOTs.bMOT_load()
            self.MOTs.atom_source_off()        
        else: 
            self.MOTs.atom_source_on()
            self.MOTs.AOMs_on_all()
            self.MOTs.set_current_dir(0)
            self.MOTs.Blackman_ramp_up()
    
        # image after loading time/lifetime
        delay(t_delay)
        self.Camera.trigger_camera()
        delay(self.Camera.Exposure_Time)
        

        self.core.wait_until_mu(now_mu())
        ports = self.Camera.process_image(bg_sub=True, return_ports=["counts"])
        self.core.break_realtime()
        delay(10*ms)


        self.MOTs.Blackman_ramp_down()
        self.MOTs.atom_source_off()
        self.MOTs.AOMs_off_all()    
        return int(ports[0])
    
