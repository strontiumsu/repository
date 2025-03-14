# -*- coding: utf-8 -*-
"""
Created on Fri Aug 16 16:32:04 2024

@author: sr
"""

from scan_framework import Scan1D, TimeFreqScan
from artiq.experiment import *

# imports
import numpy as np
import pyvisa
from CoolingClass import _Cooling
from CameraClass import _Camera
from BraggClass import _Bragg
from repository.models.scan_models import RabiModel
from AWG import WaveformGenerator
from artiq.coredevice import ad9910

class Bragg_Velocity_Selection_exp(Scan1D, TimeFreqScan, EnvExperiment):

    def build(self, **kwargs):
    # required initializations

        super().build(**kwargs)
        self.setattr_device("ttl1")  # trigger for function generator

        # import classes for experiment control
        self.MOTs = _Cooling(self)
        self.Camera = _Camera(self)
        self.Bragg = _Bragg(self)
        self.chirp_dds = self.Bragg.urukul_channels[1]

        self.rigol= None

        # attributes here
        self.enable_pausing = True # disable to speed up by not checking scheduler
        self.enable_auto_tracking=False
        self.enable_profiling = False # enable to print runtime statistics to find bottlenecks
        self.wg = WaveformGenerator()



        self.scan_arguments(times = {'start':0*us,
            'stop':20*us,
            'npoints':20,
            'unit':"us",
            'scale':us,
            'global_step':0.1*us,
            'ndecimals':2},
             frequencies={
            'start':-1000*kHz,
            'stop':1000*kHz,
            'npoints':50,
            'unit':"kHz",
            'scale':kHz,
            'global_step':0.1*kHz,
            'ndecimals':3},
            frequency_center={'default':110*MHz},
            pulse_time= {'default':0*us},
            nbins = {'default':1000},
            nrepeats = {'default':1},
            npasses = {'default':1},
            fit_options = {'default': "No Fits"}

            )


        self.setattr_argument("dipole_load_time", NumberValue(15.0*1e-3,min=0.0*1e-3,max=1000.00*1e-3,scale=1e-3,
                      unit="ms"),"parameters")
        self.setattr_argument("drift_time", NumberValue(20.0*1e-3,min=0.0*1e-3,max=100.00*1e-3,scale=1e-3,
               unit="ms"),"parameters")

        self.setattr_argument("vel_sel_time", NumberValue(20.0*1e-6,min=0.0*1e-6,max=500.00*1e-6,scale=1e-6,
               unit="us"),"parameters")
        self.setattr_argument("vel_sel_amp", NumberValue(0.5,min=0.0,max=1.0,scale=1,
               unit="V"),"parameters")



        self.setattr_argument("rabi_delay", NumberValue(20.0*1e-6,min=0.0*1e-6,max=500.00*1e-6,scale=1e-6,
               unit="us"),"parameters")

        self.setattr_argument("rabi_amp", NumberValue(0.5,min=0.0,max=1.0,scale=1,ndecimals=3,
               unit="V"),"parameters")

        self.setattr_argument("v_sel",BooleanValue(False),"parameters")

        self.v_sel_det = 42.8*kHz



        self.setattr_argument("doppler_chirp_rate", NumberValue(-42.5509*1e6,min=-100.0*1e6,max=100.0*1e6,scale=1e6,ndecimals=3,
               unit="MHz"),"parameters")

        self.freq_list= np.linspace(100.0*MHz, 100.0*MHz, 1024)
        self.freq_list_ram = np.full(1024, 1)
        self.step_size=0

        self.length = 0.0


    def prepare(self):
    #prepare/initialize mot hardware and camera
        self.prepare_rigol()
        self.MOTs.prepare_aoms()
        self.MOTs.prepare_coils()
        self.Bragg.prepare_aoms()
        self.Camera.camera_init()

        # register model with scan framework
        self.enable_histograms = True
        self.model = RabiModel(self)
        self.register_model(self.model, measurement=True, fit=True)


    @kernel
    def before_scan(self):

        self.core.reset()
        self.ttl1.output()
        self.MOTs.init_coils()
        self.MOTs.init_ttls()
        self.MOTs.init_aoms(on=False)
        self.Bragg.init_aoms(on=True)
        self.Bragg.AOMs_off(["Bragg1", "Bragg2"])

        self.MOTs.set_current_dir(0)
        delay(10*ms)


        self.MOTs.take_background_image_exp(self.Camera)
        delay(100*ms)

        self.MOTs.warm_up_MOTs()
        self.core.wait_until_mu(now_mu())

    @kernel
    def measure(self, time, frequency):

        pulse_time = time
        freq = frequency

        self.core.reset()
        delay(1*ms)
        self.core.break_realtime()
        delay(20*ms)
        if self.v_sel:
            self.length = self.vel_sel_time + self.rabi_delay + pulse_time
        else:
            self.length = pulse_time
        self.load_gravity_chirp(self.length + 50*us)
        self.core.wait_until_mu(now_mu())
        delay(100*ms)

        if self.v_sel:
            self.Bragg.set_AOM_freqs([("Bragg2",self.Bragg.freq_Bragg2+self.v_sel_det)])
        else:
            self.Bragg.set_AOM_freqs([("Bragg2",freq)])
        delay(20*ms)
        self.MOTs.AOMs_off(self.MOTs.AOMs)
        delay(15*ms)


        self.MOTs.rMOT_pulse()
        delay(self.dipole_load_time)

        self.Bragg.set_AOM_attens([("Dipole",30.0), ("Lattice",30.0)])
        self.Bragg.set_AOM_scales([("Dipole",0.6), ("Lattice",0.1)])
        self.Bragg.AOMs_off(['Lattice'])


        #exp start
        self.ttl1.on()
        if self.v_sel:
            with parallel:
                self.Bragg.bragg_pulse(self.vel_sel_time)
                self.chirp_dds.cpld.io_update.pulse_mu(8)
            with parallel:
                delay(self.rabi_delay)
                self.Bragg.set_AOM_freqs([("Bragg2",freq)])
            self.Bragg.bragg_pulse(pulse_time)


        else:
            with parallel:
                self.chirp_dds.cpld.io_update.pulse_mu(8)
                self.Bragg.bragg_pulse(pulse_time)

        self.ttl1.off()


        self.Bragg.set_AOM_attens([("Dipole",self.Bragg.atten_Dipole), ("Lattice",30.0)])  # keeping on dipole guide
        self.Bragg.set_AOM_scales([("Dipole",self.Bragg.scale_Dipole)])

        delay(self.drift_time)

        self.MOTs.take_MOT_image(self.Camera)
        self.Bragg.set_AOM_attens([("Dipole",self.Bragg.atten_Dipole ), ("Lattice",self.Bragg.atten_Lattice)])
        self.Bragg.set_AOM_scales([("Dipole",self.Bragg.scale_Dipole ), ("Lattice",self.Bragg.scale_Lattice)])
        self.Bragg.AOMs_on(['Lattice'])


        delay(50*ms)
        self.Camera.process_image(bg_sub=True)
        delay(400*ms)
        self.MOTs.AOMs_off(['3P0_repump', '3P2_repump', '3D', "3D_red"])
        delay(200*ms)
        self.chirp_dds.set_cfr1(ram_enable=0)
        self.chirp_dds.cpld.io_update.pulse_mu(8)
        delay(10*ms)
        self.core.wait_until_mu(now_mu())
        return 0


    def before_measure(self, point, measurement):

        if point > 1000:
            time =  self.pulse_time
        else:
            time = point

        LENGTH = time
        if self.v_sel:LENGTH += self.rabi_delay + self.vel_sel_time
        SAMPLES = 6000
        SAMPLE_RATE = SAMPLES/LENGTH

        self.wg.sample_rate = SAMPLE_RATE


        self.wg.reset_waveform()
        if self.v_sel:
            self.wg.add_gaussian_pulse(0, self.vel_sel_time, self.vel_sel_amp, self.vel_sel_time/7)
            self.wg.add_gaussian_pulse(self.vel_sel_time+self.rabi_delay, time, self.rabi_amp, time/7)
        else:
            self.wg.add_gaussian_pulse(0, time, self.rabi_amp, time/7)


        t, y = self.wg.get_waveform()
        val_str = ",".join(map(str, y))

        self.rigol.write(":OUTP1 OFF");

        self.rigol.write(":TRACE:DATA VOLATILE," + val_str)
        self.rigol.write(f":SOUR1:APPL:USER {1/LENGTH}, {2*self.wg.max}, 0, 0")

        self.rigol.write("SOUR1:BURS ON")
        self.rigol.write("SOUR1:BURS:MODE TRIG")
        self.rigol.write(":SOUR1:BURS:NCYC 1 ")
        self.rigol.write(":SOUR1:BURS:TRIG:SOUR EXT")


        self.rigol.write(":OUTP1 ON");

        self.Camera.arm()

    @kernel
    def after_scan(self):
        self.core.wait_until_mu(now_mu())
        delay(1000*ms)
        self.MOTs.AOMs_on(self.MOTs.AOMs)
        delay(10*ms)
        self.MOTs.atom_source_on()


    def prepare_rigol(self):

        self.rigol = pyvisa.ResourceManager().open_resource('USB0::0x1AB1::0x0641::DG4E232700930::INSTR')
        self.rigol.write(":OUTP1 OFF");

    @kernel
    def load_gravity_chirp(self, length):

        # loads frequency list
        self.step_size = int(length/(1024*4*ns))
        f_range = length*self.doppler_chirp_rate
        f0 = self.Bragg.freq_Bragg1
        f_step  = f_range/1023
        for i in range(1024):
            self.freq_list[1023-i] = f0+f_step*i


        self.chirp_dds.frequency_to_ram(self.freq_list, self.freq_list_ram)
        self.core.break_realtime()

        self.chirp_dds.set(f0, amplitude=self.Bragg.scale_Bragg1)
        delay(1 * ms)

        self.chirp_dds.set_cfr1(ram_enable=0)
        self.chirp_dds.cpld.io_update.pulse_mu(8)

        self.chirp_dds.set_profile_ram(start=0, end=1024-1, step=(self.step_size | (2**6 - 1 ) << 16),
                                  profile=0, mode=ad9910.RAM_MODE_RAMPUP)
        self.chirp_dds.cpld.set_profile(0)
        delay(10*us)

        self.chirp_dds.cpld.io_update.pulse_mu(8)
        delay(10*us)

        self.chirp_dds.write_ram(self.freq_list_ram)
        delay(10 * us)

        self.chirp_dds.set_cfr1(internal_profile=0, ram_enable=1, ram_destination=ad9910.RAM_DEST_FTW) # gets the chirp ready to pulse
        delay(10*ms)


        self.core.wait_until_mu(now_mu())
