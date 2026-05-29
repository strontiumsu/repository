# -*- coding: utf-8 -*-
"""
Created on Thu Mar 13 17:54:26 2025

@author: sr
"""

from scan_framework import Scan1D, TimeScan

from artiq.experiment import Scannable, RangeScan, EnumerationValue, BooleanValue, NumberValue, at_mu, sequential, s # pyright: ignore[reportMissingImports]
from artiq.experiment import kernel, EnvExperiment, kHz, delay, ms, parallel, us, MHz, now_mu, ns # pyright: ignore[reportMissingImports]


from CoolingClass import _Cooling
from CameraClass import _Camera
from BraggClass import _Bragg
from repository.models.scan_models import LifetimeModel # pyright: ignore[reportMissingImports]


class DipoleTrapLifetime_exp(Scan1D, TimeScan, EnvExperiment):

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
            'stop':1000*1e-3,
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


        self.setattr_argument("load_time", NumberValue(60*1e-3,min=1.0*1e-3,max=5000.00*1e-3,scale=1e-3,
                     unit="ms"),"parameters")
        self.setattr_argument("B_field", NumberValue(0.36,min=0.0,max=2,scale=1,
                      unit="V", ndecimals=3),"parameters")

    def prepare(self):
        #prepare/initialize mot hardware and camera
        self.MOTs.prepare_aoms()
        self.MOTs.prepare_coils()

        self.Camera.camera_init(N=len(list(self.get_scan_points()))*self.nrepeats*self.npasses + 5)
        self.Bragg.prepare_aoms()
        # register model with scan framework
        self.enable_histograms = True
        self.model = LifetimeModel(self)
        self.register_model(self.model, measurement=True, fit=True)



    @kernel
    def before_scan(self):
        # runs before experiment take place

        #initialize devices on host
        self.core.reset()
        self.MOTs.init_coils()
        self.MOTs.init_aoms(on=False)  # initializes whiling keeping them off
        self.Bragg.init_aoms()

        delay(10*ms)

        self.MOTs.take_background_image_exp(self.Camera)

        

        self.MOTs.AOMs_off_all()
        self.MOTs.atom_source_off()
        



    @kernel
    def measure(self, point):
        
        self.core.wait_until_mu(now_mu())
        delay(5*ms)
        self.core.break_realtime()
        self.MOTs.AOMs_off_all()
        delay(10*ms)


        self.MOTs.init_rmot_dds(self.MOTs.rmot_freq_i, 
                                self.MOTs.rmot_freq_f, 
                                self.MOTs.rmot_freq_depth_i, 
                                self.MOTs.rmot_freq_depth_f, 
                                self.MOTs.freq_3D_red)
        delay(10 * ms)
        
        self.MOTs.rMOT_pulse_new()
        
        # with parallel:
        #     delay(self.load_time/3) 
        #     self.MOTs.set_current_dir(1) # let MOT field go to zero and switch H-bridge, 15ms    
        # if self.MOTs.molasses:
        #     self.MOTs.molasses_pulse(freq=self.MOTs.molasses_frequency, amp=0.1, t=self.load_time/3)
        # else:
        #     delay(self.load_time/3)
        # self.MOTs.Blackman_ramp(0.0, self.B_field, self.load_time/3) # set bias field so 3P1 m=+1 is ~40MHz separated.
        
        
        delay(point + self.load_time)


        self.MOTs.take_MOT_image(self.Camera) # image after variable drop time

        delay(10*ms)
        self.MOTs.AOMs_on_all()
        delay(5*ms)

        self.MOTs.Blackman_ramp(self.B_field, 0.0, 30*ms)
        self.MOTs.set_current_dir(0)

        delay(5*ms)


        ports=self.Camera.process_image(bg_sub=True, return_ports=["counts"])
        total_counts = ports[0]
        self.core.break_realtime()
        delay(10*ms)

        return int(total_counts)