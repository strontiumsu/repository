# -*- coding: utf-8 -*-
"""
Created on Tue Jan 21 13:37:31 2025

@author: sr
"""

from scan_framework import Scan1D, TimeFreqScan
from artiq.experiment import *
import numpy as np
import pyvisa
from artiq.coredevice import ad9910


from CoolingClass import _Cooling
from CameraClass import _Camera

from StateControlClass import _STATE_CONTROL
from BraggClass import _Bragg
from AWG import WaveformGenerator
from repository.models.scan_models import AI_Rabi_Model as myModel


class ClockRabiVRS_exp(Scan1D, TimeFreqScan, EnvExperiment):
    
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
        
        self.scan_dds = self.Bragg.urukul_channels[1]

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
        
        self.setattr_argument("freq_center", 
                              NumberValue(
                                  3*1e6,
                                  min=0.1*1e6,
                                  max=100.0*1e6,
                                  scale=1e6,
                                  unit="MHz"),
                              "parameters")     
        self.setattr_argument("freq_width", 
                              NumberValue(
                                  1*1e6,
                                  min=-10.0*1e6,
                                  max=10.0*1e6,
                                  scale=1e6,
                                  unit="MHz"),
                              "parameters")
        self.setattr_argument("pulses", 
                              NumberValue(
                                  10,
                                  min=1,
                                  max=1000,
                                  scale=1,),
                              "parameters")
        self.setattr_argument("scan_time", 
                              NumberValue(
                                  100*1e-6,
                                  min=1*1e-6,
                                  max=50000*1e-6,
                                  scale=1e-6,
                                  unit='us'),
                              "parameters")
        
        
        self.setattr_argument("dipole_load_time", NumberValue(20.0*1e-3,min=0.0*1e-3,max=9000.00*1e-3,scale=1e-3,
                      unit="ms"),"Params")
        
        self.setattr_argument("pi_time_689", NumberValue(1.0*1e-6,min=0.0*1e-6,max=1000.00*1e-6,scale=1e-6,
                      unit="us"),"Params")
        self.setattr_argument("pi_time_Ramsey", NumberValue(1.0*1e-6,min=0.0*1e-6,max=1000.00*1e-6,scale=1e-6,
                      unit="us"),"Params")
        
        self.setattr_argument("excited_state", EnumerationValue(['3P1', "3P0"], default='3P1'), "Params")
        self.setattr_argument("readout_scheme", EnumerationValue(["0","1","2"], default="0"), "Params")
        self.setattr_argument("B_field", NumberValue(0.88,min=0.0,max=2,scale=1,
                      unit="V", ndecimals=3),"Params")
       
        self.freq_list= np.linspace(80.0*MHz, 80.0*MHz, 1024)
        self.freq_list_ram = np.full(1024, 1)
        self.step_size=0
        
        
    def prepare(self):
        #prepare/initialize mot hardware and camera
        self.MOTs.prepare_aoms()
        self.Bragg.prepare_aoms()
        self.State_Control.prepare_aoms()
        
        self.MOTs.prepare_coils()
        
        self.Camera.camera_init()
        
        
        self.enable_histograms = True
        self.model = myModel(self)
        self.register_model(self.model, measurement=True, fit=True)
      
    @kernel
    def load_scan(self):
        self.step_size = int(self.scan_time/(1024*4*ns))
        f0 = self.freq_center + self.freq_width/2
        f_step = self.freq_width/1023
        if self.freq_width/2 > self.freq_center: raise Exception("Bad Range")
        for i in range(1024):
            self.freq_list[i] = f0 - f_step*i
        self.scan_dds.frequency_to_ram(self.freq_list, self.freq_list_ram)

        self.core.break_realtime()
        delay(10 * ms)

        self.scan_dds.set(self.freq_center - self.freq_width/2, amplitude=self.Bragg.scale_Bragg1)

        delay(1 * ms)



        self.scan_dds.set_cfr1(ram_enable=0)
        self.scan_dds.cpld.io_update.pulse_mu(8)

        self.scan_dds.set_profile_ram(start=0, end=1024-1, step=(self.step_size | (2**6 - 1 ) << 16),
                                  profile=0, mode=ad9910.RAM_MODE_RAMPUP)
        self.scan_dds.cpld.set_profile(0)

        delay(100*us) # needs 2x delays here not to throw RTIOUnderflow Error?????
        delay(100*us)

        self.scan_dds.cpld.io_update.pulse_mu(8)
        delay(1000*us)
        self.scan_dds.write_ram(self.freq_list_ram)
        # prepare to enable ram and set frequency as target
        delay(10 * us)
        self.scan_dds.set_cfr1(internal_profile=0, ram_enable=1, ram_destination=ad9910.RAM_DEST_FTW)
        delay(10*ms)

        self.core.wait_until_mu(now_mu())
    
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
        self.core.wait_until_mu(now_mu())
     
        
  
 
    @kernel
    def measure(self, time, frequency):        
        
        
        #prepare
        self.core.wait_until_mu(now_mu())
        self.core.reset()
        
        delay(1 * ms)
        self.load_scan()
        delay(1*ms)

        # before this point is just for preparing the RAM and RIGOL
        self.core.break_realtime()
        delay(10*ms)
        self.Bragg.set_AOM_attens([("Bragg1", self.Bragg.atten_Bragg1)])
        
        delay(100*ms)

        self.Camera.arm()
        delay(200*ms)
        

        
        self.MOTs.AOMs_off(self.MOTs.AOMs)
        self.State_Control.AOMs_off(self.State_Control.AOMs)
        delay(1*ms)
        
 
        self.State_Control.set_AOM_freqs([('689', self.State_Control.freq_689), 
                                          ('688', self.State_Control.freq_688), 
                                          ('679', self.State_Control.freq_679)])
            
        
        delay(35*ms)
        
        # generate red mot
        self.MOTs.rMOT_pulse()
        
        # hold in dipole trap while changing MOT config
        with parallel:
            delay(self.dipole_load_time)
            with sequential:
                self.MOTs.set_current_dir(1) # XXX let MOT field go to zero and switch H-bridge, 5ms
                self.MOTs.set_current(self.B_field)
                

        delay(20*us) #??
        
        # experiment
        
        # -----  Measure VRS with all atoms -----------------------
        # self.Bragg.AOMs_on(["Bragg2"])
        # with parallel:
        #     self.scan_dds.sw.on()
        #     self.ttl5.on()
        #     self.scan_dds.cpld.io_update.pulse_mu(8)
        # delay(self.scan_time)
        # with parallel:
        #     self.scan_dds.sw.off()
        #     self.ttl5.off()
        # self.Bragg.AOMs_off(["Bragg2"])
        
        delay(20*us)
        
        # -----  3P0 state prep -----------------------
        self.State_Control.pulse_689(self.pi_time_689)
        delay(0.15*us)
        with parallel:
            self.State_Control.pulse_688(self.pi_time_Ramsey)
            self.State_Control.pulse_679(self.pi_time_Ramsey)
            
        delay(1*us)
        #delay(1*ms)
        self.State_Control.push_pulse(1*ms)
        
        
        # 3P0-> 1S0 Repump --------------------

        self.MOTs.AOMs_on(["3P0_repump","3P2_repump"])
        delay(0.8*ms)
        self.MOTs.AOMs_off(["3P0_repump","3P2_repump"]) 
        delay(200*us)


        # -----  1S0 -> 3P0 Rabi EXCITATION -----------------------
        self.State_Control.pulse_689(self.pi_time_689)
        delay(0.15*us)
        with parallel:
            self.State_Control.pulse_688(time)
            self.State_Control.pulse_679(time)
        
        # 3P0-> 1S0 Rabi EXCITATION --------------------

        # with parallel:
        #     self.State_Control.pulse_688(time)
        #     self.State_Control.pulse_679(time)
        # delay(0.15*us)
        # self.State_Control.pulse_689(self.pi_time_689)
        
        delay(200*us)
        #-----  Measure VRS with after excitation -----------------------
        self.Bragg.AOMs_on(["Bragg2"])
        with parallel:
            self.scan_dds.sw.on()
            self.ttl5.on()
            self.scan_dds.cpld.io_update.pulse_mu(8)
        delay(self.scan_time)
        with parallel:
            self.scan_dds.sw.off()
            self.ttl5.off()
        self.Bragg.AOMs_off(["Bragg2"])
        
        
        
        self.readout(scheme=self.readout_scheme)
                

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
                
  