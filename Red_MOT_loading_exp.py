# -*- coding: utf-8 -*-
"""
Created on Tue Feb 15 21:19:34 2022

@author: sr
"""



from artiq.experiment import *
import numpy as np    
from Detection import *
from MOTcoils import* 
from ZotinoRampClass import *
from Beamline461Class import*
#from Beamline689Class import*
from HCDL import* 

class Red_MOT_loading(EnvExperiment):
    
    def build(self): 
        self.setattr_device("core")
        self.setattr_device("ttl5")
        self.setattr_device("ttl7")
        self.Detect=Detection(self)
        self.MC=MOTcoils(self)
        self.BB=Beamline461(self)
        #self.BR=Beamline689(self)
        #self.Zot = ZotinoRamp(self)
        
        # MOTdriver parameters
        self.setattr_argument("Red_pulse_duration",NumberValue(200.0*1e-3,min=0.0*1e-3,max=300.0*1e-3,scale = 1e-3,
                      unit="ms"),"MOT coil driver")
        
        self.setattr_argument("Bottom_current_amplitude",NumberValue(0.0,min=0.0,max=3.00,
                      unit="A"),"MOT coil driver")
        
        self.setattr_argument("Bottom_delay",NumberValue(0.0,min=0.0,max=100*1e-3,scale = 1e-3,
                      unit="ms"),"MOT coil driver")
        
        self.setattr_argument("Red_current_amplitude",NumberValue(0.0,min=0.0,max=3.00,
                      unit="A"),"MOT coil driver")
       
        #self.setattr_argument("Lin_ramp_time",NumberValue(100.0*1e-3,min=0,max=1000.00*1e-3,scale = 1e-3,
        #              unit="ms"),"MOT coil driver")
        
        self.setattr_argument("Delay_duration",
            Scannable(default=[RangeScan(0.0*1e-3, 500.0*1e-3, 20, randomize=False),NoScan(0.0)],scale=1e-3,
                      unit="ms"),"Loading")
        
        self.setattr_argument("Background_subtract",BooleanValue(False),"Loading")
            
        if not hasattr(self.Delay_duration,'sequence'):
            self.x=np.array([0,0])
        else:
            self.x=self.Delay_duration.sequence
        self.y=np.full(len(self.x), np.nan) # Prepare result array
    
        
    def prepare(self):  
        
        # Prepare MOT pulse shape
        self.MC.Blackman_pulse_profile()
        #self.Zot.Linear_ramp_profile()
        # Set AOM attenuations
        self.BB.set_atten()
        #self.BR.set_atten()
       
        # Initialize camera
        self.Detect.camera_init()
        self.Detect.disarm()

        
    @kernel    
    def run(self):
        self.core.reset()
        self.MC.init_DAC()
        self.BB.init_aoms()
        #self.BR.init_aoms()
        
        delay(10*ms)
        self.ttl5.off()
        delay(10*ms)
        self.ttl7.on()
        delay(10*ms)
        
        Lin_ramp_time = 50*ms
        
        #self.MC.Set_current(self.MC.Current_amplitude)
        
        # Prepare datasets
        
        # Camera output datasets
        self.Detect.prep_datasets(self.y)
        self.set_dataset("time_delay", self.x, broadcast=True)
        
        # Main loop
        for ii in range(len(self.x)):
            self.Detect.arm()
            
            delay(500*ms)
            #turn of broadband sweep for 689nm
            self.ttl5.on()
            
            delay(10*ms)
            
            # BACKGROUND IMAGE SEQUENCE
            if self.Background_subtract:
                self.Detect.trigger_camera()    # Trigger camera 
                delay(self.Detect.Exposure_Time)
                self.Detect.acquire()     # Acquire images
                self.Detect.transfer_background_image(ii)
            delay(300*ms)
            ############################
            
            
            delay(10*ms)
            
            #prepare for detection image
            self.Detect.arm()
            delay(50*ms)

            #self.BB.shift_MOT2D_aom_frequency(25.0)                  # Shift 2D MOT frequency
            #delay(1*ms)
            self.BB.reinit_MOT3DDP_aom(self.BB.MOT3DDP_iatten, self.BB.f_MOT3D_load)  # Set 3D MOT frequency for loading
            delay(1*ms)
            self.BB.MOT_on()

            
            self.MC.Blackman_ramp_up()
            self.BB.shift_MOT2D_aom_frequency(0.0)                # Turn on atom beam
            self.MC.flat()

            with parallel:
                # turn off atom beam
                self.BB.shift_MOT2D_aom_frequency(25.0)
                #turn off 3D Mot
                self.BB.MOT_off()
            
            #ramp down Blue mot coils
            #self.MC.Set_current(self.Bottom_current_amplitude)
            self.MC.Set_current(self.Bottom_current_amplitude)
            
            #turn on red bean in broadband mode
            self.ttl7.off()


            delay(self.Bottom_delay)
            #delay(self.x[ii])  # Delay duration
            self.BB.set_MOT3DDP_aom_frequency(self.BB.f_MOT3D_detect) # Set 3D MOT frequency for detection
            self.BB.set_MOT3DDP_aom_atten(11.0)
            
            self.MC.Linear_ramp(self.Bottom_current_amplitude,self.Red_current_amplitude,Lin_ramp_time)
            
            # IMAGING SEQUENCE
            #delay(self.x[ii])  # Delay duration 
            #self.Detect.arm()
            #self.BB.set_MOT3DDP_aom_frequency(self.BB.f_MOT3D_detect) # Set 3D MOT frequency for detection
            #self.BB.set_MOT3DDP_aom_atten(11.0)
            with parallel:
                self.BB.MOT_on()
                self.Detect.trigger_camera()  # Trigger camera
            delay(self.Detect.Exposure_Time)
            self.BB.MOT_off()
            #delay(5*ms)
            ###########################
            
            # swith 689 to single frequency
            self.ttl5.off()
           
            #self.BR.set_Red_MOT_aom_frequency(self.BR.Red_MOT_AOM_frequency.sequence[0])
            delay(self.Red_pulse_duration)
            
            #self.MC.Blackman_ramp_down_from_to(self.Red_current_amplitude,0.0)
            self.MC.Set_current(0.0)
            
            # turn off 689 light
            self.ttl7.on()
            
            self.Detect.acquire()                                # Acquire images
            self.Detect.transfer_image_background_subtracted(ii)
            self.Detect.disarm() 
          
            self.mutate_dataset("time_delay",ii,self.x[ii])
            self.mutate_dataset("detection.index",ii,ii)
           
           
        delay(500*ms)   
        self.MC.Zero_current()  