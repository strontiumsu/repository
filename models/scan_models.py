# -*- coding: utf-8 -*-
"""
Created on Wed Dec 14 12:35:21 2022

@author: E. Porter
"""

import numpy as np
from scan_framework.models import (
    Exp,
    ExpSine,
    FreqModel,
    Gauss,
    Lor,
    MHz,
    AtomLine,
    kHz,
    Hz,
    Model,
    Poly,
    Power,
    Sine,
    TimeFreqModel,
    TimeModel,
)
from scipy import constants

class AI_Rabi_Model(TimeFreqModel):
     # global parameters
    namespace='AI_calib.%arm'
    y_label='Transition Probability'
    y_scale = 1e6
    x_scale = 1e-6
    enable_histograms = False

    @property
    def plot_title(self):
        if self.type == 'time':
            return 'Rabi Flop'
        else:
            return 'Frequency Scan'

    @property
    def fit_function(self):
        if self.type == 'frequency':
            return AtomLine
        elif self.type == 'time':
            return ExpSine
        else:
            raise ValueError("Not Valid Scan Type")

    @property
    def main_fit(self):
        if self.type == 'frequency':
            return ['f0', 'center freq']
        elif self.type == 'time':
            return "f"
        else:
            raise ValueError("Not Valid Scan Type")
    @property
    def fits_to_save(self):
        if self.type == 'frequency':        
            return {"f0":"center_freq"}
        elif self.type == 'time':
            return {"f":"Rabi Frequency", "tau": "decay time"}
        else:
            raise ValueError("Not Valid Scan Type")
    # @property
    # def x_units(self):
    #     if self.type == 'frequency':
    #         return "MHz"
    #     elif self.type == 'time':
    #         return "ns"
    #     else:
    #         raise ValueError("Not Valid Scan Type")

    @property
    def x_label(self):
        if self.type == 'frequency': unit = 'MHz'
        else: unit = 'ns'
        return f"{self.type} ({unit})"
            


    def before_validate(self, fit):
        if self.type == 'time':
            fit.fitresults['f'] = np.round(fit.fitresults['f']*1e-6, 3)
            fit.fitresults['tau'] = np.round(fit.fitresults['tau']*1e6, 2)
            # fit.fitresults['pitime'] = 1
        if self.type == 'frequency':
            fit.fitresults['f0'] = np.round(fit.fitresults['f0']*1e-6, 3)

        

    



    


class MyModel(TimeFreqModel):
    
    # global parameters
    namespace='LorentzianTest.%transition'
    y_label='Counts'
    plot_title = 'Frequency/Time Scan'
    enable_histograms = False

    @property
    def fit_function(self):
        if self.type == 'frequency':
            return Lor
        elif self.type == 'time':
            return Sine
        else:
            raise ValueError("Not Valid Scan Type")

    @property
    def main_fit(self):
        if self.type == 'frequency':
            return ['x0', 'center freq']
        elif self.type == 'time':
            return 'f'
        else:
            raise ValueError("Not Valid Scan Type")

    @property
    def x_units(self):
        if self.type == 'frequency':
            return "Hz"
        elif self.type == 'time':
            return "s"
        else:
            raise ValueError("Not Valid Scan Type")

    @property
    def x_label(self):
        if self.type == 'frequency':
            return "Frequency"
        elif self.type == 'time':
            return "time"
        else:
            print(self.type)
            raise ValueError("Not Valid Scan Type")

    @property
    def guess(self):
        if self.type == 'frequency':
            return {"A":1000,
                    "Gamma":10*1e6,
                    "x0":500*1e6}
        elif self.type == 'time':
            return {"A":1000,
                    "f":1e5,
                    "phi":np.pi/2,
                    'y0':0}
        else:
            raise ValueError("Not Valid Scan Type")
    @property
    def hold(self):
        if self.type == 'frequency':
            return {'y0':0}
        elif self.type == 'time':
            return None
        else:
            raise ValueError("Not Valid Scan Type")

    @property
    def man_bounds(self):
        if self.type == 'frequency':
            return {'A': [0.8*1e3, 1.2*1e3],
                    'x0': [400*1e6, 600*1e6],
                    'Gamma': [2*1e6,50*1e6]
                    }
        elif self.type == 'time':
            return {"A":[300, 1500],
                    "f":[10e3, 50e6],
                    "phi":[-2*np.pi, 2*np.pi],
                    'y0':[-100, 100]}
        else:
            raise ValueError("Not Valid Scan Type")

    @property
    def man_scale(self):
        if self.type == 'frequency':
            return {'A': 1,
                    'x0': 1*MHz,
                    'Gamma': 1*MHz
                    }
        elif self.type == 'time':
            return {"A":1,
                    "f":1*MHz,
                    "phi":3.14159,
                    'y0':1}
        else:
            raise ValueError("Not Valid Scan Type")

    def before_validate(self, fit):
        pass

    @property
    def validators(self):
        validators =   {
            "analysis.r2":{
                "greater_than": 0.85}
            }
        return validators

    @property
    def strong_validators(self):
        # this one will actually cancel the experiment
        return None

    @property
    def pre_validators(self):
        # ensures data looks a certain way before trying to fit
        return None

