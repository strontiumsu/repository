#-*- coding: utf-8 -*-
"""
Created on Wed Aug  2 10:59:20 2023

@author: E. Porter
"""

from scan_framework import Scan1D, TimeScan
from artiq.experiment import Scannable, RangeScan, EnumerationValue, BooleanValue, NumberValue, at_mu, sequential, s # pyright: ignore[reportMissingImports]
from artiq.experiment import kernel, EnvExperiment, kHz, delay, ms, parallel, us, MHz, now_mu, ns # pyright: ignore[reportMissingImports]


from CoolingClass import _Cooling
from CameraClass import _Camera
from BraggClass import _Bragg
from repository.models.scan_models import DipoleTemperatureModel # pyright: ignore[reportMissingImports]


class DipoleTrapTemperature_exp(Scan1D, TimeScan, EnvExperiment):

    def build(self, **kwargs):
        # required initializations

        super().build(**kwargs)
        self.setattr_device("ttl5")
        self.enable_pausing = True
        self.enable_auto_tracking = False
        self.enable_profiling = False

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
        self.Camera.camera_init()
        self.Bragg.prepare_aoms()
        # register model with scan framework
        self.enable_histograms = True
        self.model = DipoleTemperatureModel(self)
        self.register_model(self.model, measurement=True, fit=True)

        self.Camera.prep_temp_datasets(len(list(self.get_scan_points())))




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
        delay(100*ms)
        self.MOTs.atom_source_on()
        delay(100*ms)
        self.MOTs.AOMs_on_all()
        delay(200*ms)
        self.MOTs.AOMs_off_all()
        self.MOTs.atom_source_off()




    @kernel
    def measure(self, point):
        t_delay = point
        self.core.wait_until_mu(now_mu())
        self.core.reset()
        self.Camera.arm()
        delay(200*ms)
        self.ttl5.off()  # NEW TAKE OUT  
        self.MOTs.AOMs_off_all()
        delay(10*ms)

        self.MOTs.init_rmot_dds(self.MOTs.rmot_freq_i, self.MOTs.rmot_freq_f, self.MOTs.rmot_freq_depth_i, self.MOTs.rmot_freq_depth_f, self.MOTs.freq_3D_red)
        delay(10 * ms)
        
        
        # self.Bragg.aom_dipole.set_att(15.0)
        # self.Bragg.aom_lattice.set_att(30.0)
        
        # # generate red mot
        # self.MOTs.rMOT_pulse_new(dipole_on=False)
        
        # self.Bragg.aom_dipole.set_att(self.Bragg.atten_Dipole)     
        # self.Bragg.aom_lattice.set_att(3.0)
        
        self.MOTs.rMOT_pulse_new()
        
        # load into dipole trap and perform molasses (if selected)
        # Total time for this sequence needs to be >~ 40 ms for cavity shaking to stop.
        with parallel:
            delay(self.load_time/3) 
            self.MOTs.set_current_dir(1) # let MOT field go to zero and switch H-bridge, 15ms     
        if self.MOTs.molasses:
            self.MOTs.molasses_pulse(freq=self.MOTs.molasses_frequency, amp=0.1, t=self.load_time/3)
        else:
            delay(self.load_time/3)

        
        self.MOTs.Blackman_ramp(0.0, self.B_field ,self.load_time/3) # set bias field so 3P1 m=+1 is ~40MHz separated.
 
        
        self.Bragg.aom_dipole.set_att(30.0) # turn off dipole
        self.Bragg.aom_lattice.sw.off() #turn off lattice
 
        
        delay(t_delay)  # drop time
        self.MOTs.take_MOT_image(self.Camera) # image after variable drop time

        self.Bragg.aom_dipole.set_att(self.Bragg.atten_Dipole)        
        self.Bragg.aom_lattice.sw.on()
        

        delay(10*ms)
        self.MOTs.AOMs_on_all()
        self.ttl5.off()
        delay(50*ms)
        self.Camera.process_image(bg_sub=True)
        delay(400*ms)
        self.MOTs.set_current_dir(0)
        delay(100*ms)
        #return self.Camera.get_totalcount_stats_port2()
        # if self.plot_direction == 'X':
        #     return self.Camera.process_gaussian(3)
        # else:
        #     return self.Camera.process_gaussian(4)
        return 0
            
    def after_scan(self):
        pass
        
        # data = np.array(self.Camera.get_dataset('gaussianparams'))
        # A, center_y, center_x, sigma_y_2, sigma_x_2, offset = data[:,0], data[:,1], data[:,2], data[:,3],data[:,4], data[:,5]
        # t=self.get_scan_points()

        
        # popt, _ = curve_fit(self.quadratic,list(t),center_y,maxfev=20000);


        # ###g/2 = a pixels/ms^2 = 9.8m/s^2 =
        # pix2um = 9.81e6/(popt[0]*2)

        
        # sigma_y_2*=pix2um**2
        # sigma_x_2*=pix2um**2
        
        
     
        # popt_temp_x, _ = curve_fit(self.quadratic,list(t),sigma_x_2,maxfev=20000);     
        # popt_temp_y, _ = curve_fit(self.quadratic,list(t),sigma_y_2,maxfev=20000);
        
        # print(popt_temp_x)


        # M  = constants.value('atomic mass constant')*87.9
        # Kb = constants.value('Boltzmann constant')
        # tempX = popt_temp_x[0]*1e-12*M/Kb * 1e6
        # tempY = popt_temp_y[0]*1e-12*M/Kb * 1e6
        
        # self.set_dataset("TOF.TempX", tempX, broadcast=True)
        # self.set_dataset("TOF.TempY", tempY, broadcast=True)
        # self.set_dataset("TOF.pix2um", pix2um, broadcast=True)

        
    def quadratic(self, x,a,b,c):
        return a*x**2+b*x+c