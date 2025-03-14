# -*- coding: utf-8 -*-
"""
Created on Mon Dec  9 16:04:54 2024

@author: sr
"""


from scan_framework import Scan1D, TimeScan
from artiq.experiment import *
import numpy as np



from ClockAIClass import _ClockAI
from repository.models.scan_models import RabiModel

class ClockAI_phase_test(Scan1D, EnvExperiment):
    
    def build(self, **kwargs):
        # required initializations
        
        super().build(**kwargs)
        
        # import classes for experiment control

        self.AI = _ClockAI(self)
        
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
                      unit="us"),"Params")
        self.setattr_argument("pitime_2", NumberValue(0.5*1e-6,min=0.0*1e-6,max=10*1e-6,scale=1e-6,
                      unit="us"),"Params")
        
        self.setattr_argument("pi_2_time_1", NumberValue(0.25*1e-6,min=0.0*1e-6,max=10*1e-6,scale=1e-6,
                      unit="us"),"Params")
        self.setattr_argument("pi_2_time_2", NumberValue(0.25*1e-6,min=0.0*1e-6,max=10*1e-6,scale=1e-6,
                      unit="us"),"Params")
        
        self.setattr_argument("N", NumberValue(0,min=-2,max=100,scale=1),"Params")
        self.setattr_argument("start_arm", NumberValue(0,min=0,max=1,scale=1),"Params")
        
        self.setattr_argument("pi_2_delay_time", NumberValue(0.5*1e-6,min=0.0*1e-6,max=10*1e-6,scale=1e-6,
                      unit="us"),"Params")
        
        

        self.t0 = np.int64(0)
    def get_scan_points(self):
        return self.pulse_phase    
        
    def prepare(self):
        #prepare/initialize mot hardware and camera

        self.AI.prepare_aoms()
        
        self.AI_arm1_dds = self.AI.urukul_channels[2] # indexes into urukul ch array 
        self.AI_arm2_dds = self.AI.urukul_channels[3] # indexes into urukul ch array 
        
        
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
        self.AI.init_aoms(on=False)
         
                   

    @kernel
    def measure(self, point):        
        
        #prepare
        self.core.wait_until_mu(now_mu())
        self.core.reset()
        delay(100*ms)
        self.t0 = now_mu()
        
        
        self.AI.ttl7.on()
        
        self.AI.AI1_pulse(0.5*us)
        delay(100*ns)
        self.AI.AI2_pulse(1*us)
        delay(200*ns)
        self.AI.AI2_pulse(0.3*us)
        delay(500*ns)
        self.AI.AI1_pulse(0.5*us)
        
        self.AI.ttl7.off()
        
        # sets the phase for everything, 
        # self.AI.set_AOM_phase('Unused', self.AI.freq_Unused, 0.0, self.t0, 0)
        # self.AI.set_AOM_phase('Unused', self.AI.freq_Unused, 0.0, self.t0, 1)

        # #
        # self.AI.set_AOM_phase('Push', self.AI.freq_Push, 0.0, self.t0, 0)
        # self.AI.set_AOM_phase('Push', self.AI.freq_Push, 0.0, self.t0, 1)


        # self.AI.set_AOM_phase('AI1', self.AI.freq_AI1, 0.0, self.t0, 0)
        # self.AI.set_AOM_phase('AI1', self.AI.freq_AI1, 0.5, self.t0, 1)


        # self.AI.set_AOM_phase('AI2', self.AI.freq_AI2, 0.0, self.t0, 0)
        # if self.N < 0:
        #     self.AI.set_AOM_phase('AI2', self.AI.freq_AI2, 0.5, self.t0, 1)
        # else:
        #     self.AI.set_AOM_phase('AI2', self.AI.freq_AI2, 0.0, self.t0, 1)
        
        # self.AI.switch_profile(0)
        
        
        
        
        # self.AI.ttl7.on()
        # # open
        # # self.AI.pulse(self.pi_2_time_1, self.AI_arm1_dds) #pi/2  
        # # delay(-350*ns)
        # self.AI.pulse(self.pi_2_time_1, self.AI_arm2_dds) #pi/2
        # # self.AI.pulse(self.pi_2_time_1, self.AI_arm1_dds) #pi/2  
        # # self.AI.pulse(self.pi_2_time_1, self.AI_arm2_dds) #pi/2
        
            
        # ### close        
        # with parallel:
        #     delay(500*ns)
        #     # self.AI.switch_profile(1)
        # self.AI.pulse(self.pi_2_time_1, self.AI_arm1_dds) #pi/2
        # self.AI.pulse(self.pi_2_time_1, self.AI_arm2_dds) #pi/2
            
       
        # delay(300*ms)
        # self.AI.ttl7.off()
        
        return 0
        
  
    
    def after_fit(self, fit_name, valid, saved, model):
        self.set_dataset('current_scan.plots.error', model.errors, broadcast=True, persist=True)


        