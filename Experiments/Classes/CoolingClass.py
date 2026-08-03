# -*- coding: utf-8 -*-
"""
Created on Mon Jan 30 18:16:29 2023

@author: ejporter

Desc: This file contains the class that controls all blue MOT and red MOT methods
(loading, MOT coils, etc.).  The urukul1 AOMs live in their own DDS class,
CoolingDDSClass._CoolingDDS, which this class composes as self.dds (and mirrors
onto itself via aliases).  _Cooling itself holds only the MOT-specific machinery
(coils, TTLs, RAM frequency scanning and pulse sequences).
"""

from artiq.experiment import ms, us, MHz, ns, NumberValue, parallel, sequential, EnumerationValue, s # pyright: ignore[reportMissingImports]
from artiq.experiment import kernel, EnvExperiment, BooleanValue, delay, at_mu, now_mu # pyright: ignore[reportMissingImports]
from artiq.coredevice import ad9910 # pyright: ignore[reportMissingImports]
from artiq.coredevice.ad53xx import voltage_to_mu # pyright: ignore[reportMissingImports]
from artiq.coredevice.ad9910 import frequency_to_ftw # pyright: ignore[reportMissingImports]

import numpy as np
from numpy import int32, int64

from CoolingDDSClass import _CoolingDDS

#hardware constants
RATE_WORD = 8  # sets the speed of the DRG accumulator for the rmot ramps [1, 16]
RMOT_SWEEP_DT = 100*us  # time step for the rmot sweep, used to calculate n and dt in prepare_aoms
ARB_RAMP_NPOINTS = 60

# rmot-pulse field ramp (DMA) parameters
FIELD_RAMP_DT = 50*us   # time step for the DMA coil-field ramps (fine -> many points)
BINC          = 1.0     # extra coil current above bmot_current during the blue->red capture ramp
BLUE_TRANSFER_TIME = 50*ms  # duration of the blue-current + blue-attenuation capture ramp
TO_BB_TIME     = 15*ms  # duration of the ramp from blue MOT current to broadband red MOT current
SF_DOWN_TIME   = 5*ms   # duration of the final coil rampdown (dipole_on branch)
MAX_CURRENT    = 7.0    # hard limit on the coil current setpoint (DAC volts)

# zotino channels
BFIELD_DAC = 0  # controls setpoint for the MOT coils (zotino0_ch0)
SHUTTER_ATOM_SOURCE = 1 # acts as shutter for 2d and zeeman
_ = 2 # unused
SHUTTER_688 = 3 # unused
_ = 4 # unused
_ = 5 # unused
ATTEN_RAMP_DAC = 6  # controls VVA atten on rmot (zotino0_ch6)
_ = 7 # unused


