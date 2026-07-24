
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

    @kernel
    def init_aoms(self, switches=0x9):
        # default 0x9 -> Dipole (bit0) and Lattice (bit3) on
        delay(1 * ms)
        self._init_channels(switches)
        delay(1 * ms)


    ## TODO: add rampup methods for dipole/lattice, and rampdown for sideband/carrier
    @kernel
    def lattice_rampdown(self, end, time):
        dt = time / 31
        for step in range(int(31)):
            atten = self.atten_Lattice + ((end - self.atten_Lattice) / time) * step * dt
            self.aom_lattice.set_att(atten)
            delay(dt)

    @kernel
    def dipole_rampdown(self, end, time):
        dt = time / 31
        for step in range(int(31)):
            atten = self.atten_Dipole + ((end - self.atten_Dipole) / time) * step * dt
            self.aom_dipole.set_att(atten)
            delay(dt)

    @kernel
    def dipole_lattice_rampdown(self, end, time):
        dt = time / 101
        for step in range(int(31)):
            atten = self.atten_Dipole + ((end - self.atten_Dipole) / time) * step * dt
            self.aom_dipole.set_att(atten)
            delay(dt / 2)
            atten = self.atten_Lattice + ((end - self.atten_Lattice) / time) * step * dt
            self.aom_lattice.set_att(atten)
            delay(dt / 2)
