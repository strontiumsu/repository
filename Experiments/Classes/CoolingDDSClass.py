# -*- coding: utf-8 -*-
"""
CoolingDDSClass.py

Dedicated DDS class for the urukul1 AOMs used by the blue/red MOT (3D, 3P0 repump,
3P2 repump, 3D red).  Parallel to _Bragg (BraggClass.py) and _state_control
(StateControlClass.py): it is pure urukul1 configuration on top of the shared
DDSClass._DDSGroup machinery.  _Cooling (CoolingClass.py) holds an instance of this
as self.dds and drives it from its MOT sequences.
"""

from DDSClass import _DDSGroup


class _CoolingDDS(_DDSGroup):

    CPLD = "urukul1_cpld"
    URUKUL = "urukul1"

    AOM_NAMES = ["3D", "3P0_repump", "3P2_repump", "3D_red"]

    DEFAULT_SCALES = [0.8, 0.8, 0.8, 0.8]
    DEFAULT_ATTENS = [6.0, 2.0, 6.0, 9.0]
    DEFAULT_FREQS = [180.0, 210.0, 80.0, 180.0]   # MHz

    ALIASES = {"aom_3D_blue": 0, "aom_3P0": 1, "aom_3P2": 2, "aom_3D_red": 3}


    # init_aoms is inherited from _DDSGroup
