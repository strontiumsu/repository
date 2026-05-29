# -*- coding: utf-8 -*-
"""
Created on Wed Aug 27 12:17:35 2025

@author: sr
"""

from artiq.experiment import Scannable, RangeScan, EnumerationValue, BooleanValue, NumberValue, at_mu, sequential, s # pyright: ignore[reportMissingImports]
from artiq.experiment import kernel, EnvExperiment, kHz, delay, ms, parallel, us, MHz, now_mu, ns # pyright: ignore[reportMissingImports]
from artiq.coredevice import ad9910 # pyright: ignore[reportMissingImports]
from scan_framework import Scan1D, TimeScan
import numpy as np

from CoolingClass import _Cooling
from CameraClass import _Camera
from BraggClass import _Bragg
from StateControlClass import _state_control





class VRS_TTL_calib_exp(Scan1D, EnvExperiment):
    
    def build(self, **kwargs):
        
        super().build(**kwargs)
        
        # hardware and class objects
        self.setattr_device("ttl5")
        self.setattr_device("ttl0") 
        
        self.MOTs = _Cooling(self)
        self.Camera = _Camera(self)
        
        self.State_Control = _state_control(self)
        self.Bragg = _Bragg(self)
        
        
        
        self.enable_pausing = True # disable to speed up by not checking scheduler
        self.enable_auto_tracking=False

        
        #scan parameters
        self.setattr_argument('idx_offsets', Scannable(default=RangeScan(
            start=-100,
            stop=100,
            npoints=21))
            )
        
        self.scan_arguments(nbins={'default': 1000},
            nrepeats={'default': 1},
            npasses={'default': 1},
            fit_options={'default': "No Fits"})
        
        
        
        #parameters
        self.setattr_argument("B_field", NumberValue(0.21,min=0.0,max=2,scale=1, unit="V", ndecimals=3),"parameters")
        self.setattr_argument("pi_time_689", NumberValue(1.0*1e-6,min=0.0*1e-6,max=1000.00*1e-6,scale=1e-6, unit="us"),"parameters")
        self.setattr_argument("pi_time_Ramsey", NumberValue(1.0*1e-6,min=0.0*1e-6,max=1000.00*1e-6,scale=1e-6,unit="us"),"parameters")
        self.setattr_argument("dipole_load_time", NumberValue(20.0*1e-3,min=0.0*1e-3,max=9000.00*1e-3,scale=1e-3, unit="ms"),"parameters")
        
        #self.setattr_argument("probe_atten", NumberValue(12.0,min=1.0, max=30,scale=1, unit="dB",ndecimals = 2),"parameters")
        # self.setattr_argument("probe_atten", NumberValue(0.8,min=0.01, max=0.8,scale=1, ndecimals = 2),"parameters")
        # self.setattr_argument("probe_time", NumberValue(2.0*1e-3,min=0.05*1e-3,max=100.00*1e-3,scale=1e-3, unit="ms"),"parameters")
        
        # VRS Scan args
        # Arguments   
        self.setattr_argument("freq_center_sb",  NumberValue( 3*1e6,    min=0.1*1e6,   max=200.0*1e6, scale=1e6,  unit="MHz", ndecimals=3), "parameters")     
        self.setattr_argument("freq_width_sb",   NumberValue( 1*1e6,    min=-10.0*1e6, max=10.0*1e6,  scale=1e6,  unit="MHz", ndecimals=3), "parameters")
        self.setattr_argument("scan_time_sb",    NumberValue( 100*1e-6, min=1*1e-6,    max=50*1e-3,   scale=1e-6, unit='us',  ndecimals=3), "parameters")
        
        self.setattr_argument("freq_center_car",   NumberValue(80.0*1e6, min=70.0*1e6,  max=200.0*1e6, scale=1e6,  unit="MHz", ndecimals=3), "parameters")     
        self.setattr_argument("freq_width_car",    NumberValue(100e3,    min=-20.0*1e6, max=20.0*1e6,  scale=1e3,  unit="kHz", ndecimals=3), "parameters")
        self.setattr_argument("scan_time_car",     NumberValue(1*1e-6, min=50*1e-6,    max=50*1e-3,    scale=1e-6, unit='us',  ndecimals=3), "parameters")
        
        # boolean args
        self.setattr_argument("Cavity_clear", BooleanValue(True), "parameters")
        self.setattr_argument("Image", BooleanValue(False), "parameters")
        
        # Prep DDS scan
        self.freq_list= np.linspace(0.0*MHz, 0.0*MHz, 1024)
        self.freq_list_ram = np.full(1024, 1)
        self.step_mu_sb = 0
        
        
        self.scan_dds_sb = self.Bragg.urukul_channels[1]
        self.scan_dds_car = self.Bragg.urukul_channels[2]
        
        self.t0 = np.int64(0)
        
    def get_scan_points(self):
        # return the set of scan points to the framework
        return [int(round(i)) for i in self.idx_offsets]
        
        
    def prepare(self):
        #prepare/initialize mot hardware and camera
        self.MOTs.prepare_aoms()
        self.Bragg.prepare_aoms()
        self.State_Control.prepare_aoms()
        
        self.MOTs.prepare_coils()
        
        if self.Image:
            self.Camera.camera_init()
            
        # if self.probe_type != "Constant": raise Exception("Scanning Probe Not Implemented...")
        if self.freq_width_car/2 > self.freq_center_car: raise Exception("Bad Carrier Range...")
        if self.freq_width_sb/2 > self.freq_center_sb: raise Exception("Bad Sideband Range...")
        
        self.step_mu_sb = self.core.seconds_to_mu(
            int(self.scan_time_sb/(1023*4*ns)) * 4*ns
        )
        
    @kernel
    def before_scan(self):
        self.core.reset()

        # set hardware in known states and initialize
        self.ttl0.input()
        
        self.MOTs.init_coils()
        self.MOTs.init_ttls()
        
        self.MOTs.init_aoms(on=False)
        self.State_Control.init_aoms(on=False)
        self.Bragg.init_aoms(switches=0x9)
        
        delay(10*ms)
        
        if self.Image:
            self.MOTs.take_background_image_exp(self.Camera)
            self.core.break_realtime()
            delay(5*ms)
        
        self.MOTs.set_current_dir(0)
        delay(10*ms)


        self.core.wait_until_mu(now_mu())
    
    @kernel
    def before_measure(self, point, measurement):
        if self.Image: self.Camera.arm()
        
        self.core.break_realtime() 
        delay(1*ms) 
        
        ##### ENSURE KNOWN STATES ################
        
        self.ttl5.off()
        delay(100*ns) # helps with SED lane management
        self.scan_dds_car.sw.off()
        delay(100*ns)
        self.scan_dds_sb.sw.off()
        delay(100*ns)
        self.MOTs.AOMs_off_all()
        delay(100*ns)
        self.State_Control.AOMs_off_all()
        delay(100*ns)
        self.MOTs.close_688()
        delay(100*ns)
        self.MOTs.set_current_dir(0)
        delay(100*ns)
         ##### PREP scans ################
         
        
        
        
        delay(1*ms)
        
        
    
    @kernel
    def measure(self, point):
        
        # point = idx offset 
        
        self.core.reset()
        delay(1*ms)
        
          # might just have to do once ??
          # for some reason cant get it to work if we do in before_scan
        self.MOTs.init_rmot_dds(self.MOTs.rmot_freq_i, self.MOTs.rmot_freq_f,  self.MOTs.rmot_freq_depth_i, self.MOTs.rmot_freq_depth_f, self.MOTs.freq_3D_red)
        delay(15*ms)
        self.core.break_realtime()
        self.load_scan(self.scan_dds_sb,self.freq_center_sb,self.freq_width_sb,self.scan_time_sb)
        delay(10*ms)
        self.core.break_realtime()
        self.load_scan(self.scan_dds_car,self.freq_center_car,self.freq_width_car,self.scan_time_car)
        delay(10*ms)
        self.core.break_realtime()
        self.freeze_RAM(self.scan_dds_car, 511, 511, self.scan_time_car)
        delay(10*ms)
        self.core.break_realtime()
        
        ##### FORM ATOM SAMPLE ################
        # generate red mot
        self.MOTs.rMOT_pulse_new()
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
        delay(5*ms)
            
                
            
        if self.Cavity_clear:        
            ##### EXCITATION ################
            self.State_Control.pulse_689(self.pi_time_689)
            delay(0.15*us)
            with parallel:
                self.State_Control.pulse_679(self.pi_time_Ramsey)
                self.State_Control.pulse_688(self.pi_time_Ramsey)
        
            #### CLEAR CAVITY AND PREP GROUND ################
            self.State_Control.cav_clear_pulse(2.5*ms)

            with parallel:
                self.State_Control.pulse_679(self.pi_time_Ramsey)
                self.State_Control.pulse_688(self.pi_time_Ramsey)
                
            self.MOTs.close_688() # turn off 688 nm
            self.MOTs.aom_3P0.sw.on()
            self.MOTs.aom_3P2.sw.on()
            delay(0.5*ms)
            self.MOTs.aom_3P0.sw.off()
            self.MOTs.aom_3P2.sw.off()
        
        ##### PROBE FOR RESONANCE ################
        
        t_start = now_mu() + self.core.seconds_to_mu(20*us)        
        at_mu(t_start) 
        
        

        delay(10*ns)
        with parallel:   
            t_end = self.ttl0.gate_rising(self.scan_time_sb + 2*ms)
            with sequential:
                self.scan_dds_sb.cpld.io_update.pulse_mu(8) #lane1
                delay(10*ns)
                self.scan_dds_sb.sw.on() #lane1
                delay(10*ns)
                self.scan_dds_car.sw.on() #lane2
                delay(10*ns)
                

            
        t_edge = self.ttl0.timestamp_mu(t_end)
        
        if t_edge >= 0: # timestamp found
            at_mu(t_edge) # set the timeline cursor to time where first edge was found + margin 
            delay(5*us)
            
            # turn off probe
            # self.ttl5.off()
            delay(10*us)
            self.scan_dds_sb.sw.off()
            self.scan_dds_car.sw.off()      
            idx = int((t_edge - t_start) // self.step_mu_sb)
            
            delay(35*us)
            #self.freeze_RAM(self.scan_dds_sb, idx + int(point) ,idx + int(point), self.scan_time_car)
            self.freeze_RAM(self.scan_dds_sb, idx-30 ,idx -30, self.scan_time_car)
            delay(35*us)
            self.freeze_RAM(self.scan_dds_car,0,1023, self.scan_time_car)
            delay(35*us)
            
            #measure
            self.probe_pulse(self.scan_time_car)
          
            with parallel:
                delay(100*us)
                with sequential:
                    #self.freeze_RAM(self.scan_dds_sb, idx + int(point), idx + int(point), self.scan_time_car)
                    self.freeze_RAM(self.scan_dds_sb, idx -62, idx-52, self.scan_time_car)
                    delay(35*us)
                    self.freeze_RAM(self.scan_dds_car,0,1023, self.scan_time_car)
            self.probe_pulse(self.scan_time_car)
                

                  
        delay(10*us)
        self.ttl5.off()
        delay(10*ns)
        self.scan_dds_car.sw.off()
        delay(10*ns)
        self.scan_dds_sb.sw.off()
        
        delay(1*ms)
        if self.Image:
            self.MOTs.take_MOT_image(self.Camera)
            delay(5*ms)
            
        delay(5*ms)
        self.MOTs.Blackman_ramp(self.B_field, 0.0, 30*ms)
        self.MOTs.set_current_dir(0)
        delay(5*ms)
        self.MOTs.AOMs_off_all()
        self.State_Control.AOMs_off_all()
        delay(1*ms)

        self.ttl0.count(t_end) 
        
        delay(10*ms)
        delay(5*s)
        self.core.wait_until_mu(now_mu())        
        return 0
    
    @kernel
    def probe_pulse(self, t):
        self.scan_dds_sb.cpld.io_update.pulse_mu(8)
        delay(10*ns)
        self.ttl5.on()
        delay(10*ns)
        self.scan_dds_car.sw.on()
        self.scan_dds_sb.sw.on()
        
        
        delay(t - 20*ns)
        
        
        self.scan_dds_sb.sw.off()
        self.scan_dds_car.sw.off()
        delay(10*ns)
        self.ttl5.off()

  
        
    def after_measure(self, point, measurement):
        if self.Image: self.Camera.process_image(bg_sub=True)
            
    
    @kernel
    def load_scan(self, dds, freq_center, freq_width, scan_time):
        ## LOAD SIDEBAND SCAN
        step_size = int(scan_time/(1024*4*ns))
        f0 = freq_center + freq_width/2

        # Build descending frequency list
        f_step = freq_width/1023
        for i in range(1024):
            self.freq_list[i] = f0 - f_step*i
            

        dds.frequency_to_ram(self.freq_list, self.freq_list_ram)
        
        self.core.break_realtime()
        delay(10*ms)

        # Disable RAM before programming
        dds.set_cfr1(ram_enable=0)
        dds.cpld.io_update.pulse_mu(8)
        
        delay(5*ms)

        # RAM sweep from index 0 to 1023, profile 0
        dds.set_profile_ram(
            start=0,
            end=1023,
            step=(step_size | (2**6 - 1) << 16),
            profile=0,
            mode=ad9910.RAM_MODE_RAMPUP
        )

        delay(25*ms)
        dds.cpld.set_profile(0)
        dds.cpld.io_update.pulse_mu(8)
        
        
        self.core.break_realtime()
        delay(10*ms)
        dds.write_ram(self.freq_list_ram)
 
        delay(10*ms)

        dds.set_cfr1(
            internal_profile=0,
            ram_enable=1,
            ram_destination=ad9910.RAM_DEST_FTW
        )
        delay(5*ms)
        
        
        self.core.wait_until_mu(now_mu())
        
        
        
        
    @kernel
    def freeze_RAM(self, dds, start_idx, end_idx, scan_time):
        """
        Modify the trigger DDS RAM so that profile 0 consists of a single
        index (idx), effectively "freezing" the DDS at the frequency
        corresponding to the detection time.

        This is called after pulse 1, before pulse 2.
        """
        step_size = int(scan_time/(1024*4*ns))


        dds.set_profile_ram(
            start=start_idx,
            end=end_idx,
            step=(step_size | (2**6 - 1) << 16),
            profile=0,
            mode=ad9910.RAM_MODE_RAMPUP
        )
        dds.cpld.io_update.pulse_mu(8)
        
  
