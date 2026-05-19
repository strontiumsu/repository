# -*- coding: utf-8 -*-
"""
Created on Mon Jan 30 18:16:29 2023

@author: ejporter

Desc: This file contains the class that controls all blue MOT  and red MOT methods (loading, MOT coils, etc.)
"""

# from artiq.experiment import ms, us, MHz, ns
# from artiq.experiment import NumberValue, TInt32
# from artiq.experiment import parallel, sequential, delay, at_mu
# from artiq.experiment import kernel, EnvExperiment
from artiq.experiment import *

from artiq.coredevice import ad9910

import numpy as np
from CameraClass import _Camera
import matplotlib.pyplot as plt

class _Cooling(EnvExperiment):

    def build(self):
        self.setattr_device("core")

        ## TTLs
        self.setattr_device("ttl7") # MOT coil direction
        #self.setattr_device("ttl6") # for switching to single freq channel
        self.setattr_device("ttl1")
        self.setattr_device("ttl5")

        ## AOMS

        # RF synth sources
        self.setattr_device('urukul1_cpld')

        # names for all our AOMs
        self.AOMs = ["3D", "3P0_repump", "3P2_repump", '3D_red']

        # default values for all params for all AOMs
        self.scales = [0.8, 0.8, 0.8, 0.8]
        self.attens = [6.0, 2.0, 6.0, 9.0] 
        self.freqs = [180.0, 210.0, 80.0, 180]

        self.urukul_channels = [self.get_device("urukul1_ch0"),
                                self.get_device("urukul1_ch1"),
                                self.get_device("urukul1_ch2"),
                                self.get_device("urukul1_ch3")]
        
        
        self.aom_3D_blue = self.urukul_channels[0]
        self.aom_3P0 = self.urukul_channels[1]
        self.aom_3P2 = self.urukul_channels[2]
        self.aom_3D_red = self.urukul_channels[3]



        # setting attributes to controll all AOMs
        for i in range(len(self.AOMs)):
            AOM = self.AOMs[i]
            self.setattr_argument(f"scale_{AOM}", NumberValue(self.scales[i], min=0.0, max=0.9), f"{AOM}_AOMs")
            self.setattr_argument(f"atten_{AOM}", NumberValue(self.attens[i], min=1.0, max=30), f"{AOM}_AOMs")
            self.setattr_argument(f"freq_{AOM}", NumberValue(self.freqs[i]*1e6, min=0.5*1e6, max=250*1e6, scale=1e6, unit='MHz'),  f"{AOM}_AOMs")


        ## MOT Coils
        self.setattr_device("zotino0")
        self.dac_0=self.get_device("zotino0")
        
        self.enable_pausing = True # disable to speed up by not checking scheduler
        self.enable_auto_tracking=False
        self.enable_profiling = False # enable to print runtime statistics to find bottlenecks
        

        ### Blue MOT parameters
        self.setattr_argument(
            "bmot_ramp_duration", NumberValue(50.0*1e-3, min=1.0*1e-3,max=100.00*1e-3,scale=1e-3,unit="ms"), "Blue MOT") # ramp duration

        self.setattr_argument("bmot_current", NumberValue(5.0,min=0.0, max=7.0,unit="A"),"Blue MOT") # Pulse amplitude
        
        self.setattr_argument("bmot_load_duration", NumberValue(1000.0*1e-3,min=10.0*1e-3,max=9000.00*1e-3,scale=1e-3,
                      unit="ms"),"Blue MOT") # how long to hold blue mot on to load atoms
        
        self.setattr_argument("Npoints",NumberValue(60,min=0,max=500.00),"Blue MOT")
        
        
        
        
        ### Red MOT parameters
        
        self.setattr_argument("rmot_bb_current",NumberValue(0.4,min=0.0,max=5.00,
                      unit="A"),"Red MOT")  # broadband mot current

        self.setattr_argument("rmot_bb_duration",NumberValue(50.0*1e-3,min=0.0*1e-3,max=300*1e-3,scale = 1e-3,
                      unit="ms"),"Red MOT")  # how long to old broad band

        self.setattr_argument("rmot_ramp_duration",NumberValue(85.0*1e-3,min=0.0,max=200*1e-3,scale = 1e-3,
                      unit="ms"),"Red MOT")  # how long to ramp between bb and sf

        self.setattr_argument("rmot_sf_current",NumberValue(2.0,min=0.0,max=10.0,
                      unit="A"),"Red MOT") # single frequency mot current

        self.setattr_argument("rmot_sf_duration",NumberValue(25.0*1e-3,min=0.0*1e-3,max=300.0*1e-3,scale = 1e-3,
                      unit="ms"),"Red MOT")  # how long to hold atoms in sf red mot
        
        self.setattr_argument("rmot_freq_i", NumberValue(180.5*1e6,min=0.1*1e6, max=200.0*1e6, scale=1e6, unit="MHz", ndecimals = 3), "Red MOT")     
        self.setattr_argument("rmot_freq_depth_i", NumberValue(6*1e6, min=0.0*1e6, max=10.0*1e6, scale=1e6, unit="MHz"), "Red MOT")
        self.setattr_argument("rmot_freq_f", NumberValue(180.0*1e6,min=0.1*1e6, max=200.0*1e6, scale=1e6, unit="MHz", ndecimals = 3), "Red MOT")     
        self.setattr_argument("rmot_freq_depth_f", NumberValue(1.1*1e6, min=0.0*1e6, max=10.0*1e6, scale=1e6, unit="MHz"), "Red MOT")
        self.setattr_argument("nprofiles",NumberValue(7,min=2,max=7),"Red MOT")
        
        
        self.setattr_argument("rmot_scan_frequency", NumberValue(30*1e3, min=10*1e3, max=100*1e3, scale=1e3, unit='kHz'),"Red MOT")
        self.setattr_argument("molasses",BooleanValue(False),"Red MOT")
        self.setattr_argument("molasses_frequency", NumberValue(179.25*1e6, min=10*1e6, max=200*1e6, scale=1e6, unit='MHz'),"Red MOT")

        ## Misc params
        self.setattr_argument("Push_pulse_time",NumberValue(0.9*1e-6,min=0.0*1e6,max=50000.00*1e-3,scale = 1e-6,
                      unit="us"),"Detection")
        self.setattr_argument("Detection_pulse_time",NumberValue(0.02*1e-3,min=0.0,max=100.00*1e-3,scale = 1e-3,
                      unit="ms"),"Detection")
        self.setattr_argument("Delay_duration", NumberValue(800*1e-6,min=0.0*1e-6,max=15000.00*1e-6,scale = 1e-6,
                      unit="us"),"Detection")

        # misc params loaded from dataset
        self.f_MOT3D_detect=self.get_dataset('blue_MOT.f_detect')
        
        self.freq_list= np.linspace(80.0*MHz, 80.0*MHz, 1024)
        self.freq_list_ram = np.full(1024, 1)
  
        
        self.step_size=0


    #<><><><><><><>
    # AOM Functions
    #<><><><><><><>

    def prepare_aoms(self):
        self.scales = [self.scale_3D, self.scale_3P0_repump, self.scale_3P2_repump, self.scale_3D_red]
        self.attens = [self.atten_3D, self.atten_3P0_repump, self.atten_3P2_repump, self.atten_3D_red]
        self.freqs = [self.freq_3D, self.freq_3P0_repump, self.freq_3P2_repump, self.freq_3D_red]
        

    @kernel
    def init_aoms(self, on=False):
        self.core.reset()
        delay(50*ms)
        self.core.break_realtime()
        self.urukul1_cpld.init()

        for i in range(len(self.AOMs)):
            delay(2*ms)

            ch = self.urukul_channels[i]
            ch.init()

            set_f = ch.frequency_to_ftw(self.freqs[i])
            set_asf = ch.amplitude_to_asf(self.scales[i])
            ch.set_mu(set_f, asf=set_asf)
            ch.set_att(self.attens[i])
            if on:
                ch.sw.on()
            else:
                ch.sw.off()
        delay(10*ms)
        self.core.wait_until_mu(now_mu())
          
    @kernel
    def init_ttls(self):
        delay(100*ms)
        #self.ttl6.output()
        self.ttl1.input()
        delay(10*ms)
        #self.ttl6.on()
        
    @kernel
    def line_trigger(self, offset=5*ms):
        # sets start of exp relative to linetrigger
        t_end = self.ttl1.gate_rising(1/60) # ensures we only gate for one cycle
        t_edge = self.ttl1.timestamp_mu(t_end)
    
        if t_edge > 0:
            at_mu(t_edge+self.core.seconds_to_mu(offset))  # Add a tiny buffer to prevent underflow
        
        delay(1*ms)
        self.ttl1.count(t_end) # clears cache
        delay(50*ms)


    @kernel 
    def AOMs_off_all(self):
        self.aom_3D_blue.sw.off()
        self.aom_3P0.sw.off()
        self.aom_3P2.sw.off()
        self.aom_3D_red.sw.off()
        
    @kernel 
    def AOMs_on_all(self):
        self.aom_3D_blue.sw.on()
        self.aom_3P0.sw.on()
        self.aom_3P2.sw.on()
        self.aom_3D_red.sw.on()

    # takes in a tuples of (val, aom_name) to update freq/atten/sf e..g [("AOM1" new_freq1), ("AOM2", new_freq2)]
    @kernel
    def set_AOM_freqs(self, freq_list): # takes in a list of tuples
        with parallel:
            for aom, freq in freq_list:
                ind = self.index_artiq(aom)
                self.freqs[ind] = freq
                ch = self.urukul_channels[ind]
                set_freq = ch.frequency_to_ftw(freq)
                set_asf = ch.amplitude_to_asf(self.scales[ind])
                ch.set_mu(set_freq, asf=set_asf)

    @kernel
    def set_AOM_attens(self, atten_list):
        with parallel:
            for aom, atten in atten_list:
                ind  = self.index_artiq(aom)
                self.attens[ind] = atten
                self.urukul_channels[ind].set_att(atten)

    @kernel
    def set_AOM_scales(self, scale_list):
        with parallel:
            for aom, scale in scale_list:
                ind = self.index_artiq(aom)
                self.scales[ind] = scale
                ch = self.urukul_channels[ind]
                set_freq = ch.frequency_to_ftw(self.freqs[ind])
                set_asf = ch.amplitude_to_asf(self.scales[ind])
                ch.set_mu(set_freq, asf=set_asf)

    ######################################################
    ############### DAC as TTL FUNCTIONS
    ######################################################
    @kernel
    def dac_set(self, ch, val):
        self.dac_0.set_dac([val], [ch])

    # turns the zeeman and 2D off/on via shutter
    @kernel
    def atom_source_on(self):
        self.dac_set(1, 4.0)
        delay(10*us)   
        
    @kernel
    def atom_source_off(self):
        self.dac_set(1, 0.0)
        delay(10*us)
        
    # turns up the probe carrier RF signal
    @kernel
    def carrier_on(self):
        self.dac_set(7, 0.1)
        delay(10*us)
        
        
    @kernel
    def carrier_off(self):
        self.dac_set(7, 0.015)
        delay(10*us)
    
    @kernel 
    def open_688(self):
        self.dac_set(3, 4.0)
        delay(10*us)
        
    @kernel 
    def close_688(self):
        self.dac_set(3, 0.0)
        delay(10*us)
    # 
    @kernel
    def open_461(self):
        delay(-3.0*ms)
        self.dac_set(4, 4.0)
        delay(3.0*ms)
        delay(5*us)

    # 
    @kernel
    def close_461(self):
        delay(-2.5*ms)
        self.dac_set(4, 0.0)
        delay(2.5*ms)
        delay(5*us)

    @kernel
    def cavity_res_on(self):
        self.dac_set(6, 0.0)
        delay(10*us)
        
    @kernel
    def cavity_res_off(self):
        self.dac_set(6, 1.0)
        delay(10*us)
    #<><><><><><><><>
    # Coil Functions
    #<><><><><><><><>

    def prepare_coils(self):
        self.Npoints += (1-self.Npoints%2) # ensures off number of points
        self.window = np.blackman(self.Npoints)
        self.dt = self.bmot_ramp_duration/((self.Npoints+1)//2)


    @kernel
    def init_coils(self):
        self.dac_0.init() # initialize DAC that controls setpoint
        delay(5*ms)
        self.ttl7.off()  # puts in MOT config

    # sets to 0 current
    @kernel
    def coils_off(self):
        self.set_current(0.0)

    # sets MOT current
    @kernel
    def set_current(self, cur):
        if cur > 8:
            raise Exception("Current too high!")
        else:
            self.dac_set(0, cur)
            
    

    # switches between MOT configs
    @kernel
    def set_current_dir(self, direc):

        assert direc in [0,+1]

        self.coils_off() # turn off current
        delay(15*ms) # wait for current to settle

        if direc == 0: self.ttl7.off() # set appropriate direction
        else: self.ttl7.on()

        delay(1*ms)

    @kernel
    def Blackman_ramp_up(self, cur=-1.0):
        if cur == -1.0: cur = self.bmot_current
        for step in range(0, int((self.Npoints+1)//2)):
            self.dac_set(0, cur*self.window[step])
            delay(self.dt)

    @kernel
    def Blackman_ramp_down(self, cur=-1.0, time=-1.0):
        if cur == -1.0: cur = self.bmot_current
        if time==-1.0: 
            dt = self.dt
        else: 
            dt= time/((self.Npoints-1)//2)
        
        for step in range(int((self.Npoints+1)//2), int(self.Npoints)):
            self.dac_set(0, cur*self.window[step])
            delay(dt)
    
    @kernel
    def Blackman_ramp_down_set(self, cur, final, time):
        dt_ramp = time/((self.Npoints-1)//2)
        for step in range(int((self.Npoints+1)//2), int(self.Npoints)):            
            self.dac_set(0, final + (cur-final)*self.window[step])
            delay(dt_ramp)

    @kernel
    def linear_ramp_down_capture(self, time):
        dt = time/self.Npoints
        for step in range(int(self.Npoints)):
            self.dac_set(0, self.bmot_current+((self.rmot_bb_current-self.bmot_current)/time)*step*dt)
            delay(dt)

    @kernel
    def linear_ramp(self, bottom, top, time, Npoints):
        dt = time/Npoints
        for step in range(1, int(Npoints)):
            self.dac_set(0, bottom + (top-bottom)/time*step*dt)
            delay(dt)


    @kernel
    def Blackman_ramp(self, start, end, time):
        assert (start >= 0) and (end >= 0) and (start <= 7.0) and (end <= 7.0)
        dt_ramp = time/((self.Npoints-1)//2) # step size
        
        
        # ramp up
        if end > start:        
            for step in range(int((self.Npoints+1)//2)):            
                self.dac_set(0, start + (end-start)*self.window[step])
                delay(dt_ramp)
        
        #ramp down
        elif end < start:
            for step in range(int((self.Npoints-1)//2), int(self.Npoints)):            
                self.dac_set(0, end + (start-end)*self.window[step])
                delay(dt_ramp)
        
    

    @kernel
    def hold(self, time):
        delay(time)
        
        
    #<><><><><><><><><><><>
    # DDS scanning Functions
    #<><><><><><><><><><><>
    
    @kernel
    def init_rmot_dds(self, rmot_freq_i=180.5*MHz, rmot_freq_f=180.5*MHz, rmot_freq_depth_i=5.0*MHz, rmot_freq_depth_f=0.5*MHz, rmot_sf_freq=180.0*MHz):
        self.core.reset()
        delay(10*ms)
        f0_i=rmot_freq_i
        f0_f=rmot_freq_f 
        depth_i=rmot_freq_depth_i
        depth_f=rmot_freq_depth_f 
        
        
        flength = int(1022/self.nprofiles)
        self.step_size = int((1/self.rmot_scan_frequency)/(flength*4*ns)) # save last 2 entries entry for single freq mode
        
        # write in sf mode freqs
        self.freq_list[-2] = rmot_sf_freq #[self.freq_3D_red]*2
        self.freq_list[-1] = rmot_sf_freq

        
        for p in range(int(self.nprofiles)):

            fstart = f0_i + (f0_f-f0_i)*(p/(self.nprofiles-1)) - (depth_i + (depth_f-depth_i)*(p/(self.nprofiles-1)))
            fend = f0_i + (f0_f-f0_i)*(p/(self.nprofiles-1))
            
            for f_ind in range(flength):
                self.freq_list[p*flength + f_ind] = fend + (fstart-fend) * f_ind/(flength-1)
                

        self.aom_3D_red.frequency_to_ram(self.freq_list, self.freq_list_ram)

        
        self.core.break_realtime()
        delay(10 * ms)
        
        #urn off RAM mode to prepare to write
        self.aom_3D_red.set_cfr1(ram_enable=0)
        self.aom_3D_red.cpld.io_update.pulse_mu(8)
        

        
        # write in  nprofiles worth of RAM split over 1022 RAM entries
        flength = int(1022/self.nprofiles)
        for p in range(int(self.nprofiles)):
            delay(1*ms)
            self.aom_3D_red.set_profile_ram(
            start=p*flength, end=(p+1)*flength-1, step=(int(self.step_size) | (2**6 - 1 ) << 16),
            profile=p, mode=ad9910.RAM_MODE_CONT_RAMPUP)
        delay(1*ms)
        
        # write in the signal frequency stage directly
        self.aom_3D_red.set_profile_ram(
            start=1022, end=1024-1, step=(int(self.step_size) | (2**6 - 1 ) << 16),
            profile=7, mode=ad9910.RAM_MODE_CONT_RAMPUP)
        
        # write ram entries for scanning ram sections
        for p in range(int(self.nprofiles)):
            delay(5*ms)
            self.aom_3D_red.cpld.set_profile(p)
            self.aom_3D_red.cpld.io_update.pulse_mu(8)
           # print("writing RAM with following first few values:", self.freq_list_ram[:4])
            self.aom_3D_red.write_ram(self.freq_list_ram[p*flength:(p+1)*flength]) 

        # write in RAM for fixed profile 7 
        delay(5*ms)
        self.aom_3D_red.cpld.set_profile(7)
        self.aom_3D_red.cpld.io_update.pulse_mu(8)
        self.aom_3D_red.write_ram(self.freq_list_ram[-2:]) 
        
        # get ready by setting to profile 0 and queueing up RAM mode
        delay(1*ms)
        self.aom_3D_red.cpld.set_profile(0)
        delay(50*ms)
        
        self.aom_3D_red.set_cfr1(ram_enable=1, ram_destination=ad9910.RAM_DEST_FTW)
        self.aom_3D_red.cpld.io_update.pulse_mu(8)
        delay(10*ms)
        self.core.wait_until_mu(now_mu())
        
            
    @kernel
    def init_rmot_dds_new(self, rmot_freq_i=180.5*MHz, rmot_freq_f=180.5*MHz, rmot_freq_depth_i=5.0*MHz, rmot_freq_depth_f=0.5*MHz, rmot_sf_freq=180.0*MHz):
        self.core.reset()
        delay(10*ms)
        f0_i=rmot_freq_i
        f0_f=rmot_freq_f 
        depth_i=rmot_freq_depth_i
        depth_f=rmot_freq_depth_f 
        
        
        flength = int(1022/self.nprofiles)
        self.step_size = int((1/self.rmot_scan_frequency)/(flength*4*ns)) # save last 2 entries entry for single freq mode
        
        # write in sf mode freqs
        self.freq_list[0] = rmot_sf_freq #[self.freq_3D_red]*2
        self.freq_list[1] = rmot_sf_freq

        
        for p in range(int(self.nprofiles)):

            fstart = f0_i + (f0_f-f0_i)*(p/(self.nprofiles-1)) - (depth_i + (depth_f-depth_i)*(p/(self.nprofiles-1)))
            fend = f0_i + (f0_f-f0_i)*(p/(self.nprofiles-1))
            
            for f_ind in range(flength):
                self.freq_list[p*flength + f_ind + 2] = fend + (fstart-fend) * f_ind/(flength-1)
                

        self.aom_3D_red.frequency_to_ram(self.freq_list, self.freq_list_ram)

        
        self.core.break_realtime()
        delay(10 * ms)
        
        #urn off RAM mode to prepare to write
        self.aom_3D_red.set_cfr1(ram_enable=0)
        self.aom_3D_red.cpld.io_update.pulse_mu(8)
        

        # write in the signal frequency stage directly
        self.aom_3D_red.set_profile_ram(
            start=0, end=1, step=(int(self.step_size) | (2**6 - 1 ) << 16),
            profile=0, mode=ad9910.RAM_MODE_CONT_RAMPUP)
        
        # write in  nprofiles worth of RAM split over 1022 RAM entries
        flength = int(1022/self.nprofiles)
        for p in range(int(self.nprofiles)):
            delay(1*ms)
            self.aom_3D_red.set_profile_ram(
            start=p*flength+2, end=(p+1)*flength-1+2, step=(int(self.step_size) | (2**6 - 1 ) << 16),
            profile=p+1, mode=ad9910.RAM_MODE_CONT_RAMPUP)
        delay(1*ms)
        
        
        
        # write ram entries for scanning ram sections
        for p in range(int(self.nprofiles)):
            delay(5*ms)
            self.aom_3D_red.cpld.set_profile(p+1)
            self.aom_3D_red.cpld.io_update.pulse_mu(8)
           # print("writing RAM with following first few values:", self.freq_list_ram[:4])
            self.aom_3D_red.write_ram(self.freq_list_ram[p*flength+2:(p+1)*flength+2]) 

        # write in RAM for fixed profile 7 
        delay(5*ms)
        self.aom_3D_red.cpld.set_profile(0)
        self.aom_3D_red.cpld.io_update.pulse_mu(8)
        self.aom_3D_red.write_ram(self.freq_list_ram[0:2]) 
        
        # get ready by setting to profile 0 and queueing up RAM mode
        delay(1*ms)
        self.aom_3D_red.cpld.set_profile(0)
        delay(50*ms)
        
        self.aom_3D_red.set_cfr1(ram_enable=1, ram_destination=ad9910.RAM_DEST_FTW)
        self.aom_3D_red.cpld.io_update.pulse_mu(8)
        delay(10*ms)
        self.core.wait_until_mu(now_mu())
    

    #<><><><><><><><><><><>
    # General MOT Functions
    #<><><><><><><><><><><>

    @kernel
    def bMOT_pulse(self):
        self.atom_source_on()
        # turn on 3D, and repumps
        self.aom_3D_blue.sw.on()
        self.aom_3P0.sw.on()
        self.aom_3P2.sw.on()
        
        self.Blackman_ramp_up()
        self.hold(self.bmot_load_duration)
        self.Blackman_ramp_down()
        
        # turn on 3D, and repumps
        self.aom_3D_blue.sw.off()
        self.aom_3P0.sw.off()
        self.aom_3P2.sw.off()
        self.atom_source_off()
        
    @kernel
    def bMOT_pulse_shield(self, shield_freq = 180.6*MHz, shield_scale=0.8):
        self.atom_source_on()
        # turn on 3D, and repumps
        self.aom_3D_blue.sw.on()
        self.aom_3P0.sw.on()
        self.aom_3P2.sw.on()
        
        self.aom_3D_red.set_att(self.atten_3D_red)
        self.aom_3D_red.set(frequency=shield_freq, amplitude=shield_scale)
        
        self.Blackman_ramp_up()
        self.hold(self.bmot_load_duration)
        
        self.aom_3D_red.sw.on()
        self.hold(self.bmot_load_duration)
        self.aom_3D_red.sw.off()
        
        # turn on 3D, and repumps
        # self.aom_3D_blue.sw.off()
        # self.aom_3P0.sw.off()
        # self.aom_3P2.sw.off()
        # self.atom_source_off()
        
        # self.set_current(0.0)
        
        

    @kernel
    def bMOT_load(self):
        self.atom_source_on()
        # turn on 3D, and repumps
        self.aom_3D_blue.sw.on()
        self.aom_3P0.sw.on()
        self.aom_3P2.sw.on()
        
        self.set_current_dir(0)
        self.Blackman_ramp_up()
        self.hold(self.bmot_load_duration)


    @kernel 
    def rMOT_pulse_new(self, sf=False, atten_scale_factor=3.0, sf_amp = 0.05, dipole_on = True):
        self.atom_source_on() # opens on zeeman and 2D shutters
        self.close_688() # close 688 shutter to prevent leakage from optical pumping
        self.aom_3D_blue.set_att(self.atten_3D)
        self.aom_3D_red.set_att(self.atten_3D_red)
        self.aom_3D_red.set_amplitude(0.8)

        self.urukul1_cpld.set_profile(0)

        
        # turn on 3D, and repumps
        self.aom_3D_blue.sw.on()
        self.aom_3P0.sw.on()
        self.aom_3P2.sw.on()
        
        # turn to MOT mode
        self.set_current_dir(0)
        
        #ramp up bmot bfield and hold for load duration
        self.Blackman_ramp(0.0, self.bmot_current, self.bmot_ramp_duration)
        delay(self.bmot_load_duration)
        
        
       # line trigger for consistent time relative to mains
        self.line_trigger()
        delay(150*ms)
        
        # turn on broad band red mot (profile 0)
        self.aom_3D_red.cpld.io_update.pulse_mu(8)
        delay(5*us)
        self.aom_3D_red.sw.on()
        
        # ramp up blue MOT current and attenuation
        tramp = 50*ms
        binc = 1.0

        dt = tramp/int(self.Npoints)
        for step in range(1, int(self.Npoints)):
            self.dac_set(0,  self.bmot_current + binc/tramp*step*dt)
            self.aom_3D_blue.set_att(6+24*step/int(self.Npoints))
            delay(dt)

        # turn off blue light
        self.atom_source_off()
        self.aom_3D_blue.sw.off()
        delay(0.5*us)
        
        # ramp up to broad band red mot current and hold`
        self.Blackman_ramp(self.bmot_current + binc, self.rmot_bb_current, 15*ms)
        delay(self.rmot_bb_duration)
        
        # turn off repumpers
        self.aom_3P0.sw.off()
        self.aom_3P2.sw.off()
        
        with parallel:
            self.linear_ramp(self.rmot_bb_current, self.rmot_sf_current, self.rmot_ramp_duration, self.Npoints)
            with sequential:
                for p in range(int(self.nprofiles)):
                    self.aom_3D_red.cpld.set_profile(p)
                    self.aom_3D_red.set_att(self.atten_3D_red+atten_scale_factor*p)
                    delay(self.rmot_ramp_duration/self.nprofiles)

        # switch to single frequency mode then hold        
        if sf:
            self.aom_3D_red.cpld.set_profile(7)
            self.aom_3D_red.set_amplitude(sf_amp)
            self.aom_3D_red.set_att(30.0)
            delay(self.rmot_sf_duration)
        self.aom_3D_red.sw.off()
        delay(10*us) #Makes sure that the aom is fully switched off before the magnetic field ramps down.
        self.urukul1_cpld.set_profile(0)
        
        if dipole_on == True:
            self.Blackman_ramp(self.rmot_sf_current, 0.0, 5*ms)
        else:
            self.coils_off()
        
        self.open_688() # open 688 shutter to allow for excitation
        

        
    @kernel 
    def rMOT_pulse_shield(self, shield_amp = 0.8, dipole_on = False):
        self.atom_source_on() # opens on zeeman and 2D shutters
        self.close_688() # close 688 shutter to prevent leakage from optical pumping
        self.aom_3D_blue.set_att(self.atten_3D)
        self.aom_3D_red.set_att(self.atten_3D_red)
        self.aom_3D_red.set_amplitude(0.8)

        self.urukul1_cpld.set_profile(0)

        
        # turn on 3D, and repumps
        self.aom_3D_blue.sw.on()
        self.aom_3P0.sw.on()
        self.aom_3P2.sw.on()
        
        #turn on shield beams
        self.aom_3D_red.cpld.io_update.pulse_mu(8)
        delay(5*us)
        self.aom_3D_red.set_amplitude(shield_amp)
        self.aom_3D_red.sw.on()
        
        
        # turn to MOT mode
        self.set_current_dir(0)
        
        #ramp up bmot bfield and hold for load duration
        self.Blackman_ramp(0.0, self.bmot_current, self.bmot_ramp_duration)
        delay(self.bmot_load_duration)
        
        
       # line trigger for consistent time relative to mains
        self.line_trigger()
        delay(150*ms)
        
        self.aom_3D_red.sw.off()
        # ramp up blue MOT current and attenuation
        tramp = 50*ms
        binc = 1.0

        dt = tramp/int(self.Npoints)
        for step in range(1, int(self.Npoints)):
            self.dac_set(0,  self.bmot_current + binc/tramp*step*dt)
            self.aom_3D_blue.set_att(6+24*step/int(self.Npoints))
            delay(dt)

        # turn off blue light
        self.atom_source_off()
        self.aom_3D_blue.sw.off()
        
        # turn on broad band red mot (profile 0)
        self.aom_3D_red.cpld.set_profile(1)
        self.aom_3D_red.set_amplitude(0.8)
        self.aom_3D_red.sw.on()
        delay(5*us)        
        # ramp up to broad band red mot current and hold`
        self.Blackman_ramp(self.bmot_current + binc, self.rmot_bb_current, 15*ms)
        delay(self.rmot_bb_duration)
        
        # turn off repumpers
        self.aom_3P0.sw.off()
        self.aom_3P2.sw.off()
        
        atten_scale_factor=3.0
        with parallel:
            self.linear_ramp(self.rmot_bb_current, self.rmot_sf_current, self.rmot_ramp_duration, self.Npoints)
            with sequential:
                for p in range(int(self.nprofiles)):
                    self.aom_3D_red.cpld.set_profile(p+1)
                    self.aom_3D_red.set_att(self.atten_3D_red+atten_scale_factor*p)
                    delay(self.rmot_ramp_duration/self.nprofiles)


        self.aom_3D_red.sw.off()
        delay(10*us) #Makes sure that the aom is fully switched off before the magnetic field ramps down.
        self.urukul1_cpld.set_profile(0)
        
        if dipole_on == True:
            self.Blackman_ramp(self.rmot_sf_current, 0.0, 5*ms)
        else:
            self.coils_off()
        
        self.open_688() # open 688 shutter to allow for excitation
        
        
    @kernel 
    def molasses_pulse(self, freq=179*MHz, amp = 0.1, t = 40*ms):
        self.aom_3D_red.set_cfr1(ram_enable=0)
        self.aom_3D_red.cpld.io_update.pulse_mu(8)
        self.aom_3D_red.set(frequency=freq, amplitude=amp) # change rMOT beams to be constant frequency
        self.aom_3D_red.sw.on()
        delay(t)
        self.aom_3D_red.sw.off()
                   

    @kernel
    def take_background_image_exp(self, cam):     
        self.take_MOT_image(cam)

        delay(100*ms) # give imaging some time
        self.core.wait_until_mu(now_mu()) # wait to ensure image has been taken before processing background
        cam.process_background()            
        self.core.break_realtime() # break realtime after rpc
        delay(10*ms) 

    @kernel
    def take_MOT_image(self, cam):
        """
        Takes an image of the MOT using the 3D blue beams for imaging. 
        Repumpers are turned on to ensure all atoms are in the ground 
        state. Camera is triggered in parallel with the imaging pulse.
        """

        # prepare imaging AOMs
        self.AOMs_off_all()
        self.aom_3D_blue.set(frequency=self.f_MOT3D_detect,amplitude=0.8)
        self.aom_3D_blue.set_att(6.0)
        
        # turn on repumpers
        self.aom_3P0.sw.on()
        self.aom_3P2.sw.on()
        # trigger camera and pulse imaging light in parallel
        with parallel:
            cam.trigger_camera()
            with sequential:   
                self.aom_3D_blue.sw.on()           
                delay(self.Detection_pulse_time)
                self.aom_3D_blue.sw.off()
            delay(cam.Exposure_Time)

        # turn off repumpers
        self.aom_3P0.sw.off()
        self.aom_3P2.sw.off()
        
        # turn aom back to default settings for MOT loading
        self.aom_3D_blue.set(frequency=self.freq_3D,amplitude=0.8)
        self.aom_3D_blue.set_att(self.atten_3D)
        



