# -*- coding: utf-8 -*-
"""
Created on Thu Feb  2 12:41:16 2023

@author: E. Porter
"""

from artiq.experiment import delay, NumberValue, ms, kernel, EnvExperiment # pyright: ignore[reportMissingImports]
from artiq.experiment import TInt32, BooleanValue, rpc, EnumerationValue, TArray # pyright: ignore[reportMissingImports]

import numpy as np
from scipy.optimize import curve_fit
from scipy.signal import medfilt
from scipy.ndimage import gaussian_filter
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
        self.set_dataset("detection.counts", x, broadcast=True)    

    @rpc 
    def camera_init(self, N=2):
        """Initializes camera settings and parameters for data 
        analysis. Also sets up some parameters for display and 
        analysis of images.
       

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
        X, Y = np.meshgrid(np.arange(0, self.ysize, 1), np.arange(0, self.xsize, 1))
        self.xdata = np.vstack((X.ravel(), Y.ravel()))
        
        self.ind = 0

        self._load_roi()

        self.set_dataset("detection.roi", self.ROI_Scheme, broadcast=True, archive=True)

        self.arm(N=N)

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
    def process_image(self, save=True, name='', bg_sub=True, return_ports=[]) -> TArray(TInt32, 1): # pyright: ignore[reportInvalidTypeForm]
        # pulls the current image, saves/bg subs as needed. Saves to current image dataset
        self.acquire_frame()

        if save:
            self.set_dataset(f"detection.images.Raw_{name}{self.ind}", self.current_image)

        if bg_sub:
            self.current_image = np.subtract(self.current_image, self.background_image, dtype=np.int16)

        if self.Median_Filter:
            self.current_image = medfilt(self.current_image, 3)
        if self.Gaussian_Filter:
            self.current_image = gaussian_filter(self.current_image, 3)
        if save:
            self.set_dataset(f"detection.images.{name}{self.ind}", self.current_image)

        self.port_counts = {}
        for port_name, port in self.ports.items():
            x, y, w, h = port["x"], port["y"], port["w"], port["h"]
            c = int(np.sum(self.current_image[x:x+w, y:y+h]))
            self.port_counts[port_name] = c
            self.set_dataset(f"detection.counts.{port_name}{self.ind}", c)

        self.set_dataset("detection.images.current_image",
                         self.current_image, broadcast=True)

        self.ind += 1

        if return_ports == []:
            return np.array([])
        else:
            return np.array([self.port_counts[port] for port in return_ports])

            
    


    @rpc    
    def process_background(self):
        # processes the image from the background imaging
        self.acquire_frame()
        self.background_image = np.copy(self.current_image)
        
        self.set_dataset("detection.images.background_image", self.background_image )
        self.set_dataset("detection.images.current_image", self.background_image, broadcast=True)
        
        
        
    @rpc
    def process_gaussian(self):
        img = np.array(self.get_dataset("detection.images.current_image"),
                       dtype=np.float64)
        H, W = img.shape   # H = rows (xsize axis), W = cols (ysize axis)
        col_marg = img.sum(axis=0)            # length W, function of column index
        row_marg = img.sum(axis=1)            # length H, function of row index

        col_fit = _fit_1d_gauss(np.arange(W, dtype=np.float64), col_marg)
        row_fit = _fit_1d_gauss(np.arange(H, dtype=np.float64), row_marg)
        try:
            amp_col, c0, sigma_c, _ = col_fit   # col fit ⇒ center_x, σ_x in fit terms
            amp_row, r0, sigma_r, _ = row_fit   # row fit ⇒ center_y, σ_y in fit terms
            A_2D = 0.5/np.sqrt(2.0 * np.pi) * (amp_col/sigma_r + amp_row/sigma_c)

            popt = np.array([A_2D, c0, r0, np.abs(float(sigma_c)), np.abs(float(sigma_r))])

            self.mutate_dataset("gaussianparams", self.ind-1, popt)
            self.set_dataset("detection.gauss.center_y",   float(popt[1]), broadcast=True)
            self.set_dataset("detection.gauss.center_x",   float(popt[2]), broadcast=True)
            self.set_dataset("detection.gauss.sigma_y",    float(popt[3]), broadcast=True)
            self.set_dataset("detection.gauss.sigma_x",    float(popt[4]), broadcast=True)

        except Exception:
            print("Failed fit", str(self.ind-1))




def _gauss1d(x, A, x0, sigma, offset):
    return A * np.exp(-(x - x0)**2 / (2.0 * sigma**2)) + offset


def _fit_1d_gauss(x, y):
    """Fit y = A·exp(-(x-x0)²/(2σ²)) + offset on a single marginal.
    Returns (A, x0, σ, offset) or None on failure."""

    try:                  
        # generate good guess                                      
        offset0 = float(np.min(y))
        x0_guess = float(x[np.argmax(y)])
        sigma0 = np.sqrt(np.sum( np.clip(y, 0.0) * (x - x0_guess)**2) / np.sum(np.clip(y, 0.0)))
        amp0 = float(np.max(y) - offset0)
        p0 = [amp0, x0_guess, sigma0, offset0]

        # build bounds
        lo = [0.0,        float(x.min()), 0.5,  -np.inf]
        hi = [np.inf,     float(x.max()), 300,  np.inf]
       
        # perform fit and return packed in tuple
        popt, _ = curve_fit(_gauss1d, x, y, p0=p0,
                                bounds=(lo, hi), maxfev=15000)
        return tuple(float(v) for v in popt)
    except Exception as e: # catch any failure, but don't raise exception
        print(e)
        return None


        

            
                
                
    
        
       
        
        