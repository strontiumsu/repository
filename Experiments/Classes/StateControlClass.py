# -*- coding: utf-8 -*-
"""
Created on Fri Jan 17 13:44:41 2025

@author: sr

Controls the urukul0 AOMs used for state preparation / clock (688, Push, 679,
689).  Shared DDS machinery lives in DDSClass._DDSGroup; this class holds the
urukul0 configuration and the state-control-specific pulse methods.
"""

from artiq.experiment import kernel, delay, ms, ns

from DDSClass import _DDSGroup


class _state_control(_DDSGroup):

    CPLD = "urukul0_cpld"
    URUKUL = "urukul0"

    AOM_NAMES      = ["688", "Push", "679", "689"]
    DEFAULT_ATTENS = [8.0,    6.0,    7.0,   8.0]
    DEFAULT_FREQS  = [80.0,   102.5,  200.0, 220.0]   # MHz

    ALIASES = {"aom_688": 0, "aom_push": 1, "aom_679": 2, "aom_689": 3}

    def build_extra(self):
        self.setattr_device("ttl6")  # for opening cavity clear channel

    @kernel
    def init_aoms(self, switches=0x0):
        delay(50 * ms)
        self._init_channels(switches)
        delay(50 * ms)

    # ------------------------------------------------------------------
    # per-AOM frequency + amplitude setters (set both at once)
    # ------------------------------------------------------------------
    @kernel
    def set_AOM_freq_689(self, freq, amp=0.8):
        self.urukul_channels[3].set(frequency=freq, amplitude=amp)

    @kernel
    def set_AOM_freq_679(self, freq, amp=0.8):
        self.urukul_channels[2].set(frequency=freq, amplitude=amp)

    @kernel
    def set_AOM_freq_688(self, freq, amp=0.8):
        self.urukul_channels[0].set(frequency=freq, amplitude=amp)

    # ------------------------------------------------------------------
    # timing-compensated pulses
    # ------------------------------------------------------------------
    @kernel
    def shelf_pulse(self, t):
        self.pulse_688(t)

    @kernel
    def pulse_688(self, t):
        rewind = 450 * ns
        added = 130 * ns

        delay(-rewind)
        self.pulse(self.aom_688, t, added)
        delay(rewind - added)

    @kernel
    def pulse_679(self, t):
        rewind = 490 * ns
        added = 140 * ns

        delay(-rewind)
        self.pulse(self.aom_679, t, added)
        delay(rewind - added)

    @kernel
    def pulse_689(self, t):
        rewind = 400 * ns
        added = 100 * ns

        delay(-rewind)
        self.pulse(self.aom_689, t, added)
        delay(rewind - added)

    @kernel
    def pulse(self, dds, t, d):
        dds.sw.on()
        delay(t + d)
        dds.sw.off()

    @kernel
    def push_pulse(self, t):
        self.ttl6.off()
        self.pulse(self.aom_push, t, 0.0)

    @kernel
    def cav_clear_pulse(self, t):
        self.ttl6.on()  # switches to drive cavity clear aom
        self.pulse(self.aom_push, t, 0.0)
        self.ttl6.off()
