# -*- coding: utf-8 -*-
"""
Created on Tue Jan 21 13:37:31 2025

@author: sr
"""

from scan_framework import Scan1D, TimeFreqScan

from artiq.experiment import Scannable, RangeScan, EnumerationValue, BooleanValue, NumberValue, at_mu, sequential, s # pyright: ignore[reportMissingImports]
from artiq.experiment import kernel, EnvExperiment, kHz, delay, ms, parallel, us, MHz, now_mu, ns # pyright: ignore[reportMissingImports]

import numpy as np




from CoolingClass import _Cooling
from CameraClass import _Camera

from StateControlClass import _state_control
from BraggClass import _Bragg
from repository.models.scan_models import AI_Rabi_Model as myModel # pyright: ignore[reportMissingImports]


class ClockExcitationSimul_exp(Scan1D, TimeFreqScan, EnvExperiment):
    
    def build(self, **kwargs):
        # required initializations
        
        super().build(**kwargs)
        
        self.setattr_device("ttl5") # triggering pulse
        self.setattr_device("ttl1")
        # import classes for experiment control
        self.MOTs = _Cooling(self)
        self.Camera = _Camera(self)
        self.State_Control = _state_control(self)
        self.Bragg = _Bragg(self)
        
        self.enable_pausing = True # disable to speed up by not checking scheduler
        self.enable_auto_tracking=False
        self.enable_profiling = False # enable to print runtime statistics to find bottlenecks

        self.scan_arguments(times = {'start':0*us,'stop':1.5*us,'npoints':20,'unit':"us",'scale':us,'global_step':0.1*us,'ndecimals':4},
             frequencies={'start':-3*MHz,'stop':3*MHz,'npoints':50,'unit':"MHz",'scale':MHz,'global_step':0.1*MHz,'ndecimals':5},
            frequency_center={'default':100*MHz}, pulse_time= {'default':0*us},nbins = {'default':1000},nrepeats = {'default':1},npasses = {'default':1},fit_options = {'default': "No Fits"} )
        
        self.setattr_argument("dipole_load_time", NumberValue(60.0*1e-3,min=0.0*1e-3,max=9000.00*1e-3,scale=1e-3,
                      unit="ms"),"Params")
        
        self.setattr_argument("pi_time_689", NumberValue(0.15*1e-6,min=0.0*1e-6,max=1000.00*1e-6,scale=1e-6,ndecimals=3,
                      unit="us"),"Params")
        self.setattr_argument("pi_time_Raman", NumberValue(0.55*1e-6,min=0.0*1e-6,max=1000.00*1e-6,scale=1e-6,ndecimals=3,
                      unit="us"),"Params")
        
        self.setattr_argument("excited_state", EnumerationValue(['3P1', "3P0"], default='3P1'), "Params")
        self.setattr_argument("readout_scheme", EnumerationValue(["0","1","2"], default="0"), "Params")
        self.setattr_argument("cavity_clear",BooleanValue(False),"Params")
        self.setattr_argument("free_space",BooleanValue(False),"Params")
        self.setattr_argument("B_field", NumberValue(0.36,min=0.0,max=2,scale=1,
                      unit="V", ndecimals=3),"Params")
        
        self.ind=0
        
        
        
    def prepare(self):
        #prepare/initialize mot hardware and camera
        self.MOTs.prepare_aoms()
        self.Bragg.prepare_aoms()
        self.State_Control.prepare_aoms()
        
        self.MOTs.prepare_coils()
        
        self.Camera.camera_init(scheme = 0)
        
        
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
        self.State_Control.init_aoms(on=False)
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
        
        self.ttl5.off()

        self.MOTs.init_rmot_dds(self.MOTs.rmot_freq_i, self.MOTs.rmot_freq_f,  self.MOTs.rmot_freq_depth_i, self.MOTs.rmot_freq_depth_f, self.MOTs.freq_3D_red)

        delay(1*ms)
        
        self.core.break_realtime()
        delay(10*ms)

        
        self.MOTs.AOMs_off_all()
        self.State_Control.AOMs_off_all()
        delay(1*ms)
        
        # if self.ind%2==0:
        #     self.State_Control.set_AOM_freq_689(frequency-250*Hz, self.State_Control.scale_689)
        # else:
        #     self.State_Control.set_AOM_freq_689(frequency+250*Hz, self.State_Control.scale_689)
        # self.ind=self.ind+1
        
        # if self.ind%4==0:
        #     self.State_Control.set_AOM_freq_689(frequency-250*Hz, self.State_Control.scale_689)
        # elif self.ind%4==1:
        #     self.State_Control.set_AOM_freq_689(frequency, self.State_Control.scale_689)
        # elif self.ind%4==2:
        #     self.State_Control.set_AOM_freq_689(frequency+250*Hz, self.State_Control.scale_689)
        # else:
        #     self.State_Control.set_AOM_freq_689(frequency+1*MHz, self.State_Control.scale_689)
        # self.ind=self.ind+1
        
        self.State_Control.set_AOM_freq_689(frequency, self.State_Control.scale_689)
        self.State_Control.set_AOM_freq_688(self.State_Control.freq_688, self.State_Control.scale_688)
        self.State_Control.set_AOM_freq_679(self.State_Control.freq_679, self.State_Control.scale_679)
        
        
        # generate red mot
        self.MOTs.close_688() # turn off 688 nm
        self.MOTs.rMOT_pulse_new()
        
        # self.Bragg.aom_dipole.set_att(15.0)
        # self.Bragg.aom_lattice.set_att(30.0)
        
        # # generate red mot
        # self.MOTs.rMOT_pulse_new(dipole_on=False)
        
        # self.Bragg.aom_dipole.set_att(self.Bragg.atten_Dipole)     
        # self.Bragg.aom_lattice.set_att(3.0)
        # load into dipole trap and perform molasses (if selected)
        # Total time for this sequence needs to be >~ 40 ms for cavity shaking to stop.
        with parallel:
            delay(self.dipole_load_time/3) 
            self.MOTs.set_current_dir(1) # let MOT field go to zero and switch H-bridge, 15ms        
        if self.MOTs.molasses:
            self.MOTs.molasses_pulse(freq=self.MOTs.molasses_frequency, amp=0.1, t=self.dipole_load_time/3)
        else:
            delay(self.dipole_load_time/3)
        self.MOTs.Blackman_ramp(0.0, self.B_field,self.dipole_load_time/3) # set bias field so 3P1 m=+1 is ~40MHz separated.
        with parallel:
            self.MOTs.open_688() # turn off 688 nm
            delay(5*ms)
        
        # self.Bragg.aom_dipole.set_att(30.0) # turn off dipole
        # self.Bragg.aom_lattice.sw.off() #turn off lattice
        #delay(2*ms)
        
        # focus for variable time
        # self.Bragg.aom_dipole.set_att(self.Bragg.atten_Dipole) # turn off dipole
        #delay(1.25*ms)
        
            
        if self.free_space:
            self.Bragg.aom_dipole.set_att(30.0 )
            self.Bragg.aom_lattice.sw.off()
        delay(150*us)
        
        
        # ######## CHEAP RAMSEY FREQUENCY SCAN ###########
        # self.ttl5.on()       # for triggering start
        # self.State_Control.pulse_689(self.pi_time_689/2)
        # delay(0.15*us)
        # with parallel:
        #     self.State_Control.pulse_679(self.pi_time_Raman)
        #     self.State_Control.pulse_688(self.pi_time_Raman)
        
        # delay(0.1*ms)
        # with parallel:
        #     self.State_Control.pulse_679(self.pi_time_Raman)
        #     self.State_Control.pulse_688(self.pi_time_Raman)
        # delay(0.35*us)
        # self.State_Control.pulse_689(self.pi_time_689/2)

        # self.ttl5.off()
        # self.readout(scheme=self.readout_scheme)
        # ##############################
        

        # experiment        
        # -----  3P1 EXCITATION -----------------------
        if self.excited_state=='3P1':
            self.ttl5.on() 
            self.State_Control.pulse_689(time)

            self.readout(scheme="0")
            self.ttl5.off()


        # -----  3P0 EXCITATION -----------------------
        elif self.excited_state=='3P0':

            self.ttl5.on()       # for triggering start

            # with parallel:
            #     self.State_Control.pulse_679(time)
            #     self.State_Control.pulse_688(time)
            #     with sequential:
            #         delay(170*ns)
            #         self.State_Control.pulse_689(time)
            delay(3000*us)
            with parallel:
                self.State_Control.pulse_679(time)
                self.State_Control.pulse_688(time)
                with sequential:
                    delay(90*ns)
                    self.State_Control.pulse_689(time)
                
                
             ################# RAMSEY TIME SCAN #####################  
            # with parallel:
            #     self.State_Control.pulse_679(self.pi_time_Raman+400*ns)
            #     self.State_Control.pulse_688(self.pi_time_Raman+400*ns)
            #     with sequential:
            #         delay(370*ns)
            #         self.State_Control.pulse_689(self.pi_time_Raman)
                    
            # delay(time)
                    
            # with parallel:
            #     self.State_Control.pulse_679(self.pi_time_Raman+400*ns)
            #     self.State_Control.pulse_688(self.pi_time_Raman+400*ns)
            #     with sequential:
            #         delay(370*ns)
            #         self.State_Control.pulse_689(self.pi_time_Raman)
                
            self.ttl5.off()
            self.readout(scheme=self.readout_scheme)


        
        
        
        # image and reset for next shot
        self.MOTs.take_MOT_image(self.Camera)  
        self.Bragg.aom_dipole.set_att(self.Bragg.atten_Dipole)
        self.Bragg.aom_lattice.sw.on()
        delay(15*ms)
        
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
    def readout(self, scheme):
        """
        reading out ports
        scheme 0 seperates 1S0 and 3P1, leaves metastable states dark
        scheme 1 seperates 1S0 and 3P1 and 3P1/2
        scheme 2 seperates 1S0+3P1 and 3P2 and 3P0
            note there is mixing of metstable ports in scheme 2

        """
        if scheme == "0":
            self.State_Control.push_pulse(self.MOTs.Push_pulse_time)            
            self.MOTs.aom_3P0.sw.on()
            self.MOTs.aom_3P2.sw.on()
            delay(self.MOTs.Delay_duration)
            self.MOTs.aom_3P0.sw.off()
            self.MOTs.aom_3P2.sw.off()

        elif scheme == "1":
            self.State_Control.push_pulse(self.MOTs.Push_pulse_time)
            delay(200*us)
            self.State_Control.push_pulse(self.MOTs.Push_pulse_time)
            delay(5*us)
            
            self.MOTs.aom_3P0.sw.on()
            self.MOTs.aom_3P2.sw.on()
            delay(self.MOTs.Delay_duration)
            self.MOTs.aom_3P0.sw.off()
            self.MOTs.aom_3P2.sw.off()
            
        elif scheme == "2": #readout with 3P2 port
            delay(200*us)
            self.State_Control.push_pulse(self.MOTs.Push_pulse_time)

            self.MOTs.aom_3P2.sw.on()
            delay(200*us)
            self.MOTs.aom_3P2.sw.off()
            
            delay(200*us)
            self.State_Control.push_pulse(self.MOTs.Push_pulse_time)
            delay(5*us)
            
            self.MOTs.aom_3P0.sw.on()
            self.MOTs.aom_3P2.sw.on()
            delay(self.MOTs.Delay_duration)
            self.MOTs.aom_3P0.sw.off()
            self.MOTs.aom_3P2.sw.off()
            
        elif scheme == "3": #readout without repumpers
            self.State_Control.set_AOM_freq_679(self.State_Control.freq_679, self.State_Control.scale_679)
            delay(100*us)
            self.State_Control.push_pulse(self.MOTs.Push_pulse_time)
            with parallel:
                    self.State_Control.pulse_688(self.pi_time_Raman)
                    self.State_Control.pulse_679(self.pi_time_Raman)

            delay(200*us)
            
            delay(self.MOTs.Delay_duration)
        else:
            raise Exception("Not a valid readout scheme...")
            
            
        
                
    @kernel
    def after_scan(self):
        self.core.reset()
        delay(50*ms)
        for i in range(3):
            self.MOTs.urukul_channels[i].sw.on()
        self.MOTs.atom_source_on()    
  