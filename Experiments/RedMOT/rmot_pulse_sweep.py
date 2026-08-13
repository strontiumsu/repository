# -*- coding: utf-8 -*-

from artiq.experiment import (EnvExperiment, kernel, ms,
                              NumberValue, EnumerationValue,
                              delay, now_mu, rpc)  # pyright: ignore[reportMissingImports]

import numpy as np

# imports (same class helpers Red_MOT_pulse uses)
from CoolingClass import _Cooling
from CameraClass import _Camera
from BraggClass import _Bragg


# Parameters you are allowed to sweep.
SCAN_PARAMS = [
    # --- Red MOT  sweep ---
    "freq_high_i", "freq_high_f",          # top of the modulation-depth sweep (Hz)
    "span_i", "span_f",                    # modulation depth below the top (Hz)
    "rmot_bb_current", "rmot_bb_duration", # broadband stage current (A) / hold (s)
    "rmot_ramp_duration",                  # bb -> sf compression time (s)
    "rmot_sf_current", "rmot_sf_duration", # single-frequency stage current (A) / time (s)
    "rmot_sf_freq_i", "rmot_sf_freq_f",    # sf-stage frequency endpoints (Hz)
    "rmot_sf_atten_i", "rmot_sf_atten_f",  # sf-stage Urukul atten endpoints (dB)
    "atten_ramp_i", "atten_ramp_f",        # VVA attenuation ramp endpoints (V)
    "ramp_tau",                            # shape time-constant
    "rmot_scan_frequency",                 # DRG modulation frequency (Hz)
    "binc", "to_bb_time", 
    "bmot_compress_atten", "bmot_compress_time",
    # --- AOM powers applied during the pulse ---
    "atten_3D_red", "scale_3D_red",        # red 3D AOM atten (dB) / amplitude
    "atten_3D", "scale_3D",                # blue 3D AOM atten (dB) / amplitude
    # --- Blue MOT ---
    "bmot_current", "bmot_ramp_duration", "bmot_load_duration"
]


class rmot_pulse_sweep(EnvExperiment):

    def build(self):
        self.setattr_device("core")
        self.setattr_device("scheduler")

        self.MOTs = _Cooling(self)
        self.Bragg = _Bragg(self)   # dipole/lattice beam AOMs in here
        self.Camera = _Camera(self)

        self.setattr_device("ttl5")  # timing pulse

        # --- pulse repeats + fixed wait (same idea as Red_MOT_pulse) ---
        self.setattr_argument("wait_time",
                              NumberValue(50.0*1e-3, min=0.0*1e-3, max=9000.0*1e-3, scale=1e-3, unit="ms"),
                              "parameters")
        self.setattr_argument("shots_per_point",
                              NumberValue(1, min=1, max=1000, ndecimals=0, step=1),
                              "parameters")

        # --- the 1D sweep ---
        self.setattr_argument("scan_param",
                              EnumerationValue(SCAN_PARAMS, default="freq_high_i"),
                              "sweep")
        # start/stop are in the parameter's BASE units (Hz, s, dB, A, V) -- see docstring
        self.setattr_argument("scan_start",
                              NumberValue(180.0e6, min=-1.0e12, max=1.0e12, ndecimals=6),
                              "sweep")
        self.setattr_argument("scan_stop",
                              NumberValue(181.0e6, min=-1.0e12, max=1.0e12, ndecimals=6),
                              "sweep")
        self.setattr_argument("scan_points",
                              NumberValue(11, min=1, max=1000, ndecimals=0, step=1),
                              "sweep")

    def prepare(self):
        # build the scan list (base units); keep as python floats for the kernel
        self.scan_values = [float(v) for v in
                            np.linspace(self.scan_start, self.scan_stop, int(self.scan_points))]
        n_shots = int(self.shots_per_point)
        n_images = 1 + len(self.scan_values) * n_shots   # 1 background + all pulse images

        # save the scan bookkeeping for post-processing
        self.set_dataset("rmot_sweep.param", self.scan_param, broadcast=True, archive=True)
        self.set_dataset("rmot_sweep.values", self.scan_values, broadcast=True, archive=True)
        self.set_dataset("rmot_sweep.shots_per_point", n_shots, broadcast=True, archive=True)
        self.set_dataset("rmot_sweep.counts", np.zeros(n_shots*len(self.scan_values)), broadcast=True, archive=True)
        self._img_ind = 0   # running pulse-image index into rmot_sweep.counts

        # same host prepares as Red_MOT_pulse
        self.MOTs.prepare_cooling()
        self.Bragg.prepare_aoms()
        self.Camera.camera_init(N=n_images)

    # ------------------------------------------------------------------
    # host: set the swept attribute wherever it lives, then recompute arrays
    # ------------------------------------------------------------------
    def _apply_value(self, value):
        name = self.scan_param
        hit = False
        for target in (self, self.MOTs, self.MOTs.dds):
            if hasattr(target, name):
                setattr(target, name, value)
                hit = True
        if not hit:
            raise ValueError("scan parameter '{}' not found on experiment/MOTs/dds".format(name))
        # recompute all host values
        self.MOTs.prepare_cooling()

    @rpc(flags={"async"})
    def _record_counts(self, counts):
        self.mutate_dataset("rmot_sweep.counts", self._img_ind, int(counts))
        self._img_ind += 1

    def run(self):
        print("rmot_pulse_sweep: scanning '{}' over {} (base units)".format(
            self.scan_param, self.scan_values))

        self._init_hardware()

        n_pts = len(self.scan_values)
        n_shots = int(self.shots_per_point)
        for pi in range(n_pts):
            value = self.scan_values[pi]
            self._apply_value(value)              # host: set attr + prepare_cooling
            self._rerecord()                      # kernel: erase + re-record DMA (once per point)

            print("  point {}/{}  {} = {:g}".format(pi + 1, n_pts, self.scan_param, value))
            for _ in range(n_shots):
                self._shot()                      # kernel: pulse + image

        self._finish()

    # ------------------------------------------------------------------
    # kernels
    # ------------------------------------------------------------------
    @kernel
    def _init_hardware(self):
        self.core.reset()
        self.Bragg.init_aoms(switches=0x9)
        self.MOTs.init_cooling()
        delay(10*ms)
        self.MOTs.take_background_image_exp(self.Camera)

    @kernel
    def _rerecord(self):
        # Re-record the 6 cooling DMA traces for the just-prepared parameters.
        # Erase first (reverse of record order) so the top block frees cleanly --
        # re-recording variable-size traces without erasing hangs the core.
        self.core.break_realtime()
        self.MOTs.core_dma.erase("field_blue_load")
        self.MOTs.core_dma.erase("field_sf_down")
        self.MOTs.core_dma.erase("field_to_bb")
        self.MOTs.core_dma.erase("field_blue_down")
        self.MOTs.core_dma.erase("field_blue_up")
        self.MOTs.core_dma.erase("rmot_ramp")
        self.MOTs._dma_record()
        self.core.break_realtime()

    @kernel
    def _shot(self):
        self.core.break_realtime()
        self.MOTs.rmot_pulse()
        delay(self.wait_time)
        self.MOTs.take_MOT_image(self.Camera)

        delay(10*ms)
        self.core.wait_until_mu(now_mu())
        ports = self.Camera.process_image(bg_sub=True, return_ports=['lattice'])
        lattice_counts = ports[0]
        self._record_counts(lattice_counts)
        self.core.break_realtime()

        delay(10*ms)

    @kernel
    def _finish(self):
        self.core.break_realtime()
        delay(100*ms)
        self.MOTs.AOMs_on_all()
        self.MOTs.atom_source_on()
