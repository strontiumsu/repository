# -*- coding: utf-8 -*-
"""
Created on Thu Aug 11 14:23:42 2022

@author: sr
"""


from artiq.experiment import *

from Detection import *
from MOTcoils import*
from ZotinoRampClass import *
from Beamline461Class import*
from Beamline689Class import*
from HCDL import*

from scipy.optimize import curve_fit
from scipy import constants
from numpy import unravel_index
import numpy as np


class Blue_MOT_atom_count(EnvExperiment):

    def build(self):
        pass
        # self.setattr_device("core")
        # self.Detect=Detection(self)
        # self.MC=MOTcoils(self)
        # self.BB=Beamline461(self)
        # self.BR=Beamline689(self)


        # which detunings to sweep through
        # self.setattr_argument("Detunings",
            # Scannable(default=[RangeScan(start, stop, points, randomize=False), NoScan(0.0)], scale=1e6))
        # which powers to sweep through
        # self.setattr_argument("Powers",
            # Scannable(default=[RangeScan(start, stop, points, randomize=False), NoScan(0.0)], scale=1e-3))
       # how long to hold at one settings to measure PD
        # self.setattr_argument("PD_Duration",NumberValue(0.1*1e-3,min=0.0,max=10.00*1e-3,scale = 1e-3,
                      # unit="ms"),"Detection")

        # self.ms = np.zeros(len())


        # self.setattr_argument("Delay_duration",
        #     Scannable(default=[RangeScan(0.0*1e-3, 25.0*1e-3, 20, randomize=False),NoScan(0.0)],scale=1e-3,
        #               unit="ms"),"Loading")

        # self.setattr_argument("Background_subtract",BooleanValue(False),"Loading")

        # self.setattr_argument("Detection_pulse_time",NumberValue(0.1*1e-3,min=0.0,max=10.00*1e-3,scale = 1e-3,
        #               unit="ms"),"Detection")

        # if not hasattr(self.Delay_duration,'sequence'):
        #     self.x=np.array([0,0])
        # else:
        #     self.x=self.Delay_duration.sequence
        # self.y=np.full(len(self.x), np.nan) # Prepare result array
        # self.xdev = np.zeros(len(self.x)) # Prepare result array
        # self.ydev = np.zeros(len(self.x)) # Prepare result array

    def prepare(self):
       pass
        # Prepare MOT pulse shape
        # self.MC.Blackman_pulse_profile()
        # Set AOM attenuations
        # self.BB.set_atten()
        # self.BR.set_atten()

        # Initialize camera
        # self.Detect.camera_init()

    @kernel
    def run(self):
        pass
        # general inicialization
        # self.core.reset()
        # self.MC.init_DAC()
        # self.BB.init_aoms()
        # self.BR.init_aoms()
        #
        # Camera output datasets
        # self.Detect.prep_datasets(self.y)
        # self.set_dataset("time_delay", self.x, broadcast=True)
        #
        #
        # delay(100*ms)
        # self.BB.MOT2D_off()  # turn off 2D MOT beam
        # delay(1*ms)
        # self.BB.Zeeman_off()
        # delay(1*ms)
        # self.BB.Probe_AOM_off()
        # self.BR.Hp688_aom_off()
        # delay(1*ms)


        # Main loop
        # for ii in range(len(self.x)):
        #     self.Detect.arm()
        #     delay(800*ms)
        #
        #     self.BB.MOT2D_off()  # turn off 2D MOT beam
        #     delay(1*ms)
        #     self.BB.Zeeman_off()
        #     delay(1*ms)
        #
        #     # BACKGROUND IMAGE SEQUENCE
        #     if self.Background_subtract:
        #         self.BB.reinit_MOT3DDP_aom(6.0, self.BB.f_MOT3D_detect)  # Set 3D MOT frequency for imaging
        #         delay(10*ms)
        #         self.BR.repumpers_on() # turn on repumpers
        #         self.Detect.trigger_camera()    # Trigger camera
        #         self.BB.MOT_on() #turn on mot for background image
        #         delay(self.Detection_pulse_time)
        #         self.BB.MOT_off()
        #         delay(self.Detect.Exposure_Time)
        #         self.BR.repumpers_off() # turn off repumpers
        #         self.Detect.acquire()     # Acquire images
        #         delay(100*ms)
        #         self.Detect.transfer_background_image(ii)
        #         delay(300*ms)
            ############################

            #prepare for detection image
    #         self.Detect.arm()
    #         delay(300*ms)
    #
    #         self.BB.reinit_MOT3DDP_aom(self.BB.MOT3DDP_iatten, self.BB.f_MOT3D_load)  # Set 3D MOT frequency for loading
    #         delay(1*ms)
    #
    #         delay(1*ms)
    #         self.BR.repumpers_on() # turn on repumpers
    #         delay(1*ms)
    #         self.MC.Blackman_ramp_up()
    #         delay(1*ms)
    #         self.BB.Zeeman_on()
    #         delay(1*ms)
    #         self.BB.MOT2D_on() # Turn on atom beam
    #         delay(1*ms)
    #         self.BB.MOT_on()
    #
    #         delay(1*ms)
    #         self.MC.flat()
    #
    #         with parallel:
    #             self.BB.Zeeman_off()
    #             self.BB.MOT2D_off() # turn off atom beam
    #             self.BB.MOT_off() #turn off 3D
    #             self.BB.reinit_MOT3DDP_aom(6.0, self.BB.f_MOT3D_detect) # switch to detection frequency
    #             self.BR.repumpers_off() # turn off repumpers
    #
    #         delay(self.x[ii])  # Delay
    #
    #         # IMAGING SEQUENCE
    #         self.BR.repumpers_on() # turn on repumpers
    #         self.Detect.trigger_camera()  # Trigger
    #         self.BB.MOT_on()
    #         delay(self.Detection_pulse_time)
    #         self.BB.MOT_off()
    #         delay(self.Detect.Exposure_Time)
    #         self.BR.repumpers_off() # turn off repumpers
    #         delay(1*ms)
    #         ###########################
    #         self.MC.Set_current(0.0)
    #
    #         self.Detect.acquire()                                # Acquire images
    #         delay(100*ms)
    #         self.Detect.transfer_image_background_subtracted(ii)
    #         delay(100*ms)
    #         self.Detect.disarm()
    #
    #         self.mutate_dataset("time_delay",ii,self.x[ii])
    #         self.mutate_dataset("detection.index",ii,ii)
    #
    #
    #     delay(500*ms)
    #     self.MC.Zero_current()
    #
    def analyze(self):
        """
        analyze function takes the images generated in the run() function and
        fits gaussians to them to find atom cloud expansion as a function of time.
        This data is then fit to a parabola and solved for the temperature in
        both directions.
        """
        pass
