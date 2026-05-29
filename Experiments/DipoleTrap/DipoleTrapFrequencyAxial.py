# -*- coding: utf-8 -*-
"""
Created on Fri May 15 15:47:21 2026
@author: sr

Lattice trap-frequency scan via parametric amplitude modulation.

RAM strategy
------------
The lattice DDS stays in RAM-DEST-ASF mode for the entire experiment.
Two RAM profiles are used:

  Profile 7 (rest):  RAM addresses 1022-1023, both holding scale_Lattice.
                     The RAM "sweep" just bounces between two identical
                     values, so the output is a steady carrier at
                     scale_Lattice amplitude.

  Profile 0 (shake): RAM addresses 0-1021 holding N_CYCLES_IN_RAM full
                     cosine cycles between (ai, af). CONT_RAMPUP loops
                     this region to produce parametric modulation at
                     the requested frequency.

Switching between rest and shake is a single set_profile() + io_update
on the CPLD — no CFR1 toggling, no set() calls that could clobber
profile registers. The dipole rides through unaffected because the only
thing changing is the lattice's RAM address range.
"""

from scan_framework import Scan1D, FreqScan

from artiq.experiment import TInt32, TArray, TTuple, Scannable, RangeScan, EnumerationValue, BooleanValue, NumberValue, at_mu, sequential, s # pyright: ignore[reportMissingImports]
from artiq.experiment import rpc, kernel, EnvExperiment, kHz, delay, ms, parallel, us, MHz, now_mu, ns # pyright: ignore[reportMissingImports]
from artiq.coredevice import ad9910 # pyright: ignore[reportMissingImports]
import numpy as np


from CoolingClass import _Cooling
from CameraClass import _Camera
from BraggClass import _Bragg
from scipy import constants

from repository.models.scan_models import DipoleFreqModel # pyright: ignore[reportMissingImports]

# module level constants
N_CYCLES_IN_RAM = 8
N_SINE = 1022



