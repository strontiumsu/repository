# -*- coding: utf-8 -*-
"""
Created on Mon Aug 22 11:06:21 2022

@author: sr - E. Porter
"""

import numpy as np    
from Detection import Detection
from  artiq.language import EnvExperiment, scan, delay, ms, kernel



class CameraBugsTest(EnvExperiment):
    
    def build(self):
        # initiate connection interface to devices
        self.setattr_device("core")
        self.Detect=Detection(self)
        
        # how long to wait before taking a picture
        self.setattr_argument("Delay_duration",
            scan.Scannable(default=[scan.RangeScan(50.0*1e-3, 500.0*1e-3, 25, randomize=False),scan.NoScan(0.0)],scale=1e-3,
                      unit="ms"),"Loading")
        
        if not hasattr(self.Delay_duration,'sequence'):
            self.delays=np.array([0,0])
        else:
            self.delays=self.Delay_duration.sequence
        
        # self.datasets = {"detection.index":[],
        #             "detection.image_sum":[], 
        #             "detection.bg_image_sum":[],
        #             "detection.image":[],
        #             "detection.bg_image":[],
        #             "detection.bg_subtracted_image":[]}
        
        

    
    def prepare(self):
        # initiates hardware
        self.Detect.camera_init()
       
        
    @kernel    
    def run(self):
        self.core.reset() # always reset the core on run
        
        # self.Detect.prep_datasets(self.datasets.keys(), len(self.delays))
        self.set_dataset("time_delay", self.delays, broadcast=True)
        # self.set_dataset("")
        
        for ii in range(len(self.delays)):
            
            #############
            # background image
            delay(300*ms) 
            self.Detect.arm()  # arm device
            delay(100*ms)   # wait some amount of time
            self.Detect.trigger_camera()
            delay(self.Detect.Exposure_Time)
            self.Detect.acquire() 
            delay(100*ms)
            self.Detect.disarm()
            self.Detect.transfer_background_image(ii)
            # print(self.Detect.get_images()[0,0])
            # print('here')
            # self.datasets['detection.bg_image'].append(self.Detect.get_images())
            
        
    
            ###########
            # do experiment thing here
            ###########
            delay(10*ms)
            self.Detect.arm()  # arm device
            delay(100*ms)   # wait some amount of time
            self.Detect.trigger_camera()
            delay(self.Detect.Exposure_Time + self.delays[ii])
            self.Detect.acquire() 
            delay(100*ms)
            self.Detect.disarm()
            self.Detect.transfer_image(ii, bg_sub=True)
            
            
            
            # self.datasets['detection.image'].append(self.Detect.get_images())
            
            # store data
            # self.Detect.mutate_dataset("detection.index", ii, ii)
            # self.Detect.mutate_dataset("detection.image", ii, self.datasets["detection.image"][ii])
            # self.Detect.mutate_dataset("detection.bg_image", ii, self.datasets["detection.bg_image"][ii])
            # self.Detect.mutate_dataset('detection.big_subtracted_im', ii, 
            #                             )
            # sub = np.subtract(self.datasets["detection.image"][ii],
            #                   self.datasets["detection.bg_image"][ii],dtype=np.int16)
            # sub = np.where(sub<0, 0, sub)
            # self.Detect.mutate_dataset("detection.bg_subtracted_image", ii, np.copy(sub))
            # self.Detect.mutatute_dataset("detection.bg_image_sum", ii, np.sum(self.datasets["detection.bg_image"][ii]))                           
            # self.Detect.mutatute_dataset("detection.image_sum", ii, np.sum(self.datasets["detection.bg_subtracted_image"][ii]))

            
    

        