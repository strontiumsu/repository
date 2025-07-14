from artiq.experiment import EnvExperiment, kernel, BooleanValue, us, ms
from BraggClass import _Bragg

class ringdown_689_exp(EnvExperiment):


    def build(self):
        self.setattr_device("core")
        self.bragg=_Bragg(self)
        self.setattr_device("ttl5")
        



    def prepare(self):
        self.bragg.prepare_aoms()

    @kernel
    def run(self):
        self.core.reset()
        self.bragg.init_aoms(on=True)

        self.bragg.AOMs_off(["Bragg1", "Bragg2"])

        delay(200*ms)

        for _ in range(30):
            delay(200*ms)

            self.bragg.AOMs_on(["Bragg1"])
            delay(50*us)
            self.ttl5.on()
            # delay(5*us)
            self.bragg.AOMs_off(["Bragg1"])
            delay(100*us)
            self.ttl5.off()

        