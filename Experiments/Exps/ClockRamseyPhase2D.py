# -*- coding: utf-8 -*-
"""
Created on Tue Jan 21 13:37:31 2025

@author: sr
"""

from scan_framework import Scan2D
from artiq.experiment import *
import numpy as np
import pyvisa



from CoolingClass import _Cooling
from CameraClass import _Camera

from StateControlClass import _state_control
from BraggClass import _Bragg

from repository.models.scan_models import RamseyPhaseModel
from repository.models.scan_models import RamseyDecayModel


class ClockRamseyPhase2D_exp(Scan2D, EnvExperiment):
    
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
        
        self.ind = 1
        self.ramsey_phase_exp = 0.0*1e-6
        self.delay_exp = 0.0*1e-6

        self.setattr_argument('pulse_phase',
            Scannable(default=RangeScan(
            start=0.0,
            stop=2.0,
            npoints=20),
            scale=1,
            ndecimals=2,
            unit="Turns", ), 'Params')
        
        self.setattr_argument('delay', Scannable(
            default=RangeScan(
                start=0.0,
                stop=100.0e-6,
                npoints=20
            ),
            scale=1e-6,
            ndecimals=2,
            unit="us"
        ), group='Ramsey')
        
        self.scan_arguments(nbins={'default':1000},
                    nrepeats={'default':1},
                    npasses={'default':1},
                    fit_options={'default':"No Fits"})
        
        self.setattr_argument("dipole_load_time", NumberValue(40.0*1e-3,min=0.0*1e-3,max=9000.00*1e-3,scale=1e-3,
                      unit="ms"),"Params")
        
        self.setattr_argument("pi_2_time689", NumberValue(1.0*1e-6,min=0.0*1e-6,max=1000.00*1e-6,scale=1e-6,ndecimals=3,
                      unit="us"),"Params")
        self.setattr_argument("pi_time689", NumberValue(1.0*1e-6,min=0.0*1e-6,max=1000.00*1e-6,scale=1e-6,ndecimals=3,
                      unit="us"),"Params")
        self.setattr_argument("pi_timeRaman", NumberValue(1.0*1e-6,min=0.0*1e-6,max=1000.00*1e-6,scale=1e-6,ndecimals=3,
                      unit="us"),"Params")
        self.setattr_argument("pi_2_timeRaman", NumberValue(1.0*1e-6,min=0.0*1e-6,max=1000.00*1e-6,scale=1e-6,ndecimals=3,
                      unit="us"),"Params")
        self.setattr_argument("Ramsey_time", NumberValue(10.0*1e-6,min=0.0*1e-6,max=1000.00*1e-6,scale=1e-6,
                      unit="us"),"Params")
        
        self.setattr_argument("excited_state", EnumerationValue(['3P1', '3P0'], default='3P1'), "Params")
        self.setattr_argument("readout_scheme", EnumerationValue(["0","1","2"], default="0"), "Params")
        self.setattr_argument("B_field", NumberValue(0.21,min=0.0,max=2,scale=1,
                      unit="V", ndecimals=3),"Params")
        
        self.setattr_argument("Echo",BooleanValue(False),"Ramsey")
        self.setattr_argument("cavity_clear",BooleanValue(False),"Params")
        self.setattr_argument("free_space",BooleanValue(False),"Params")

        self.t0 = np.int64(0)
        self.FIX_DELAY_TIME = 150*ns
        self.scan0 = 0
        self.scan1 = 0
        
    def get_scan_points(self):
        return [self.delay, self.pulse_phase]  
    
    @kernel
    def set_scan_point(self, i_point, point):
        self.ramsey_phase_exp = point[1]
        self.delay_exp = point[0]
        self.core.break_realtime()
        
    def prepare(self):
        #prepare/initialize mot hardware and camera
        self.MOTs.prepare_aoms()
        self.Bragg.prepare_aoms()
        self.State_Control.prepare_aoms()
        
        self.MOTs.prepare_coils()
        
        self.Camera.camera_init(scheme = 0)
        
        
        self.enable_histograms = True
        self.model1 = RamseyDecayModel(self)
        self.model2 = RamseyPhaseModel(self)
        self.register_model(self.model1, dimension=0, fit=True, set=True)
        self.register_model(self.model2, dimension=1, fit=True, set=True, measurement=True)
        
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
    def measure(self, point):        
        
        
        #prepare
        self.core.wait_until_mu(now_mu())
        self.core.reset()
        

        self.MOTs.init_rmot_dds(self.MOTs.rmot_freq_i, self.MOTs.rmot_freq_f,  self.MOTs.rmot_freq_depth_i, self.MOTs.rmot_freq_depth_f, self.MOTs.freq_3D_red)

        delay(1*ms)
        self.core.break_realtime()
        delay(10*ms)

        self.MOTs.AOMs_off_all()
        self.State_Control.AOMs_off_all()               
        delay(200*ms)

        self.set_phases(point)
        delay(10*ms)
        
        # generate red mot
        self.MOTs.close_688() # close 688 shutter to prevent leakage from optical pumping
        delay(10*ms)

        self.MOTs.rMOT_pulse_new()
        self.MOTs.open_688() # open shutter after 689 rMOT light turns off to be prepare for Raman pulse
        
        if self.MOTs.molasses:
               with parallel:
                   self.MOTs.set_current_dir(1) 
                   self.MOTs.molasses_pulse(freq=self.MOTs.molasses_frequency, amp=0.1, t = self.dipole_load_time)
        else:
            with parallel:
                delay(self.dipole_load_time) # Needs to by >~ 40 ms for cavity shaking to stop.
                self.MOTs.set_current_dir(1) # let MOT field go to zero and switch H-bridge, 5ms
        
        self.MOTs.Blackman_ramp(0.0, self.B_field, 20*ms) # set bias field so 3P1 m=+1 is ~40MHz separated.    
        delay(5*ms) # extra time for field to settle
            

        if self.free_space:
            self.Bragg.aom_dipole.set_att(30.0)
            self.Bragg.aom_lattice.sw.off()
        
        delay(100*us)
        
        # -----  3P1 EXCITATION -----------------------
        if self.excited_state=='3P1':
            self.ttl5.on()       # for triggering start
            self.State_Control.pulse_689(self.pi_2_time689)
            if self.Echo:
                delay(self.delay_exp)
                self.State_Control.pulse_689(self.pi_time689)
            
            with parallel:
                #delay(1.2*us) # ensures the profile has enough time to switch
                delay(self.delay_exp+1.2*us)
                #delay(self.delay_exp*point[1]+1.2*us)
                self.State_Control.switch_profile(1)
            self.State_Control.pulse_689(self.pi_2_time689)
            self.ttl5.off()
        
            self.readout(scheme="0")

            

        

        # -----  3P0 EXCITATION -----------------------
        elif self.excited_state=='3P0':
            if self.cavity_clear:
                # prepare in 3P0
                self.ttl5.on()       # for triggering start
                self.State_Control.pulse_689(self.pi_time689)
                delay(0.15*us)
                with parallel:
                    self.State_Control.pulse_679(self.pi_timeRaman)
                    self.State_Control.pulse_688(self.pi_timeRaman)
                # clear cavity
                self.State_Control.cav_clear_pulse(2.5*ms)
                
                # Rabi flop from 3P0
                with parallel:
                    self.State_Control.pulse_679(self.pi_2_timeRaman)
                    self.State_Control.pulse_688(self.pi_2_timeRaman)
                delay(0.3*us)
                self.State_Control.pulse_689(self.pi_time689)
                
                if self.Echo:
                    #delay(500*us)
                    #delay(self.delay_exp)
                    delay(self.delay_exp*point[1])
                    
                    ### Procedure 1
                    self.State_Control.pulse_689(self.pi_time689)
                    delay(0.1*us)
                    with parallel:
                        self.State_Control.pulse_688(self.pi_timeRaman)
                        self.State_Control.pulse_679(self.pi_timeRaman)
                    delay(0.25*us)
                    self.State_Control.pulse_689(self.pi_time689)
                    
                    
                with parallel:
                    #delay(1.2*us) # ensures the profile has enough time to switch
                    delay(self.delay_exp+1.2*us)
                    #delay(self.delay_exp*point[1]+1.2*us)
                    self.State_Control.switch_profile(1)
                self.State_Control.pulse_689(self.pi_time689)
                delay(0.15*us)
                with parallel:
                    self.State_Control.pulse_679(self.pi_2_timeRaman)
                    self.State_Control.pulse_688(self.pi_2_timeRaman)

                # with parallel:
                #     self.State_Control.pulse_679(self.pi_timeRaman)
                #     self.State_Control.pulse_688(self.pi_timeRaman)
                # delay(0.3*us)
                # self.State_Control.pulse_689(self.pi_2_time689)
                
                
                
                

            
                
            else:    
                self.ttl5.on()       # for triggering start
                
                self.State_Control.pulse_689(self.pi_2_time689)
                delay(0.15*us)
                with parallel:
                    self.State_Control.pulse_688(self.pi_timeRaman)
                    self.State_Control.pulse_679(self.pi_timeRaman)
                    
                if self.Echo:
                    #delay(500*us)
                    delay(self.delay_exp+1.2*us)
                    #delay(self.delay_exp*point[1])
                    
                    ## Procedure 1
                    # self.State_Control.pulse_689(self.pi_time689)
                    # delay(0.15*us)
                    # with parallel:
                    #     self.State_Control.pulse_688(self.pi_timeRaman)
                    #     self.State_Control.pulse_679(self.pi_timeRaman)
                    # delay(0.35*us)
                    # self.State_Control.pulse_689(self.pi_time689)
                    
                    ### Procedure 2
                    with parallel:
                        self.State_Control.pulse_688(self.pi_timeRaman)
                        self.State_Control.pulse_679(self.pi_timeRaman)
                    delay(0.35*us)
                    self.State_Control.pulse_689(self.pi_time689)
                    delay(0.15*us)
                    with parallel:
                        self.State_Control.pulse_688(self.pi_timeRaman)
                        self.State_Control.pulse_679(self.pi_timeRaman)
                    
                with parallel:
                    #delay(1.2*us) # ensures the profile has enough time to switch
                    delay(self.delay_exp+1.2*us)
                    #delay(self.delay_exp*point[1]+1.2*us)
                    self.State_Control.switch_profile(1)
                with parallel:
                    self.State_Control.pulse_688(self.pi_timeRaman)
                    self.State_Control.pulse_679(self.pi_timeRaman)
                delay(0.35*us)
                self.State_Control.pulse_689(self.pi_2_time689)
            
            
            self.ttl5.off()

            self.readout(scheme=self.readout_scheme)
       
                
                
                
        else:
            raise Exception('Not Valid State')

        
        self.Bragg.aom_dipole.set_att(self.Bragg.atten_Dipole)
        self.Bragg.aom_lattice.sw.on()
        # image and reset for next shot
        self.MOTs.take_MOT_image(self.Camera)  
        delay(15*ms)
        
        self.MOTs.set_current(0.0)
        delay(20*ms)
        self.MOTs.set_current_dir(0)
        delay(5*ms)  
        
        #process and output
        self.MOTs.AOMs_on_all() # just keeps AOMs warm

        self.Camera.process_image(save=True, name='', bg_sub=True)

        delay(400*ms)
         
        self.ind += 1
        val = self.Camera.get_push_stats()
        self.write_val(val)
        return val
        #return self.Camera.get_push_stats()
        
 
    
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
            self.State_Control.push_pulse(self.MOTs.Push_pulse_time)
            delay(10*us)
            with parallel:
                    self.State_Control.pulse_688(self.pi_timeRaman)
                    self.State_Control.pulse_679(self.pi_timeRaman)

            delay(200*us)
            
            delay(self.MOTs.Delay_duration)
        else:
            raise Exception("Not a valid readout scheme...")
            
            
            
    @kernel
    def raman_pulse(self, time):
        self.State_Control.aom_688.sw.on()
        delay(0.1*us)
        self.State_Control.aom_679.sw.on()
        
        
        delay(time)
        
        
        self.State_Control.aom_688.sw.off()
        delay(0.07*us)
        self.State_Control.aom_679.sw.on()
                
    @kernel
    def set_phases(self, point):

        self.State_Control.set_AOM_phase(0, self.State_Control.freq_688, 0.0, self.t0, 0)
        self.State_Control.set_AOM_phase(0, self.State_Control.freq_688, 0.0, self.t0, 1)

        #
        self.State_Control.set_AOM_phase(1, self.State_Control.freq_Push, 0.0, self.t0, 0)
        self.State_Control.set_AOM_phase(1, self.State_Control.freq_Push, 0.0, self.t0, 1)


        self.State_Control.set_AOM_phase(2, self.State_Control.freq_679, 0.0, self.t0, 0)
        self.State_Control.set_AOM_phase(2, self.State_Control.freq_679, 0.0, self.t0, 1)


        self.State_Control.set_AOM_phase(3, self.State_Control.freq_689, 0.0, self.t0, 0)
        self.State_Control.set_AOM_phase(3, self.State_Control.freq_689, point[1], self.t0, 1)

        
        self.State_Control.switch_profile(0)
        
    def calculate_dim0(self, dim1_model):
        param = 2*dim1_model.fit.params.A
        # weight final fit by error in this dimension 1 fit param
        error = dim1_model.fit.errs.A_err
        self.set_dataset(f"ContrastMeasurement__{self.scan1}", param, broadcast=False)
        self.scan1 += 1
        return param, error
    
    def write_val(self, val):
        self.set_dataset(f"PhaseMeasurement_{self.scan0}_{self.scan1}", val, broadcast=False)
        self.scan0 += 1  
        
        