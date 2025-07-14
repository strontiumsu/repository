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

from StateControlClass import _STATE_CONTROL
from BraggClass import _Bragg
from AWG import WaveformGenerator
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
        self.State_Control = _STATE_CONTROL(self)
        self.Bragg = _Bragg(self)
        
        self.rigol=None
        self.wg = WaveformGenerator()
        
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
        
        self.setattr_argument("dipole_load_time", NumberValue(20.0*1e-3,min=0.0*1e-3,max=9000.00*1e-3,scale=1e-3,
                      unit="ms"),"Params")
        
        self.setattr_argument("pi_2_time689", NumberValue(1.0*1e-6,min=0.0*1e-6,max=1000.00*1e-6,scale=1e-6,ndecimals=3,
                      unit="us"),"Params")
        self.setattr_argument("pi_time689", NumberValue(1.0*1e-6,min=0.0*1e-6,max=1000.00*1e-6,scale=1e-6,ndecimals=3,
                      unit="us"),"Params")
        self.setattr_argument("pi_timeRaman", NumberValue(1.0*1e-6,min=0.0*1e-6,max=1000.00*1e-6,scale=1e-6,ndecimals=3,
                      unit="us"),"Params")
        self.setattr_argument("Ramsey_time", NumberValue(10.0*1e-6,min=0.0*1e-6,max=1000.00*1e-6,scale=1e-6,
                      unit="us"),"Params")
        
        self.setattr_argument("excited_state", EnumerationValue(['3P1', '3P0'], default='3P1'), "Params")
        self.setattr_argument("readout_scheme", EnumerationValue(["0","1","2"], default="0"), "Params")
        self.setattr_argument("B_field", NumberValue(0.88,min=0.0,max=2,scale=1,
                      unit="V", ndecimals=3),"Params")
        
        self.setattr_argument("Echo",BooleanValue(False),"Ramsey")
        
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
        
        self.Camera.camera_init()
        
        
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
        self.Bragg.init_aoms(on=True)
        
        delay(10*ms)
        
        #MOT Config
        self.MOTs.set_current_dir(0)
        delay(10*ms)
        
        self.MOTs.take_background_image_exp(self.Camera)
        
        # Warm up before exp
        delay(50*ms)
    
        
  
 
    @kernel
    def measure(self, point):        
        
        
        #prepare
        self.core.wait_until_mu(now_mu())
        self.core.reset()
        
        delay(10*ms)
        self.Camera.arm()
        delay(200*ms)

        

        
        self.MOTs.AOMs_off(self.MOTs.AOMs)
        self.State_Control.AOMs_off(self.State_Control.AOMs)
        delay(1*ms)
        self.State_Control.set_AOM_attens([("689", self.State_Control.atten_689),
                                           ("679", self.State_Control.atten_679),
                                           ("688", self.State_Control.atten_688)])
        delay(1*ms)

        
        # generate red mot
        self.MOTs.rMOT_pulse()
        
        # hold in dipole trap while changing MOT config
        self.t0 = now_mu()
        with parallel:
            delay(self.dipole_load_time)
            self.set_phases(point)
            with sequential:
                self.MOTs.set_current_dir(1) # XXX let MOT field go to zero and switch H-bridge, 5ms
                self.MOTs.set_current(self.B_field)
                #self.MOTs.set_current(time/(1*us))
                
        delay(1020*us) #??
        
        # experiment
        self.ttl5.on()       # for triggering start
        
    
        
        
        # -----  3P1 EXCITATION -----------------------
        if self.excited_state=='3P1':
            self.State_Control.pulse_689(self.pi_2_time689)
            if self.Echo:
                delay(self.delay_exp)
                self.State_Control.pulse_689(self.pi_time689)
            
            with parallel:
                #delay(1.2*us) # ensures the profile has enough time to switch
                #delay(self.delay_exp)
                delay(self.delay_exp*point[1]+1.2*us)
                #self.State_Control.switch_profile(1)
            self.State_Control.pulse_689(self.pi_2_time689)
            self.ttl5.off()
        
            self.readout(scheme="0")

            



        # -----  3P0 EXCITATION -----------------------
        elif self.excited_state=='3P0':
            self.State_Control.pulse_689(self.pi_2_time689)
            delay(0.1*us)
            with parallel:
                self.State_Control.pulse_688(self.pi_timeRaman)
                self.State_Control.pulse_679(self.pi_timeRaman)
                
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
                
                ### Procedure 2
                # with parallel:
                #     self.State_Control.pulse_688(self.pi_timeRaman)
                #     self.State_Control.pulse_679(self.pi_timeRaman)
                # delay(0.25*us)
                # self.State_Control.pulse_689(self.pi_time689)
                # delay(0.1*us)
                # with parallel:
                #     self.State_Control.pulse_688(self.pi_timeRaman)
                #     self.State_Control.pulse_679(self.pi_timeRaman)
                
            with parallel:
                #delay(self.delay_exp)
                delay(self.delay_exp*point[1])
                #self.State_Control.switch_profile(1)
            with parallel:
                self.State_Control.pulse_688(self.pi_timeRaman)
                self.State_Control.pulse_679(self.pi_timeRaman)
            delay(0.25*us)
            self.State_Control.pulse_689(self.pi_2_time689)
            
            
            self.ttl5.off()
            
            self.readout(scheme=self.readout_scheme)
            
        # # -----  3P0 EXCITATION -----------------------
        # elif self.excited_state=='3P0':
        #     self.State_Control.pulse_689(self.pi_2_time689)
        #     delay(0.1*us)
        #     with parallel:
        #         self.State_Control.pulse_688(self.pi_timeRaman)
        #         self.State_Control.pulse_679(self.pi_timeRaman)
             
        #     ### Pi_X #############################################
        #     delay(self.delay_exp*point[1]/2)
        #     self.State_Control.pulse_689(self.pi_time689)
        #     delay(0.1*us)
        #     with parallel:
        #         self.State_Control.pulse_688(self.pi_timeRaman)
        #         self.State_Control.pulse_679(self.pi_timeRaman)
        #     delay(0.25*us)
        #     self.State_Control.pulse_689(self.pi_time689)
            
        #     with parallel:
        #         delay(self.delay_exp*point[1])
        #         self.State_Control.switch_profile(1)
                
        #     ### Pi_Y #############################################
        #     self.State_Control.pulse_689(self.pi_time689)
        #     delay(0.1*us)
        #     with parallel:
        #         self.State_Control.pulse_688(self.pi_timeRaman)
        #         self.State_Control.pulse_679(self.pi_timeRaman)
        #     delay(0.25*us)
        #     self.State_Control.pulse_689(self.pi_time689)
            
        #     with parallel:
        #         delay(self.delay_exp*point[1])
        #         self.State_Control.switch_profile(0)
                
        #     ### Pi_X #############################################
        #     self.State_Control.pulse_689(self.pi_time689)
        #     delay(0.1*us)
        #     with parallel:
        #         self.State_Control.pulse_688(self.pi_timeRaman)
        #         self.State_Control.pulse_679(self.pi_timeRaman)
        #     delay(0.25*us)
        #     self.State_Control.pulse_689(self.pi_time689)
            
        #     with parallel:
        #         delay(self.delay_exp*point[1])
        #         self.State_Control.switch_profile(1)
                
        #     ### Pi_Y #############################################
        #     self.State_Control.pulse_689(self.pi_time689)
        #     delay(0.1*us)
        #     with parallel:
        #         self.State_Control.pulse_688(self.pi_timeRaman)
        #         self.State_Control.pulse_679(self.pi_timeRaman)
        #     delay(0.25*us)
        #     self.State_Control.pulse_689(self.pi_time689)
            
        #     with parallel:
        #         delay(self.delay_exp*point[1]/2)
        #         self.State_Control.switch_profile(0)
                
        #     ### close #############################################
        #     with parallel:
        #         self.State_Control.pulse_688(self.pi_timeRaman)
        #         self.State_Control.pulse_679(self.pi_timeRaman)
        #     delay(0.25*us)
        #     self.State_Control.pulse_689(self.pi_2_time689)
            
            
        #     self.ttl5.off()
            
        #     self.readout(scheme=self.readout_scheme)
                
                
                
                
                
                
        else:
            raise Exception('Not Valid State')
            
        
        self.Bragg.set_AOM_attens([("Dipole",self.Bragg.atten_Dipole)]) 
        self.Bragg.AOMs_on(["Lattice"])    
        
        
        
        # image and reset for next shot
        self.MOTs.take_MOT_image(self.Camera)  
        delay(15*ms)
        
        self.MOTs.set_current(0.0)
        delay(20*ms)
        self.MOTs.set_current_dir(0)
        delay(5*ms)  
        
        #process and output
        self.MOTs.AOMs_on(self.MOTs.AOMs) # just keeps AOMs warm

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
            delay(self.MOTs.Delay_duration)

        elif scheme == "1":
            self.State_Control.push_pulse(self.MOTs.Push_pulse_time)
            delay(200*us)
            self.State_Control.push_pulse(self.MOTs.Push_pulse_time)
            delay(5*us)
            
            self.MOTs.AOMs_on(['3P0_repump', '3P2_repump'])
            delay(self.MOTs.Delay_duration)
            self.MOTs.AOMs_off(['3P0_repump', '3P2_repump'])
        elif scheme == "2":
            delay(200*us)
            self.State_Control.push_pulse(self.MOTs.Push_pulse_time)
            
            self.MOTs.AOMs_on(['3P2_repump'])
            delay(200*us)
            self.MOTs.AOMs_off(['3P2_repump'])
            
            delay(200*us)
            self.State_Control.push_pulse(self.MOTs.Push_pulse_time)
            delay(5*us)
            
            self.MOTs.AOMs_on(['3P0_repump', '3P2_repump'])
            delay(self.MOTs.Delay_duration)
            self.MOTs.AOMs_off(['3P0_repump', '3P2_repump'])
        else:
            raise Exception("Not a valid readout scheme...")
            
            
            
    @kernel
    def raman_pulse(self, time):
        self.State_Control.AOMs_on(['688'])
        delay(0.1*us)
        self.State_Control.AOMs_on(["679"]) 
        
        
        delay(time)
        
        
        self.State_Control.AOMs_off(['688']) 
        delay(0.07*us)
        self.State_Control.AOMs_off(["679"])
                
    @kernel
    def set_phases(self, point):

        self.State_Control.set_AOM_phase('688', self.State_Control.freq_688, 0.0, self.t0, 0)
        self.State_Control.set_AOM_phase('688', self.State_Control.freq_688, 0.0, self.t0, 1)

        #
        self.State_Control.set_AOM_phase('Push', self.State_Control.freq_Push, 0.0, self.t0, 0)
        self.State_Control.set_AOM_phase('Push', self.State_Control.freq_Push, 0.0, self.t0, 1)


        self.State_Control.set_AOM_phase('679', self.State_Control.freq_679, 0.0, self.t0, 0)
        self.State_Control.set_AOM_phase('679', self.State_Control.freq_679, 0.0, self.t0, 1)


        self.State_Control.set_AOM_phase('689', self.State_Control.freq_689, 0.0, self.t0, 0)
        self.State_Control.set_AOM_phase('689', self.State_Control.freq_689, point[1], self.t0, 1)
        #self.State_Control.set_AOM_phase('689', self.State_Control.freq_689,0.0, self.t0, 1)
        
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
        
        