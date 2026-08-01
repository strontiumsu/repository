# -*- coding: utf-8 -*-
"""
AD9910 DRG sawtooth with span compression + concurrent Zotino bias ramp.
Whole ramp is recorded into DMA, so the update rate is limited by SPI
transfer time (~4 us/point) rather than by CPU event-issue time.

@author: sr
"""

from numpy import int32, int64
from artiq.experiment import *
from artiq.coredevice.ad53xx import voltage_to_mu
import numpy as np

# ---- AD9910 registers -----------------------------------------------------
REG_CFR1  = 0x00
REG_CFR2  = 0x01
REG_LIMIT = 0x0B          # [63:32] upper FTW, [31:0] lower FTW
REG_STEP  = 0x0C          # [63:32] decrement step, [31:0] increment step
REG_RATE  = 0x0D          # [31:16] negative slope, [15:0] positive slope

CFR1_DEFAULT = 0x00000002              # SDIO input only
CFR1_AUTOCLR = 0x00000002 | (1 << 14)  # + autoclear DRG accumulator
CFR2_RUN     = 0x010F0020              # ASF from profile, DRG on, freq dest,
                                       # both no-dwell bits = free-running

# ---- hardware -------------------------------------------------------------
SYSCLK     = 1e9
DRG_TICK_S = 4.0 / SYSCLK              # SYNC_CLK = SYSCLK/4
RATE_WORD = 8

# ---- settings are requested as arguments in build() -----------------------


def shape(kind, x, tau=0.3):
    """x in [0,1] -> progress in [0,1]."""
    if kind == "lin":     return x
    if kind == "smooth":  return x*x*(3.0 - 2.0*x)
    if kind == "exp":     return (1 - np.exp(-x/tau)) / (1 - np.exp(-1/tau))
    if kind == "expinv":  return 1 - (1 - np.exp(-(1-x)/tau)) / (1 - np.exp(-1/tau))
    if kind == "quad":    return x*x
    if kind == "sqrt":    return np.sqrt(x)
    raise ValueError("unknown shape: " + kind)


