# -*- coding: utf-8 -*-
"""
Created on Mon Nov  4 11:01:45 2024

@author: ejporter
"""

from artiq.experiment import *
from scan_framework import Scan1D, TimeScan
import numpy as np
from artiq.coredevice import ad9910

from CoolingClass import _Cooling
from CameraClass import _Camera
from BraggClass import _Bragg
from repository.models.scan_models import RabiModel


class VRS_sideband_scan_exp(Scan1D, TimeScan, EnvExperiment):
    
    def build(self, **kwargs):
        
        super().build(**kwargs)
        self.setattr_device("ttl5") # triggering pulse

        # import classes for experiment control
        self.MOTs = _Cooling(self)
        self.Camera = _Camera(self)
        self.Bragg = _Bragg(self)
        
        # self.log = [(np.int64(0), np.int64(0))]*5
        # self.ind = 0
        # self.t0 = np.int64(0)
        # self.t0_rtio = np.int64(0)
        
                # attributes here
        self.enable_pausing = True # disable to speed up by not checking scheduler
        self.enable_auto_tracking=False
        self.enable_profiling = False # enable to print runtime statistics to find bottlenecks
        
        self.scan_dds = self.Bragg.urukul_channels[1]
        
        self.scan_arguments(times = {'start':10*1e-6,
            'stop':10*1e-6,
            'npoints':20,
            'unit':"us",
            'scale':us,
            'global_step':1*us,
            'ndecimals':2},
            nbins = {'default':1000},
            nrepeats = {'default':1},
            npasses = {'default':1},
            fit_options = {'default':"Fit and Save"}
            )

        # Arguments 
        self.setattr_argument("dipole_load_time", 
                              NumberValue(
                                  15*1e-3,
                                  min=1.0*1e-3,
                                  max=5000.00*1e-3,
                                  scale=1e-3,
                                  unit="ms"),
                              "parameters")     
        self.setattr_argument("freq_center", 
                              NumberValue(
                                  3*1e6,
                                  min=0.1*1e6,
                                  max=100.0*1e6,
                                  scale=1e6,
                                  unit="MHz"),
                              "parameters")     
        self.setattr_argument("freq_width", 
                              NumberValue(
                                  1*1e6,
                                  min=-10.0*1e6,
                                  max=10.0*1e6,
                                  scale=1e6,
                                  unit="MHz"),
                              "parameters")
        self.setattr_argument("pulses", 
                              NumberValue(
                                  10,
                                  min=1,
                                  max=1000,
                                  scale=1,),
                              "parameters")
        self.setattr_argument("scan_time", 
                              NumberValue(
                                  100*1e-6,
                                  min=1*1e-6,
                                  max=50000*1e-6,
                                  scale=1e-6,
                                  unit='us'),
                              "parameters")

        self.freq_list= np.linspace(80.0*MHz, 80.0*MHz, 1024)
        self.freq_list_ram = np.full(1024, 1)
        self.step_size=0
        
        
        
    def prepare(self):
        #prepare/initialize mot hardware and camera
        
        self.MOTs.prepare_aoms()
        self.MOTs.prepare_coils()
        self.Camera.camera_init()
        self.Bragg.prepare_aoms()
        # register model with scan framework
        
        self.enable_histograms = True
        self.model = RabiModel(self)
        self.register_model(self.model, measurement=False, fit=False)
        
        
    @kernel
    def load_scan(self):
        self.step_size = int(self.scan_time/(1024*4*ns))
        f0 = self.freq_center + self.freq_width/2
        f_step = self.freq_width/1023
        if self.freq_width/2 > self.freq_center: raise Exception("Bad Range")
        for i in range(1024):
            self.freq_list[i] = f0 - f_step*i
        self.scan_dds.frequency_to_ram(self.freq_list, self.freq_list_ram)

        self.core.break_realtime()
        delay(10 * ms)

        self.scan_dds.set(self.freq_center - self.freq_width/2, amplitude=self.Bragg.scale_Bragg1)

        delay(1 * ms)



        self.scan_dds.set_cfr1(ram_enable=0)
        self.scan_dds.cpld.io_update.pulse_mu(8)

        self.scan_dds.set_profile_ram(start=0, end=1024-1, step=(self.step_size | (2**6 - 1 ) << 16),
                                  profile=0, mode=ad9910.RAM_MODE_RAMPUP)
        self.scan_dds.cpld.set_profile(0)

        delay(100*us) # needs 2x delays here not to throw RTIOUnderflow Error?????
        delay(100*us)

        self.scan_dds.cpld.io_update.pulse_mu(8)
        delay(100*us)
        self.scan_dds.write_ram(self.freq_list_ram)
        # prepare to enable ram and set frequency as target
        delay(10 * us)
        self.scan_dds.set_cfr1(internal_profile=0, ram_enable=1, ram_destination=ad9910.RAM_DEST_FTW)
        delay(10*ms)

        self.core.wait_until_mu(now_mu())



    @kernel 
    def before_scan(self):
        self.core.reset()
        #self.ttl1.output()
        self.ttl5.off()
        self.MOTs.init_coils()
        self.MOTs.init_ttls()
        self.MOTs.init_aoms(on=False)
        self.Bragg.init_aoms(on=True)

        self.Bragg.AOMs_off(["Bragg1", "Bragg2"])
        self.MOTs.set_current_dir(0)
        delay(10*ms)
        self.MOTs.take_background_image_exp(self.Camera)
        self.MOTs.atom_source_on()
        delay(100*ms)
        self.MOTs.AOMs_on(['3D', "3P0_repump", "3P2_repump"])
        delay(200*ms)

        self.MOTs.AOMs_off(['3D', "3P0_repump", "3P2_repump"])
        self.MOTs.atom_source_off()
        
        self.core.wait_until_mu(now_mu())
     
    def before_measure(self, point, measurement):
        self.Camera.arm()
        
    @kernel
    def measure(self, point):
        self.core.reset()
        delay(1 * ms)
        self.load_scan()
        delay(1*ms)

        # before this point is just for preparing the RAM and RIGOL
        self.core.break_realtime()
        delay(10*ms)
        self.Bragg.set_AOM_attens([("Bragg1", self.Bragg.atten_Bragg1)])
        
        delay(10 * ms)
        delay(100*ms)
        self.MOTs.AOMs_off(self.MOTs.AOMs)
        delay(50*ms)

        self.run_exp(point)
        
        
        self.MOTs.take_MOT_image(self.Camera) # image after variable drop time
        delay(5*ms)
        
        
        self.scan_dds.set_cfr1(ram_enable=0)
        self.scan_dds.cpld.io_update.pulse_mu(8)
        delay(5*ms)
        self.MOTs.set_current_dir(0)
        delay(50*ms)
        self.Camera.process_image(bg_sub=True)
        delay(400*ms)
        self.core.wait_until_mu(now_mu())
        delay(200*ms)
        self.MOTs.AOMs_off(['3P0_repump', '3P2_repump', '3D', "3D_red"])
        delay(300*ms)

        self.core.wait_until_mu(now_mu())
        return 0
     
    
    @kernel
    def run_exp(self, delay_time):


        self.MOTs.rMOT_pulse()
        
        
        self.MOTs.set_current_dir(1)
        self.MOTs.set_current(0.85)
        
        delay(self.dipole_load_time)
        
        for _ in range(int(self.pulses)):
            
            self.Bragg.AOMs_on(["Bragg2"])
            with parallel:
                self.scan_dds.sw.on()
                self.ttl5.on()
                self.scan_dds.cpld.io_update.pulse_mu(8)
            delay(self.scan_time)
            with parallel:
                self.scan_dds.sw.off()
                self.ttl5.off()            
            delay(delay_time)
            self.Bragg.AOMs_off(["Bragg2"])
        
        

    
    @kernel
    def after_scan(self):
        self.core.break_realtime()
        self.core.wait_until_mu(now_mu())
        delay(100*ms)
        self.MOTs.AOMs_on(self.MOTs.AOMs)
        delay(10*ms)
        self.MOTs.atom_source_on()
        
    # @kernel    
    # def log_time(self):
    #     self.log[self.ind] = ((self.core.get_rtio_counter_mu()-self.t0_rtio)//10**6, (now_mu()-self.t0)//10**6)
    #     self.ind += 1