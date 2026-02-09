# -*- coding: utf-8 -*-

from artiq.experiment import *
from scan_framework import Scan1D, TimeScan


from BraggClass import _Bragg
from artiq.coredevice import ad9910

import numpy as np

class TTL_VRS(Scan1D, TimeScan, EnvExperiment):

    def build(self, **kwargs):
        super().build(**kwargs)

        # Core/hardware devices
        self.setattr_device("core")
        self.setattr_device("ttl5")     # exp timing
        self.setattr_device("ttl0")     # detection TTL input (gate_rising)

        # Experiment-specific helper classes
        self.Bragg = _Bragg(self)


        self.enable_pausing = True      # allow scheduler pausing
        self.enable_auto_tracking = False

        # --------- Scan framework parameters ---------
        self.scan_arguments(
            times={
                'start': 1*1e-6,
                'stop': 10*1e-6,
                'npoints': 20,
                'unit': "us",
                'scale': us,
                'global_step': 1*us,
                'ndecimals': 2
            },
            nbins={'default': 1000},
            nrepeats={'default': 1},
            npasses={'default': 1},
            fit_options={'default': "No Fits"}
        )

        # Trigger DDS (Bragg) scan parameters (pulse 1)
        self.setattr_argument("freq_center_sb", NumberValue(3*1e6, min=0.1*1e6, max=200.0*1e6, scale=1e6, unit="MHz", ndecimals=3), "scans")
        self.setattr_argument("freq_width_sb",  NumberValue(1*1e6, min=-50.0*1e6, max=50.0*1e6,scale=1e6, unit="MHz" ),"scans")
        self.setattr_argument("scan_time_sb",   NumberValue(1000*1e-6, min=1*1e-6, max=50000*1e-6,scale=1e-6, unit='us'),"scans")

        self.setattr_argument("freq_center_car",NumberValue(80*1e6, min=0.1*1e6, max=200.0*1e6,scale=1e6, unit="MHz", ndecimals=3 ),"scans")
        self.setattr_argument("freq_width_car", NumberValue( 1*1e6, min=-50.0*1e6, max=50.0*1e6,scale=1e6, unit="MHz"), "scans" )
        self.setattr_argument("scan_time_car",  NumberValue(1000*1e-6, min=1*1e-6, max=50000*1e-6,scale=1e-6, unit='us'),"scans")

        # --------- RAM buffers for the two DDS channels ---------  
        # Trigger DDS (Bragg sideband sweep)
        self.freq_list = np.linspace(0.0*MHz, 0.0*MHz, 1024)
        self.freq_list_ram = np.full(1024, 1)

        # Short-hands for the two actual ad9910 devices
        self.scan_dds_sb = self.Bragg.urukul_channels[1]
        self.scan_dds_car = self.Bragg.urukul_channels[2]
        
        self.step_mu_sb = 0

    def prepare(self):
        # Called on host; prepare AOMs/Urukul but not RTIO-critical
        self.Bragg.prepare_aoms()
        
        self.step_mu_sb = self.core.seconds_to_mu(
            int(self.scan_time_sb/(1023*4*ns)) * 4*ns
        )

    @kernel
    def before_scan(self):
        """
        Run once before the scan loop starts.
        Puts hardware into a known state.
        """
        self.core.reset()

        self.ttl0.input()      # ttl0 will be used as an input (gate_rising)
        # Initialize AOM DDS (sets frequencies, amplitudes, attenuation, etc.)
        self.Bragg.init_aoms(switches=0x9)
        delay(1*ms)
        self.core.wait_until_mu(now_mu())
        
        
    @kernel 
    def before_measure(self, point, measurement): # Make sure outputs start in a safe state 
        self.core.break_realtime() 
        delay(1*ms) 
        self.ttl5.off() 
        self.scan_dds_sb.sw.off() 
        self.scan_dds_car.sw.off() 
        delay(1*ms) # # Program RAM scan for trigger DDS (sideband) 
        self.core.wait_until_mu(now_mu())

    @kernel
    def measure(self, point):
        """
        One shot of the experiment.

        Sequence:
            1. Program RAM for trigger DDS (sideband sweep) and measurement DDS
               (carrier + scan in two profiles).
            2. Pulse 1:
                - Trigger DDS: RAM sweep
                - Measurement DDS: held at center frequency (profile 0 constant)
                - ttl0.gate_rising used to detect event time.
            3. Compute RAM index from the detection time and "freeze" the
               trigger DDS RAM at that index.
            4. Pulse 2:
                - Trigger DDS: fixed at frozen RAM index
                - Measurement DDS: RAM profile 1 (scan around carrier).
        """
        self.core.reset()
        delay(10*ms)
        
        self.ttl5.off()


        # # Program RAM scan for trigger DDS (sideband)
        self.load_scan(self.scan_dds_sb,self.freq_center_sb,self.freq_width_sb,self.scan_time_sb, 0, 1023)
        delay(5*ms)
        self.load_scan(self.scan_dds_car,self.freq_center_car,self.freq_width_car,self.scan_time_car, 0, 1023)
        delay(5*ms)
        self.freeze_RAM(self.scan_dds_car, 511, 511, self.scan_time_car)
        self.core.break_realtime()
        delay(1*ms)



        # --------- PULSE 1: trigger scan, meas held at carrier ----------
        t_start = now_mu() + self.core.seconds_to_mu(100*us)
        at_mu(t_start)


        #self.ttl5.on()
        delay(10*ns) # dont increment SED lane when sync not important

        with parallel:        
            t_end = self.ttl0.gate_rising(self.scan_time_sb + 2*ms) #lane0
            self.scan_dds_sb.cpld.io_update.pulse_mu(8) #lane1
            delay(10*ns)
            self.scan_dds_sb.sw.on() #lane1
            delay(10*ns)
            self.scan_dds_car.sw.on() #lane2
            



        t_edge = self.ttl0.timestamp_mu(t_end)


        if t_edge >= 0:
            # Move timeline to just after detected edge
            at_mu(t_edge)
            delay(10*us)

            # End of pulse 1
            #self.ttl5.off()
            delay(1*us)
            self.scan_dds_sb.sw.off()
            # delay(10*ns)
            self.scan_dds_car.sw.off()
            idx = int((t_edge - t_start) // self.step_mu_sb)

            
            delay(30*us)
            self.freeze_RAM(self.scan_dds_sb, idx,idx,self.scan_time_car)
            delay(30*us)
            self.freeze_RAM(self.scan_dds_car,0,1023, self.scan_time_car)
            delay(30*us)
 
            for _ in range(2):
                self.scan_dds_sb.cpld.io_update.pulse_mu(8)
                delay(10*ns)
                self.ttl5.on()
                delay(10*ns)
                self.scan_dds_car.sw.on()
                # delay(10*ns)
                self.scan_dds_sb.sw.on()
                
                
                delay(self.scan_time_car)
                
                
                self.scan_dds_sb.sw.off()
                delay(10*ns)
                self.scan_dds_car.sw.off()
                delay(10*ns)
                self.ttl5.off()
                delay(100*us)
            
        
            
        delay(20*ms)
        
        self.core.wait_until_mu(now_mu())

        return 0

    # ------------------------------------------------------------------
    # DDS RAM setup helpers
    # ------------------------------------------------------------------
    @kernel
    def load_scan(self, dds, freq_center, freq_width, scan_time,start_idx=0,end_idx=1023):
        ## LOAD SIDEBAND SCAN
        step_size = int(scan_time/(1024*4*ns))
        f0 = freq_center + freq_width/2

        # Build descending frequency list
        f_step = freq_width/1023
        for i in range(1024):
            self.freq_list[i] = f0 - f_step*i
            

        dds.frequency_to_ram(self.freq_list, self.freq_list_ram)
        
        self.core.break_realtime()
        delay(10*ms)

        # Disable RAM before programming
        dds.set_cfr1(ram_enable=0)
        dds.cpld.io_update.pulse_mu(8)
        
        delay(5*ms)

        # RAM sweep from index 0 to 1023, profile 0
        dds.set_profile_ram(
            start=0,
            end=1023,
            step=(step_size | (2**6 - 1) << 16),
            profile=0,
            mode=ad9910.RAM_MODE_RAMPUP
        )

        delay(25*ms)
        dds.cpld.set_profile(0)
        dds.cpld.io_update.pulse_mu(8)
        
        
        self.core.break_realtime()
        
        dds.write_ram(self.freq_list_ram)
 
        delay(1*ms)
        dds.set_cfr1(
            internal_profile=0,
            ram_enable=1,
            ram_destination=ad9910.RAM_DEST_FTW
        )
        delay(5*ms)
        
        
        self.core.wait_until_mu(now_mu())
    
    
    @kernel
    def freeze_RAM(self, dds, start_idx, end_idx, scan_time):
        """
        Modify the trigger DDS RAM so that profile 0 consists of a single
        index (idx), effectively "freezing" the DDS at the frequency
        corresponding to the detection time.

        This is called after pulse 1, before pulse 2.
        """
        step_size = int(scan_time/(1024*4*ns))


        dds.set_profile_ram(
            start=start_idx,
            end=end_idx,
            step=(step_size | (2**6 - 1) << 16),
            profile=0,
            mode=ad9910.RAM_MODE_RAMPUP
        )
        dds.cpld.io_update.pulse_mu(8)



        
