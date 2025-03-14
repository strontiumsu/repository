# -*- coding: utf-8 -*-
"""
Created on Mon Jan 30 18:16:29 2023

@author: ejporter

Desc: This file contains the class that controls all blue MOT  and red MOT methods (loading, MOT coils, etc.)
"""

from artiq.experiment import ms, us, MHz
from artiq.experiment import NumberValue, TInt32
from artiq.experiment import parallel, sequential, delay, at_mu
from artiq.experiment import kernel, EnvExperiment

import numpy as np


class _Cooling(EnvExperiment):

    def build(self):
        self.setattr_device("core")

        ## TTLs
        #self.setattr_device("ttl0") # shutter TTLs (2D and zeeman)
        self.setattr_device("ttl7") # MOT coil direction
        self.setattr_device("ttl6") # for switching to single freq channel
        self.setattr_device("ttl1")

        ## AOMS

        # RF synth sources
        self.setattr_device('urukul1_cpld')

        # names for all our AOMs
        self.AOMs = ["3D", "3P0_repump", "3P2_repump", '3D_red']

        # default values for all params for all AOMs
        self.scales = [0.8, 0.8, 0.8, 0.8]
        self.attens = [6.0, 2.0, 6.0, 16.0] 
        self.freqs = [180.0, 210.0, 80.0, 180]

        self.urukul_channels = [self.get_device("urukul1_ch0"),
                                self.get_device("urukul1_ch1"),
                                self.get_device("urukul1_ch2"),
                                self.get_device("urukul1_ch3")]



        # setting attributes to controll all AOMs
        for i in range(len(self.AOMs)):
            AOM = self.AOMs[i]
            self.setattr_argument(f"scale_{AOM}", NumberValue(self.scales[i], min=0.0, max=0.9), f"{AOM}_AOMs")
            self.setattr_argument(f"atten_{AOM}", NumberValue(self.attens[i], min=1.0, max=30), f"{AOM}_AOMs")
            self.setattr_argument(f"freq_{AOM}", NumberValue(self.freqs[i]*1e6, min=0.5*1e6, max=250*1e6, scale=1e6, unit='MHz'),  f"{AOM}_AOMs")


        ## MOT Coils
        self.setattr_device("zotino0")
        self.dac_0=self.get_device("zotino0")

        self.setattr_argument(
            "bmot_ramp_duration",
                NumberValue(
                50.0*1e-3,
                min=1.0*1e-3,
                max=100.00*1e-3,
                scale=1e-3,
                unit="ms"
                ),
            "MOT coil driver") # ramp duration

        self.setattr_argument(
            "bmot_current",
                NumberValue(
                5.0,
                min=0.0,
                max=10.0,
                unit="A"
                ),
            "MOT coil driver") # Pulse amplitude

        self.setattr_argument("bmot_load_duration", NumberValue(1000.0*1e-3,min=10.0*1e-3,max=9000.00*1e-3,scale=1e-3,
                      unit="ms"),"MOT coil driver") # how long to hold blue mot on to load atoms

        self.setattr_argument("rmot_bb_current",NumberValue(0.5,min=0.0,max=5.00,
                      unit="A"),"MOT coil driver")  # broadband mot current

        self.setattr_argument("rmot_bb_duration",NumberValue(100.0*1e-3,min=0.0*1e-3,max=100*1e-3,scale = 1e-3,
                      unit="ms"),"MOT coil driver")  # how long to old broad band

        self.setattr_argument("rmot_ramp_duration",NumberValue(100.0*1e-3,min=0.0,max=200*1e-3,scale = 1e-3,
                      unit="ms"),"MOT coil driver")  # how long to ramp between bb and sf

        self.setattr_argument("rmot_sf_current",NumberValue(2.0,min=0.0,max=10.0,
                      unit="A"),"MOT coil driver") # single frequency mot current

        self.setattr_argument("rmot_sf_duration",NumberValue(25.0*1e-3,min=0.0*1e-3,max=300.0*1e-3,scale = 1e-3,
                      unit="ms"),"MOT coil driver")  # how long to hold atoms in sf red mot

        self.setattr_argument("Npoints",NumberValue(60,min=0,max=100.00),"MOT coil driver")


        ## Misc params
        self.setattr_argument("Push_pulse_time",NumberValue(0.7*1e-6,min=0.0*1e6,max=50000.00*1e-3,scale = 1e-6,
                      unit="us"),"Detection")
        self.setattr_argument("Detection_pulse_time",NumberValue(0.1*1e-3,min=0.0,max=100.00*1e-3,scale = 1e-3,
                      unit="ms"),"Detection")
        self.setattr_argument("Delay_duration", NumberValue(1000*1e-6,min=0.0*1e-6,max=15000.00*1e-6,scale = 1e-6,
                      unit="us"),"Detection")

        # misc params loaded from dataset
        self.f_MOT3D_detect=self.get_dataset('blue_MOT.f_detect')


    #<><><><><><><>
    # AOM Functions
    #<><><><><><><>

    def prepare_aoms(self):
        self.scales = [self.scale_3D, self.scale_3P0_repump, self.scale_3P2_repump, self.scale_3D_red]
        self.attens = [self.atten_3D, self.atten_3P0_repump, self.atten_3P2_repump, self.atten_3D_red]
        self.freqs = [self.freq_3D, self.freq_3P0_repump, self.freq_3P2_repump, self.freq_3D_red]


    @kernel
    def init_aoms(self, on=False):

        delay(50*ms)
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
        delay(50*ms)


    @kernel
    def init_ttls(self):
        delay(100*ms)
        self.ttl6.output()
        self.ttl1.input()
        delay(10*ms)
        self.ttl6.on()
        
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


    # turns AOMs on/off via RF switch
    @kernel
    def AOMs_on(self, AOMs):
        with parallel:
            for aom in AOMs:
                self.urukul_channels[self.index_artiq(aom)].sw.on()

    @kernel
    def AOMs_off(self, AOMs):
        with parallel:
            for aom in AOMs:
                self.urukul_channels[self.index_artiq(aom)].sw.off()



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



    # turns the zeeman and 2D off/on via shutter
    @kernel
    def atom_source_on(self):
        #self.ttl0.on()
        self.dac_set(1, 4.0)
    @kernel
    def atom_source_off(self):
        self.dac_set(1, 0.0)
        #self.ttl0.off()



    #<><><><><><><><>
    # Coil Functions
    #<><><><><><><><>

    def prepare_coils(self):
        self.Npoints += (1-self.Npoints%2)
        self.window = np.blackman(self.Npoints)
        self.dt = self.bmot_ramp_duration/((self.Npoints-1)//2)


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

        #is this right?
        assert direc in [0,+1]

        self.coils_off() # turn off current
        delay(20*ms) # wait for current to settle

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
    def Blackman_ramp_down(self, cur=-1.0):
        if cur == -1.0: cur = self.bmot_current
        for step in range(int((self.Npoints+1)//2), int(self.Npoints)):
            self.dac_set(0, cur*self.window[step])
            delay(self.dt)


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
    def dac_set(self, ch, val):
        self.dac_0.write_dac(ch, val)
        self.dac_0.load()

    @kernel
    def hold(self, time):
        delay(time)

    #<><><><><><><><><><><>
    # General MOT Functions
    #<><><><><><><><><><><>

    @kernel
    def bMOT_pulse(self):
        self.atom_source_on()
        self.AOMs_on(["3D", "3P0_repump", "3P2_repump"])
        self.Blackman_ramp_up()
        self.hold(self.bmot_load_duration)
        self.Blackman_ramp_down()
        self.AOMs_off(["3D", "3P0_repump", "3P2_repump"])
        self.atom_source_off()

    @kernel
    def bMOT_load(self):
        self.atom_source_on()
        self.AOMs_on(["3D", "3P0_repump", "3P2_repump"])
        self.set_current_dir(0)
        self.Blackman_ramp_up()
        self.hold(self.bmot_load_duration)

    @kernel
    def rMOT_pulse(self, sf = True):
        # self.core.break_realtime()
        # delay(1*ms)

        self.atom_source_on()
        self.AOMs_on(["3D", "3P0_repump", "3P2_repump"])
        self.set_current_dir(0)
        # self.dac_0.write_dac(1, 9.9) #dont think we need this anymore
        # self.dac_0.load()
        # delay(5*ms)
        # self.ttl6.off() # moved this line to after bmot loading to keep bb red light off
        self.Blackman_ramp_up()
        self.hold(self.bmot_load_duration)
        
        # line trigger
        #self.line_trigger()
        #delay(25*ms)

        ### Ramp transfer sequence
        self.ttl6.off() #start in broadband mode
        tramp = 100*ms
        dt = tramp/int(self.Npoints)
        for step in range(1, int(self.Npoints)):
            self.dac_0.write_dac(0, self.bmot_current + 1.0/tramp*step*dt)
            self.dac_0.load()
            self.set_AOM_attens([("3D",6+10*step/int(self.Npoints))])
            delay(dt)
        self.dac_0.write_dac(0, self.bmot_current + 1.0)
        self.dac_0.load()
        ##########################

        #with parallel:
        self.atom_source_off()
        self.AOMs_off(['3D'])
        delay(0.5*us)

        self.set_current(self.rmot_bb_current)


        delay(self.rmot_bb_duration)

        self.AOMs_off(["3P0_repump","3P2_repump"])
        self.AOMs_on(["3D_red"])
        self.linear_ramp(self.rmot_bb_current, self.rmot_sf_current, self.rmot_ramp_duration, self.Npoints)


        ### Signle-frequency transfer sequence
        # self.ttl6.on() #switch to single frequency with RF switch
        # if sf:
        #     tramp = 20*ms
        #     dt = tramp/10
        #     for step in range(1, 11):
        #         self.set_AOM_freqs([("3D_red",self.freq_3D_red-(1-step/10)*1*MHz)])
        #         delay(dt/2)
        #         self.set_AOM_attens([("3D_red",4+10*step/10)])
        #         delay(dt/2)
        #     delay(self.rmot_sf_duration)

        self.ttl6.on() #switch to single frequency with RF switch
        if sf:
            delay(self.rmot_sf_duration)

        self.AOMs_off(["3D_red"])

        self.set_current(0.0)

    @kernel
    def take_background_image_exp(self, cam):
        cam.arm()
        delay(150*ms)
        self.take_MOT_image(cam)
        delay(150*ms)
        cam.process_background()

    @kernel
    def take_image_exp(self, cam):
        cam.trigger_camera()
        delay(cam.Exposure_Time)

    @kernel
    def take_MOT_image(self, cam):
        self.atom_source_off()
        self.AOMs_off(['3P0_repump', '3P2_repump', '3D','3D_red'])
        self.set_AOM_freqs([('3D', self.f_MOT3D_detect)])
        self.set_AOM_attens([('3D', 6.0)])
        delay(1*ms)
        with parallel:
            cam.trigger_camera()
            with sequential:
                #self.AOMs_on(['3P0_repump', '3P2_repump', '3D'])
                self.AOMs_on(['3D'])
                delay(self.Detection_pulse_time)
                self.AOMs_off(['3D'])
            delay(cam.Exposure_Time)
        self.set_AOM_freqs([('3D', self.freq_3D)])
        self.set_AOM_attens([('3D', self.atten_3D)])
        self.AOMs_off(['3P0_repump', '3P2_repump'])



    def index_artiq(self, aom) -> TInt32:
        for i in range(len(self.AOMs)):
            if self.AOMs[i] == aom:
                return i
        raise Exception("No AOM with that name")


    # @kernel
    # def rMOT_pulse(self):
    #     self.core.break_realtime()
    #     self.ttl5.on()  # make sure moglabs ch1 off
    #     self.atom_source_on()
    #     self.AOMs_on(["3D", "3P0_repump", "3P2_repump"])
    #     self.set_current_dir(0)
    #     self.dac_0.write_dac(1, 9.9) #set initial detuning
    #     self.dac_0.load()
    #     delay(5*ms)
    #     self.ttl5.off()  # switch on  broadband mode (ch1)
    #     self.Blackman_ramp_up()
    #     self.hold(self.bmot_load_duration)

    #     ### Ramp transfer sequence
    #     tramp = 100*ms
    #     dt = tramp/int(self.Npoints)
    #     for step in range(1, int(self.Npoints)):
    #         self.dac_0.write_dac(0, self.bmot_current + 1.0/tramp*step*dt)
    #         self.dac_0.load()
    #         self.set_AOM_attens([("3D",6+10*step/int(self.Npoints))])
    #         delay(dt)
    #     self.dac_0.write_dac(0, self.bmot_current + 1.0)
    #     self.dac_0.load()
    #     ##########################

    #     #with parallel:
    #     self.atom_source_off()
    #     self.AOMs_off(['3D'])
    #     delay(0.5*us)

    #     self.set_current(self.rmot_bb_current)

    #     delay(self.rmot_bb_duration)

    #     self.AOMs_off(["3P0_repump","3P2_repump"])
    #     self.linear_ramp(self.rmot_bb_current, self.rmot_sf_current, self.rmot_ramp_duration, self.Npoints)

    #     #self.bb_det_ramp(self.rmot_ramp_duration/2, self.Npoints)

    #     with parallel:
    #         self.ttl5.on()
    #         self.ttl6.on()

    #     delay(self.rmot_sf_duration)
    #     self.ttl6.off()
    #     self.set_current(0.0)


    # @kernel
    # def bb_det_ramp(self, time, Npoints):
    #     dt = time/Npoints
    #     for step in range(1, int(Npoints)):
    #         self.dac_0.write_dac(1,9.9*(1-step*dt/time)+0.1)
    #         self.dac_0.load()
    #         delay(dt)
    #
    # @kernel
    # def bb_det_pow_ramp(self, time, Npoints):
    #     dt = time/Npoints
    #     for step in range(1, int(Npoints)):
    #         self.dac_0.write_dac(1,9.9*(1-step*dt/time)+0.1)
    #         self.dac_0.write_dac(2,-0.6+1.4*(1-step*dt/time))
    #         self.dac_0.load()
    #         delay(dt)
    #
    #
    # @kernel
    # def bb_capture_ramps(self, d0, df, ddev0, ddevf, time, Npoints):
    #     dt = time/Npoints
    #     self.set_current(self.rmot_bb_current)
    #     for step in range(1, int(Npoints)):
    #         self.dac_0.write_dac(1, 0.143*(d0 + (df-d0)/time*step*dt))
    #         self.dac_0.write_dac(2, -0.0358*(ddev0 + (ddevf-ddev0)/time*step*dt)+1.2)
    #         self.dac_0.load()
    #         delay(dt)
    #
    # @kernel
    # def bb_compression_ramp(self, d0, df, ddev0, ddevf, time, Npoints):
    #     dt = time/Npoints
    #     self.set_current(self.rmot_sf_current)
    #     for step in range(1, int(Npoints)):
    #         self.dac_0.write_dac(0, self.rmot_bb_current + (self.rmot_sf_current-self.rmot_bb_current)/time*step*dt)
    #         self.dac_0.write_dac(1, 0.143*(d0 + (df-d0)/time*step*dt))
    #         self.dac_0.write_dac(2, -0.0358*(ddev0 + (ddevf-ddev0)/time*step*dt)+1.2)
    #         self.dac_0.load()
    #         delay(dt)
    #
    # @kernel
    # def freq_ramp(self, amp, time, Npoints):
    #     dt = time/Npoints
    #     for step in range(1, int(Npoints)):
    #         self.dac_0.write_dac(2, amp - 2*amp/time*step*dt)
    #         self.dac_0.load()
    #         delay(dt)
    #     self.dac_0.write_dac(2, amp)
    #     self.dac_0.load()
    #
    # @kernel
    # def cavity_ramp(self, amp, time, Npoints):
    #     dt = time/Npoints
    #     for step in range(1, int(Npoints)):
    #         self.dac_0.write_dac(3, 8.65 - amp/2 + amp*step*dt/time)
    #         self.dac_0.load()
    #         delay(dt)
    #     self.dac_0.write_dac(3, 8.65)
    #     self.dac_0.load()
    #
    # @kernel
    # def cavity_scan_trig(self):
    #     self.dac_0.write_dac(3, 5.0)
    #     self.dac_0.load()
    #     delay(4*ms)
    #     self.dac_0.write_dac(3, 0.0)
    #     self.dac_0.load()


    # @kernel
    # def rMOT_broadband_pulse(self, time):
    #     self.core.break_realtime()
    #     self.ttl5.on()  # make sure moglabs ch1 off
    #     self.ttl6.off()
    #     self.atom_source_on()
    #     self.AOMs_on(["3D", "3P0_repump", "3P2_repump"])
    #     self.dac_0.write_dac(1, 9.9) #set initial detuning
    #     self.dac_0.load()
    #     delay(5*ms)
    #     self.ttl5.off()  # switch on  broadband mode (ch1)
    #     self.set_current_dir(0)
    #     self.Blackman_ramp_up()
    #     self.hold(self.bmot_load_duration)
    #
    #     ### Ramp transfer sequence
    #     tramp = 100*ms
    #     dt = tramp/int(self.Npoints)
    #     for step in range(1, int(self.Npoints)):
    #         self.dac_0.write_dac(0, self.bmot_current + 1.0/tramp*step*dt)
    #         self.dac_0.load()
    #         self.set_AOM_attens([("3D",6+10*step/int(self.Npoints))])
    #         delay(dt)
    #     self.dac_0.write_dac(0, self.bmot_current + 1.0)
    #     self.dac_0.load()
    #     #########################
    #
    #     self.atom_source_off()
    #     delay(50*ms)
    #     self.AOMs_off(['3D'])
    #     delay(0.5*us)
    #
    #     self.set_current(self.rmot_bb_current)
    #     delay(self.rmot_bb_duration)
    #
    #     self.AOMs_off(["3P0_repump","3P2_repump"])
    #     self.linear_ramp(self.rmot_bb_current, self.rmot_sf_current, self.rmot_ramp_duration, self.Npoints)
    #     #self.bb_det_ramp(self.rmot_ramp_duration, self.Npoints)
    #
    #     self.ttl6.off()
    #     self.set_current(0.0)


    # @kernel
    # def rMOT_beam_pulse(self, dur):
    #
    #     with parallel:
    #         self.ttl5.on()   # make sure moglabs ch1 off
    #         self.ttl6.off() # switch RF switch to broadband mode
    #
    #     self.ttl6.on()
    #     delay(dur)
    #     self.ttl6.off()
    #
    #
    def index_artiq(self, aom) -> TInt32:
        for i in range(len(self.AOMs)):
            if self.AOMs[i] == aom:
                return i
        raise Exception("No AOM with that name")



    # @kernel
    # def blow_away(self, time):
    #     self.atom_source_off()
    #     self.AOMs_off(['3P0_repump', '3P2_repump', '3D'])
    #     self.set_AOM_freqs([('3D', self.f_MOT3D_detect)])
    #     self.set_AOM_attens([('3D', 6.0)])
    #     self.AOMs_on(['3D'])
    #     #self.AOMs_on(['3P0_repump','3D'])
    #     #self.AOMs_on(['3P0_repump', '3P2_repump', '3D'])
    #     delay(time)
    #     self.AOMs_off(['3D'])
    #     self.set_AOM_freqs([('3D', self.freq_3D)])
    #     self.set_AOM_attens([('3D', self.atten_3D)])

    # @kernel
    # def warm_up_MOTs(self, time=500*ms):
    #     self.atom_source_on()
    #     self.AOMs_on(self.AOMs)
    #     delay(time)
    #     self.AOMs_off(self.AOMs)
    #     self.atom_source_off()
