#-*- coding: utf-8 -*-
"""
Created on Wed Aug  2 10:59:20 2023

@author: E. Porter
"""

from scan_framework import Scan1D, TimeScan
from artiq.experiment import  EnumerationValue, NumberValue  # pyright: ignore[reportMissingImports]
from artiq.experiment import kernel, EnvExperiment, delay, ms, parallel, us, now_mu # pyright: ignore[reportMissingImports]

import numpy as np
from scipy.optimize import curve_fit
from scipy import constants

from CoolingClass import _Cooling
from CameraClass import _Camera
from BraggClass import _Bragg

from repository.models.scan_models import DipoleTemperatureModel # pyright: ignore[reportMissingImports]


class DipoleTrapTemperature_exp(Scan1D, TimeScan, EnvExperiment):

    def build(self, **kwargs):
        super().build(**kwargs)
        self.enable_auto_tracking = False

        # import classes for experiment control
        self.MOTs = _Cooling(self)
        self.Camera = _Camera(self)
        self.Bragg = _Bragg(self)

        # scan settings
        self.scan_arguments(times = {'start':0.1*1e-3,
            'stop':100*1e-3,
            'npoints':20,
            'unit':"ms",
            'scale':ms,
            'global_step':1*us,
            'ndecimals':2},
            nbins = {'default':1000},
            nrepeats = {'default':1},
            npasses = {'default':1},
            fit_options = {'default':"Fit and Save"}
            )


        self.setattr_argument("load_time", NumberValue(60*1e-3,min=1.0*1e-3,max=5000.00*1e-3,scale=1e-3,
                     unit="ms"),"parameters")
        self.setattr_argument("plot_direction", EnumerationValue(['X','Y']),"parameters")
        self.setattr_argument("B_field", NumberValue(0.36,min=0.0,max=2,scale=1,
                      unit="V", ndecimals=3),"parameters")

    def prepare(self):
        #prepare/initialize mot hardware and camera
        self.MOTs.prepare_aoms()
        self.MOTs.prepare_coils()
        self.Bragg.prepare_aoms()

        scan_points = np.array(list(self.get_scan_points()))
        N = len(scan_points)

        self.Camera.camera_init(N=N*self.nrepeats*self.npasses + 1)

        self.model = DipoleTemperatureModel(self)
        self.register_model(self.model, measurement=True, fit=True)


        # prepare empty datasets for fitting
        self.set_dataset( "gaussianparams", np.zeros((N, 5)), broadcast=True)
        self.set_dataset("TOF.drop_times_s", scan_points, broadcast=True, persist=False)
        self.set_dataset("TOF.fit_t_dense",
                         np.linspace(0.0, float(scan_points.max()), 200),
                         broadcast=True, persist=False)
        for k in ("TOF.pix2um", "TOF.T_x_uK", "TOF.T_y_uK",
                  "TOF.sigma0_x_um", "TOF.sigma0_y_um"):
            self.set_dataset(k, float("nan"), broadcast=True, persist=False)

        nan_pair = np.array([float("nan"), float("nan")])
        self.set_dataset("TOF.fit_T_x", nan_pair, broadcast=True, persist=False)
        self.set_dataset("TOF.fit_T_y", nan_pair, broadcast=True, persist=False)





    @kernel
    def before_scan(self):
        # runs before experiment take place

        #initialize devices on host
        self.core.reset()
        self.MOTs.init_coils()
        self.MOTs.init_aoms(on=False)  # initializes whiling keeping them off
        self.Bragg.init_aoms()
        delay(10*ms)

        self.MOTs.take_background_image_exp(self.Camera)

        self.MOTs.AOMs_off_all()
        self.MOTs.atom_source_off()

        delay(10*ms)
        self.MOTs.init_rmot_dds(self.MOTs.rmot_freq_i,
                                self.MOTs.rmot_freq_f,
                                self.MOTs.rmot_freq_depth_i,
                                self.MOTs.rmot_freq_depth_f,
                                self.MOTs.freq_3D_red)




    @kernel
    def measure(self, point):
        self.core.break_realtime()
        delay(10*ms)

      
        self.MOTs.rMOT_pulse_new()
        delay(self.load_time)
        
        self.Bragg.aom_dipole.set_att(30.0) # turn off dipole
        self.Bragg.aom_lattice.sw.off() #turn off lattice
 
        delay(point)  # drop time
        self.MOTs.take_MOT_image(self.Camera) # image after variable drop time

        self.Bragg.aom_dipole.set_att(self.Bragg.atten_Dipole)        
        self.Bragg.aom_lattice.sw.on()
        delay(10*ms)
        
        self.core.wait_until_mu(now_mu())
        self.Camera.process_image(bg_sub=True)
        self.Camera.process_gaussian()
        self.core.break_realtime()

        return 0

    def after_scan(self):
        data = np.array(self.get_dataset("gaussianparams"))
        t = np.array(list(self.get_scan_points()))   # seconds

        cy_pix  = data[:, 1]   # column position = gravity direction
        sy_pix = data[:, 3]   # physical Y (vertical / gravity) variance, pix
        sx_pix = data[:, 4]   # physical X (horizontal) variance, pix

        try:
            popt_g, _ = curve_fit(lambda x, a,b,c:  a*x**2 + b*x + c, 
                                  t, cy_pix, maxfev=20000)
        except Exception as exc:
            raise RuntimeError(
                "after_scan: gravity-calibration fit on column centroid")

        g_coeff = abs(float(popt_g[0]))
        pix2m = 9.81 / (2.0 * g_coeff)
        pix2um = pix2m * 1e6

        sx_m = sx_pix * pix2m
        sy_m = sy_pix * pix2m

        M = constants.value('atomic mass constant') * 87.9056
        Kb = constants.value('Boltzmann constant')

        def sigma_model(tt, T, s0):
            return np.sqrt(s0**2 + (Kb * T / M) * tt**2)

        def fit_one_axis(tt, ss):
            popt, _ = curve_fit(sigma_model, tt, ss,
                                p0=[8e-6, ss[0]],
                                bounds=([0.0, 0.0], [np.inf, np.inf]),
                                maxfev=20000)
            return popt

        popt_x = fit_one_axis(t, sx_m)
        popt_y = fit_one_axis(t, sy_m)

        T_x_uK = float(popt_x[0] * 1e6)
        T_y_uK = float(popt_y[0] * 1e6)
        sigma0_x_um = float(popt_x[1]) * 1e6
        sigma0_y_um = float(popt_y[1]) * 1e6

        self.set_dataset("TOF.pix2um",       float(pix2um),      broadcast=True)
        self.set_dataset("TOF.T_x_uK",       T_x_uK,             broadcast=True)
        self.set_dataset("TOF.T_y_uK",       T_y_uK,             broadcast=True)
        self.set_dataset("TOF.sigma0_x_um",  sigma0_x_um,        broadcast=True)
        self.set_dataset("TOF.sigma0_y_um",  sigma0_y_um,        broadcast=True)
        self.set_dataset("TOF.fit_T_x",      np.asarray(popt_x), broadcast=True)
        self.set_dataset("TOF.fit_T_y",      np.asarray(popt_y), broadcast=True)


    