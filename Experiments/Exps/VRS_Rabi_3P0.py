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
from STIRAPClass import _STIRAP
from repository.models.scan_models import RabiModel


class VRS_Rabi3P0_exp(Scan1D, TimeScan, EnvExperiment):
    
    def build(self, **kwargs):
        
        super().build(**kwargs)
        self.setattr_device("ttl5") # triggering pulse

        # import classes for experiment control
        self.MOTs = _Cooling(self)
        self.Camera = _Camera(self)
        self.Bragg = _Bragg(self)
        self.STIRAP = _STIRAP(self) # controls 689, 679, 688, and push AOMs
        

        
                # attributes here
        self.enable_pausing = True # disable to speed up by not checking scheduler
        self.enable_auto_tracking=False
        self.enable_profiling = False # enable to print runtime statistics to find bottlenecks
        
        self.scan_dds = self.Bragg.urukul_channels[1]
        
        self.scan_arguments(times = {'start':0*1e-6,
            'stop':10*1e-6,
            'npoints':20,
            'unit':"us",
            'scale':us,
            'global_step':0.01*us,
            'ndecimals':2},
            nbins = {'default':1000},
            nrepeats = {'default':1},
            npasses = {'default':1},
            fit_options = {'default':"Fit and Save"}
            )

        # Arguments 
        
        self.setattr_argument("pi_2_time689", NumberValue(1.0*1e-6,min=0.0*1e-6,max=1000.00*1e-6,scale=1e-6,
                      unit="us"),"Params")
        self.setattr_argument("pi_timeRaman", NumberValue(1.0*1e-6,min=0.0*1e-6,max=1000.00*1e-6,scale=1e-6,
                      unit="us"),"Params")
        
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
        
        self.setattr_argument("B_field", NumberValue(0.88,min=0.0,max=2,scale=1,
                      unit="V", ndecimals=3),"Params")

        self.freq_list= np.linspace(80.0*MHz, 80.0*MHz, 1024)
        self.freq_list_ram = np.full(1024, 1)
        self.step_size=0
        
        
    def prepare(self):
        #prepare/initialize mot hardware and camera
        
        self.MOTs.prepare_aoms()
        self.MOTs.prepare_coils()
        self.Camera.camera_init()
        self.Bragg.prepare_aoms()
        self.STIRAP.prepare_aoms()
        # register model with scan framework
        
        self.enable_histograms = True
        self.model = RabiModel(self)
        self.register_model(self.model, measurement=True, fit=False)
        
        
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
        self.STIRAP.init_aoms(on=False)

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

        self.MOTs.rMOT_pulse()
        
        
        with parallel:
            delay(self.dipole_load_time)
            with sequential:
                self.MOTs.set_current_dir(1) # XXX let MOT field go to zero and switch H-bridge, 5ms
                self.MOTs.set_current(self.B_field)
        
        ### Measure VRS with all atoms
        self.Bragg.AOMs_on(["Bragg2"])
        with parallel:
            self.scan_dds.sw.on()
            self.ttl5.on()
            self.scan_dds.cpld.io_update.pulse_mu(8)
        delay(self.scan_time)
        with parallel:
            self.scan_dds.sw.off()
            self.ttl5.off()
        self.Bragg.AOMs_off(["Bragg2"])
        #delay(1000*us)
        
        delay(200*us)
        
        #Excite to 3P0
        self.ttl5.on()
        self.STIRAP.pulse(point, self.STIRAP.urukul_channels[self.STIRAP.index_artiq("689")])
        delay(0.2*us)
        self.raman_pulse(self.pi_timeRaman)
        self.ttl5.off()
        
        delay(200*us)
        ### VRS for N_down
        self.Bragg.AOMs_on(["Bragg2"])
        with parallel:
            self.scan_dds.sw.on()
            self.ttl5.on()
            self.scan_dds.cpld.io_update.pulse_mu(8)
        delay(self.scan_time)
        with parallel:
            self.scan_dds.sw.off()
            self.ttl5.off()            
        self.Bragg.AOMs_off(["Bragg2"])
        #delay(1000*us)
        
        ### Push and separate
        self.STIRAP.push_pulse(self.MOTs.Push_pulse_time)
        self.MOTs.AOMs_on(['3P0_repump', '3P2_repump'])
        delay(self.MOTs.Delay_duration)
        self.MOTs.AOMs_off(['3P0_repump', '3P2_repump'])
        
        
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
        return self.Camera.get_push_stats()
     

    
    @kernel
    def after_scan(self):
        self.core.break_realtime()
        self.core.wait_until_mu(now_mu())
        delay(100*ms)
        self.MOTs.AOMs_on(self.MOTs.AOMs)
        delay(10*ms)
        self.MOTs.atom_source_on()
    
    
    @kernel
    def raman_pulse(self, time):
        self.STIRAP.AOMs_on(['688']) # turn on 688 for STIRAP sequence
        delay(0.1*us)
        self.STIRAP.AOMs_on(["679"]) # turn on 688 for STIRAP sequence
        delay(time)
        self.STIRAP.AOMs_off(['688']) # turn on 688 for STIRAP sequence
        delay(0.07*us)
        self.STIRAP.AOMs_off(["679"]) # turn on 688 for STIRAP sequence
    # @kernel    
    # def log_time(self):
    #     self.log[self.ind] = ((self.core.get_rtio_counter_mu()-self.t0_rtio)//10**6, (now_mu()-self.t0)//10**6)
    #     self.ind += 1