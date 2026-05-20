# -*- coding: utf-8 -*-
"""
Created on Thu Feb  2 12:41:16 2023

@author: E. Porter
"""

from artiq.experiment import delay, NumberValue, ms, kernel, EnvExperiment, TInt32, BooleanValue, rpc, EnumerationValue, TArray, TTuple
import numpy as np
from scipy.optimize import curve_fit
from scipy.signal import medfilt
from scipy.ndimage import gaussian_filter
import matplotlib.pyplot as plt
from PIL import Image
import time
import json
from pathlib import Path

class _Camera(EnvExperiment):
    
    def build(self):
        """
        Camera
        Class to handle control of the thor labs cameras
        
        parameters:
        exposure_time: exposure time for a single image
        hardware_gain: gain setting for images

        """

        
        self.setattr_device("core") 
        self.setattr_device("ttl4")         # Camera hardware trigger
        self.cam=self.get_device("camera") # Thorlabs camera
        
        self.setattr_argument("Exposure_Time",NumberValue(0.5*1e-3,min=0.5e-3,max=100*1e-3,scale=1e-3,
                      unit="ms"),"Detection")        
        self.setattr_argument("Hardware_Gain",NumberValue(150,min=0,max=350,scale=1
                      ),"Detection")
        
        self.setattr_argument("Median_Filter",BooleanValue(True),"Detection")
        self.setattr_argument("Gaussian_Filter",BooleanValue(False),"Detection")

        self.ROI_list = Path(__file__).parent / "rois.json"
        with open(self.ROI_list) as f:
            schemes = [k for k in json.load(f) if not k.startswith("_")]
        self.setattr_argument("ROI_Scheme",
            EnumerationValue(schemes, default=schemes[0]),
            "Detection")

                
        self.xsize = 314
        self.ysize = 264
        self.current_image = np.zeros((self.xsize, self.ysize)) 
        self.background_image = np.zeros((self.xsize, self.ysize)) 
        
    @rpc
    def _load_roi(self):
        """loads the ROIs for the current experiment from the rois.json file. Should be called in prepare() of each experiment."""
        with open(self.ROI_list, 'r') as f:
            all_rois = json.load(f)

        self.current_roi = all_rois[self.ROI_Scheme]
        self.ports = self.current_roi["ports"]


    def prep_datasets(self,x):
        self.set_dataset("detection.counts",x, broadcast=True)    

    @rpc 
    def camera_init(self, N=2, scheme=0):
        """Initializes camera settings and parameters for data 
        analysis. Also sets up some parameters for display and 
        analysis of images.
        scheme: sets parameters for display and analysis of 
        images. 0 is for 689 horizontal push, 1 is for 689 
        horizontal double push, 2 is for 689 vertical push, 3 
        is for Bragg spectroscopy. 

        arms the camera at the end of initialization.
        """
        

        # set camera settings
        if self.get_is_armed(): self.disarm()
        self.cam.set_exposure(self.Exposure_Time)
        self.cam.set_gain(self.Hardware_Gain)

        self.cam.set_roi(1250,1425,400,300)
        self.cam_range = (50,-40, 30,-10)
        self.cam.get_all_images() ## clears buffer

        # for data analysis
        self.pix2um = 67.8
        X, Y = np.meshgrid(np.arange(0, self.ysize, 1), np.arange(0, self.xsize, 1))
        self.xdata = np.vstack((X.ravel(), Y.ravel()))
        
        self.ind = 0

        self._load_roi()

        self.set_dataset("detection.roi", self.ROI_Scheme, broadcast=True, archive=True)

        self.arm(N=N)
    
    def _draw_box(self, img, x, y, w, h, color):
        """Draw a hollow rectangle on img at (x, y) of size (w, h)."""
        x_end = min(x + w, img.shape[0] - 1)
        y_end = min(y + h, img.shape[1] - 1)
        img[x:x_end+1, y]     = color  # left edge
        img[x:x_end+1, y_end] = color  # right edge
        img[x,     y:y_end+1] = color  # top edge
        img[x_end, y:y_end+1] = color  # bottom edge

    @rpc
    def arm(self, N=2):   
        """arms the camera to take N images. If already armed, does nothing."""
        if not self.get_is_armed():
            self.cam.arm(N)
            time.sleep(0.05) # give camera time to arm
    @rpc  
    def acquire_frame(self):
        """acquires N images. Camera should already be armed. If not armed, arms and acquires."""
        self.cam.acquire()  
        raw = self.cam.get_all_images()[0]

        x1, x2, y1, y2 = self.cam_range
        self.current_image=np.copy(raw)[x1:x2,y1:y2] # acquire and crop image


    @rpc  
    def get_is_armed(self):
        """returns whether the camera is currently armed."""
        return self.cam.get_is_armed()
              
    @rpc            
    def disarm(self):
        """disarms the camera if it is armed. If not armed, does nothing."""
        if self.get_is_armed():
            self.cam.disarm()
    @rpc            
    def dispose(self): 
        """disposes of the camera resources. Should be called at end of experiment."""
        self.cam.dispose()
    
    @kernel
    def trigger_camera(self):
        """
        kernel decorator.
        Triggers the camera to take an image."""
        self.ttl4.pulse(1*ms)

       
    @kernel
    def camera_delay(self, time):
        # add in a kernel function for delaying camera exposure
        delay(time)

    @rpc     
    def process_image(self, save=True, name='', bg_sub=True, return_ports=[]) -> TArray(TInt32):
        # pulls the current image, saves/bg subs as needed. Saves to current image dataset
        self.acquire_frame()
       
        if save:
            self.set_dataset(f"detection.images.Raw_{name}{self.ind}", self.current_image)
        
        if bg_sub: 
            self.current_image = np.subtract(self.current_image,self.background_image,dtype=np.int16)
               
        if self.Median_Filter:
            self.current_image = medfilt(self.current_image, 3)
        if self.Gaussian_Filter:
            self.current_image = gaussian_filter(self.current_image, 3)
        if save:
            self.set_dataset(f"detection.images.{name}{self.ind}", self.current_image)

        display_image = np.copy(self.current_image)
        self.ports_counts = {}
        for port_name, port in self.ports.items():
            x, y, w, h = port["x"], port["y"], port["w"], port["h"]
            c = int(np.sum(self.current_image[x:x+w, y:y+h]))
            self.ports_counts[port_name] = c

            self.set_dataset(f"detection.counts.{port_name}{self.ind}", c )
            self._draw_box(display_image,
                           x, y, w, h,
                           port.get("color", 200))

        display_image = np.where(display_image > 0, display_image, 0)
        self.set_dataset("detection.images.current_image",
                         display_image, broadcast=True)

        self.ind += 1

        if return_ports == []:
            return np.array([])
        else:
            return np.array([self.ports_counts[port] for port in return_ports])

            
    


    @rpc    
    def process_background(self):
        # processes the image from the background imaging
        self.acquire_frame()
        self.background_image = np.copy(self.current_image)
        
        self.set_dataset("detection.images.background_image", self.background_image )
        self.set_dataset("detection.images.current_image", self.background_image, broadcast=True)

    @rpc
    def prep_temp_datasets(self, n):
        self.set_dataset( "gaussianparams", [[0.0]*6]*n, broadcast=True)
        
        
    @rpc    
    def process_gaussian(self, index) -> TInt32:
        img = np.array(self.get_dataset("detection.images.current_image"))
        center_x, center_y = np.unravel_index(img.argmax(), img.shape)
        val_max = self.current_image[center_x, center_y]
        guess = [val_max, center_x, center_y, 30, 30, 0]
        popt, pcov = curve_fit(_twoDGaussian, self.xdata, img.ravel(), p0=guess, maxfev=15000)
        
        self.mutate_dataset("gaussianparams", self.ind-1, popt)

              

        return int(10**6*popt[index])
    
    @rpc
    def get_push_stats(self) -> TInt32:
        return self.get_dataset('detection.images.ratio')
    
    @rpc
    def get_count_stats(self) -> TInt32:
        return int(self.get_dataset('detection.images.total_counts'))
    
    @rpc
    def get_totalcount_stats(self) -> TInt32:
        return self.get_dataset('detection.images.total_counts')

    @rpc
    def get_totalcount_stats_port2(self) -> TInt32:
        return self.get_dataset('detection.images.total_counts_port2')
    @rpc
    def get_peak(self) -> TInt32:
        img = np.array(self.get_dataset("detection.images.current_image"))
        cx, cy = np.unravel_index(img.argmax(), img.shape  )
        return int(cy)

        
def fit2DGaussian(x, y, A, center_x, center_y, sigma_x_sq, sigma_y_sq, offset):
    return A*np.exp(-((x-center_x)**2/(2*sigma_x_sq) + (y-center_y)**2/(2*sigma_y_sq)))

def _twoDGaussian(M, *args):
    x, y = M
    return fit2DGaussian(x, y, *args) 
        

            
                
                
    
        
       
        
        