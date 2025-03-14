# -*- coding: utf-8 -*-
"""
Created on Tue Jan 21 13:37:31 2025

@author: sr
"""

from scan_framework import Scan1D, TimeFreqScan
from artiq.experiment import *
import numpy as np
import pyvisa



from CoolingClass import _Cooling
from CameraClass import _Camera
from STIRAPClass import _STIRAP
from BraggClass import _Bragg
from AWG import WaveformGenerator
from repository.models.scan_models import AI_Rabi_Model as myModel


class STIRAP_exp(Scan1D, TimeFreqScan, EnvExperiment):
    
    def build(self, **kwargs):
        # required initializations
        
        super().build(**kwargs)
        
        self.setattr_device("ttl5") # triggering pulse
        self.setattr_device("ttl1")
        # import classes for experiment control
        self.MOTs = _Cooling(self)
        self.Camera = _Camera(self)
        self.STIRAP = _STIRAP(self)
        self.Bragg = _Bragg(self)
        
        self.rigol=None
        self.wg = WaveformGenerator()
        
        self.enable_pausing = True # disable to speed up by not checking scheduler
        self.enable_auto_tracking=False
        self.enable_profiling = False # enable to print runtime statistics to find bottlenecks

        self.scan_arguments(times = {'start':0*us,
            'stop':1.5*us,
            'npoints':20,
            'unit':"us",
            'scale':us,
            'global_step':0.1*us,
            'ndecimals':2},
             frequencies={
            'start':-3*MHz,
            'stop':3*MHz,
            'npoints':50,
            'unit':"MHz",
            'scale':MHz,
            'global_step':0.1*MHz,
            'ndecimals':4},
            frequency_center={'default':100*MHz},
            pulse_time= {'default':0*us},
            nbins = {'default':1000},
            nrepeats = {'default':1},
            npasses = {'default':1},
            fit_options = {'default': "No Fits"}
        
            )
        
        self.setattr_argument("dipole_load_time", NumberValue(20.0*1e-3,min=0.0*1e-3,max=9000.00*1e-3,scale=1e-3,
                      unit="ms"),"Params")
        
        self.setattr_argument("pi_time", NumberValue(1.0*1e-6,min=0.0*1e-6,max=1000.00*1e-6,scale=1e-6,
                      unit="us"),"Params")
        self.setattr_argument("STIRAP_time", NumberValue(10.0*1e-6,min=0.0*1e-6,max=1000.00*1e-6,scale=1e-6,
                      unit="us"),"Params")
        self.setattr_argument("Calib_689",BooleanValue(False),"Params")


        self.setattr_argument("B_field", NumberValue(0.88,min=0.0,max=2,scale=1,
                      unit="V", ndecimals=3),"Params")
        
        
        
    def prepare(self):
        #prepare/initialize mot hardware and camera
        self.MOTs.prepare_aoms()
        self.MOTs.prepare_coils()
        self.Bragg.prepare_aoms()
        self.Camera.camera_init()
        self.STIRAP.prepare_aoms()
        #self.prepare_rigol()

        # register model with scan framework
        
        
        self.enable_histograms = True
        self.model = myModel(self)
        self.register_model(self.model, measurement=True, fit=True)
        
    @kernel
    def before_scan(self):
        # runs before experiment take place
        
        #initialize devices on host
        self.core.reset()
        delay(10*ms)
        self.ttl5.off()
        self.MOTs.init_coils()
        self.MOTs.init_ttls()
        self.MOTs.init_aoms(on=False)  
        self.STIRAP.init_aoms(on=False)
        self.Bragg.init_aoms(on=True)
        delay(10*ms)
        
        self.MOTs.set_current_dir(0)
        delay(10*ms)
        
        self.MOTs.take_background_image_exp(self.Camera)
        
        delay(5*ms)
        self.MOTs.AOMs_on(['3D', "3P0_repump", "3P2_repump", "3D_red"])
        delay(2000*ms)
        self.MOTs.AOMs_off(['3D', "3P0_repump", "3P2_repump", "3D_red"])
     
        
    # def before_measure(self, point, measurement):
    #     if point > 1:
    #         LENGTH = self.STIRAP_time
    #     else:
    #         LENGTH = point

    #     SAMPLES = 6000
    #     SAMPLE_RATE = SAMPLES/LENGTH
    #     t_offset = 5*us
    #     self.wg.sample_rate = SAMPLE_RATE
        
        
    #     self.wg.reset_waveform()
        
    #     self.wg.add_point(0.0, 0.0)
    #     self.wg.add_sigmoid_pulse(t_offset, LENGTH-2*t_offset, 1, LENGTH/10, +1)
    #     self.wg.add_point(LENGTH, 0.0)
        
    #     t, y = self.wg.get_waveform()
    #     val_str_ch1 = ",".join(map(str, y))
        
    #     self.wg.reset_waveform()
        
    #     self.wg.add_point(0.0, 0.0)
    #     self.wg.add_sigmoid_pulse(t_offset, LENGTH-2*t_offset, 1, LENGTH/10, -1)
    #     self.wg.add_point(LENGTH, 0.0)
        
    #     t, y = self.wg.get_waveform()
    #     val_str_ch2 = ",".join(map(str, y))
        
    #     waves = [val_str_ch1,val_str_ch2]
        
    #     for i in range(1,3):
    #         self.rigol.write(f":OUTP{i} OFF");
        
    #         self.rigol.write(f":TRACE:DATA VOLATILE," + waves[i-1])
    #         self.rigol.write(f":SOUR{i}:APPL:USER {1/LENGTH}, {2*self.wg.max}, 0, 0")
        
    #         self.rigol.write(f"SOUR{i}:BURS ON")
    #         self.rigol.write(f"SOUR{i}:BURS:MODE TRIG")
    #         self.rigol.write(f":SOUR{i}:BURS:NCYC 1 ")
    #         self.rigol.write(f":SOUR{i}:BURS:TRIG:SOUR EXT")
        
        
    #         self.rigol.write(f":OUTP{i} ON");

 
    @kernel
    def measure(self, time, frequency):        
        
        
        #prepare
        self.core.wait_until_mu(now_mu())
        self.core.reset()
        
        
        
        pi_pulse_freq = frequency if self.Calib_689 else self.STIRAP.freq_689
        pi_pulse_time = time if self.Calib_689 else self.pi_time
        
        stirap679_freq = frequency # unused if self.Calib_689 = True


        delay(100*ms)
        self.Camera.arm()
        delay(200*ms)
        
        
        self.STIRAP.set_AOM_freqs([('689', pi_pulse_freq)])
        self.STIRAP.set_AOM_freqs([('679', frequency)])

        delay(10*ms)
        
        # perform experiment
        self.MOTs.AOMs_off(self.MOTs.AOMs)
        self.STIRAP.AOMs_off(self.STIRAP.AOMs)
        delay(15*ms)
        
        # line trigger
        self.MOTs.line_trigger()
        
        self.MOTs.rMOT_pulse()  # generates the red MOT

        with parallel:
            delay(self.dipole_load_time)
            with sequential:
                self.MOTs.set_current_dir(1) # XXX let MOT field go to zero and switch H-bridge, 5ms
                self.MOTs.set_current(self.B_field)
                

        self.Bragg.set_AOM_attens([("Dipole",24.0 )]) # Turn off lattice
        self.Bragg.AOMs_off(["Lattice"])
        delay(20*us)
        
        
        
        
        if self.Calib_689:
            # self.ttl5.on()
            # self.STIRAP.pulse(self.STIRAP_time, self.STIRAP.urukul_channels[self.STIRAP.index_artiq("689")])
            # delay(time)
            # #self.STIRAP.pulse(self.STIRAP_time, self.STIRAP.urukul_channels[self.STIRAP.index_artiq("689")])
            # self.ttl5.off()
            # self.STIRAP.push_pulse(self.MOTs.Push_pulse_time) #seperate for readout
            # self.Bragg.set_AOM_attens([("Dipole",12.0 )])
            # self.Bragg.AOMs_on(["Lattice"])
            # delay(self.MOTs.Delay_duration)

            self.ttl5.on()
            self.STIRAP.pulse(pi_pulse_time, self.STIRAP.urukul_channels[self.STIRAP.index_artiq("689")])
            self.STIRAP.push_pulse(self.MOTs.Push_pulse_time) #seperate for readout
            self.Bragg.set_AOM_attens([("Dipole",12.0 )])
            self.Bragg.AOMs_on(["Lattice"])
            delay(self.MOTs.Delay_duration)
            self.ttl5.off()
        
        else:
            
            ## Raman transfer sequence
            # self.ttl5.on()
            # self.STIRAP.pulse(pi_pulse_time, self.STIRAP.urukul_channels[self.STIRAP.index_artiq("689")])
            # delay(0.1*us)
            # self.raman_pulse(time)
            # self.ttl5.off()
            
            self.ttl5.on()
            self.STIRAP.pulse(pi_pulse_time, self.STIRAP.urukul_channels[self.STIRAP.index_artiq("689")])
            delay(0.2*us)
            self.raman_pulse(time)
            #delay(0.2*us)
            #self.STIRAP.pulse(pi_pulse_time, self.STIRAP.urukul_channels[self.STIRAP.index_artiq("689")])
            self.ttl5.off()
            
            #Raman ramsey sequence
            # self.ttl5.on()
            
            # self.STIRAP.pulse(pi_pulse_time, self.STIRAP.urukul_channels[self.STIRAP.index_artiq("689")])
            # delay(0.1*us)
            # self.raman_pulse(self.STIRAP_time)
            # #delay(0.1*us)
            # #self.STIRAP.pulse(pi_pulse_time, self.STIRAP.urukul_channels[self.STIRAP.index_artiq("689")])
            
            # delay(time)

            
            # #self.STIRAP.pulse(pi_pulse_time, self.STIRAP.urukul_channels[self.STIRAP.index_artiq("689")])
            # #delay(0.1*us)
            # self.raman_pulse(self.STIRAP_time)
            # delay(0.1*us)
            # self.STIRAP.pulse(pi_pulse_time, self.STIRAP.urukul_channels[self.STIRAP.index_artiq("689")])
            

            # self.ttl5.off()
            
            #self.seperate_ports(2)
            self.STIRAP.push_pulse(self.MOTs.Push_pulse_time) #seperate for readout
            delay(200*us)
            self.STIRAP.push_pulse(self.MOTs.Push_pulse_time) #seperate for readout
            self.Bragg.set_AOM_attens([("Dipole",12.0 )])
            self.Bragg.AOMs_on(["Lattice"])
            delay(5*us)
            self.MOTs.AOMs_on(['3P0_repump', '3P2_repump'])
            delay(self.MOTs.Delay_duration)
            self.MOTs.AOMs_off(['3P0_repump', '3P2_repump'])
            
            
            
        # else:
        #     self.ttl5.on() 
        #     self.STIRAP.AOMs_on(['688']) # turn on 688 for STIRAP sequence
        #     delay(5*us)
            
        #     #Square pulses:
        #     self.STIRAP.AOMs_on(['679']) # turn on 688 for STIRAP sequence
        #     delay(time/3)
        #     self.STIRAP.AOMs_on(['689']) # turn on 688 for STIRAP sequence
        #     delay(time/3)
        #     self.STIRAP.AOMs_off(['679'])
        #     delay(time/3)
        #     self.STIRAP.AOMs_off(['689'])
            
        #     # self.STIRAP.AOMs_on(['679']) # turn on 688 for STIRAP sequence
        #     # delay(time/2)
        #     # self.STIRAP.AOMs_off(['679'])
        #     # delay(1*us)
        #     # self.STIRAP.AOMs_on(['689']) # turn on 688 for STIRAP sequence
        #     # delay(time/2)
        #     # self.STIRAP.AOMs_off(['689'])
            
        #     # Smooth pulses
        #     # self.STIRAP.AOMs_on(['679'])
        #     # self.STIRAP.AOMs_on(['689'])
        #     # delay(time)
        #     # self.STIRAP.AOMs_off(['679'])
        #     # self.STIRAP.AOMs_off(['689'])
           
            
        #     delay(5*us)
        #     self.STIRAP.AOMs_off(['688'])
        #     self.ttl5.off()
    
    
        #     # exp ends
        #     self.seperate_ports(1)
    
        #     #self.STIRAP.push_pulse(self.MOTs.Push_pulse_time) #seperate for readout
        #     # delay(200*us)
        #     # self.STIRAP.push_pulse(self.MOTs.Push_pulse_time) #seperate for readout
        #     # delay(5*us)
    
        #     # self.MOTs.AOMs_on(['3P0_repump', '3P2_repump'])
        #     # #self.MOTs.AOMs_on(['3P0_repump'])
        #     # delay(self.MOTs.Delay_duration)
        #     # #self.MOTs.AOMs_off(['3P0_repump'])
        #     # self.MOTs.AOMs_off(['3P0_repump', '3P2_repump'])
        
               
        
        self.Bragg.set_AOM_attens([("Dipole",12.0 )])
        self.Bragg.AOMs_on(["Lattice"])
        
        
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
    
    @kernel
    def seperate_ports(self, scheme = 1):
        if scheme ==1:
            delay(200*us)
            self.STIRAP.push_pulse(self.MOTs.Push_pulse_time)
            delay(5*us)
            
            self.MOTs.AOMs_on(['3P0_repump', '3P2_repump'])
            delay(self.MOTs.Delay_duration)
            self.MOTs.AOMs_off(['3P0_repump', '3P2_repump'])
        else:
            delay(200*us)
            self.STIRAP.push_pulse(self.MOTs.Push_pulse_time)
            
            self.MOTs.AOMs_on(['3P2_repump'])
            delay(200*us)
            self.MOTs.AOMs_off(['3P2_repump'])
            
            delay(200*us)
            self.STIRAP.push_pulse(self.MOTs.Push_pulse_time)
            delay(5*us)
            
            self.MOTs.AOMs_on(['3P0_repump', '3P2_repump'])
            delay(self.MOTs.Delay_duration)
            self.MOTs.AOMs_off(['3P0_repump', '3P2_repump'])
        
                
    @kernel
    def smooth_pulse(self, time):
        self.ttl5.on() 
        self.STIRAP.AOMs_on(['688', "679", "689"]) # turn on 688 for STIRAP sequence
        delay(time)
        self.STIRAP.AOMs_off(['688', "679", "689"]) # turn on 688 for STIRAP sequence
        self.ttl5.off()
    
    @kernel
    def raman_pulse(self, time):
        self.STIRAP.AOMs_on(['688']) # turn on 688 for STIRAP sequence
        delay(0.05*us)
        self.STIRAP.AOMs_on(["679"]) # turn on 688 for STIRAP sequence
        delay(time)
        self.STIRAP.AOMs_off(['688']) # turn on 688 for STIRAP sequence
        delay(0.1*us)
        self.STIRAP.AOMs_off(["679"]) # turn on 688 for STIRAP sequence
        
    def prepare_rigol(self):
        self.rigol = pyvisa.ResourceManager().open_resource('USB0::0x1AB1::0x0641::DG4E232700930::INSTR')
        self.rigol.write(":OUTP1 OFF");
        self.rigol.write(":OUTP2 OFF");
    