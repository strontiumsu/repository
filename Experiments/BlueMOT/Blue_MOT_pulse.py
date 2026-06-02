# -*- coding: utf-8 -*-
"""
Created on Tue Jan 31 10:03:56 2023

@author: E. Porter
"""

from artiq.experiment import EnvExperiment, BooleanValue, kernel, ms, NumberValue, delay, now_mu # pyright: ignore[reportMissingImports]

# imports
from CoolingClass import _Cooling
from CameraClass import _Camera


class Blue_MOT_pulse_exp(EnvExperiment):

    def build(self):
        self.setattr_device("core")
        self.MOTs = _Cooling(self)
        self.Camera = _Camera(self)

        # attributes for this experiment
        self.setattr_argument("pulses", NumberValue(5,min=0, max=100), "parameters")
        self.setattr_argument("wait_time", NumberValue(1000.0*1e-3,min=10.0*1e-3,max=9000.00*1e-3,scale=1e-3,
                      unit="ms"),"parameters")
        self.setattr_argument("image", BooleanValue(False),"parameters")

    def prepare(self):
        # initial datasets for the aoms and mot coils, does not run on core
        self.MOTs.prepare_aoms()
        self.MOTs.prepare_coils()

        if self.image: self.Camera.camera_init(N=int(self.pulses) + 10)

    @kernel
    def run(self):
        self.core.reset()

        self.MOTs.init_coils()
        self.MOTs.init_ttls()
        self.MOTs.init_aoms(on=False)
        delay(10*ms)

        if self.image: self.MOTs.take_background_image_exp(self.Camera)

        self.MOTs.AOMs_off_all()
        self.MOTs.atom_source_off()

        for _ in range(int(self.pulses)):
            self.MOTs.bMOT_load()
            
        
            if self.image: self.MOTs.take_MOT_image(self.Camera)
            delay(10*ms)

            self.MOTs.Blackman_ramp_down()
            self.MOTs.atom_source_off()
            self.MOTs.AOMs_off_all()
            delay(50*ms)

            if self.image: 
                self.core.wait_until_mu(now_mu())
                self.Camera.process_image(bg_sub=True)
                self.core.break_realtime()

            delay(self.wait_time)