class DipoleTrapFrequencyAxial_exp(Scan1D, FreqScan, EnvExperiment):

    def build(self, **kwargs):
        super().build(**kwargs)
        self.setattr_device("ttl5")

        self.MOTs = _Cooling(self)
        self.Camera = _Camera(self)
        self.Bragg = _Bragg(self)
        
        self.enable_auto_tracking = False
        

        self.scan_arguments(
            frequencies={
                'start': 0.5e3, 'stop': 250e3, 'npoints': 20,
                'unit': "kHz", 'scale': kHz,
                'global_step': 0.1*kHz, 'ndecimals': 2,
            },
            nbins={'default': 1000},
            nrepeats={'default': 1},
            npasses={'default': 1},
            fit_options={'default': "Fit and Save"},
        )

        self.setattr_argument("load_time",
            NumberValue(15e-3, min=0.0, max=5000e-3, scale=1e-3, unit="ms"),
            "parameters")


        # how long to shake for
        self.setattr_argument("shake_type", EnumerationValue(['duration','number']),"parameters")
        self.setattr_argument("shake_num",
            NumberValue(10, min=1, max=1000, scale=1),
            "parameters")
        self.setattr_argument("shake_time",
            NumberValue(10e-3, min=0.1e-3, max=100e-3, scale=1e-3, unit="ms"),
            "parameters")
        
        # modulation depth
        self.setattr_argument("mod_depth",
            NumberValue(0.7, min=0.0, max=0.8, scale=1),
            "parameters")
        
        # wait before imaging
        self.setattr_argument("drop_time",
            NumberValue(5e-3, min=0.1e-3, max=500e-3, scale=1e-3, unit="ms"),
            "parameters")
        

        
        

    def prepare(self):
        self.MOTs.prepare_aoms()
        self.MOTs.prepare_coils()
        self.Camera.camera_init(N=len(list(self.get_scan_points()))*self.nrepeats*self.npasses + 10)
        self.Bragg.prepare_aoms()
        
        # register model with scan framework
        self.enable_histograms = True
        self.model = DipoleFreqModel(self)
        self.register_model(self.model, measurement=True, fit=True)

    @kernel
    def before_scan(self):
        self.core.reset()
        self.MOTs.init_coils()
        self.MOTs.init_aoms(on=False)
        self.Bragg.init_aoms(switches=0x9)
        delay(10*ms)

        self.MOTs.take_background_image_exp(self.Camera)
        
        
        self.MOTs.AOMs_off_all()
        self.MOTs.atom_source_off()
        
        # set the profiles for the dipole trap
        self.Bragg.aom_dipole.set(self.Bragg.freq_Dipole, 0.0, self.Bragg.scale_Dipole, profile=0)
        self.Bragg.aom_dipole.set(self.Bragg.freq_Dipole, 0.0, self.Bragg.scale_Dipole, profile=7)

    @kernel
    def before_measure(self, point, measurement):
        # load mod into RAM
        # dont let the scale go below 0.05
        delay(1*ms)
        self.load_mod(
            self.Bragg.aom_lattice,
            self.Bragg.scale_Lattice,
            max(self.Bragg.scale_Lattice - self.mod_depth, 0.05),
            point,
        )
        delay(1*ms)
        self.core.break_realtime()


    @kernel
    def measure(self, point):
        # point = oscillation frequency
        self.core.wait_until_mu(now_mu())
        delay(1*ms)

        self.MOTs.AOMs_off_all()
        delay(10*ms)

        self.MOTs.init_rmot_dds(
            self.MOTs.rmot_freq_i, self.MOTs.rmot_freq_f,
            self.MOTs.rmot_freq_depth_i, self.MOTs.rmot_freq_depth_f,
            self.MOTs.freq_3D_red)
        delay(10*ms)

        self.MOTs.rMOT_pulse_new(sf=False)
        delay(self.load_time)

        # Start shaking: switch lattice RAM playback to profile 0
        # (addresses 0-1021, the sine cycles).
        self.Bragg.aom_lattice.cpld.set_profile(0)
        self.ttl5.on()
        self.Bragg.aom_lattice.cpld.io_update.pulse_mu(8)



        if self.shake_type == "duration":
            delay(self.shake_time)
        elif self.shake_type == "number":
            delay(self.shake_num/point) # shake for num periods
        else:
            raise Exception("Invalid shake type..")
            
            

        # Stop shaking: switch back to profile 7 (addresses 1022-1023,
        self.ttl5.off()
        self.Bragg.aom_lattice.cpld.set_profile(7)
        self.Bragg.aom_lattice.cpld.io_update.pulse_mu(8)

        delay(self.drop_time)
        self.MOTs.take_MOT_image(self.Camera)

        delay(10*ms)
        self.MOTs.AOMs_on_all()
        delay(50*ms)
        ports = self.Camera.process_image(bg_sub=True, return_ports=["narrow", "wide"])
        narrow_counts, wide_counts = ports[0], ports[1]
        self.core.break_realtime()
        delay(10*ms)
        return int(10**6 * narrow_counts/wide_counts)



    def after_scan(self):
        self.Camera.disarm()

    @kernel
    def load_mod(self, dds, ai, af, freq):
        # one host round-trip, table arrives prepacked
        step, ram_data = self._build_ram_table(ai, af, freq)
        self.core.break_realtime()  # RPC ate ~ms of wall clock
        delay(1*ms)
        
        # turn off RAM mode
        dds.set_cfr1(ram_enable=0)
        dds.cpld.io_update.pulse_mu(8)
        delay(100*us)

        # set profile registers
        dds.set_profile_ram(start=1022, end=1023, step=step,
                            profile=7, mode=ad9910.RAM_MODE_CONT_RAMPUP)
        delay(100*us)
        dds.set_profile_ram(start=0, end=1021, step=step,
                            profile=0, mode=ad9910.RAM_MODE_CONT_RAMPUP)
        delay(100*us)

    
        # write sweep
        dds.cpld.set_profile(0)
        dds.cpld.io_update.pulse_mu(8)
        delay(100*us)
        dds.write_ram(ram_data[:1022])
        delay(100*us)
    
        # write single frequency
        dds.cpld.set_profile(7)
        dds.cpld.io_update.pulse_mu(8)
        delay(100*us)
        dds.write_ram(ram_data[1022:])
        delay(100*us)        
        
        # ram enable
        dds.set_cfr1(internal_profile=0, ram_enable=1,
                     ram_destination=ad9910.RAM_DEST_ASF)
        dds.cpld.io_update.pulse_mu(8)
        delay(1000*us)



    @rpc
    def _build_ram_table(self, ai, af, freq) -> TTuple([TInt32, TArray(TInt32)]):  # pyright: ignore[reportInvalidTypeForm]
        # perform on host
        k_ideal = round(N_CYCLES_IN_RAM/(N_SINE*freq*(4*ns)))
        k = min(5000, max(1, k_ideal))
        
        dphi = 2*np.pi * freq * 4*ns * k
        table = 0.5*(ai+af) + 0.5*(ai-af)*np.cos(dphi*np.arange(N_SINE))  
        
        
        table = np.concatenate([table, [self.Bragg.scale_Lattice]*2])
        ram = np.zeros(1024, dtype=np.int32)
        self.Bragg.aom_lattice.amplitude_to_ram(table, ram)
        return (k, ram)










        
        