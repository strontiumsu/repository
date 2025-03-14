# -*- coding: utf-8 -*-
"""
Created on Tue Dec 10 16:32:42 2024

@author: sr
"""

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

class clockAI_deifferntial_exp(Scan1D, EnvExperiment):
    
    def build(self, **kwargs):
        # required initializations
        
        super().build(**kwargs)
        
        # import classes for experiment control
        self.MOTs = _Cooling(self)
        self.Camera = _Camera(self)
        self.AI = _ClockAI(self)
        self.Bragg = _Bragg(self)
        
        self.enable_pausing = True # disable to speed up by not checking scheduler
        self.enable_auto_tracking=False
        self.enable_profiling = False # enable to print runtime statistics to find bottlenecks


        self.setattr_argument('pi_time_1',
            Scannable(default=RangeScan(
            start=0.3*1e-6,
            stop=0.5*1e-6,
            npoints=20),
            scale=1e-6,
            ndecimals=3,
            unit="us", ), 'Params')
        
        self.scan_arguments(nbins={'default':1000},
                    nrepeats={'default':1},
                    npasses={'default':1},
                    fit_options={'default':"No Fits"})
        
        self.setattr_argument("load_time", NumberValue(20.0*1e-3,min=0.0*1e-3,max=200.00*1e-3,scale=1e-3,
                      unit="ms"),"Params")
        
        self.setattr_argument("pitime_1", NumberValue(0.5*1e-6,min=0.0*1e-6,max=10*1e-6,scale=1e-6,
                      unit="us"),"Params")
        self.setattr_argument("pitime_2", NumberValue(0.5*1e-6,min=0.0*1e-6,max=10*1e-6,scale=1e-6,ndecimals=3,
                      unit="us"),"Params")
        
        self.setattr_argument("pi_2_time_1", NumberValue(0.25*1e-6,min=0.0*1e-6,max=10*1e-6,scale=1e-6,
                      unit="us"),"Params")
        self.setattr_argument("pi_2_time_2", NumberValue(0.25*1e-6,min=0.0*1e-6,max=10*1e-6,scale=1e-6,
                      unit="us"),"Params")
        
        self.setattr_argument("N", NumberValue(0,min=0,max=100,scale=1),"Params")
        self.setattr_argument("start_arm", NumberValue(0,min=0,max=1,scale=1),"Params")
        
        self.setattr_argument("pi_2_delay_time", NumberValue(0.5*1e-6,min=0.0*1e-6,max=10*1e-6,scale=1e-6,
                      unit="us"),"Params")
        
        

        self.t0 = np.int64(0)
    def get_scan_points(self):
        return self.pi_time_1    
        
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
        
        self.MOTs.take_background_image_exp(self.Camera)
        
        delay(10*ms)
        
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
        # self.AI.set_AOM_phase('Unused', self.AI.freq_Unused, 0.0, self.t0, 0)
        # self.AI.set_AOM_phase('Unused', self.AI.freq_Unused, 0.0, self.t0, 1)

        # #
        # self.AI.set_AOM_phase('Push', self.AI.freq_Push, 0.0, self.t0, 0)
        # self.AI.set_AOM_phase('Push', self.AI.freq_Push, 0.0, self.t0, 1)


        # self.AI.set_AOM_phase('AI1', self.AI.freq_AI1, 0.0, self.t0, 0)
        # self.AI.set_AOM_phase('AI1', self.AI.freq_AI1, point, self.t0, 1)


        # self.AI.set_AOM_phase('AI2', self.AI.freq_AI2, 0.0, self.t0, 0)
        # if self.N < 0:
        #     self.AI.set_AOM_phase('AI2', self.AI.freq_AI2, point, self.t0, 1)
        # else:
        #     self.AI.set_AOM_phase('AI2', self.AI.freq_AI2, 0.0, self.t0, 1)
        
        # self.AI.switch_profile(0)
        
        
        
        
            
        
        
        # perform experiment
        self.MOTs.AOMs_off(self.MOTs.AOMs)
        delay(15*ms)
        self.MOTs.rMOT_pulse()  # generates the red MOT

        self.MOTs.set_current_dir(1) # XXX let MOT field go to zero and switch H-bridge, 5ms
        self.MOTs.set_current(0.4)
        delay(self.load_time)
        
        self.Bragg.set_AOM_attens([("Dipole",30.0 )])
        self.Bragg.AOMs_off(["Lattice"])
        delay(10*us)
        
        
        
        
        #####################################
        # start interferometery sequence
        self.AI.ttl7.on()
        
        # self.pulse_N(1, self.start_arm, self.pi_2_times)
        # delay(self.pi_2_delay_time)    # nominal 500 ns
        
        # # acceleration
        # self.pulse_N(self.N, (self.start_arm+1)%2, self.pi_times)
        
        # #mirror
        # self.pulse_N(2*self.N+1, (self.start_arm+N)%2, self.pi_times)
        
        # # de-acceleration
        # self.pulse_N(self.N, (self.start_arm+1)%2, self.pi_times)
        
        # # recombine
        # with parallel:
        #     delay(self.pi_2_delay_time)    # nominal 500 ns
        #     self.AI.switch_profile(1)
        # self.pulse_N(1, self.start_arm, self.pi_2_times)
        
        # self.AI.ttl7.off()
        # end interferomter sequence
        #####################################

        # self.AI.AI1_pulse(self.pi_2_time_1) 
        # delay(500*ns) 
        for _ in range(8):
            self.AI.AI1_pulse(point) 
            delay(150*ns)
            self.AI.AI2_pulse(self.pitime_2) 
            delay(150*ns)
        # self.AI.AI1_pulse(self.pitime_1) 
        # delay(150*ns)
        # self.AI.AI2_pulse(self.pitime_2) 
        # delay(150*ns)
        # self.AI.AI1_pulse(self.pitime_1) 
        # delay(150*ns)
        # self.AI.AI2_pulse(self.pitime_2) 
        # delay(150*ns)
        # self.AI.AI1_pulse(self.pitime_1) 
        # delay(150*ns)
        # self.AI.AI2_pulse(self.pitime_2) 
        # delay(150*ns)
        # self.AI.AI1_pulse(self.pitime_1) 
        # delay(150*ns)
        # self.AI.AI2_pulse(self.pitime_2) 
        # delay(150*ns)
        # self.AI.AI1_pulse(self.pitime_1) 
        # delay(150*ns)
        # self.AI.AI2_pulse(self.pitime_2) 
        # delay(150*ns)
        # self.AI.AI1_pulse(self.pitime_1) 
        # delay(150*ns)
        # self.AI.AI2_pulse(self.pitime_2) 
        # delay(150*ns)
        # self.AI.AI1_pulse(self.pitime_1) 
        # delay(150*ns)
        
        # self.AI.AI2_pulse(self.pitime_2) 
        # delay(150*ns)
        # self.AI.AI1_pulse(self.pitime_1) 
        # delay(150*ns)
        # self.AI.AI2_pulse(self.pitime_2) 
        # delay(150*ns)
        # self.AI.AI1_pulse(self.pitime_1) 
        # delay(150*ns)
        # self.AI.AI2_pulse(self.pitime_2) 
        # delay(150*ns)
        # self.AI.AI1_pulse(self.pitime_1) 
        # delay(150*ns)
        # self.AI.AI2_pulse(self.pitime_2) 
        # delay(150*ns)
        # self.AI.AI1_pulse(self.pitime_1) 
        # delay(150*ns)
        # self.AI.AI2_pulse(self.pitime_2) 
        # delay(150*ns)
        # self.AI.AI1_pulse(self.pitime_1) 
        # delay(150*ns)
        # self.AI.AI2_pulse(self.pitime_2) 
        # delay(150*ns)
        # self.AI.AI1_pulse(self.pitime_1) 
        # delay(150*ns)
        # self.AI.AI2_pulse(self.pitime_2) 
        # delay(150*ns)
        # self.AI.AI1_pulse(self.pitime_1) 
        
        
        #self.Bragg.set_AOM_attens([("Dipole",self.Bragg.atten_Dipole )])

        
        #self.Bragg.set_AOM_attens([("Dipole",30.0)])

        
        #self.AI.pulse(0.25*us, self.AI_arm1_dds) #pi/2

    
        ### push
        #self.AI.push_pulse(self.MOTs.Push_pulse_time) #seperate for readout
        delay(self.MOTs.Delay_duration)

        self.Bragg.set_AOM_attens([("Dipole",self.Bragg.atten_Dipole )])
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
        
        
        
        
        
        
        # if self.N == -1:
        #     ### open
        #     self.AI.pulse(0.25*us, self.AI_arm1_dds) #pi/2
        #     delay(500*ns)        
            
        #     #delay(T)
            
        #     ### mirror 
        #     self.AI.pulse(self.pitime_1, self.AI_arm1_dds) #drive 3P0
        #     delay(150*ns)
            
        #     #delay(T)        
            
        #     ### close        
        #     with parallel:
        #         delay(500*ns)
        #         self.AI.switch_profile(1)
        #     self.AI.pulse(0.25*us, self.AI_arm1_dds) #pi/2
            
        # elif self.N ==-2:

        #     self.AI.pulse(0.48*us, self.AI_arm2_dds) #pi/2
        #     delay(500*ns)        
            
        #     #delay(T)
            
        #     ### mirror 
        #     self.AI.pulse(self.pitime_2, self.AI_arm2_dds) #drive 3P0
        #     delay(150*ns)
            
        #     #delay(T)        
            
        #     ### close        
        #     with parallel:
        #         delay(500*ns)
        #         self.AI.switch_profile(1)
        #     self.AI.pulse(0.48*us, self.AI_arm2_dds) #pi/2
            
        # else:
        #     self.AI.pulse(0.25*us, self.AI_arm1_dds) #pi/2
        #     delay(500*ns)   
            
        #     ### accel
        #     # for _ in range(int(self.N)):
        #     #     self.AI.pulse(self.pitime_2, self.AI_arm2_dds) 
        #     #     delay(150*ns)
        #     #     self.AI.pulse(self.pitime_1, self.AI_arm1_dds) 
        #     #     delay(150*ns)
        #     self.AI.pulse(self.pitime_2, self.AI_arm2_dds) 
        #     delay(150*ns)
        #     self.AI.pulse(self.pitime_1, self.AI_arm1_dds) 
        #     delay(150*ns)
        #     # self.AI.pulse(self.pitime_2, self.AI_arm2_dds)
        #     # delay(150*ns)
            
        #     #delay(T)
            
        #     ### mirror 
        #     # for _ in range(int(2*self.N+1)):
        #     #     self.AI.pulse(self.pitime_2, self.AI_arm2_dds) 
        #     #     delay(150*ns)
        #     #     self.AI.pulse(self.pitime_1, self.AI_arm1_dds)
        #     #     delay(150*ns)
        #     # self.AI.pulse(self.pitime_2, self.AI_arm2_dds) 
        #     # delay(150*ns)
            
        #     # self.AI.pulse(self.pitime_2, self.AI_arm2_dds)
        #     # delay(150*ns)
        #     self.AI.pulse(self.pitime_1, self.AI_arm1_dds) 
        #     delay(150*ns)
        #     self.AI.pulse(self.pitime_2, self.AI_arm2_dds)
        #     delay(150*ns)
        #     self.AI.pulse(self.pitime_1, self.AI_arm1_dds) 
        #     delay(150*ns)
        #     self.AI.pulse(self.pitime_2, self.AI_arm2_dds)
        #     delay(150*ns)
        #     self.AI.pulse(self.pitime_1, self.AI_arm1_dds) 
        #     delay(150*ns)
        #     # self.AI.pulse(self.pitime_2, self.AI_arm2_dds)
        #     # delay(150*ns)
            
        #     #delay(T)        
    
        #     ### decel
        #     # for _ in range(int(self.N)):
        #     #     self.AI.pulse(self.pitime_2, self.AI_arm2_dds) #drive 3P0
        #     #     delay(150*ns)
        #     #     self.AI.pulse(self.pitime_1, self.AI_arm1_dds) #drive 3P0
        #     #     delay(150*ns)
        #     # self.AI.pulse(self.pitime_2, self.AI_arm2_dds) #drive 3P0
        #     # delay(150*ns)
        #     self.AI.pulse(self.pitime_1, self.AI_arm1_dds) 
        #     delay(150*ns)
        #     self.AI.pulse(self.pitime_2, self.AI_arm2_dds)
        #     delay(150*ns)
            
            
        #     ### close        
        #     with parallel:
        #         delay(500*ns)
        #         self.AI.switch_profile(1)
        #     self.AI.pulse(0.25*us, self.AI_arm1_dds) #pi/2
        
        
        
            
    
    def after_fit(self, fit_name, valid, saved, model):
        self.set_dataset('current_scan.plots.error', model.errors, broadcast=True, persist=True)

    def pulse_N(self, N, start_arm, times):        
        for i in range(N):
            arm_num = (i+start_arm)%2
            self.AI.pulse(times[arm_num], self.arms[arm_num]) #drive 3P0
            delay(150*ns)
            
        