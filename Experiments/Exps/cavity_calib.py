# -*- coding: utf-8 -*-
"""
Created on Wed Jun 11 17:22:54 2025

@author: ejporter
"""


from artiq.experiment import *
from scan_framework import Scan1D
import numpy as np
from artiq.coredevice import ad9910

from CoolingClass import _Cooling
from BraggClass import _Bragg
# from repository.models.scan_models import LinearModel
# 
from time import sleep

class cavity_calib_exp(Scan1D, EnvExperiment):

    def build(self, **kwargs):
        
        super().build(**kwargs)
        self.setattr_device("ttl5") # triggering pulse

        # import classes for experiment control
        self.MOTs = _Cooling(self)
        self.Bragg = _Bragg(self)

        self.enable_auto_tracking=False

        self.setattr_argument('offsets_freqs', 
            Scannable(default=RangeScan(
            start=0*kHz,
            stop=500*kHz,
            npoints=6),
            scale=1*kHz,
            ndecimals=1,
            unit="kHz"))
        self.setattr_argument("freq_center", 
                              NumberValue(
                                  3*1e6,
                                  min=0.1*1e6,
                                  max=200.0*1e6,
                                  scale=1e6,
                                  unit="MHz",
                                  ndecimals = 3),
                              "parameters")     
        self.setattr_argument("freq_width", 
                              NumberValue(
                                  1*1e6,
                                  min=-10.0*1e6,
                                  max=10.0*1e6,
                                  scale=1e6,
                                  unit="MHz"),
                              "parameters")
        self.setattr_argument("scan_time", 
                              NumberValue(
                                  100*1e-6,
                                  min=1*1e-6,
                                  max=50000*1e-6,
                                  scale=1e-6,
                                  unit='us'),
                              "parameters")

        # create GUI arguments for configuring the scan
        self.scan_arguments(
            nbins = {'default':1000},
            nrepeats = {'default':1},
            npasses = {'default':1},
            fit_options = {'default':"Fit and Save"}
            )

        # self.setattr_argument("shots", NumberValue(11, min=1, max=500, scale=1, unit=""), "parameters")
        
        self.freq_list= np.linspace(0.0*MHz, 0.0*MHz, 1024)
        self.freq_list_ram = np.full(1024, 1)
        self.step_size=0

        self.scan_dds = self.Bragg.urukul_channels[1]


    def get_scan_points(self):
        # return the set of scan points to the framework
        bools = [0, 1]*len(self.offsets_freqs)
        freqs = np.repeat(list(self.offsets_freqs), 2)

        
        return [(bools[i], freqs[i]) for i in range(len(bools))]
        
    def prepare(self):
        self.MOTs.prepare_aoms()
        self.MOTs.prepare_coils()
        self.Bragg.prepare_aoms()

        # self.model = LinearModel()
        # self.register_model(self.model, measurement=False, fit=True)

    @kernel
    def load_scan(self, dds):
        self.step_size = int(self.scan_time/(1024*4*ns))
        f0 = self.freq_center + self.freq_width/2
        if self.freq_width/2 > self.freq_center: raise Exception("Bad Range")
    
        f_step = self.freq_width / 1023        
        for i in range(1024):
            self.freq_list[i] = f0 - f_step*i
            
        dds.frequency_to_ram(self.freq_list, self.freq_list_ram)

        self.core.break_realtime()
        delay(10 * ms)

        dds.set(self.freq_center - self.freq_width/2, amplitude=self.Bragg.scale_Bragg1)

        delay(1 * ms)

        dds.set_cfr1(ram_enable=0)
        dds.cpld.io_update.pulse_mu(8)

        dds.set_profile_ram(start=0, end=1024-1, step=(self.step_size | (2**6 - 1 ) << 16),
                                  profile=0, mode=ad9910.RAM_MODE_RAMPUP)
        dds.cpld.set_profile(0)

        delay(100*us) # need to not to throw RTIOUnderflow Error (not sure why)
        delay(100*us)

        dds.cpld.io_update.pulse_mu(8)
        delay(100*us)
        delay(1000*us)
        dds.write_ram(self.freq_list_ram)
        # prepare to enable ram and set frequency as target
        delay(10 * us)
        dds.set_cfr1(internal_profile=0, ram_enable=1, ram_destination=ad9910.RAM_DEST_FTW)
        delay(10*ms)

        self.core.wait_until_mu(now_mu())

 
    @kernel
    def before_scan(self):
        self.core.reset()

        self.ttl5.off()
        self.MOTs.init_coils()
        self.MOTs.init_ttls()
        self.MOTs.init_aoms(on=False)
        self.Bragg.init_aoms(on=True)

        self.Bragg.AOMs_off(["Bragg1", "Bragg2"])
        self.MOTs.set_current_dir(0)
        delay(10*ms)



        self.core.wait_until_mu(now_mu())


    


    @kernel
    def measure(self, point):
     
        delay(50*ms)
        self.core.wait_until_mu(now_mu())
        self.core.reset() 
        delay(50*ms)

        self.load_scan(self.scan_dds)
        delay(50*ms)

        self.Bragg.set_AOM_attens([("Bragg1", self.Bragg.atten_Bragg1)])
        delay(1 * ms)
        self.MOTs.set_AOM_attens([("3D", self.MOTs.atten_3D)])
        delay(10 * ms)
    
        self.MOTs.AOMs_off(self.MOTs.AOMs) # ensure AOMs are off
        delay(10*ms)

        self.run_exp(point[0]%2==1)

        self.MOTs.set_current_dir(0)
        self.MOTs.AOMs_off(self.MOTs.AOMs)
        delay(50*ms)
        self.core.wait_until_mu(now_mu())
        return 0

   
    @kernel
    def run_exp(self, atoms_on):

        self.MOTs.rMOT_pulse(real=atoms_on)
        
        
        with parallel:
            with sequential:
                delay(10*ms)
                self.MOTs.ttl7.on()
                delay(1*ms)
                self.MOTs.Blackman_ramp(0.0, 0.3, 20*ms)
        
            delay(50*ms) # dipole load time
        
        self.Bragg.AOMs_on(["Bragg2"]) # turn on probe light
        with parallel:
            self.scan_dds.sw.on()
            self.ttl5.on()
            self.scan_dds.cpld.io_update.pulse_mu(8)
        delay(self.scan_time)
        with parallel:
            self.scan_dds.sw.off()
            self.ttl5.off()            
        self.Bragg.AOMs_off(["Bragg2"])

        
        
    def after_measure(self, point, measurement):
        if point[0]%2 == 1:
            print(point[1])


        sleep(1)