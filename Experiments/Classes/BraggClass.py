
"""
Created on Mon Feb 14 15:48:49 2022

@author: sr

Controls the urukul2 AOMs used for the dipole/lattice trap and Bragg beams.
Shared DDS machinery lives in DDSClass._DDSGroup; this class only holds the
urukul2 configuration and the Bragg-specific ramp methods.
"""

import numpy as np

from artiq.experiment import kernel, delay, ms, NumberValue, EnumerationValue, us

from DDSClass import _DDSGroup


class _Bragg(_DDSGroup):

    CPLD = "urukul2_cpld"
    URUKUL = "urukul2"

    AOM_NAMES      = ["Dipole", "Sideband", "Carrier", "Lattice"]
    DEFAULT_ATTENS = [12.0,      9.0,        6.0,       3.0]
    DEFAULT_FREQS  = [80.0,      3.0,        80.0,      80.0]   # MHz

    ALIASES = {"aom_dipole": 0, "aom_sideband": 1, "aom_carrier": 2, "aom_lattice": 3}

    ATTEN_DAC_CH = 6      # zotino0 channel wired to the variable attenuator

    # AOM response calibration: DAC voltage (V) -> measured optical power (a.u.).
    CAL_V_DIPOLE  = np.array([9.99, 9.5, 9.0, 8.5, 8.0, 7.5, 7.0, 6.5, 6.0, 5.5, 5.0, 4.5, 4.0, 3.5, 3.0, 2.5, 2.0, 1.5, 1.0, 0.5, 0.0])
    CAL_P_DIPOLE  = (np.array([1.915, 1.910, 1.9035, 1.896, 1.884, 1.872, 1.856, 1.8385, 1.8109, 1.773, 1.7152, 1.6305, 1.532, 1.4152, 1.2123, 0.893, 0.568, 0.278, 0.065, -0.03, -0.06]) + 0.06)/1.915
    CAL_V_LATTICE = CAL_V_DIPOLE
    CAL_P_LATTICE = CAL_P_DIPOLE

    # steepness of the "sigmoid" ramp shape (larger = sharper S-curve)
    SIGMOID_STEEPNESS = 12.0

    def build_extra(self):
        self.setattr_device("zotino0")
        self.dac_0 = self.get_device("zotino0")
        self.setattr_device("core_dma")

        self.setattr_argument("ramp_time",
            NumberValue(1.0*ms, min=0.1*ms, max=200.0*ms, scale=ms, unit="ms", ndecimals=2),
            "Dipole_AOMs")

        self.setattr_argument("ramp_shape",
            EnumerationValue(["cosine", "linear", "sigmoid"], default="cosine"),
            "Dipole_AOMs")

        # bottom of the ramp as a fraction of full optical power (1 = full, 0 = off)
        self.setattr_argument("ramp_bottom_dipole",
            NumberValue(0.0, min=0.0, max=1.0, scale=1, ndecimals=3),
            "Dipole_AOMs")
        self.setattr_argument("ramp_bottom_lattice",
            NumberValue(0.0, min=0.0, max=1.0, scale=1, ndecimals=3),
            "Dipole_AOMs")
        

    # ------------------------------------------------------------------
    # host-side ramp precomputation (predistortion)
    # ------------------------------------------------------------------
    def prepare_aoms(self):
        super().prepare_aoms()          # _DDSGroup: pull GUI scales/attens/freqs
        self._build_ramp_arrays()

    def _build_ramp_arrays(self):
        # Precompute the predistorted DAC-voltage ramps on the host; the kernel
        # replays these arrays verbatim (it cannot do numpy.interp). dt here MUST
        # match dt in record().
        dt = 2e-6                                        # 2 us; matches record()
        n = int(self.ramp_time / dt)
        ramp_npoints = n + 1

        i = np.arange(ramp_npoints)
        sh = self._easing(i / n)                          # 0 -> 1 ramp shape

        # target optical power: full (1) -> bottom fraction
        p_dip = 1.0 - (1.0 - self.ramp_bottom_dipole)  * sh
        p_lat = 1.0 - (1.0 - self.ramp_bottom_lattice) * sh

        self.dipole_ramp_v  = [float(v) for v in
            self._predistort(p_dip, self.CAL_V_DIPOLE, self.CAL_P_DIPOLE)]
        self.lattice_ramp_v = [float(v) for v in
            self._predistort(p_lat, self.CAL_V_LATTICE, self.CAL_P_LATTICE)]

    def _easing(self, x):
        # map normalized time x in [0, 1] -> monotonic ramp shape in [0, 1],
        # with s(0) = 0 and s(1) = 1, selected by the ramp_shape dropdown.
        if self.ramp_shape == "linear":
            return x
        elif self.ramp_shape == "sigmoid":
            k = self.SIGMOID_STEEPNESS
            raw = 1.0 / (1.0 + np.exp(-k * (x - 0.5)))
            lo  = 1.0 / (1.0 + np.exp(-k * (0.0 - 0.5)))  # raw at x=0
            hi  = 1.0 / (1.0 + np.exp(-k * (1.0 - 0.5)))  # raw at x=1
            return (raw - lo) / (hi - lo)                 # renormalize to hit 0 and 1
        else:  # "cosine"
            return (1.0 - np.cos(np.pi * x)) / 2.0

    def _predistort(self, p_target, V_cal, P_cal):
        # Invert the measured response: given a target optical-power fraction,
        # return the DAC voltage that produces it via linear interpolation of the
        # calibration table. Normalizing + sorting handles either direction.
        V = np.asarray(V_cal, dtype=float)
        P = np.asarray(P_cal, dtype=float)
        Pn = (P - P.min()) / (P.max() - P.min())         # normalize power to [0, 1]
        order = np.argsort(Pn)                           # np.interp needs ascending x
        return np.interp(np.clip(p_target, 0.0, 1.0), Pn[order], V[order])

    @kernel
    def init_aoms(self, switches=0x9):
        # default 0x9 -> Dipole (bit0) and Lattice (bit3) on
        delay(1 * ms)
        self._init_channels(switches)
        delay(1 * ms)
        self.record()

        self.core.break_realtime()



    @kernel
    def dac_set(self, ch, val):
        self.dac_0.set_dac([val], [ch])

    @kernel
    def record(self):
        dt = 2*us                       # must match dt in _build_ramp_arrays()
        ramp_npoints = int(self.ramp_time/dt) + 1

        with self.core_dma.record("dipole_rampdown"):
            for i in range(ramp_npoints):
                self.dac_set(6, self.dipole_ramp_v[i])
                delay(dt)

        with self.core_dma.record("dipole_rampup"):
            for i in range(ramp_npoints - 1, -1, -1):
                self.dac_set(6, self.dipole_ramp_v[i])
                delay(dt)

        with self.core_dma.record("lattice_rampdown"):
            for i in range(ramp_npoints):
                self.dac_set(5, self.lattice_ramp_v[i])
                delay(dt)

        with self.core_dma.record("lattice_rampup"):
            for i in range(ramp_npoints - 1, -1, -1):
                self.dac_set(5, self.lattice_ramp_v[i])
                delay(dt)

    @kernel
    def lattice_rampdown(self):
        self.core_dma.playback("lattice_rampdown")

    @kernel
    def lattice_rampup(self):
        self.core_dma.playback("lattice_rampup")

    @kernel
    def dipole_rampdown(self):
        self.core_dma.playback("dipole_rampdown")

    @kernel
    def dipole_rampup(self):
        self.core_dma.playback("dipole_rampup")

