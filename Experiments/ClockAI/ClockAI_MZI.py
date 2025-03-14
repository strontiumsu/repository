# -*- coding: utf-8 -*-
"""
Created on Mon Dec  9 16:04:54 2024

@author: sr
"""


from scan_framework import Scan1D, TimeScan
from artiq.experiment import *
import numpy as np



from CoolingClass import _Cooling
from CameraClass import _Camera
from ClockAIClass import _ClockAI
from BraggClass import _Bragg
from repository.models.scan_models import RabiModel

class ClockAI_MZI_exp(Scan1D, EnvExperiment):
    
    def build(self, **kwargs):
        # required initializations
        
        super().build(**kwargs)
        
        # import classes for experiment control
        self.MOTs = _Cooling(self)
        self.Camera = _Camera(self)
        self.AI = _ClockAI(self)
        self.Bragg = _Bragg(self)
        
        self.setattr_device("ttl5")
        
        self.enable_pausing = True # disable to speed up by not checking scheduler
        self.enable_auto_tracking=False
        self.enable_profiling = False # enable to print runtime statistics to find bottlenecks


        self.setattr_argument('pulse_phase',
            Scannable(default=RangeScan(
            start=0.0,
            stop=2.0,
            npoints=20),
            scale=1,
            ndecimals=2,
            unit="Turns", ), 'Params')
        
        self.scan_arguments(nbins={'default':1000},
                    nrepeats={'default':1},
                    npasses={'default':1},
                    fit_options={'default':"No Fits"})
        
        self.setattr_argument("load_time", NumberValue(20.0*1e-3,min=0.0*1e-3,max=200.00*1e-3,scale=1e-3,
                      unit="ms"),"Params")
        
        self.setattr_argument("pitime_1", NumberValue(0.5*1e-6,min=0.0*1e-6,max=10*1e-6,scale=1e-6,
                      unit="us", ndecimals=3),"Params")
        self.setattr_argument("pitime_2", NumberValue(0.5*1e-6,min=0.0*1e-6,max=10*1e-6,scale=1e-6,
                      unit="us", ndecimals=3),"Params")
        
        self.setattr_argument("pi_2_time_1", NumberValue(0.25*1e-6,min=0.0*1e-6,max=10*1e-6,scale=1e-6,
                      unit="us", ndecimals=3),"Params")
        self.setattr_argument("pi_2_time_2", NumberValue(0.25*1e-6,min=0.0*1e-6,max=10*1e-6,scale=1e-6,
                      unit="us", ndecimals=3),"Params")
        
        self.setattr_argument("N", NumberValue(0,min=-2,max=100,scale=1),"Params")
        self.setattr_argument("pi_2_delay_time", NumberValue(0.5*1e-6,min=0.0*1e-6,max=10*1e-6,scale=1e-6,
                      unit="us"),"Params")
        
        self.setattr_argument("B_field", NumberValue(0.88,min=0.0,max=2,scale=1,
                      unit="V", ndecimals=3),"Params")
        
        

        self.t0 = np.int64(0)
        self.FIX_DELAY_TIME = 150*ns
        
    def get_scan_points(self):
        return self.pulse_phase    
        
    def prepare(self):
        #prepare/initialize mot hardware and camera
        self.MOTs.prepare_aoms()
        self.MOTs.prepare_coils()
        self.Bragg.prepare_aoms()
        self.Camera.camera_init()
        self.AI.prepare_aoms()
        
        self.AI_arm1_dds = self.AI.urukul_channels[2] # indexes into urukul ch array 
        self.AI_arm2_dds = self.AI.urukul_channels[3] # indexes into urukul ch array 
        self.arms = [self.AI_arm1_dds, self.AI_arm2_dds]
        
        self.pi_times = [self.pitime_1, self.pitime_2]
        self.pi_2_times = [self.pi_2_time_1, self.pi_2_time_2]
        
        # register model with scan framework
        self.enable_histograms = True
        self.model = RabiModel(self)
        self.register_model(self.model, measurement=True, fit=True)

    @kernel
    def before_scan(self):
        # runs before experiment take place
        
        #initialize devices on host
        self.core.reset()
        delay(10*ms)
        self.MOTs.init_coils()
        self.MOTs.init_ttls()
        self.MOTs.init_aoms(on=False)  
        self.AI.init_aoms(on=False)
        self.Bragg.init_aoms(on=True)
        delay(10*ms)
        
        self.MOTs.set_current_dir(0)
        delay(10*ms)
        self.ttl5.off()
        
        self.MOTs.take_background_image_exp(self.Camera)
        
        self.MOTs.atom_source_on()
        delay(5*ms)
        self.MOTs.AOMs_on(['3D', "3P0_repump", "3P2_repump", "3D_red"])
        delay(2000*ms)
        self.MOTs.AOMs_off(['3D', "3P0_repump", "3P2_repump", "3D_red"])
        self.MOTs.atom_source_off()    
                   

    @kernel
    def measure(self, point):        
        
        #prepare
        self.core.wait_until_mu(now_mu())
        self.core.reset()
        delay(100*ms)
        self.Camera.arm()
        delay(200*ms)
        self.t0 = now_mu()
        
        # sets the phase for everything, 
        self.AI.set_AOM_phase('Unused', self.AI.freq_Unused, 0.0, self.t0, 0)
        self.AI.set_AOM_phase('Unused', self.AI.freq_Unused, 0.0, self.t0, 1)

        #
        self.AI.set_AOM_phase('Push', self.AI.freq_Push, 0.0, self.t0, 0)
        self.AI.set_AOM_phase('Push', self.AI.freq_Push, 0.0, self.t0, 1)


        self.AI.set_AOM_phase('AI1', self.AI.freq_AI1, 0.0, self.t0, 0)
        self.AI.set_AOM_phase('AI1', self.AI.freq_AI1, point, self.t0, 1)


        self.AI.set_AOM_phase('AI2', self.AI.freq_AI2, 0.0, self.t0, 0)
        if self.N <0:
            self.AI.set_AOM_phase('AI2', self.AI.freq_AI2, point, self.t0, 1)
        else:
            self.AI.set_AOM_phase('AI2', self.AI.freq_AI2, 0.0, self.t0, 1)
        
        self.AI.switch_profile(0)
        
        
        
        
        # perform experiment
        self.MOTs.AOMs_off(self.MOTs.AOMs)
        delay(15*ms)
        self.MOTs.rMOT_pulse()  # generates the red MOT

        self.MOTs.set_current_dir(1) # XXX let MOT field go to zero and switch H-bridge, 5ms
        self.MOTs.set_current(self.B_field)
        delay(self.load_time)
        
        #self.Bragg.set_AOM_attens([("Dipole",30.0 )])
        #self.Bragg.AOMs_off(["Lattice"])
        delay(10*us)
        
        if self.N == -1:
            ### open
            self.AI.AI_pulse(self.pi_2_time_1, 0)
            delay(1000*ns)        
            
            ### mirror 
            self.AI.AI_pulse(self.pitime_1, 0)
                        ### close        
            with parallel:
                delay(1000*ns)
                self.AI.switch_profile(1)
            self.AI.AI_pulse(self.pi_2_time_1, 0)
            
        elif self.N ==-2:

            self.AI.AI_pulse(self.pi_2_time_2, 1)
            delay(1000*ns)        
            
            #delay(T)
            
            ### mirror 
            self.AI.AI_pulse(self.pitime_2, 1)
            
            #delay(T)        
            
            ### close        
            with parallel:
                delay(1000*ns)
                self.AI.switch_profile(1)
            self.AI.AI_pulse(self.pi_2_time_2, 1)
            
        else:
        
            # pi/2 pulse for state prep
            self.AI.AI_pulse(self.pi_2_time_1, 0) #pi/2
            delay(self.pi_2_delay_time)    
            
            delay(self.FIX_DELAY_TIME)

            arm_num = 1 # starts on arm 2 (index = 1, arm 1 index is 0)
            
            # acceleration
            for _ in range(int(self.N)):
                self.AI.AI_pulse(self.pi_times[arm_num], int(arm_num)) #drive 3P1
                delay(self.FIX_DELAY_TIME)
                arm_num = (arm_num+1)%2 # switches arm
                    
            delay(self.FIX_DELAY_TIME)
            
            
            # # mirror pulse
            arm_num = (arm_num+1)%2
            for _ in range(int(self.N)*2+1):
                self.AI.AI_pulse(self.pi_times[arm_num], int(arm_num)) #drive 3P1
                delay(self.FIX_DELAY_TIME)
                arm_num = (arm_num+1)%2  # switches arm
                  
            delay(self.FIX_DELAY_TIME)      
            
            
            # deceleration
            arm_num = (arm_num+1)%2
            for _ in range(int(self.N)):
                self.AI.AI_pulse(self.pi_times[arm_num], int(arm_num)) #drive 3P1
                delay(self.FIX_DELAY_TIME)
                arm_num = (arm_num+1)%2  # switches arm
                    
            ### interferometer   
            with parallel:
                delay(self.pi_2_delay_time)
                self.AI.switch_profile(1)
            self.AI.AI_pulse(self.pi_2_time_1, 0) #pi/2

  
    
  
    
    
        ### push
        self.AI.push_pulse(self.MOTs.Push_pulse_time) #seperate for readout


        self.Bragg.set_AOM_attens([("Dipole",self.Bragg.atten_Dipole )])
        delay(self.MOTs.Delay_duration)
        self.Bragg.AOMs_on(["Lattice"])
        
        

        self.MOTs.take_MOT_image(self.Camera)  
        delay(5*ms)
        self.MOTs.set_current_dir(0)
        delay(5*ms)  
        
        #process and output
        self.MOTs.atom_source_on() # just keeps AOMs warm
        self.MOTs.AOMs_on(self.MOTs.AOMs) # just keeps AOMs warm

        self.Camera.process_image(save=True, name='', bg_sub=True)

        delay(400*ms)
        
        
        return self.Camera.get_push_stats()
        
        
        

    
    def after_fit(self, fit_name, valid, saved, model):
        self.set_dataset('current_scan.plots.error', model.errors, broadcast=True, persist=True)


        