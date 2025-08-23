# -*- coding: utf-8 -*-
"""
Created on Wed Aug 20 16:23:50 2025

@author: sr
"""

# -*- coding: utf-8 -*-
"""
Created on Tue Jan 31 10:03:56 2023

@author: E. Porter
"""

from artiq.experiment import EnvExperiment, BooleanValue, delay_mu, kernel, ms, us, NumberValue, delay, parallel, sequential, RTIOUnderflow, now_mu
import math
# imports
import numpy as np
from CoolingClass import _Cooling
from CameraClass import _Camera


class field_testing_exp(EnvExperiment):

    def build(self):
        self.setattr_device("core")
        self.MOTs = _Cooling(self)
        self.setattr_device("ttl5")
        self.setattr_device("core_dma")
        self.setattr_device("zotino0")
        
        self.ramp_time = 30*ms
        self.dt = 20*us
        self.nsteps = int(self.ramp_time/self.dt)
        self.ch = 0
        self.v0 = 0.0
        self.v1 = 5.0
        self.v2 = 5.5
        self.v3 = 0.4
        self.v4 = 2.0
        self.dv = (self.v1 - self.v0) / float(self.nsteps)
        self.window = np.zeros(self.nsteps)
        self.bmot_ramp_time = 100*ms
        self.bb_time = 50*ms
        self.bb_ramp_time = 85*ms
        self.bb_off_time = 5*ms
        
        self.nsteps2 = int(self.bmot_ramp_time/self.dt)


    def prepare(self):
        # initial datasets for the aoms and mot coils, does not run on core
        self.MOTs.prepare_aoms()
        self.MOTs.prepare_coils()
        self.window = np.blackman(2*self.nsteps-1)
        

    @kernel
    def record_ramp_dma(self):


        with self.core_dma.record("zotino_ramp_up"):
            # Prime first value
            self.zotino0.write_dac(self.ch, self.v0)
            self.zotino0.load()
            delay(self.dt)


            for step in self.window[:self.nsteps+1]:
                
                self.zotino0.write_dac(self.ch, self.v0 + (self.v1-self.v0)*step)
                self.zotino0.load()
                delay(self.dt)
            self.zotino0.write_dac(self.ch, self.v1)
            self.zotino0.load()
            
        with self.core_dma.record("zotino_bmot_ramp"):
            # Prime first value
            self.zotino0.write_dac(self.ch, self.v1)
            self.zotino0.load()
            delay(self.dt)
            
            for i in range(self.nsteps2):
                
                self.zotino0.write_dac(self.ch, self.v1 + (self.v2-self.v1)*i/self.nsteps2)
                self.zotino0.load()
                delay(self.dt)
            self.zotino0.write_dac(self.ch, self.v2)
            self.zotino0.load()
            
        with self.core_dma.record("zotino_ramp_down"):
            # Prime first value
            self.zotino0.write_dac(self.ch, self.v2)
            self.zotino0.load()
            delay(self.dt)


            for step in self.window[self.nsteps:]:
                
                self.zotino0.write_dac(self.ch, self.v3 + (self.v2-self.v3)*step)
                self.zotino0.load()
                delay(self.dt)
            self.zotino0.write_dac(self.ch, self.v3)
            self.zotino0.load()
            
        
            
        # with self.core_dma.record("zotino_bb"):
        #     # Prime first value
        #     self.zotino0.write_dac(self.ch, self.v3)
        #     self.zotino0.load()
        #     delay(self.bb_time)
            
        # with self.core_dma.record("zotino_bb_ramp"):
        #     # Prime first value
        #     self.zotino0.write_dac(self.ch, self.v3)
        #     self.zotino0.load()
        #     delay(self.dt)
            
        #     for i in range(int(self.bb_ramp_time/self.dt)):
                
        #         self.zotino0.write_dac(self.ch, self.v3 + (self.v4-self.v3)*i/int(self.bb_ramp_time/self.dt))
        #         self.zotino0.load()
        #         delay(self.dt)
        #     self.zotino0.write_dac(self.ch, self.v4)
        #     self.zotino0.load()
            
        # with self.core_dma.record("zotino_off"):
        #     # Prime first value
        #     self.zotino0.write_dac(self.ch, self.v4)
        #     self.zotino0.load()
        #     delay(self.dt)


        #     for step in self.window[self.nsteps:]:
                
        #         self.zotino0.write_dac(self.ch, self.v0 + (self.v4-self.v0)*step)
        #         self.zotino0.load()
        #         delay(self.dt)
        #     self.zotino0.write_dac(self.ch, self.v0)
        #     self.zotino0.load()
    

    @kernel
    def run(self):
        # initial devices
        self.core.reset()
        self.MOTs.init_coils()
        self.MOTs.init_ttls()
        self.MOTs.init_aoms(on=False)
        delay(5*ms)
        # self.MOTs.atom_source_on()
        
        
        
        self.zotino0.init()
        self.core.break_realtime()
        delay(5*ms)
        
        
        self.record_ramp_dma()
        handle_up = self.core_dma.get_handle("zotino_ramp_up")
        handle_bmot_ramp = self.core_dma.get_handle("zotino_bmot_ramp")
        handle_down = self.core_dma.get_handle("zotino_ramp_down")
        
        # handle_bb = self.core_dma.get_handle("zotino_bb")
        # handle_bb_ramp = self.core_dma.get_handle("zotino_bb_ramp")
        # handle_off = self.core_dma.get_handle("zotino_off")
        
        
        
        self.core.break_realtime()
        tramp = 25*ms
        binc = 1.0
        
        for shots in range(20):
            
            
            
            self.core.wait_until_mu(now_mu())
            delay(500*ms)
        
            self.MOTs.set_current_dir(0)
            
            
            self.ttl5.on()
            # self.core_dma.playback_handle(handle_up)
            # delay(1000*ms)
            # self.core_dma.playback_handle(handle_bmot_ramp)
            # self.core_dma.playback_handle(handle_down)
            
            self.MOTs.Blackman_ramp(0.0, self.MOTs.bmot_current, self.MOTs.bmot_ramp_duration)
            delay(self.MOTs.bmot_load_duration)
            self.ttl5.off()
            dt = tramp/int(self.MOTs.Npoints)
            for step in range(1, int(self.MOTs.Npoints)):
                self.MOTs.dac_set(0,  self.MOTs.bmot_current + binc/tramp*step*dt)
                delay(dt)

            delay(0.5*us)
        
            # ramp up to broad band red mot current and hold
            self.MOTs.Blackman_ramp(self.MOTs.bmot_current + binc, self.MOTs.rmot_bb_current, 30*ms)
            
            delay(self.MOTs.rmot_bb_duration)
            self.MOTs.linear_ramp(self.MOTs.rmot_bb_current, self.MOTs.rmot_sf_current, self.MOTs.rmot_ramp_duration, self.MOTs.Npoints)
            self.MOTs.Blackman_ramp(self.MOTs.rmot_sf_current, 0.0, 20*ms)
            # self.core_dma.playback_handle(handle_bb)
            # self.core_dma.playback_handle(handle_bb_ramp)
            # self.core_dma.playback_handle(handle_off)
            self.MOTs.set_current_dir(1)
            self.MOTs.Blackman_ramp(0.0, 0.3, 20*ms)
            
            delay(100*ms)
            
            self.MOTs.Blackman_ramp(0.3, 0.0, 20*ms)
            
            
            self.MOTs.set_current_dir(0)
            
            
        
        # self.MOTs.atom_source_off()

        # self.MOTs.Blackman_ramp(self.v0, self.v1, self.ramp_time)



        # for _ in range(3):
        #     self.ttl5.on()
        #     self.MOTs.Blackman_ramp(self.v0, self.v1, self.ramp_time)
        #     delay(1000*ms)
        #     self.MOTs.Blackman_ramp(self.v1, self.v0, self.ramp_time)
        #     self.ttl5.off()


        #     delay(500*ms)
