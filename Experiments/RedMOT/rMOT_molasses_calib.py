# -*- coding: utf-8 -*-
"""
Created on Tue Jan 21 13:37:31 2025

@author: sr
"""

from scan_framework import Scan1D, TimeFreqScan

from artiq.experiment import Scannable, RangeScan, EnumerationValue, BooleanValue, NumberValue # pyright: ignore[reportMissingImports]
from artiq.experiment import kernel, EnvExperiment, kHz, delay, ms, parallel, us, MHz, now_mu, ns # pyright: ignore[reportMissingImports]




from CoolingClass import _Cooling
from CameraClass import _Camera

from BraggClass import _Bragg
from repository.models.scan_models import AI_Rabi_Model as myModel # pyright: ignore[reportMissingImports]


class rMOT_molasses_calib_exp(Scan1D, TimeFreqScan, EnvExperiment):
    
    def build(self, **kwargs):
        # required initializations
        
        super().build(**kwargs)
        
        self.setattr_device("ttl5") # triggering pulse
        self.setattr_device("ttl1")
        # import classes for experiment control
        self.MOTs = _Cooling(self)
        self.Camera = _Camera(self)
        self.Bragg = _Bragg(self)
        
        self.enable_pausing = True # disable to speed up by not checking scheduler
        self.enable_auto_tracking=False
        self.enable_profiling = False # enable to print runtime statistics to find bottlenecks

        self.scan_arguments(times = {'start':10*ms,'stop':100*ms,'npoints':20,'unit':"ms",'scale':ms,'global_step':0.1*ms,'ndecimals':4},
             frequencies={'start':-3*MHz,'stop':3*MHz,'npoints':10,'unit':"MHz",'scale':MHz,'global_step':0.1*MHz,'ndecimals':4},
            frequency_center={'default':179*MHz}, pulse_time= {'default':40*ms},nbins = {'default':1000},nrepeats = {'default':1},npasses = {'default':1},fit_options = {'default': "No Fits"} )
        
        self.setattr_argument("dipole_load_time", NumberValue(60.0*1e-3,min=0.0*1e-3,max=9000.00*1e-3,scale=1e-3,
                      unit="ms"),"Params")   
        self.setattr_argument("B_field", NumberValue(0.36,min=0.0,max=2,scale=1,
                      unit="V", ndecimals=3),"Params")
        
        
    def prepare(self):
        #prepare/initialize mot hardware and camera
        self.MOTs.prepare_aoms()
        self.Bragg.prepare_aoms()
        
        self.MOTs.prepare_coils()
        
        self.Camera.camera_init()
        
        
        self.enable_histograms = True
        self.model = myModel(self)
        self.register_model(self.model, measurement=True, fit=True)
        
    @kernel
    def before_scan(self):
        # runs before experiment take place
        
        self.core.reset()
        delay(10*ms)
        self.ttl5.off()
        self.MOTs.init_coils()
        self.MOTs.init_ttls()
        
        #init AOMs
        self.MOTs.init_aoms(on=False)  
        self.Bragg.init_aoms()
        
        delay(10*ms)
        
        #MOT Config
        self.MOTs.set_current_dir(0)
        delay(10*ms)
        
        self.MOTs.take_background_image_exp(self.Camera)
        
        # Warm up before exp
        delay(50*ms)
        self.core.wait_until_mu(now_mu())
        
    def before_measure(self, point, measurement):
        self.Camera.arm()
 
    @kernel
    def measure(self, time, frequency):        
        
        
        #prepare
        self.core.wait_until_mu(now_mu())
        self.core.reset()
        
        self.MOTs.init_rmot_dds(self.MOTs.rmot_freq_i, self.MOTs.rmot_freq_f,  self.MOTs.rmot_freq_depth_i, self.MOTs.rmot_freq_depth_f, self.MOTs.freq_3D_red)

        delay(1*ms)
        
        self.core.break_realtime()
        delay(10*ms)

        self.MOTs.AOMs_off_all()
        delay(5*ms)
        
         # generate red mot
        self.MOTs.rMOT_pulse_new()
        
        # load into dipole trap and perform molasses (if selected)
        # Total time for this sequence needs to be >~ 40 ms for cavity shaking to stop.
        with parallel:
            delay(self.dipole_load_time/3) 
            self.MOTs.set_current_dir(1) # let MOT field go to zero and switch H-bridge, 15ms        
        self.MOTs.Blackman_ramp(0.0, self.B_field ,self.dipole_load_time/3) # set bias field so 3P1 m=+1 is ~40MHz separated.
        if self.MOTs.molasses:
            self.MOTs.molasses_pulse(freq=frequency, amp=0.1, t=time)
        else:
            delay(time)
            
            
            
        # load into dipole trap and perform molasses (if selected)
        # Total time for this sequence needs to be >~ 40 ms for cavity shaking to stop.
        # with parallel:
        #     delay(self.dipole_load_time/3) 
        #     self.MOTs.set_current_dir(1) # let MOT field go to zero and switch H-bridge, 15ms 
        # if self.MOTs.molasses:
        #     self.MOTs.molasses_pulse(freq=frequency, amp=0.1, t=time)
        # else:
        #     delay(time)
        # self.MOTs.Blackman_ramp(0.0, self.B_field ,self.dipole_load_time/3) # set bias field so 3P1 m=+1 is ~40MHz separated.
        
        # release from lattice for 1ms
        self.Bragg.aom_dipole.set_att(30.0) # turn off dipole
        self.Bragg.aom_lattice.sw.off() #turn off lattice
        delay(2*ms)
        
        # focus for variable time
        self.Bragg.aom_dipole.set_att(self.Bragg.atten_Dipole) # turn off dipole
        delay(time)
        

        self.Bragg.aom_dipole.set_att(30.0) # turn off dipole
        self.Bragg.aom_lattice.sw.off() #turn off lattice
        delay(4*ms)

        # image and reset for next shot
        self.MOTs.take_MOT_image(self.Camera)  
        delay(15*ms)
        
        self.Bragg.aom_dipole.set_att(self.Bragg.atten_Dipole)
        self.Bragg.aom_lattice.sw.on()
        
        self.MOTs.set_current(0.0)
        delay(20*ms)
        self.MOTs.set_current_dir(0)
        delay(5*ms)  
        
        #process and output
        self.MOTs.AOMs_on_all() # just keeps AOMs warm
        self.Camera.process_image(save=True, name='', bg_sub=True)
        delay(400*ms)
        
        return self.Camera.get_push_stats()
                  
        
                
    @kernel
    def after_scan(self):
        self.core.reset()
        delay(50*ms)
        for i in range(3):
            self.MOTs.urukul_channels[i].sw.on()
        self.MOTs.atom_source_on()    
  