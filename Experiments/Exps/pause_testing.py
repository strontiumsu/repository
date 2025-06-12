from artiq.experiment import *
from time import sleep

class UserPausedExperiment(EnvExperiment):

    def build(self):
        # Normal hardware devices …
        self.setattr_device("core")
        # The virtual device that talks to the scheduler:
        self.setattr_device("scheduler")


        # How many shots you want to take in total
        self.setattr_argument("n_shots", NumberValue(10, step=1, ndecimals=0))
        
        self.setattr_device("ttl5") # triggering pulse

    # ----------------------------------------------------------------------
    # Real-time part: one “shot”
    # ----------------------------------------------------------------------
    @kernel
    def shot(self, i: TInt32):
        self.core.reset()                    # always restart the RTIO timeline
        delay(1*ms)

        # Pull the (possibly changed) parameter value each time
        self.ttl5.pulse((i+1)*10*us)
        # … use `det` for DDS frequency, pulse length, etc.

        # hardware sequence here
        delay(10*ms)                        # placeholder
        self.core.wait_until_mu(now_mu())

    # ----------------------------------------------------------------------
    # Host-side loop with explicit pauses
    # ----------------------------------------------------------------------
    def run(self):
        for i in range(self.n_shots):
            self.shot(i)
            print("Step Value")
            sleep(3)
           