class BlankModel(TimeModel):
    namespace = ''
    x_label = ''
    x_unit = ''
    
    y_label = ''
    y_unit = ' '
    y_scale = 1
    
    plot_title = ''
    enable_histograms = False

    
class LoadingModel(TimeModel):

    # global parameters
    namespace="LoadingExp"
    y_label='Counts'
    x_label='pulse time'
    x_units = 's'
    plot_title = 'Loading Scan'
    enable_histograms = False
    fit_function = Exp
    #man_bounds = {'A': [-100_000_000, 0],
        #            'b': [-5, 0],
         #           'y0':[0, 1000000]
         #           }
    guess = {'b': -1}
    
    main_fit = "tau"
    def before_validate(self, fit):
        fit.fitresults["tau"] = -1/fit.fitresults['b']
    
class TemperatureModel(TimeModel):
    
    
    namespace = 'TOF_temp'
    x_label = 'TOF time'
    x_unit = 'ms'
    
    y_label = 'variance'
    y_unit = 'pixel squared'
    y_scale = 1e6
    
    plot_title = 'Cloud Radius over time'
    enable_histograms = False
    fit_function = Power
    hold = {'alpha':2}
    pix2um = 10
    
    @property
    def main_fit(self):
        return 'temp_X'
    
    def before_validate(self, fit):
            M  = constants.value('atomic mass constant')*87.9
            Kb = constants.value('Boltzmann constant')
            fit.fitresults['temp_X'] = 10**2*fit.fitresults['A']*1e-12*M/Kb

            
class DipoleTemperatureModel(TimeModel):
    
    
    namespace = 'TimeOfFlight'
    x_label = 'drop time'
    x_unit = 'ms'
    
    y_label = 'variance'
    y_unit = 'pixel squared'
    y_scale = 1e6
    
    plot_title = 'Cloud Size over time'
    enable_histograms = False
    fit_function = Power
    hold = {'alpha':2}

class RabiFlopModel(TimeModel):
    
    # global parameters
    namespace="RabiFlopExp"
    y_label='Transition Prob.'
    enable_histograms = False
    x_label = 'Pulse Time'
    x_units = 'ms'

    plot_title = 'Rabi Flop'
    fit_function = ExpSine
    main_fit = 'f'
    def before_validate(self, fit):
        fit.fitresults['f'] = np.round(fit.fitresults['f']*1e-6, 3)
    y_scale = 1e6
    
    
class DipoleFreqModel(TimeModel):
    
    # global parameters
    enable_histograms=False
    namespace="DipoleOscExp"
    y_label='Cloud size'
    x_label = "Time"
    x_units = 'ms'
    plot_title = "Dipole Oscillation"
    fit_function = Sine
    main_fit = 'f'

    
