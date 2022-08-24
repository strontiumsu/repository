# -*- coding: utf-8 -*-
"""
Created on Mon Aug 23 11:06:21 2022

@author: Sr - E. Porter
"""
from artiq.language import EnvExperiment, delay, NumberValue, kernel


class PulseTesting(EnvExperiment):
    """
    Experiment that outputs a pulse train of varying length, width, and spacing
    """

    def build(self):
        #interface with device_db to connect to our devices
        self.setattr_device('core')
        self.setattr_device('ttl4') # output TTL port

        # parameters
        self.setattr_argument("pulse_seperation", NumberValue(2e-3,min=0.1e-3,max=4000e-3, unit=
        'ms'),"Params") # pulse seperation imte
        self.setattr_argument("on_time", NumberValue(1e-3,min=0.1e-3,max=10e-3, unit=
        'ms'),"Params") # time for the pulse to be on
        self.setattr_argument("pulse_num", NumberValue(1,min=100,max=100000, type=
        "int", ndecimals=0, scale=1, step=1),"Params") # how many pulse to send

    @kernel
    def run(self):
        # get devices ready
        self.core.reset()
        self.ttl4.output()


        # generate pulse train
        for _ in range(int(self.pulse_num)):
            self.ttl4.pulse(self.on_time)
            delay(self.pulse_seperation)
        print(f"Done.. T: {self.pulse_seperation + self.on_time}, Ton: {self.on_time}, N: {self.pulse_num}")