class DRG_test_exp(EnvExperiment):

    def build(self):
        self.setattr_device("core")
        self.setattr_device("core_dma")
        self.setattr_device("ttl5")
        self.dac = self.get_device("zotino0")
        self.dds = self.get_device("urukul2_ch0")

        # ---- frequency sweep --------------------------------------------
        self.setattr_argument("F_HIGH",                     # sweep top, fixed
            NumberValue(20.0*MHz, unit="MHz", min=0.0, max=400.0*MHz),
            group="Frequency")
        self.setattr_argument("F_LOW",                      # sweep bottom at t=0
            NumberValue(5.0*MHz, unit="MHz", min=0.0, max=400.0*MHz),
            group="Frequency")
        self.setattr_argument("F_LOW_FINAL",                # sweep bottom at end
            NumberValue(19.99*MHz, unit="MHz", min=0.0, max=400.0*MHz),
            group="Frequency")
        self.setattr_argument("F_MOD",                      # sawtooth rep rate
            NumberValue(30*kHz, unit="kHz", min=0.0),
            group="Frequency")


        # ---- Zotino bias ------------------------------------------------
        self.setattr_argument("V_START",                    # Zotino bias, volts
            NumberValue(9.99, unit="V", min=-10.0, max=10.0),
            group="Atten")
        self.setattr_argument("V_FINAL",
            NumberValue(5.0, unit="V", min=-10.0, max=10.0),
            group="Atten")

        # ---- ramp shaping -----------------------------------------------
        self.setattr_argument("RAMP_TIME",
            NumberValue(80*ms, unit="ms", min=0.0),
            group="Ramp")
        self.setattr_argument("RAMP_STEP",                  # target update period
            NumberValue(100*us, unit="us", min=10.0*us),
            group="Ramp")
        self.setattr_argument("SHAPE_FREQ",
            EnumerationValue(["lin", "smooth", "exp", "expinv", "quad", "sqrt"],
                             default="lin"),
            group="Ramp")
        self.setattr_argument("SHAPE_ATTEN",
            EnumerationValue(["lin", "smooth", "exp", "expinv", "quad", "sqrt"],
                             default="exp"),
            group="Ramp")
        self.setattr_argument("TAU",
            NumberValue(0.5, ndecimals=3, step=0.01, min=0.0),
            group="Ramp")

        # ---- Urukul output ----------------------------------------------
        self.setattr_argument("ATT_DB",
            NumberValue(12.0, unit="dB", min=0.0, max=31.5),
            group="Output")
        self.setattr_argument("AMPL",
            NumberValue(0.8, ndecimals=3, step=0.01, min=0.0, max=1.0),
            group="Output")


        self.upper   = int32(0)
        self.lower   = [int32(0)]
        self.step_up = [int32(0)]
        self.step_dn = [int32(0)]
        self.dac_mu  = [int32(0)]
        self.rate    = (RATE_WORD << 16) | RATE_WORD
        self.n       = 0
        self.dt_mu   = int64(0)

    # ------------------------------------------------------------- host side
    def prepare(self):
        n = int(self.RAMP_TIME / self.RAMP_STEP)
        dt = self.RAMP_TIME / n
        assert self.F_LOW < self.F_LOW_FINAL < self.F_HIGH
        assert dt > 10e-6, "dt = {:.1f} us leaves no room for the SPI writes".format(dt*1e6)

        x = np.arange(n) / (n - 1.0)            # 0 at the start, 1 at the end

        # --- frequency span -> DRG limits and step words
        span = (self.F_HIGH - self.F_LOW) + (self.F_LOW - self.F_LOW_FINAL)*shape(self.SHAPE_FREQ, x, self.TAU)
        upper = int(round(self.F_HIGH / SYSCLK * 2**32))
        assert upper < 2**31, "FTW overflows int32"
        span_ftw = np.maximum(16, np.round(span / SYSCLK * 2**32).astype(int))
        step_up = np.maximum(1, np.round(span_ftw * self.F_MOD * DRG_TICK_S * RATE_WORD
                                         ).astype(int))
        if step_up.min() < 8:
            print("WARNING: step_up down to {}, F_MOD quantization > 12%"
                  .format(step_up.min()))

        # --- Zotino bias
        volts = self.V_START + (self.V_FINAL - self.V_START)*shape(self.SHAPE_ATTEN, x, self.TAU)
        assert np.abs(volts).max() < 10.0, "Zotino output out of range"

        self.upper   = int32(upper)
        self.lower   = [int32(upper - v) for v in span_ftw]
        self.step_up = [int32(v) for v in step_up]
        self.step_dn = [int32(v) for v in span_ftw]     # flyback in one tick
        self.dac_mu  = [int32(voltage_to_mu(float(v), self.dac.offset_dacs,
                                            self.dac.vref)) for v in volts]
        self.n       = n
        self.dt_mu   = self.core.seconds_to_mu(dt)

    # ---------------------------------------------------------------- kernel
    @kernel
    def record(self):
        """~14 RTIO events and ~4 us of SPI per point, all in one DMA trace.
        use the at_mu functionality to keep timing synced without intrinsic
        delay built into the writes."""
        with self.core_dma.record("ramp"):
            t = now_mu()
            for i in range(self.n):
                at_mu(t)
                self.dac.write_dac_mu(6, self.dac_mu[i])
                self.dac.load()
                self.set_sweep(i)
                t += self.dt_mu
            at_mu(t)

    @kernel
    def set_sweep(self, i, init=False):
        self.dds.write32(REG_RATE, self.rate)
        self.dds.write64(REG_LIMIT, self.upper, self.lower[i])
        self.dds.write64(REG_STEP, self.step_dn[i], self.step_up[i])
        if init: self.dds.write32(REG_CFR2, CFR2_RUN)
        self.dds.cpld.io_update.pulse_mu(8)

    @kernel
    def run(self):
        # reset and init devices
        self.core.reset()
        

        self.dds.cpld.init()
        self.dds.init()
        self.dac.init()
        self.core.break_realtime()

        delay(100*ms)

        # record ramp
        self.record()                   # host-CPU bound, ~20 ms for 1000 points
        ramp_handle = self.core_dma.get_handle("ramp")
        self.core.break_realtime()

        # init outputs
        self.dds.set_att(self.ATT_DB)
        delay(1*ms)
        self.dds.set(self.F_LOW, amplitude=self.AMPL)   # sets ASF; FTW from DRG
        self.dac.write_dac_mu(6 , self.dac_mu[0])
        self.dac.load()
        delay(100*ms)
        
        self.set_sweep(0, init=True)  # starts red mot sweep at initial depth, init to config CFR2

        # experimental sweep
        self.ttl5.on()
        self.dds.sw.on()

        self.core_dma.playback_handle(ramp_handle)

        self.dds.sw.off()
        self.ttl5.off()
        