class RabiModel(TimeModel):

    # global parameters
    namespace="RabiFlopExp"
    y_label='Transition Prob.'
    enable_histograms = False
    @property
    def x_label(self):
        if self.type == 'time':
            return 'Pulse Time'
        else:
            return 'Detuning'
    @property
    def x_units(self):
        if self.type == 'time':
            return 'us'
        else:
            return 'MHz'
    @property
    def plot_title(self):
        if self.type == 'time':
            return 'Rabi Flop'
        else:
            return 'Frequency Scan'
    
    @property
    def fit_function(self):
        if self.type == 'time':
            return ExpSine
        else:
            return Lor

    main_fit = 'f'
    def before_validate(self, fit):
        if self.type == 'time':
            fit.fitresults['f'] = np.round(fit.fitresults['f']*1e-6, 3)
        else:
            fit.fitresults['FWHM'] = 2*np.round(fit.fitresults['Gamma']*1e-3, 3)

    y_scale = 1e6
class RamseyModel(TimeModel):

    # global parameters
    enable_histograms=False
    namespace="RamseyScanExp"
    y_label='Excite. Prob.'
    y_scale = 1e6
    x_label = "Delay Time"
    x_units = 'us'
    plot_title = "Ramsey Delay Scan"
    fit_function = ExpSine
    main_fit = 'f'
    persist=False

           
class RamseyPhaseModel(TimeModel):

    # global parameters
    enable_histograms=False
    namespace="RamseyPhaseScanExp"
    y_label='Excite. Prob.'
    y_scale = 1e6
    x_label = "Phase"
    x_units = 'Turns'
    plot_title = "Ramsey Phase Scan"
    fit_function = Sine
    main_fit = 'A'
    hold = {"f":1}
    persist=False
    def before_validate(self, fit):
        fit.fitresults['A'] = 2*np.round(fit.fitresults['A']*1e-6, 3)
        
class RamseyDecayModel(TimeModel):

    # global parameters
    enable_histograms=False
    namespace="RamseyDelayExp"
    y_label='Contrast'
    y_scale = 1e6
    x_label = "Delay Time"
    x_units = 'us'
    plot_title = "Constrast Decay"
    fit_function = Exp
    main_fit = 'b'
    persist=False

    
    
    
class PicoModel(TimeModel):
    namespace='PM2'
    y_label='Transition prob (x10e6)'
    enable_histograms=False
    x_label='Picomotor 2 Position'
    x_units = 'steps'
    plot_title = 'Picomotor Scan'
    fit_function = Gauss
    main_fit = 'x0'
         
    x_scale = 1000
    y_scale = 1e6
    
class FreqModelGen(FreqModel):
    namespace='FreqModel'
    y_label='Transition prob.'
    enable_histograms=False
    x_label='Frequency'
    x_units = 'MHz'
    plot_title = 'Frequency Scan'
    fit_function = Gauss
         
    x_scale = 1e6
    y_scale = 1 
    
    
class LinearModel(TimeModel):
    namespace='PMCal'
    y_label='Picomotor 2 Optimum'
    y_units = 'steps'
    enable_histograms=False
    x_label='Picomotor 1 Position'
    x_units = 'steps'
    plot_title = 'Picomotor Calibration'
    fit_function = Poly
    y_scale = 1000
    x_scale = 1000
    
class PicoAngleModel(TimeModel):
    namespace='PMAngle'
    y_label='Max Contrast Ratio'
    enable_histograms=False
    x_label='Picomotor 1 Position'
    x_scale = 1e3
    x_units = '1e3 steps'
    plot_title = 'Picomotor Angle Scan'
    fit_function = Gauss
    main_fit=True
    persist=False
    hold = {"y0":0}
    # man_scale={'sigma':1, 'A':1, 'x0':1, 'y0':1}
    
    
class PicoScanModel(TimeModel):
    namespace='PMAngle_Compensation'
    y_label='Contrast Ratio'
    y_scale = 1e6
    enable_histograms=False
    x_label='Picomotor 2 Position'
    x_scale = 1e3
    x_units = '1e3 steps'
    main_fit = 'A'
    plot_title = 'Picomotor Angle Compensation Scan'
    fit_function = Gauss
    hold = {"y0":0}
    # man_scale={'sigma':1, 'A':1, 'x0':1, 'y0':1}
