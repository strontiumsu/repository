# -*- coding: utf-8 -*-
"""
Created on Tue Jan 21 13:37:31 2025

@author: sr
"""

from scan_framework import Scan2D

from artiq.experiment import Scannable, RangeScan, EnumerationValue, BooleanValue, NumberValue, at_mu, sequential, s # pyright: ignore[reportMissingImports]
from artiq.experiment import kernel, EnvExperiment, kHz, delay, ms, parallel, us, MHz, now_mu, ns # pyright: ignore[reportMissingImports]
from artiq.coredevice import ad9910 # pyright: ignore[reportMissingImports]
import numpy as np




from CoolingClass import _Cooling
from CameraClass import _Camera

from StateControlClass import _state_control
from BraggClass import _Bragg

from repository.models.scan_models import RamseyPhaseModel # pyright: ignore[reportMissingImports]
from repository.models.scan_models import RamseyDecayModel # pyright: ignore[reportMissingImports]


class ClockRamseyPhase2D_VRSexp(Scan2D, EnvExperiment):
    
    def build(self, **kwargs):
        # required initializations
        
        super().build(**kwargs)
        
        self.setattr_device("ttl5") # triggering pulse
        self.setattr_device("ttl1")
        # import classes for experiment control
        self.MOTs = _Cooling(self)
        self.Camera = _Camera(self)
        self.State_Control = _state_control(self)
        self.Bragg = _Bragg(self)
        
        
        self.enable_pausing = True # disable to speed up by not checking scheduler
        self.enable_auto_tracking=False
        self.enable_profiling = False # enable to print runtime statistics to find bottlenecks
        
        self.ind = 0
        self.ramsey_phase_exp = 0.0*1e-6
        self.delay_exp = 0.0*1e-6

        self.setattr_argument('pulse_phase',
            Scannable(default=RangeScan(
            start=0.0,
            stop=2.0,
            npoints=20),
            scale=1,
            ndecimals=2,
            unit="Turns", ), 'Params')
        
        self.setattr_argument('delay', Scannable(
            default=RangeScan(
                start=0.0,
                stop=100.0e-6,
                npoints=20
            ),
            scale=1e-6,
            ndecimals=2,
            unit="us"
        ), group='Ramsey')
        
        self.scan_arguments(nbins={'default':1000},
                    nrepeats={'default':1},
                    npasses={'default':1},
                    fit_options={'default':"No Fits"})
        
        self.setattr_argument("dipole_load_time", NumberValue(60.0*1e-3,min=0.0*1e-3,max=9000.00*1e-3,scale=1e-3,
                      unit="ms"),"Params")
        
        self.setattr_argument("pi_2_time689", NumberValue(1.0*1e-6,min=0.0*1e-6,max=1000.00*1e-6,scale=1e-6,ndecimals=3,
                      unit="us"),"Params")
        self.setattr_argument("pi_time689", NumberValue(1.0*1e-6,min=0.0*1e-6,max=1000.00*1e-6,scale=1e-6,ndecimals=3,
                      unit="us"),"Params")
        self.setattr_argument("pi_timeRaman", NumberValue(1.0*1e-6,min=0.0*1e-6,max=1000.00*1e-6,scale=1e-6,ndecimals=3,
                      unit="us"),"Params")
        self.setattr_argument("pi_2_timeRaman", NumberValue(1.0*1e-6,min=0.0*1e-6,max=1000.00*1e-6,scale=1e-6,ndecimals=3,
                      unit="us"),"Params")
        self.setattr_argument("Ramsey_time", NumberValue(10.0*1e-6,min=0.0*1e-6,max=1000.00*1e-6,scale=1e-6,
                      unit="us"),"Params")
        
        self.setattr_argument("excited_state", EnumerationValue(['3P1', '3P0'], default='3P1'), "Params")
        self.setattr_argument("readout_scheme", EnumerationValue(["0","1","2"], default="0"), "Params")
        self.setattr_argument("B_field", NumberValue(0.21,min=0.0,max=2,scale=1,
                      unit="V", ndecimals=3),"Params")
        
        self.setattr_argument("Echo",BooleanValue(False),"Ramsey")
        self.setattr_argument("cavity_clear",BooleanValue(False),"Params")
        self.setattr_argument("free_space",BooleanValue(False),"Params")
        self.setattr_argument("randomize_phase",BooleanValue(False),"Params")


        # VRS Scan args
        self.setattr_argument("freq_center", NumberValue( 3*1e6,min=0.1*1e6, max=200.0*1e6,scale=1e6, unit="MHz",ndecimals = 3),"parameters")
        self.setattr_argument("freq_width", NumberValue( 1*1e6,min=-10*1e6, max=50.0*1e6,scale=1e6, unit="MHz",ndecimals = 3),"parameters")     
        self.setattr_argument("scan_time", NumberValue( 100*1e-6,min=1*1e-6, max=100000.0*1e-6,scale=1e-6, unit="us",ndecimals = 3),"parameters")
        self.setattr_argument("Scan_Ch", EnumerationValue(["Carrier", "Sideband"], default='Carrier'), "parameters")
        self.setattr_argument("delay_time", NumberValue(60.0*1e-3,min=0.0*1e-3,max=10.00*1e-3,scale=1e-3,
                      unit="ms"),"Params")
        
        # boolean args
        self.setattr_argument("Pre_measure", BooleanValue(True), "parameters")
             
                
        # Prep DDS scan
        self.freq_list= np.linspace(0.0*MHz, 0.0*MHz, 1024)
        self.freq_list_ram = np.full(1024, 1)
        self.step_size=0
        self.scan_dds = self.Bragg.aom_carrier
        
        self.t0 = np.int64(0)
        self.FIX_DELAY_TIME = 150*ns
        self.scan0 = 0
        self.scan1 = 0
        
        #self.random_phase = list(np.random.uniform(0,2,100))
        #self.set_dataset("random_phases", np.full(100, np.nan), broadcast=True)


        
    def get_scan_points(self):
        if self.randomize_phase:
            phases=list(self.pulse_phase)
            
            rng = np.random.default_rng(seed=42)
            rand_phases     = rng.uniform(low=phases[0], high=phases[-1], size=len(phases))
            
            #rand_phases=list(np.random.uniform(phases[0],phases[-1],len(phases)))
            self.set_dataset("random_phases", rand_phases, broadcast=True)

            return [self.delay, rand_phases]  
        else:   
            return [self.delay, self.pulse_phase]  
    
    @kernel
    def set_scan_point(self, i_point, point):
        self.ramsey_phase_exp = point[1]
        self.delay_exp = point[0]
        self.core.break_realtime()
        
    def prepare(self):
        #prepare/initialize mot hardware and camera
        self.MOTs.prepare_aoms()
        self.Bragg.prepare_aoms()
        self.State_Control.prepare_aoms()
        
        self.MOTs.prepare_coils()
        
        self.Camera.camera_init(scheme = 0)
        
        
        self.enable_histograms = True
        self.model1 = RamseyDecayModel(self)
        self.model2 = RamseyPhaseModel(self)
        self.register_model(self.model1, dimension=0, fit=True, set=True)
        self.register_model(self.model2, dimension=1, fit=True, set=True, measurement=True)
        
        if self.freq_width/2 > self.freq_center: raise Exception("Bad Range...")
        if self.Scan_Ch == "Sideband": self.scan_dds = self.Bragg.aom_sideband

    @kernel
    def before_scan(self):
        # runs before experiment take place
        
        self.core.reset()
        delay(10*ms)
        self.ttl5.off()
        self.MOTs.init_coils()
        self.MOTs.init_ttls()
        
        #init AOMs
        self.MOTs.init_aoms(on=False)  
        self.State_Control.init_aoms(on=False)
        self.Bragg.init_aoms()
        
        delay(10*ms)
        
        #MOT Config
        self.MOTs.set_current_dir(0)
        delay(10*ms)
        
        self.MOTs.take_background_image_exp(self.Camera)
        
        # Warm up before exp
        delay(50*ms)
        self.core.wait_until_mu(now_mu())
    
    def before_measure(self, point, measurement):
        self.Camera.arm()    
        
        
    @kernel
    def measure(self, point):        
        
        #prepare
        self.core.wait_until_mu(now_mu())
        self.core.reset()
        

        self.MOTs.init_rmot_dds(self.MOTs.rmot_freq_i, self.MOTs.rmot_freq_f,  self.MOTs.rmot_freq_depth_i, self.MOTs.rmot_freq_depth_f, self.MOTs.freq_3D_red)
        delay(5*ms)
        
        self.core.break_realtime()
        delay(10*ms)
        self.load_scan()
        delay(10*ms)
        self.core.break_realtime()
        delay(10*ms)

    

        self.MOTs.AOMs_off_all()
        self.State_Control.AOMs_off_all()               
        delay(200*ms)

        self.set_phases(point)
        delay(10*ms)
        
        #### ENSURE KNOWN STATES ################
        delay(1*ms)
         
        self.State_Control.aom_689.set(frequency=self.State_Control.freq_689, amplitude=0.8)
        self.State_Control.aom_688.set(frequency=self.State_Control.freq_688, amplitude=0.8)
        self.State_Control.aom_679.set(frequency=self.State_Control.freq_679, amplitude=0.8)
        
        delay(1*ms)
        
        self.Bragg.aom_sideband.set_att(self.Bragg.atten_Sideband)
        self.Bragg.aom_carrier.set_att(self.Bragg.atten_Carrier)
        self.MOTs.aom_3D_blue.set_att(self.MOTs.atten_3D)
        delay(1*ms)
        
    
        # generate red mot
        self.MOTs.rMOT_pulse_new()
        # load into dipole trap and perform molasses (if selected)
        # Total time for this sequence needs to be >~ 40 ms for cavity shaking to stop.
        with parallel:
            delay(self.dipole_load_time/3) 
            self.MOTs.set_current_dir(1) # let MOT field go to zero and switch H-bridge, 15ms        
        if self.MOTs.molasses:
            self.MOTs.molasses_pulse(freq=self.MOTs.molasses_frequency, amp=0.1, t=self.dipole_load_time/3)
        else:
            delay(self.dipole_load_time/3)
        self.MOTs.Blackman_ramp(0.0, self.B_field,self.dipole_load_time/3) # set bias field so 3P1 m=+1 is ~40MHz separated.
        delay(5*ms)
            

        if self.free_space:
            self.Bragg.aom_dipole.set_att(30.0)
            self.Bragg.aom_lattice.sw.off()
        
        delay(150*us)
        #self.MOTs.aom_3D_blue.sw.on()
        #delay(50*us)
        #self.MOTs.aom_3D_blue.sw.off()
    
        if self.Pre_measure:    
            self.ttl5.on()       # for triggering start

            self.scan_probe(self.scan_time)
            self.ttl5.off()       # for triggering start
        delay(1*us)
        # -----  3P1 EXCITATION -----------------------
        if self.excited_state=='3P1':
            self.ttl5.on()       # for triggering start
            self.State_Control.pulse_689(self.pi_2_time689)
            if self.Echo:
                delay(self.delay_exp)
                self.State_Control.pulse_689(self.pi_time689)
            
            with parallel:
                #delay(1.2*us) # ensures the profile has enough time to switch
                delay(self.delay_exp+1.2*us)
                #delay(self.delay_exp*point[1]+1.2*us)
                self.State_Control.switch_profile(1)
            self.State_Control.pulse_689(self.pi_2_time689)
            self.ttl5.off()
            
            
            ############## BAD CODING PRACTICE, 3P0 SIMUL ##############
            # with parallel:
            #     self.State_Control.pulse_679(self.pi_2_time689)
            #     self.State_Control.pulse_688(self.pi_2_time689)
            #     with sequential:
            #         delay(90*ns)
            #         self.State_Control.pulse_689(self.pi_2_time689)
            
            # with parallel:
            #     #delay(1.2*us) # ensures the profile has enough time to switch
            #     delay(self.delay_exp+1.2*us)
            #     self.State_Control.switch_profile(1)
                
            # with parallel:
            #     self.State_Control.pulse_679(self.pi_2_time689)
            #     self.State_Control.pulse_688(self.pi_2_time689)
            #     with sequential:
            #         delay(90*ns)
            #         self.State_Control.pulse_689(self.pi_2_time689)
            # self.ttl5.off()
            #########################################################
        
            self.readout(scheme="0")

            

        

        # -----  3P0 EXCITATION -----------------------
        elif self.excited_state=='3P0':
            if self.cavity_clear:
                # prepare in 3P0
                self.ttl5.on()       # for triggering start
                self.State_Control.pulse_689(self.pi_time689)
                delay(0.05*us)
                with parallel:
                    self.State_Control.pulse_679(self.pi_timeRaman)
                    self.State_Control.pulse_688(self.pi_timeRaman)
                # clear cavity
                #self.State_Control.cav_clear_pulse(2.5*ms)
                self.State_Control.push_pulse(20*us)
                delay(2*us)
                
                # Rabi flop from 3P0
                with parallel:
                    self.State_Control.pulse_679(self.pi_2_timeRaman)
                    self.State_Control.pulse_688(self.pi_2_timeRaman)
                delay(0.25*us)
                self.State_Control.pulse_689(self.pi_time689)
                
                delay(self.delay_exp/2)

                #### MEASURE VRS ############
                self.ttl5.on()       # for triggering start
                self.scan_probe(self.scan_time)
                self.ttl5.off() 
    
                if self.Echo:
                    #delay(500*us)
                    #delay(self.delay_exp)
                    #delay(self.delay_exp*point[1])
                    
                    ### Procedure 1
                    self.State_Control.pulse_689(self.pi_time689)
                    delay(0.05*us)
                    with parallel:
                        self.State_Control.pulse_688(self.pi_timeRaman)
                        self.State_Control.pulse_679(self.pi_timeRaman)
                    delay(0.25*us)
                    self.State_Control.pulse_689(self.pi_time689)
                    
                    
                with parallel:
                    delay(self.delay_exp/2+1.2*us)
                    self.State_Control.switch_profile(1)
                # self.State_Control.pulse_689(self.pi_time689)
                # delay(0.05*us)
                # with parallel:
                #     self.State_Control.pulse_679(self.pi_2_timeRaman)
                #     self.State_Control.pulse_688(self.pi_2_timeRaman)
                
                

                with parallel:
                    self.State_Control.pulse_679(self.pi_timeRaman)
                    self.State_Control.pulse_688(self.pi_timeRaman)
                delay(.25*us)
                self.State_Control.pulse_689(self.pi_2_time689)
                
                # with parallel:
                #     self.State_Control.pulse_679(self.pi_timeRaman)
                #     self.State_Control.pulse_688(self.pi_timeRaman)
                # delay(0.3*us)
                # self.State_Control.pulse_689(self.pi_2_time689)
                
                
                
                

            
                
            else:    
                ############ CURRENTLY NO CAVITY READOUT HERE 
                self.ttl5.on()       # for triggering start
                
              
                     
                self.State_Control.pulse_689(self.pi_2_time689)
                delay(0.05*us)
                with parallel:
                    self.State_Control.pulse_688(self.pi_timeRaman)
                    self.State_Control.pulse_679(self.pi_timeRaman)
                    
                if self.Echo:
                    #delay(500*us)
                    delay(self.delay_exp+1.2*us)
                    
                    ## Procedure 1
                    self.State_Control.pulse_689(self.pi_time689)
                    delay(0.05*us)
                    with parallel:
                        self.State_Control.pulse_688(self.pi_timeRaman)
                        self.State_Control.pulse_679(self.pi_timeRaman)
                    delay(0.25*us)
                    self.State_Control.pulse_689(self.pi_time689)
                    
                    ### Procedure 2
                    # with parallel:
                    #     self.State_Control.pulse_688(self.pi_timeRaman)
                    #     self.State_Control.pulse_679(self.pi_timeRaman)
                    # delay(0.35*us)
                    # self.State_Control.pulse_689(self.pi_time689)
                    # delay(0.15*us)
                    # with parallel:
                    #     self.State_Control.pulse_688(self.pi_timeRaman)
                    #     self.State_Control.pulse_679(self.pi_timeRaman)
                    
                with parallel:
                    delay(self.delay_exp+1.2*us)
                    self.State_Control.switch_profile(1)
                with parallel:
                    self.State_Control.pulse_688(self.pi_timeRaman)
                    self.State_Control.pulse_679(self.pi_timeRaman)
                delay(0.25*us)
                self.State_Control.pulse_689(self.pi_2_time689)
            
            
            self.ttl5.off()

            self.readout(scheme=self.readout_scheme)
       
                
                
        else:
            raise Exception('Not Valid State')

        
        self.Bragg.aom_dipole.set_att(self.Bragg.atten_Dipole)
        self.Bragg.aom_lattice.sw.on()
        # image and reset for next shot
        self.MOTs.take_MOT_image(self.Camera)  
        delay(15*ms)
        
        self.scan_dds.set_cfr1(ram_enable=0)
        self.scan_dds.cpld.io_update.pulse_mu(8)
        self.MOTs.set_current(0.0)
        delay(20*ms)
        self.MOTs.set_current_dir(0)
        delay(5*ms)  
        
        #process and output
        self.MOTs.AOMs_on_all() # just keeps AOMs warm

        self.Camera.process_image(save=True, name='', bg_sub=True)

        delay(400*ms)
        #self.mutate_dataset("random_phases", self.ind, self.random_phase[self.ind])

        self.ind += 1
        val = self.Camera.get_push_stats()
        self.write_val(val)
        return val
        #return self.Camera.get_push_stats()

    @kernel
    def scan_probe(self, time):
        with parallel:
            self.Bragg.aom_carrier.sw.on()
            self.Bragg.aom_sideband.sw.on()
            self.ttl5.on()
            self.scan_dds.cpld.io_update.pulse_mu(8)
            
        delay(time)
        
        with parallel:
            self.Bragg.aom_carrier.sw.off()
            self.Bragg.aom_sideband.sw.off()
            self.ttl5.off()
            
            
    @kernel
    def load_scan(self):
        self.step_size = int(self.scan_time/(1024*4*ns))
        f0 = self.freq_center + self.freq_width/2
        
    
        f_step = self.freq_width / 1023        
        for i in range(1024):
            self.freq_list[i] = f0 - f_step*i
            
        # f_step = self.freq_width / 511       
        # for i in range(512):
        #     self.freq_list[i] = f0 - f_step*i
        #     self.freq_list[-1-i] = f0 - f_step*i

            
        self.scan_dds.frequency_to_ram(self.freq_list, self.freq_list_ram)

        self.core.break_realtime()
        delay(10 * ms)


        self.scan_dds.set_cfr1(ram_enable=0)
        self.scan_dds.cpld.io_update.pulse_mu(8)

        delay(1*ms)
        self.scan_dds.set_profile_ram(start=0, end=1024-1, step=(self.step_size | (2**6 - 1 ) << 16),
                                  profile=0, mode=ad9910.RAM_MODE_RAMPUP)
        delay(5*ms)
        self.scan_dds.cpld.set_profile(0)
        self.scan_dds.cpld.io_update.pulse_mu(8)
        self.scan_dds.write_ram(self.freq_list_ram)
        # prepare to enable ram and set frequency as target
        delay(1*ms)
        self.scan_dds.set_cfr1(internal_profile=0, ram_enable=1, ram_destination=ad9910.RAM_DEST_FTW)
        delay(10*ms)

        self.core.wait_until_mu(now_mu())  
    
    @kernel
    def readout(self, scheme):
        """
        reading out ports
        scheme 0 seperates 1S0 and 3P1, leaves metastable states dark
        scheme 1 seperates 1S0 and 3P1 and 3P1/2
        scheme 2 seperates 1S0+3P1 and 3P2 and 3P0
            note there is mixing of metstable ports in scheme 2

        """
        if scheme == "0":
            self.State_Control.push_pulse(self.MOTs.Push_pulse_time)            
            #self.MOTs.aom_3P0.sw.on()
            #self.MOTs.aom_3P2.sw.on()
            delay(self.MOTs.Delay_duration)
            #self.MOTs.aom_3P0.sw.off()
            #self.MOTs.aom_3P2.sw.off()

        elif scheme == "1":
            self.State_Control.push_pulse(self.MOTs.Push_pulse_time)
            delay(200*us)
            self.State_Control.push_pulse(self.MOTs.Push_pulse_time)
            delay(5*us)
            
            self.MOTs.aom_3P0.sw.on()
            self.MOTs.aom_3P2.sw.on()
            delay(self.MOTs.Delay_duration)
            self.MOTs.aom_3P0.sw.off()
            self.MOTs.aom_3P2.sw.off()
            
        elif scheme == "2": #readout with 3P2 port
            delay(200*us)
            self.State_Control.push_pulse(self.MOTs.Push_pulse_time)

            self.MOTs.aom_3P2.sw.on()
            delay(200*us)
            self.MOTs.aom_3P2.sw.off()
            
            delay(200*us)
            self.State_Control.push_pulse(self.MOTs.Push_pulse_time)
            delay(5*us)
            
            self.MOTs.aom_3P0.sw.on()
            self.MOTs.aom_3P2.sw.on()
            delay(self.MOTs.Delay_duration)
            self.MOTs.aom_3P0.sw.off()
            self.MOTs.aom_3P2.sw.off()
            
        elif scheme == "3": #readout without repumpers
            self.State_Control.push_pulse(self.MOTs.Push_pulse_time)
            delay(10*us)
            with parallel:
                    self.State_Control.pulse_688(self.pi_timeRaman)
                    self.State_Control.pulse_679(self.pi_timeRaman)

            delay(200*us)
            
            delay(self.MOTs.Delay_duration)
        else:
            raise Exception("Not a valid readout scheme...")
            
            
            
    @kernel
    def raman_pulse(self, time):
        self.State_Control.aom_688.sw.on()
        delay(0.1*us)
        self.State_Control.aom_679.sw.on()
        
        
        delay(time)
        
        
        self.State_Control.aom_688.sw.off()
        delay(0.07*us)
        self.State_Control.aom_679.sw.on()
                
    @kernel
    def set_phases(self, point):
        #rphase = self.random_phase[self.ind] 
        
        self.State_Control.set_AOM_phase(0, self.State_Control.freq_688, 0.0, self.t0, 0)
        self.State_Control.set_AOM_phase(0, self.State_Control.freq_688, 0.0, self.t0, 1)

        #
        self.State_Control.set_AOM_phase(1, self.State_Control.freq_Push, 0.0, self.t0, 0)
        self.State_Control.set_AOM_phase(1, self.State_Control.freq_Push, 0.0, self.t0, 1)


        self.State_Control.set_AOM_phase(2, self.State_Control.freq_679, 0.0, self.t0, 0)
        self.State_Control.set_AOM_phase(2, self.State_Control.freq_679, point[1], self.t0, 1)


        self.State_Control.set_AOM_phase(3, self.State_Control.freq_689, 0.0, self.t0, 0)
        self.State_Control.set_AOM_phase(3, self.State_Control.freq_689, 0.0, self.t0, 1)
        #self.State_Control.set_AOM_phase(3, self.State_Control.freq_689, rphase, self.t0, 1)

        
        self.State_Control.switch_profile(0)
        
    def calculate_dim0(self, dim1_model):   
        param = 2*dim1_model.fit.params.A
        # weight final fit by error in this dimension 1 fit param
        error = dim1_model.fit.errs.A_err
        self.set_dataset(f"ContrastMeasurement_{self.scan1}", param, broadcast=False)
        self.scan1 += 1
        return param, error
    
    def write_val(self, val):
        self.set_dataset(f"PhaseMeasurement_{self.scan0}_{self.scan1}", val, broadcast=False)
        self.scan0 += 1  
        
        