# -*- coding: utf-8 -*-
"""
DDSClass.py

Base class for controlling one ARTIQ Urukul (AD9910) CPLD and its channels.

Subclasses (_Bragg, _Cooling, _state_control) drive a group of AOMs on a single
Urukul card.  They configure the group by overriding the class-level attributes
below and add their own specialized methods; all the shared build / init / setter
machinery lives here.

ARTIQ notes (see the DDS refactor plan):
  * Attribute types are inferred from the live value at kernel-compile time, so
    every attribute touched in a @kernel is created in build() on the host.
  * Inherited @kernel methods are specialized per concrete subclass, so each
    subclass is typed independently -- there is no cross-class conflict.
  * Kernels never call super(); subclass @kernel overrides call the inherited
    helper _init_channels(...) directly.
  * scales / attens / freqs are coerced to float so each is a TList(TFloat) even
    though the setters mutate elements in-kernel; kernel loops use the int
    self.n_channels rather than len() of a list of strings.
"""

from artiq.experiment import EnvExperiment, NumberValue, kernel, delay, ms  # pyright: ignore[reportMissingImports]
from artiq.coredevice.ad9910 import PHASE_MODE_TRACKING # pyright: ignore[reportMissingImports]


class _DDSGroup(EnvExperiment):

    # ------------------------------------------------------------------
    # subclass configuration (override these in each subclass)
    # ------------------------------------------------------------------
    CPLD = ""            # e.g. "urukul2_cpld"
    URUKUL = ""          # e.g. "urukul2"  ->  <URUKUL>_ch0 .. _ch(N-1)
    AOM_NAMES = []       # e.g. ["Dipole", "Sideband", "Carrier", "Lattice"]

    DEFAULT_SCALES = [0.8, 0.8, 0.8, 0.8]  # amplitude scale per AOM (0..1)
    DEFAULT_ATTENS = []  # attenuation per AOM (dB)
    DEFAULT_FREQS = []   # frequency per AOM in MHz

    ALIASES = {}         # {"aom_dipole": 0, ...}  ->  self.aom_dipole = channel

    # GUI NumberValue ranges (override as needed)
    SCALE_MAX = 0.9
    ATTEN_MIN = 1.0
    ATTEN_MAX = 30.0
    FREQ_MIN = 0.1e6
    FREQ_MAX = 350.0e6
    FREQ_DECIMALS = 3

    # ------------------------------------------------------------------
    # build / prepare  (host side)
    # ------------------------------------------------------------------
    def build(self):
        self.setattr_device("core")
        self.setattr_device(self.CPLD)
        self.cpld = self.get_device(self.CPLD)

        self.AOMs = list(self.AOM_NAMES)            # host-only (list of str)
        self.n_channels = len(self.AOM_NAMES)       # int, used in kernel loops

        # coerce to float so the compiler infers TList(TFloat)
        self.scales = [float(x) for x in self.DEFAULT_SCALES]
        self.attens = [float(x) for x in self.DEFAULT_ATTENS]
        self.freqs = [float(f) * 1e6 for f in self.DEFAULT_FREQS]

        self.urukul_channels = [self.get_device("{}_ch{}".format(self.URUKUL, i))
                                for i in range(self.n_channels)]

        # named channel aliases, e.g. self.aom_dipole = urukul2_ch0
        for alias, ind in self.ALIASES.items():
            setattr(self, alias, self.urukul_channels[ind])

        # per-AOM GUI arguments: scale_/atten_/freq_<name> in group "<name>_AOMs"
        for i in range(self.n_channels):
            name = self.AOMs[i]
            group = "{}_AOMs".format(name)
            self.setattr_argument(
                "scale_{}".format(name),
                NumberValue(self.scales[i], min=0.0, max=self.SCALE_MAX, ndecimals=3),
                group)
            self.setattr_argument(
                "atten_{}".format(name),
                NumberValue(self.attens[i], min=self.ATTEN_MIN, max=self.ATTEN_MAX, ndecimals=3),
                group)
            self.setattr_argument(
                "freq_{}".format(name),
                NumberValue(self.freqs[i], min=self.FREQ_MIN, max=self.FREQ_MAX,
                            scale=1e6, unit="MHz", ndecimals=self.FREQ_DECIMALS),
                group)

        self.build_extra()

    def build_extra(self):
        """Hook for subclasses to add extra devices / arguments (TTLs, coils...)."""
        pass

    def prepare_aoms(self):
        self.scales = [float(getattr(self, "scale_{}".format(n))) for n in self.AOMs]
        self.attens = [float(getattr(self, "atten_{}".format(n))) for n in self.AOMs]
        self.freqs = [float(getattr(self, "freq_{}".format(n))) for n in self.AOMs]

    # ------------------------------------------------------------------
    # channel initialization  (kernel)
    # ------------------------------------------------------------------
    @kernel
    def _init_channels(self, switches):
        # switches is a bitmask: bit i controls whether channel i is switched on
        self.cpld.init()
        for i in range(self.n_channels):
            delay(2 * ms)
            ch = self.urukul_channels[i]
            ch.init()
            ch.set_mu(ch.frequency_to_ftw(self.freqs[i]),
                      asf=ch.amplitude_to_asf(self.scales[i]))
            ch.set_att(self.attens[i])
            if (switches >> i) & 0b1 == 1:
                ch.sw.on()
            else:
                ch.sw.off()

    @kernel
    def init_aoms(self, switches=0x0):
        delay(1 * ms)
        self._init_channels(switches)
        delay(1 * ms)

    # ------------------------------------------------------------------
    # basic switch / setter methods  (kernel)
    # ------------------------------------------------------------------
    @kernel
    def AOMs_off_all(self):
        for i in range(self.n_channels):
            self.urukul_channels[i].sw.off()

    @kernel
    def AOMs_on_all(self):
        for i in range(self.n_channels):
            self.urukul_channels[i].sw.on()

    @kernel
    def set_AOM_freq(self, ind, freq, scale=0.8):
        self.freqs[ind] = freq
        ch = self.urukul_channels[ind]
        ch.set_mu(ch.frequency_to_ftw(freq),
                  asf=ch.amplitude_to_asf(scale))

    @kernel
    def set_AOM_atten(self, ind, atten):
        self.attens[ind] = atten
        self.urukul_channels[ind].set_att(atten)

    @kernel
    def set_AOM_scale(self, ind, scale):
        self.scales[ind] = scale
        ch = self.urukul_channels[ind]
        ch.set_mu(ch.frequency_to_ftw(self.freqs[ind]),
                  asf=ch.amplitude_to_asf(scale))

    @kernel
    def set_AOM_phase(self, ind, freq, ph, t, prof=0):
        self.freqs[ind] = freq
        ch = self.urukul_channels[ind]
        ch.set(freq, phase=ph, phase_mode=PHASE_MODE_TRACKING,
               amplitude=0.8, ref_time_mu=t, profile=prof)

    @kernel
    def set_phase_mode(self, mode):
        for i in range(self.n_channels):
            self.urukul_channels[i].set_phase_mode(mode)

    @kernel
    def switch_profile(self, prof=0):
        self.urukul_channels[0].cpld.set_profile(prof)