class _Cooling(EnvExperiment):

    def build(self):
        # CORE HARDWARE DEVICES
        self.setattr_device("core")
        self.setattr_device("core_dma")
        self.setattr_device("scheduler")

        ## ------------- COOLING DDS
        # urukul1 AOMs live in their own DDS class; _Cooling drives it as self.dds, everything mirrors to cooling class for simplicity
        self.dds = _CoolingDDS(self)
        for a in self.dds.ALIASES:                     # aom_3D_blue / aom_3P0 / aom_3P2 / aom_3D_red
            setattr(self, a, getattr(self.dds, a))
        self.urukul_channels = self.dds.urukul_channels
        self.urukul1_cpld = self.dds.cpld
        for n in self.dds.AOMs:                        # scale_/atten_/freq_<name> incl. freq_3D_red
            for p in ("scale_", "atten_", "freq_"):
                setattr(self, p + n, getattr(self.dds, p + n))


        ## ------------- TTLs (UNCOMMENT AND LABEL AS NEEDED)
        # self.setattr_device("ttl0")  # unused
        self.setattr_device("ttl1")  # for line trigger
        # self.setattr_device("ttl2") # unused
        # self.setattr_device("ttl3") # unused
        # self.setattr_device("ttl4") # unused
        self.setattr_device("ttl5") # # for misc timing
        # self.setattr_device("ttl6") # unused
        self.setattr_device("ttl7") # # MOT coil direction

        ## ------------- ZOTIN0 (LABEL CHANNELS ABOVE)
        self.setattr_device("zotino0")


        # MISC ##TODO
        self.setattr_argument("Npoints", NumberValue(60, min=0, max=500.00), "Blue MOT")


        ## ------------- BLUE MOT PARAMS
        self.setattr_argument("bmot_ramp_duration", 
                              NumberValue(50.0*1e-3, min=1.0*1e-3, max=100.00*1e-3, scale=1e-3, unit="ms"), "Blue MOT")  # ramp duration
        self.setattr_argument("bmot_current", 
                              NumberValue(5.0, min=0.0, max=7.0, scale = 1, unit="A"), "Blue MOT")  # Pulse amplitude
        self.setattr_argument("bmot_load_duration", 
                              NumberValue(1.0*s, min=0.01*s, max=9.0*s, scale=1e-3, unit="ms"), "Blue MOT")  # how long to hold blue mot on to load atoms

        

        ## ------------- RED MOT PARAMS
        self.setattr_argument("rmot_bb_current", 
                            NumberValue(0.4, min=0.0, max=5.00,unit="A"), "Red MOT")  # broadband mot current
        self.setattr_argument("rmot_bb_duration", 
                            NumberValue(50.0*1e-3, min=0.0*1e-3, max=300*1e-3, scale=1e-3,unit="ms"), "Red MOT")  # how long to old broad band
        self.setattr_argument("rmot_ramp_duration", 
                            NumberValue(85.0*1e-3, min=0.0, max=200*1e-3, scale=1e-3, unit="ms"), "Red MOT")  # how long to ramp between bb and sf
        self.setattr_argument("rmot_sf_current",
                            NumberValue(2.0, min=0.0, max=7.0,unit="A"), "Red MOT")  # single frequency mot current
        self.setattr_argument("rmot_sf_duration", 
                            NumberValue(25.0*1e-3, min=0.0*1e-3, max=300.0*1e-3, scale=1e-3, unit="ms"), "Red MOT")  # how long to hold atoms in sf red mot
        self.setattr_argument("freq_high", 
                            NumberValue(180.5*1e6, min=10.0*1e6, max=200.0*1e6, scale=1e6, unit="MHz", ndecimals=3), "Red MOT")
        self.setattr_argument("freq_low_i", 
                            NumberValue(174.0*1e6, min=10.0*1e6, max=200.0*1e6, scale=1e6, unit="MHz", ndecimals=3), "Red MOT")
        self.setattr_argument("freq_low_f", 
                            NumberValue(180.0*1e6, min=10.0*1e6, max=200.0*1e6, scale=1e6, unit="MHz", ndecimals=3), "Red MOT")
        self.setattr_argument("shape_freq",
                            EnumerationValue(["lin", "smooth", "exp", "expinv", "quad", "sqrt"], default="lin"), "Red MOT")
        self.setattr_argument("shape_atten",
                            EnumerationValue(["lin", "smooth", "exp", "expinv", "quad", "sqrt"],default="exp"), "Red MOT")
        self.setattr_argument("ramp_tau", 
                            NumberValue(0.5, ndecimals=3, step=0.01, min=0.0),"Red MOT")
        self.setattr_argument("atten_ramp_i", 
                            NumberValue(9.99, unit="V", min=0.0, max=9.99), "Red MOT")
        self.setattr_argument("atten_ramp_f", 
                            NumberValue(0.1,  unit="V", min=0.0, max=9.99), "Red MOT")
        self.setattr_argument("rmot_scan_frequency", 
                            NumberValue(30*1e3, min=10*1e3, max=100*1e3, scale=1e3, unit='kHz'), "Red MOT")
        self.setattr_argument("molasses", 
                            BooleanValue(False), "Red MOT")
        self.setattr_argument("molasses_frequency", 
                            NumberValue(179.25*1e6, min=10*1e6, max=200*1e6, scale=1e6, unit='MHz'), "Red MOT")

        ## ------------- IMAGING/DETECTION PARAMS
        self.setattr_argument("Push_pulse_time", 
                            NumberValue(0.9*1e-6, min=0.0*1e6, max=50000.00*1e-3, scale=1e-6, unit="us"), "Detection")
        self.setattr_argument("Detection_pulse_time", 
                            NumberValue(0.02*1e-3, min=0.0, max=100.00*1e-3, scale=1e-3,unit="ms"), "Detection")
        self.setattr_argument("Delay_duration", 
                            NumberValue(800*1e-6, min=0.0*1e-6, max=15000.00*1e-6, scale=1e-6,unit="us"), "Detection")
        self.setattr_argument("f_MOT3D_detect", 
                            NumberValue(180*1e6, min=100*1e6, max=200*1e6, scale=1e6, unit='MHz'), "Detection")


        ## ------------- INITIATE VARIABLES FOR LATER USE HERE
        # variables for handling rmot ramp parameters and DRG sweep
        self.upper         = int32(0)    # upper frequ
        self.lower         = [int32(0)]  # lower freq
        self.step_up       = [int32(0)]  # hardware step size up
        self.step_dn       = [int32(0)]  # hardware step size down
        self.atten_dac_mu  = [int32(0)]  # for ramping attenuation
        self.field_dac_mu  = [int32(0)]  # for ramping b field
        self.rate          = (RATE_WORD << 16) | RATE_WORD # sets the speed of the DRG accumulator for the rmot ramps [1, 16]
        self.n             = 0 # points in sweep
        self.dt_mu         = int64(0) # time step

        # precomputed DMA coil-field ramps for the rmot pulse (built in prepare_coils)
        self.blue_up_mu    = [int32(0)]  # 0 -> bmot_current
        self.blue_load_mu  = [int32(0)]  # bmot_current -> +BINC
        self.blue_att_db   = [0.0]       # blue AOM attenuation baked into the blue_load trace
        self.to_bb_mu      = [int32(0)]  # +BINC -> rmot_bb_current
        self.sf_down_mu    = [int32(0)]  # rmot_sf_current -> 0

        # normalized shape for the one-off (non-DMA) ramp_field()
        self.ramp_npoints  = 0
        self.ramp_norm     = [0.0]

    @kernel
    def init_ttls(self):
        "uncomment as needed"
        delay(10*ms)
        # self.ttl0.input()
        self.ttl1.input()
        # self.ttl2.input()
        # self.ttl3.input()
        # self.ttl4.output()
        self.ttl5.output()
        # self.ttl6.output()
        self.ttl7.output()
        self.core.break_realtime()
        delay(10*ms)

    ## ------------- AOM FUNCTIONS
    def prepare_aoms(self):
        self.dds.prepare_aoms()
        self._prepare_rmot_ramp()  # precompute the rmot ramps for DMA recording (played every shot)
    

    def _prepare_rmot_ramp(self):
        """Precompute the rmot ramps for DMA recording (played every shot)."""

        n = int(self.rmot_ramp_duration / (RMOT_SWEEP_DT))  # update at 100us step size the rmot ramp
        dt = self.rmot_ramp_duration / n

        x = np.linspace(0, 1, n)            # 0 at the start, 1 at the end

        # --- frequency span -> DRG limits and step words
        span = (self.freq_high - self.freq_low_i) + (self.freq_low_i - self.freq_low_f)*shape(self.shape_freq, x, self.ramp_tau)
        span_ftw = [frequency_to_ftw(s) for s in span]

        upper = frequency_to_ftw(self.freq_high)
        step_up = [int(np.round(s * self.rmot_scan_frequency * 4e-9 * RATE_WORD)) for s in span_ftw]

        # --- Zotino sweep values
        volts_atten = self.atten_ramp_i + (self.atten_ramp_f - self.atten_ramp_i)*shape(self.shape_atten, x, self.ramp_tau)
        volts_field = self.rmot_bb_current + (self.rmot_sf_current - self.rmot_bb_current)*shape('lin', x)

        self.upper   = int32(upper)
        self.lower   = [int32(upper - v) for v in span_ftw]
        self.step_up = [int32(v) for v in step_up]
        self.step_dn = [int32(v) for v in span_ftw]  

        self.atten_dac_mu  = [voltage_to_mu(float(v)) for v in volts_atten]
        self.field_dac_mu  = [voltage_to_mu(float(v)) for v in volts_field]

        self.n       = n
        self.dt_mu   = self.core.seconds_to_mu(dt)

    # mirrors for convenience
    @kernel
    def AOMs_off_all(self):
        self.dds.AOMs_off_all()
    @kernel
    def AOMs_on_all(self):
        self.dds.AOMs_on_all()


    @kernel
    def init_aoms(self, switches=0x0):
        delay(5*ms)
        self.dds.init_aoms(switches)
        self.core.break_realtime()
        delay(5*ms)

        self.aom_3D_red.set(self.freq_low_i, amplitude=self.scale_3D_red)   # sets ASF; FTW from DRG
        self.zotino0.write_dac_mu(ATTEN_RAMP_DAC,  self.atten_dac_mu[0])  # sets initial attenuation for red MOT
        self.zotino0.load()
    
        self.set_sweep(0, init=True)  # starts red mot sweep at initial depth, init to config CFR2
        self.core.break_realtime()

        # record every repeated rmot-pulse field ramp into DMA once; played each shot
        self.record_rmot_ramp()
        self.record_field_ramps()
        self.core.break_realtime()

    ## ---------- RMOT SWEEP HANDLING AND DMA RECORDINGS
    @kernel
    def set_sweep(self, i, init=False, REG_LIMIT=0x0B, REG_STEP=0x0C, REG_RATE=0x0D, REG_CFR2=0x01, CFR2_RUN=0x010F0020):
        """
        Set the DRG sweep parameters for the i-th point in the ramp.
        If init is True, also set the CFR2 register to start the sweep.
        Only needs to be used at the start of the ramp, since the DRG will continue to sweep until the next update.
        """
        self.aom_3D_red.write64(REG_LIMIT, self.upper, self.lower[i]) # update sweep params
        self.aom_3D_red.write64(REG_STEP, self.step_dn[i], self.step_up[i])

        if init: 
            self.aom_3D_red.write32(REG_RATE, self.rate)  # if first time initialize sweep params
            self.aom_3D_red.write32(REG_CFR2, CFR2_RUN)

        self.aom_3D_red.cpld.io_update.pulse_mu(8) # update once at the end

    @kernel
    def record_rmot_ramp(self):
        with self.core_dma.record("rmot_ramp"):
            t = now_mu()
            for i in range(self.n):
                at_mu(t)

                self.zotino0.write_dac_mu(ATTEN_RAMP_DAC, self.atten_dac_mu[i])
                self.zotino0.write_dac_mu(BFIELD_DAC,     self.field_dac_mu[i])
                self.zotino0.load()

                self.set_sweep(i) # sets the frequency sweep params for the DRG, assumes already running

                t += self.dt_mu
            at_mu(t)

    @kernel
    def _record_field_ramp(self, name, ramp_mu, dt, duration):
        """Record a single-channel coil-field DMA ramp (BFIELD_DAC) under `name`.

        Given the point spacing `dt` and total `duration`, the point count and
        machine-unit step are computed here (must match build_field_ramp's sizing).
        """
        n = int(duration / dt)
        dt_mu = self.core.seconds_to_mu(duration / n)
        with self.core_dma.record(name):
            t = now_mu()
            for i in range(n):
                at_mu(t)
                self.zotino0.write_dac_mu(BFIELD_DAC, ramp_mu[i])
                self.zotino0.load()
                t += dt_mu
            at_mu(t)

    @kernel
    def record_field_ramps(self):
        """Record the repeated rmot-pulse coil-field ramps into named DMA traces (once, at init)."""
        self._record_field_ramp("field_blue_up", self.blue_up_mu, FIELD_RAMP_DT, self.bmot_ramp_duration)
        self._record_field_ramp("field_to_bb",   self.to_bb_mu,   FIELD_RAMP_DT, TO_BB_TIME)
        self._record_field_ramp("field_sf_down", self.sf_down_mu, FIELD_RAMP_DT, SF_DOWN_TIME)

        # blue capture ramp: coil current + blue AOM attenuation baked into one trace
        n = int(BLUE_TRANSFER_TIME / FIELD_RAMP_DT)
        dt_mu = self.core.seconds_to_mu(BLUE_TRANSFER_TIME / n)
        with self.core_dma.record("field_blue_load"):
            t = now_mu()
            for i in range(n):
                at_mu(t)
                self.zotino0.write_dac_mu(BFIELD_DAC, self.blue_load_mu[i])
                self.zotino0.load()
                self.aom_3D_blue.set_att(self.blue_att_db[i])
                t += dt_mu
            at_mu(t)

    @kernel
    def line_trigger(self, offset=5*ms):
        # sets start of exp relative to linetrigger
        t_end = self.ttl1.gate_rising(1/60)  # ensures we only gate for one cycle
        t_edge = self.ttl1.timestamp_mu(t_end)

        if t_edge > 0:
            at_mu(t_edge+self.core.seconds_to_mu(offset))  # Add a tiny buffer to prevent underflow

        delay(1*ms)
        self.ttl1.count(t_end)  # clears cache
        delay(15*ms)

    ## ----------- DAC FUNCTIONS
    @kernel
    def dac_set(self, chs, vals):
        if type(chs) is not list: chs = [chs]  # cast to list if needed
        if type(vals) is not list: vals = [vals]

        for ch, val in zip(chs, vals):
            self.zotino0.write_dac(ch, val)  # write values without updating

        self.zotino0.load()  # update all at once

    # turns the zeeman and 2D off/on via shutter
    @kernel
    def atom_source_on(self):
        self.dac_set(SHUTTER_ATOM_SOURCE, 4.0)
    @kernel
    def atom_source_off(self):
        self.dac_set(SHUTTER_ATOM_SOURCE, 0.0)

    # turns the 688 shutter on/off via DAC
    @kernel
    def open_688(self):
        self.dac_set(SHUTTER_688, 4.0)
    @kernel
    def close_688(self):
        self.dac_set(SHUTTER_688, 0.0)

    # turns the carrier signal on via mixer offset
    @kernel
    def carrier_on(self):
        raise Exception("carrier_on() is not implemented yet.  Please implement it in CoolingClass.py")
    @kernel
    def carrier_off(self):
        raise Exception("carrier_off() is not implemented yet.  Please implement it in CoolingClass.py")
    
    # turns the sidebands on/off via DAC
    @kernel
    def cavity_res_on(self):
        raise Exception("cavity_res_on() is not implemented yet.  Please implement it in CoolingClass.py")
    @kernel
    def cavity_res_off(self):
        raise Exception("cavity_res_off() is not implemented yet.  Please implement it in CoolingClass.py")


    ## --------------- MOT COIL FUNCTIONS
    def build_field_ramp(self, start, end, time, dt, shape_kind):
        """Host: build a coil-field ramp as a list of DAC machine units.

        The coil setpoint IS a DAC voltage, so values map through voltage_to_mu
        (no current<->voltage conversion). Point count is int(time/dt) -- the
        recorder recomputes the same n from the same (dt, time) it is given.
        """
        n = int(time / dt)
        x = np.linspace(0, 1, n)
        v = start + (end - start) * shape(shape_kind, x, self.ramp_tau)   # setpoint = DAC volts
        assert v.max() <= MAX_CURRENT and v.min() >= 0.0, "field ramp setpoint out of range [0, MAX_CURRENT]"
        return [voltage_to_mu(float(vi)) for vi in v]

    def prepare_coils(self):
        # one-off (non-DMA) ramp: normalized 0->1 shape, scaled in-kernel by ramp_field()
        self.ramp_norm = [float(v) for v in
                          shape('blackman', np.linspace(0, 1, ARB_RAMP_NPOINTS), self.ramp_tau)]

        # precomputed DMA field ramps for the rmot pulse (recorded once, played every shot);

        self.blue_up_mu   = self.build_field_ramp(0.0,                      self.bmot_current,          self.bmot_ramp_duration, FIELD_RAMP_DT, "blackman")
        self.blue_load_mu = self.build_field_ramp(self.bmot_current,        self.bmot_current + BINC,   BLUE_TRANSFER_TIME,      FIELD_RAMP_DT, "lin")
        self.to_bb_mu     = self.build_field_ramp(self.bmot_current + BINC, self.rmot_bb_current,       TO_BB_TIME,              FIELD_RAMP_DT, "blackman")
        self.sf_down_mu   = self.build_field_ramp(self.rmot_sf_current,     0.0,                        SF_DOWN_TIME,            FIELD_RAMP_DT, "blackman")

        self.blue_att_db  = [float(a) for a in np.linspace(6.0, 30.0, len(self.blue_load_mu))]

    @kernel
    def init_coils(self):
        self.zotino0.init()  # initialize DAC that controls setpoint
        delay(5*ms)
        self.ttl7.off()  # puts in MOT config
        self.core.break_realtime()

    # sets to 0 current
    @kernel
    def coils_off(self):
        self.set_current(0.0)

    # sets MOT current
    @kernel
    def set_current(self, cur):
        if cur > MAX_CURRENT:
            raise Exception("Current too high!")
        else:
            self.dac_set(BFIELD_DAC, cur)

    # switches between MOT configs
    @kernel
    def set_current_dir(self, direc):
        self.coils_off()  # turn off current
        delay(15*ms)  # wait for current to settle

        if direc == 0: 
            self.ttl7.off()  # set appropriate direction
        elif direc == +1:
            self.ttl7.on()
        else:
            raise Exception("Invalid direction for set_current_dir()")
        delay(1*ms)

    @kernel
    def ramp_field(self, start, end, time, kind="blackman"):
        """One-off (non-DMA), CPU-issued coil-field ramp for arbitrary experiments.

        Scales the normalized shape precomputed in prepare_coils() by the endpoints, so
        start/end/time are fully runtime-flexible. Use the DMA traces for the repeated
        rmot-pulse ramps instead (see record_field_ramps).
        """
        assert (start >= 0.0) and (end >= 0.0) and (start <= MAX_CURRENT) and (end <= MAX_CURRENT)
        dt = time / (ARB_RAMP_NPOINTS - 1)
        for step in range(ARB_RAMP_NPOINTS):
            if kind == "blackman":
                self.set_current(start + (end - start) * self.ramp_norm[step])
            elif kind == 'lin':
                self.set_current(start + (end - start) * step / (ARB_RAMP_NPOINTS - 1))
            else:
                raise Exception("Invalid ramp kind for ramp_field()")
            delay(dt)

    @kernel
    def bMOT_pulse(self):
        self.atom_source_on()
        # turn on 3D, and repumps
        self.aom_3D_blue.sw.on()
        self.aom_3P0.sw.on()
        self.aom_3P2.sw.on()

        self.ramp_field(0.0, self.bmot_current, self.bmot_ramp_duration)
        delay(self.bmot_load_duration)
        self.ramp_field(self.bmot_current, 0.0, self.bmot_ramp_duration)

        # turn on 3D, and repumps
        self.aom_3D_blue.sw.off()
        self.aom_3P0.sw.off()
        self.aom_3P2.sw.off()
        self.atom_source_off()

    @kernel
    def bMOT_load(self):
        """
        Load atoms into the blue MOT.  This is a blocking call that will hold for the duration of the load.
        """
        self.atom_source_on() # turn all lasers on
        self.aom_3D_blue.sw.on()
        self.aom_3P0.sw.on()
        self.aom_3P2.sw.on()

        self.set_current_dir(0) # ramp current up
        self.ramp_field(0.0, self.bmot_current, self.bmot_ramp_duration)

        delay(self.bmot_load_duration) # hold for load duration

    @kernel
    def rmot_pulse_drg(self, sf=False, sf_amp=0.0, sf_freq=180.0*MHz, sf_atten=30.0, dipole_on=True):
        self.atom_source_on()  # opens on zeeman and 2D shutters
        self.close_688()  # close 688 shutter to prevent leakage from optical pumping
        self.aom_3D_blue.set_att(self.atten_3D)
        self.aom_3D_red.set_att(self.atten_3D_red)
        self.aom_3D_red.set_amplitude(0.8)

        # turn on 3D, and repumps
        self.aom_3D_blue.sw.on()
        self.aom_3P0.sw.on()
        self.aom_3P2.sw.on()
        self.aom_3D_red.sw.off()

        # turn to MOT mode
        self.set_current_dir(0)

        # ramp up bmot bfield (DMA) and hold for load duration
        self.core_dma.playback("field_blue_up")
        delay(self.bmot_load_duration)

       # line trigger for consistent time relative to mains
        self.line_trigger()

        delay(5*us)
        self.aom_3D_red.sw.on()

        # ramp up blue MOT current + blue attenuation together (DMA)
        self.core_dma.playback("field_blue_load")

        # turn off blue light
        self.atom_source_off()
        self.aom_3D_blue.sw.off()
        delay(0.5*us)

        # ramp up to broad band red mot current and hold (DMA)
        self.core_dma.playback("field_to_bb")
        delay(self.rmot_bb_duration)

        # turn off repumpers
        self.aom_3P0.sw.off()
        self.aom_3P2.sw.off()

        # rmot compression: coil field + attenuation VVA + DRG frequency sweep (DMA)
        self.core_dma.playback("rmot_ramp")

        # switch to single frequency mode then hold
        if sf:
            delay(self.rmot_sf_duration)
        self.aom_3D_red.sw.off()
        delay(10*us)  #Makes sure that the aom is fully switched off before the magnetic field ramps down.
        self.urukul1_cpld.set_profile(0)

        if dipole_on == True:
            self.core_dma.playback("field_sf_down")  # rmot_sf_current -> 0 (DMA)
        else:
            self.coils_off()

        self.open_688()  # open 688 shutter to allow for excitation

    @kernel
    def molasses_pulse(self, freq=179*MHz, amp=0.1, t=40*ms):
        raise Exception("molasses_pulse() is not implemented yet.  Please implement it in CoolingClass.py") 

    
    ## ---------- IMAGING FUNCTIONS
    @kernel
    def take_background_image_exp(self, cam):
        """
        Takes a background image for background subtraction.
        """
        self.take_MOT_image(cam)
        delay(10*ms)

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
        self.aom_3D_blue.set(frequency=self.f_MOT3D_detect, amplitude=0.8)
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
        self.aom_3D_blue.set(frequency=self.freq_3D, amplitude=0.8)
        self.aom_3D_blue.set_att(self.atten_3D)


## ---------- HELPERS
def shape(kind, x, tau=0.3):
    """x in [0,1] -> progress in [0,1].
    Used for generating ramp shapes for the red MOT frequency and attenuation ramps.
    """
    if kind == "lin":     return x
    if kind == "smooth":  return x*x*(3.0 - 2.0*x)
    if kind == "exp":     return (1 - np.exp(-x/tau)) / (1 - np.exp(-1/tau))
    if kind == "expinv":  return 1 - (1 - np.exp(-(1-x)/tau)) / (1 - np.exp(-1/tau))
    if kind == "quad":    return x*x
    if kind == "sqrt":    return np.sqrt(x)
    if kind == "blackman": return 0.42 - 0.5*np.cos(np.pi*x) + 0.08*np.cos(2*np.pi*x)
    raise ValueError("unknown shape: " + kind)