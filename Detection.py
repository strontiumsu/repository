# -*- coding: utf-8 -*-
"""
Created on Thu Jul  1 12:17:03 2021

@author: sr
"""

from artiq.language import EnvExperiment, delay, NumberValue, kernel, ms
import numpy as np

   

class Detection(EnvExperiment):

    def build(self):
        self.setattr_device("core") 
        self.setattr_device("ttl4")         # Camera hardware trigger
        self.cam=self.get_device("camera")  # Thorlabs camera
        self.setattr_argument("Exposure_Time",NumberValue(25*1e-3,min=1*1e-3,max=100*1e-3,scale=1e-3,
                      unit="ms"),"Detection")
        
        self.setattr_argument("Hardware_gain",NumberValue(100,min=0,max=350,scale=1
                      ),"Detection")
        
        #self.setattr_argument("N_reps",NumberValue(2000,min=1,max=2000, ndecimals = 0, scale = 1,step=1,type='int'),"Detection")
        
       
        
        
    @kernel
    def trigger_camera(self):
        """
        sends a LVTTL pulse to the thor lab camera over ttl4 

        Returns
        -------
        None.

        """
        self.ttl4.on()
        delay(1*ms)
        self.ttl4.off()  

       
    def arm(self, N=2):   
        """

        Parameters
        ----------
        N : int
            arms the camera with an N frame buffer. The default is 2.

        Returns
        -------
        None.

        """
        self.cam.arm(N)
        
    def acquire(self):
        """
        begins filling buffer armed upon trigger
        see thorlabs manual for different operating modes and interactions
        between triggers and buffer. Currently can only operate in 
        OPERATION_MODE=1 for hardware trigger
        #TODO: add functionality for OPERATION_MOD=BULB

        Returns
        -------
        None.

        """
        self.cam.acquire()
        
    def get_is_armed(self):
        """
        returns the current state of the camera

        Returns
        -------
        bool
            bool representing whether the camera is armed or not.

        """
        return self.cam.get_is_armed()
    
    def camera_init(self):
        """
        Initializes the camera

        Returns
        -------
        None.

        """
        if (self.get_is_armed()): self.cam.disarm() # check if the camera was left armed

        # camera settings
        self.cam.set_exposure(self.Exposure_Time)
        self.cam.set_gain(self.Hardware_gain)
        self.cam.set_roi(1150,1075,100,150) # hardcoded in for experiment

 
    def prep_datasets(self, datasets, exp_length=1):
        """
        stores image datasets for the experiment

        Parameters
        ----------
        datasets : arraytype of strings
            array with strings naming the datasets to store for the exp.
        exp_length : int, optional
            length of experiment, how many pictures of each type. The default is 1.

        Returns
        -------
        None.

        """
        empty_dataset = np.full(exp_length, np.nan )  # empty data set to fill

        self.set_dataset("detection.index", list(range(exp_length)), broadcast=True)
        
        self.set_dataset("detection.image_sum", empty_dataset, broadcast=True)
        self.set_dataset("detection.bg_image_sum", empty_dataset, broadcast=True)
        self.set_dataset("detection.bg_subtracted_image_sum", empty_dataset, broadcast=True)
            
        self.set_dataset("detection.image", empty_dataset, broadcast=True)
        self.set_dataset("detection.bg_image", empty_dataset, broadcast=True)
        self.set_dataset("detection.bg_subtracted_image", empty_dataset, broadcast=True)
        
    def get_images(self, N=1):
        """
        returns N images from the saved buffer

        Parameters
        ----------
        N : int, 
            number of images in buffer to return. The default is 1.

        Returns
        -------
        np.array([np.array, np.array, ...])
            returned images stored as an array of numpy arrays, deep copied.

        """
        return np.copy(self.cam.get_all_images()[0:N])
    def disarm(self):
        """
        disarms the camera

        Returns
        -------
        None.

        """
        self.cam.disarm()
        
    def dispose(self):
        """
        disposes the camera

        Returns
        -------
        None.

        """
        self.cam.dispose()
        
    # def __exit__(self):
    #     if (self.get_is_armed()): 
    #         self.disarm()
    #     self.dispose()
        
    def transfer_background_image(self,i):
        self.bg_image=np.copy(self.cam.get_all_images()[0])                
        self.mutate_dataset("detection.bg_image", i, self.bg_image, broadcast=True)
        self.mutate_dataset("detection.bg_image_sum",i,np.sum(self.bg_image))
                
    
    
    def transfer_image(self, i, bg_sub=True):
        self.image = np.copy(self.cam.get_all_images()[0])

        self.mutate_dataset("detection.image_sum", i, np.sum(self.image))
        self.mutate_dataset("detection.image", i, self.image, broadcast=True)
        
        if bg_sub and self.bg_image is not None:
            self.bg_free_image = np.subtract(self.image,self.bg_image,dtype=np.int16)
            self.bg_free_image = np.where(self.bg_free_image<0, 0, self.bg_free_image)
            self.mutate_dataset("detection.bg_sub_image_sum", i, np.sum(self.bg_free_image))
            self.set_dataset("detection.bg_sub_image", self.bg_free_image_display, broadcast=True)
                
    # def transfer_image_background_subtracted(self,i):
    #     self.image_buffer_copy1=np.copy(self.cam.get_all_images()[0])
    #     self.background_free_image= np.subtract(self.image_buffer_copy1,self.background_image,dtype=np.int16)

    #     self.background_free_image_display=np.where(self.background_free_image<0, 0, self.background_free_image)
    #     self.mutate_dataset("detection.image_sum", i, np.sum(self.image_buffer_copy1))
    #     self.set_dataset("detection.images.image", self.image_buffer_copy1, broadcast=True)
        
    #     self.mutate_dataset("detection.background_subtracted_image_sum",i, np.sum(self.background_free_image))
    #     self.set_dataset("detection.images.background_subtracted_image", self.background_free_image_display, broadcast=True)
    #     self.set_dataset(f"detection.images.background_subtracted_image{i}", self.background_free_image_display, broadcast=True)
    #     self.cam.disarm()     

  


    ## this stuff should be in the analysis window of the individual experiment, not in here
    # def calc_push_stats(self,i):
        
    #     x1 = 55
    #     x2 = 120
    #     x3 = 150
    #     y1 = 45
    #     y2 = 95
        
    #     noise = np.mean(self.background_free_image[x3+20:x3+70,y1:y2])
    #     print(noise)
        
    #     num1S0 = np.sum(self.background_free_image[x1:x2,y1:y2])#-(x2-x1)*(y2-y1)*noise
    #     num3P1 = np.sum(self.background_free_image[x2:x3,y1:y2])#-(x3-x2)*(y2-y1)*noise
        
    #     if num1S0 <= 0:
    #         num1S0 = 1
    #     if num3P1 <= 0:
    #         num3P1 = 1
        
    #     #print(["1S0 data:",noise,(x2-x1)*(y2-y1)*noise,np.sum(self.background_free_image[x1:x2,y1:y2]),num1S0])
    #     #print(["3P1 data:",noise,(x3-x2)*(y2-y1)*noise,np.sum(self.background_free_image[x2:x3,y1:y2]),num3P1])
        

    #     self.background_free_image_display[x2:x3,y1]=300
    #     self.background_free_image_display[x2:x3,y2]=300
    #     self.background_free_image_display[x2,y1:y2]=300
    #     self.background_free_image_display[x3,y1:y2]=300
        
    #     self.background_free_image_display[x1:x2,y1]=300
    #     self.background_free_image_display[x1:x2,y2]=300
    #     self.background_free_image_display[x1,y1:y2]=300
    #     self.background_free_image_display[x2,y1:y2]=300
        
    #     # if i == 0:
    #     #     self.set_dataset("detection.maxContrast",num3P1/(num3P1+num1S0),broadcast=True)

    #     self.set_dataset("detection.images.background_subtracted_image", self.background_free_image_display, broadcast=True)
    #     self.mutate_dataset("detection.Probup", i, num3P1/(num3P1+num1S0))
    #     #self.mutate_dataset("detection.Probup", i,( num3P1/(num3P1+num1S0) - 0.0441786826544748)/ 0.873846684266737)
        
    #     #print(len(np.transpose(self.background_free_image)[1]))
    #     #print(self.background_free_image[50:60,50:60]) 
        
                
    # def calc_marginal_stats(self,i):
    #     tot = np.sum(self.background_free_image)
    #     print(tot)
        
    #     #ly = 200
        
    #     ix = self.background_free_image/np.sum(self.background_free_image)
    #     iy = np.transpose(self.background_free_image)/np.sum(self.background_free_image)

    #     lx = 110
    #     ux = 170
    #     ly = 1
    #     uy = 190
        
    #     lenx = ux-lx
    #     leny = uy-ly
        
    #     datax = np.zeros(lenx)
    #     datay = np.zeros(leny)
        
    #     for j in range(lenx):
    #         datax[j] = np.sum(ix[j+lx])
    #     for j in range(leny):
    #         datay[j] = np.sum(iy[j+ly])
            
    #     datax = datax/np.sum(datax)
    #     datay = datay/np.sum(datay)

    #     # for j in range(len(ix[0])):
    #     #     datax[j] = np.sum(ix[j])
    #     # for j in range(ly):
    #     #     datay[j] = np.sum(iy[j])
            
    #     meanx = 0.
    #     meany = 0.

    #     for j in range(lenx):
    #         meanx = meanx + j*datax[j]
    #     for j in range(leny):
    #         meany = meany + j*datay[j]
    
    #     varx = 0.
    #     vary = 0.
    #     for j in range(lenx):
    #         varx = varx + ((j-meanx)**2)*datax[j]
    #     for j in range(leny):
    #         vary = vary + ((j-meany)**2)*datay[j]
               
    #     self.mutate_dataset("detection.deviationx", i, np.sqrt(varx))
    #     self.mutate_dataset("detection.deviationy", i, np.sqrt(vary))
        
    #     self.set_dataset("detection.margx", datax, broadcast=True)
    #     self.set_dataset("detection.margy", datay, broadcast=True)
                
    # def return_bg_subtracted_image_array(self):     
    #     return self.background_free_image
                
    # def print_image_array(self):
    #            print('Image array: ')
    #            print(self.image_buffer_copy1)      
    # def print_bg_image_array(self):
    #            print('Background image array: ')
    #            print(self.background_image)           
   
    # def print_bg_subtracted_image_array(self):
    #            print('Background subtracted image array: ')
    #            print(self.background_free_image)     
            
            
                
                
    
        
        
        