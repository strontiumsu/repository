# -*- coding: utf-8 -*-
"""
Created on Thu Mar 13 17:26:44 2025

@author: sr
"""

from scan_framework import Scan1D, TimeScan
from artiq.experiment import kernel, EnvExperiment, NumberValue, delay, ms, us, now_mu# pyright: ignore[reportMissingImports]


from CoolingClass import _Cooling
from CameraClass import _Camera
from BraggClass import _Bragg
from repository.models.scan_models import DipoleFreqModel # pyright: ignore[reportMissingImports]


class DipoleTrapFrequency_exp(Scan1D, TimeScan, EnvExperiment):

    def build(self, **kwargs):
        # required initializations
        super().build(**kwargs)
        self.enable_auto_tracking = False

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
        self.Bragg.prepare_aoms()

        self.Camera.camera_init(N=len(list(self.get_scan_points()))*self.nrepeats*self.npasses + 1)
        
        self.model = DipoleFreqModel(self)
        self.register_model(self.model, measurement=True, fit=True)

    @kernel
    def before_scan(self):
        self.core.reset()
        self.MOTs.init_coils()
        self.MOTs.init_ttls()
        self.MOTs.init_aoms(on=False)  # initializes whiling keeping them off
        self.Bragg.init_aoms()

        delay(10*ms)

        self.MOTs.take_background_image_exp(self.Camera)
        
        self.MOTs.AOMs_off_all()
        self.MOTs.atom_source_off()

        delay(10*ms)
        self.MOTs.init_rmot_dds(self.MOTs.rmot_freq_i,
                                self.MOTs.rmot_freq_f,
                                self.MOTs.rmot_freq_depth_i,
                                self.MOTs.rmot_freq_depth_f,
                                self.MOTs.freq_3D_red)




    @kernel
    def measure(self, point):
        t_delay = point
        self.core.break_realtime()
        delay(10*ms)

      
        self.MOTs.rMOT_pulse_new()
        delay(self.load_time)


        ## EXP SEQUENCE
        self.Bragg.aom_dipole.set_att(26.0)
        self.Bragg.aom_lattice.sw.off()
        delay(self.wait_time)  # drop time
        self.Bragg.aom_dipole.set_att(self.Bragg.atten_Dipole)
        delay(t_delay)   
        self.MOTs.take_MOT_image(self.Camera) # image after variable drop time
        self.Bragg.aom_dipole.set_att(self.Bragg.atten_Dipole)
        self.Bragg.aom_lattice.sw.on()
        delay(10*ms)
        

        ## PROCESS IMIAGE
        self.core.wait_until_mu(now_mu())     
        ports=self.Camera.process_image(bg_sub=True, return_ports=["narrow", "wide"])
        self.core.break_realtime()

        self.MOTs.AOMs_on_all()
        delay(10*ms)

        # return ratio of two ports
        narrow, wide = ports[0], ports[1]
        return int(1e6*narrow/wide)
    
    def after_fit(self, fit_name, valid, saved, model):
        self.set_dataset('current_scan.plots.error', model.errors, broadcast=True)