# -*- coding: utf-8 -*-
"""
Created on Mon Apr 28 11:19:32 2025

@author: sr
"""



from scan_framework import Scan1D, TimeScan
from artiq.experiment import *
import numpy as np



from CoolingClass import _Cooling
from CameraClass import _Camera
from STIRAPClass import _STIRAP
from BraggClass import _Bragg
from repository.models.scan_models import RabiModel

class Sq_Ramsey(Scan1D, EnvExperiment):
    
    def build(self, **kwargs):
        # required initializations
        
        super().build(**kwargs)
        
        # import classes for experiment control
        self.MOTs = _Cooling(self)
        self.Camera = _Camera(self)
        self.STIRAP = _STIRAP(self) # controls 689, 679, 688, and push AOMs
        self.Bragg = _Bragg(self) # controls dipole trap and lattice
        
        self.setattr_device("ttl5") # for triggering and timing experimental sequence
        
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
        
        self.setattr_argument("dipole_load_time", NumberValue(20.0*1e-3,min=0.0*1e-3,max=9000.00*1e-3,scale=1e-3,
                      unit="ms"),"Params")
        
        self.setattr_argument("pi_2_time689", NumberValue(1.0*1e-6,min=0.0*1e-6,max=1000.00*1e-6,scale=1e-6,
                      unit="us"),"Params")
        self.setattr_argument("pi_time689", NumberValue(1.0*1e-6,min=0.0*1e-6,max=1000.00*1e-6,scale=1e-6,
                      unit="us"),"Params")
        self.setattr_argument("pi_2_timeRaman", NumberValue(1.0*1e-6,min=0.0*1e-6,max=1000.00*1e-6,scale=1e-6,
                      unit="us"),"Params")
        self.setattr_argument("Ramsey_time", NumberValue(10.0*1e-6,min=0.0*1e-6,max=1000.00*1e-6,scale=1e-6,
                      unit="us"),"Params")
        self.setattr_argument("probe_time", NumberValue(1.0*1e-6,min=0.0*1e-6,max=1000.00*1e-6,scale=1e-6,
                      unit="us"),"Params")
        self.setattr_argument("Calib_689",BooleanValue(False),"Params")
        self.setattr_argument("Probe",BooleanValue(False),"Params")
        self.Echo = False

        self.setattr_argument("B_field", NumberValue(0.88,min=0.0,max=2,scale=1,
                      unit="V", ndecimals=3),"Params")
        

        self.t0 = np.int64(0)
        self.FIX_DELAY_TIME = 150*ns
        
        self.powers = [15.0, 18.0, 21.0, 24.0, 27.0, 30.0]
        self.power_ind = 0
        
    def get_scan_points(self):
        return self.pulse_phase    
        
    def prepare(self):
        #prepare/initialize mot hardware and camera
        self.MOTs.prepare_aoms()
        self.MOTs.prepare_coils()
        self.Bragg.prepare_aoms()
        self.Camera.camera_init()
        self.STIRAP.prepare_aoms()
        
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
        self.STIRAP.init_aoms(on=False)
        self.Bragg.init_aoms(on=True)
        delay(10*ms)
        
        self.MOTs.set_current_dir(0)
        delay(10*ms)
        self.ttl5.off()
        
        self.MOTs.take_background_image_exp(self.Camera)
        
        delay(5*ms)
        self.MOTs.AOMs_on(['3D', "3P0_repump", "3P2_repump", "3D_red"])
        delay(2000*ms)
        self.MOTs.AOMs_off(['3D', "3P0_repump", "3P2_repump", "3D_red"]) 
                   


        
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
        self.set_phases(point)

        
        # perform experiment
        self.MOTs.AOMs_off(self.MOTs.AOMs)
        self.STIRAP.AOMs_off(self.STIRAP.AOMs)
        self.Bragg.AOMs_off(["Bragg1"])
        delay(15*ms)
        
        self.Bragg.set_AOM_attens([("Bragg1", self.powers[self.power_ind])])
        self.power_ind = (self.power_ind + 1)%len(self.powers)
        
        
        
        
        self.MOTs.rMOT_pulse()  # generates the red MOT

        with parallel:
            delay(self.dipole_load_time)
            with sequential:
                self.MOTs.set_current_dir(1) # XXX let MOT field go to zero and switch H-bridge, 5ms
                self.MOTs.set_current(self.B_field)
        
        self.Bragg.set_AOM_attens([("Dipole",26.0 )]) # Turn off lattice
        self.Bragg.AOMs_off(["Lattice"])
        delay(20*us)
        
        delay(250*us)
        
        if self.Calib_689: # for characterizing 689 frequency
            self.ttl5.on()
            
            self.STIRAP.pulse(self.pi_2_time689, self.STIRAP.urukul_channels[self.STIRAP.index_artiq("689")])
            
            if self.Echo: # add in additional delay + pi pulse if using spin echo
                delay(self.Ramsey_time)
                self.STIRAP.pulse(self.pi_time689, self.STIRAP.urukul_channels[self.STIRAP.index_artiq("689")])
            with parallel:
                delay(self.Ramsey_time)
                self.STIRAP.switch_profile(1)

            
            self.STIRAP.pulse(self.pi_2_time689, self.STIRAP.urukul_channels[self.STIRAP.index_artiq("689")])
            
            
            self.STIRAP.push_pulse(self.MOTs.Push_pulse_time) #seperate for readout
            self.Bragg.set_AOM_attens([("Dipole",12.0 )])
            self.Bragg.AOMs_on(["Lattice"])
            delay(self.MOTs.Delay_duration)
            
        else:
            
            ### Ramsey sequence############################
            
            
            self.STIRAP.pulse(self.pi_2_time689, self.STIRAP.urukul_channels[self.STIRAP.index_artiq("689")])
            delay(0.2*us)
            self.raman_pulse(self.pi_2_timeRaman)
                        
          
            if self.Echo:
                delay(self.Ramsey_time)

                self.raman_pulse(self.pi_2_timeRaman)
                delay(-0.2*us)
                self.STIRAP.pulse(self.pi_time689, self.STIRAP.urukul_channels[self.STIRAP.index_artiq("689")])
                delay(0.2*us)
                self.raman_pulse(self.pi_2_timeRaman)

            self.ttl5.on()
            with parallel:
                delay(self.Ramsey_time-10*us)
                self.STIRAP.switch_profile(1)
                
                if self.Probe:
                ### Measure static VRS with all atoms
                    self.Bragg.AOMs_on(["Bragg1"])
                    delay(self.probe_time)
                    self.Bragg.AOMs_off(["Bragg1"])
                #delay(1*us)
            
            self.ttl5.off()
            delay(10*us)

            self.raman_pulse(self.pi_2_timeRaman)
            delay(-0.2*us)
            self.STIRAP.pulse(self.pi_2_time689, self.STIRAP.urukul_channels[self.STIRAP.index_artiq("689")])


            self.ttl5.off()
            
            #3P1 viewing
            self.STIRAP.push_pulse(self.MOTs.Push_pulse_time) #seperate for readout
            delay(200*us)
            self.STIRAP.push_pulse(self.MOTs.Push_pulse_time) #seperate for readout
            self.Bragg.set_AOM_attens([("Dipole",12.0 )])
            self.Bragg.AOMs_on(["Lattice"])
            delay(5*us)
            self.MOTs.AOMs_on(['3P0_repump', '3P2_repump'])
            delay(self.MOTs.Delay_duration)
            self.MOTs.AOMs_off(['3P0_repump', '3P2_repump'])
            
            ### 3P0 viewing
            # delay(200*us)
            # self.STIRAP.push_pulse(self.MOTs.Push_pulse_time)
            
            # self.MOTs.AOMs_on(['3P2_repump'])
            # delay(200*us)
            # self.MOTs.AOMs_off(['3P2_repump'])
            
            # delay(200*us)
            # self.STIRAP.push_pulse(self.MOTs.Push_pulse_time)
            # self.Bragg.set_AOM_attens([("Dipole",12.0 )])
            # self.Bragg.AOMs_on(["Lattice"])
            # delay(5*us)
            
            # self.MOTs.AOMs_on(['3P0_repump', '3P2_repump'])
            # delay(self.MOTs.Delay_duration)
            # self.MOTs.AOMs_off(['3P0_repump', '3P2_repump'])
            
        
            
        
        
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
        
        
        return self.Camera.get_push_stats()


    
    def after_fit(self, fit_name, valid, saved, model):
        self.set_dataset('current_scan.plots.error', model.errors, broadcast=True, persist=True)

  
    @kernel
    def raman_pulse(self, time):
        self.STIRAP.AOMs_on(['688']) # turn on 688 for STIRAP sequence
        delay(0.1*us)
        self.STIRAP.AOMs_on(["679"]) # turn on 688 for STIRAP sequence
        delay(time)
        self.STIRAP.AOMs_off(['688']) # turn on 688 for STIRAP sequence
        delay(0.07*us)
        self.STIRAP.AOMs_off(["679"]) # turn on 688 for STIRAP sequence
        
    @kernel
    def set_phases(self, point):
        self.STIRAP.set_AOM_phase('688', self.STIRAP.freq_688, 0.0, self.t0, 0)
        self.STIRAP.set_AOM_phase('688', self.STIRAP.freq_688, 0.0, self.t0, 1)

        #
        self.STIRAP.set_AOM_phase('Push', self.STIRAP.freq_Push, 0.0, self.t0, 0)
        self.STIRAP.set_AOM_phase('Push', self.STIRAP.freq_Push, 0.0, self.t0, 1)


        self.STIRAP.set_AOM_phase('679', self.STIRAP.freq_679, 0.0, self.t0, 0)
        self.STIRAP.set_AOM_phase('679', self.STIRAP.freq_679, 0.0, self.t0, 1)


        self.STIRAP.set_AOM_phase('689', self.STIRAP.freq_689, 0.0, self.t0, 0)
        if self.Calib_689:
            self.STIRAP.set_AOM_phase('689', self.STIRAP.freq_689, point, self.t0, 1)
        else:
            self.STIRAP.set_AOM_phase('689', self.STIRAP.freq_689, point, self.t0, 1)
        
        self.STIRAP.switch_profile(0)