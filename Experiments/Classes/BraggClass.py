
"""
Created on Mon Feb 14 15:48:49 2022

@author: sr

Controls the urukul2 AOMs used for the dipole/lattice trap and Bragg beams.
Shared DDS machinery lives in DDSClass._DDSGroup; this class only holds the
urukul2 configuration and the Bragg-specific ramp methods.
"""

from artiq.experiment import kernel, delay, ms

from DDSClass import _DDSGroup


class _Bragg(_DDSGroup):

    CPLD = "urukul2_cpld"
    URUKUL = "urukul2"

    AOM_NAMES      = ["Dipole", "Sideband", "Carrier", "Lattice"]
    DEFAULT_ATTENS = [12.0,      9.0,        6.0,       3.0]
    DEFAULT_FREQS  = [80.0,      3.0,        80.0,      80.0]   # MHz

    ALIASES = {"aom_dipole": 0, "aom_sideband": 1, "aom_carrier": 2, "aom_lattice": 3}

    ATTEN_DAC_CH = 6      # zotino0 channel wired to the variable attenuator

    def build_extra(self):
        self.setattr_device("zotino0")
        self.dac_0 = self.get_device("zotino0")

    @kernel
    def init_aoms(self, switches=0x9):
        # default 0x9 -> Dipole (bit0) and Lattice (bit3) on
        delay(1 * ms)
        self._init_channels(switches)
        delay(1 * ms)

    @kernel
    def dac_set(self, ch, val):
        self.dac_0.set_dac([val], [ch])

    ## TODO: add rampup methods for dipole/lattice, and rampdown for sideband/carrier
    @kernel
    def dipole_ramp(self, start, stop, time, pts=31):
        dt = time / pts
        for step in range(int(pts)):
            volt = start + ((stop - start) / time) * step * dt
            self.dac_set(6, volt)
            delay(dt)

    @kernel
    def lattice_ramp(self, start, stop, time, pts=31):
        dt = time / pts
        for step in range(int(pts)):
            volt = start + ((stop - start) / time) * step * dt
            self.dac_set(5, volt)
            delay(dt)


