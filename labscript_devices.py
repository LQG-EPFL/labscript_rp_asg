#####################################################################
#                                                                   #
# /red_pitaya_pyrpl.py                                              #
#                                                                   #
#                                                                   #
#                                                                   #
#####################################################################

import numpy as np
import h5py
import re

from labscript import *


class red_pitaya_pyrpl_asg(TriggerableDevice):
    """
    A labscript device to use PYRPL ASG0 as an
    externally triggered device with trigger_edge_type = 'rising'
    in experimental sequences.
    """
    description = 'Red Pitaya PYRPL Arbitray Signal Generator (ASG)'

    # RP has two analog outputs/inputs
    # However, since the RP is not connected to the fast clock of pseudoclock,
    # methods of class AnalogOut are not compatible with how we program RP
    # i.e. we don't allow children
    allowed_children = []

    # This decorator declares that some keyword arguments should be saved to the
    # connection table and device properties:
    @set_passed_properties({'connection_table_properties': ['ip_addr'],
                            'device_properties': ['waveform', 'cycle_duration',
                            'amplitude', 'offset', 'cycles_per_burst',
                            'time_const', 'ratio_trap_temp']})
    def __init__(self,
                 name,
                 trigger_device=None,
                 trigger_connection=None,
                 ip_addr=None,
                 waveform=None,
                 cycle_duration=0.0,
                 amplitude=0.0,
                 offset=0.0,
                 cycles_per_burst=0,
                 time_const=None,
                 ratio_trap_temp=None,
                 **kwargs):

        if trigger_device is None:
            TriggerableDevice.__init__(self,
                                       name,
                                       parent_device=None,
                                       connection=None,
                                       parentless=True,
                                       **kwargs)
        else:
            TriggerableDevice.__init__(self,
                                       name,
                                       parent_device=trigger_device,
                                       connection=trigger_connection,
                                       **kwargs)

        # BLACS_connection attribute saves information regarding Red Pitaya
        # connection to control PC. The existence of this attribute is how
        # BLACS knows it needs to make a tab for this device:
        self.BLACS_connection = ip_addr

        # check if waveform is valid
        valid_waveforms = ['sin', 'cos', 'ramp', 'halframp', 'square',
                           'dc', 'noise', 'evaporation_ramp']
        if not waveform in valid_waveforms:
            raise TypeError("Red Pitaya PYRPL ASG {} needs keyword argument"
                                 "\'waveform\':"
                                 "\'sin\', \'cos\', \'ramp\', \'halframp\', "
                                 "\'square\', \'dc\', \'noise\',"
                                 "\'evaporation_ramp\'".format(self.name))
        if not 1.6e-8 <= cycle_duration:
            raise LabscriptError("Red Pitaya PYRPL ASG {} keyword argument "
                            "\'cycle_duration\'"
                            "out of range [1e-7, 10]".format(self.name))
        self.cycle_duration = cycle_duration

        if not 0.0 <= amplitude <= 1.0:
            raise LabscriptError("Red Pitaya PYRPL ASG {} keyword argument "
                            "\'amplitude\' out of "
                            "range [0, 1]".format(self.name))

        if not 0.0 <= offset <= 2.0:
            raise LabscriptError("Red Pitaya PYRPL ASG {} keyword argument "
                            "\'offset\' out of range [0, 2]".format(self.name))

        if not isinstance(cycles_per_burst, int):
            raise TypeError("Red Pitaya PYRPL ASG {} keyword argument "
                            "\'cycles_per_burst\' needs to be"
                            "of type \'int\'".format(self.name))

        if waveform == 'evaporation_ramp':
            if not 0.0 < time_const <= self.cycle_duration:
                raise LabscriptError("Red Pitaya PYRPL ASG {} keyword argument "
                                "\'evaporation_ramp\' expects additional "
                                "keyword argument \'time_const\' of type "
                                "\'strictly positive float\' "
                                "in range [0.0, cycle_duration]".format(self.name))
            if not 0.0 < ratio_trap_temp :
                raise LabscriptError("Red Pitaya PYRPL ASG {} keyword argument "
                                "\'evaporation_ramp\' expects additional "
                                "keyword argument \'ratio_trap_temp\' of type "
                                "\'strictly positive float\'".format(self.name))
    def trigger(self, t):
        """
        Trigger triggers parent_device at time 't'
        for duration 'cycle_duration'.
        """
        TriggerableDevice.trigger(self, t, self.cycle_duration)

    def generate_code(self, hdf5_file):
        """
        Generate_code method, which creates hardware instructions for PYRPL.
        """
        TriggerableDevice.generate_code(self, hdf5_file)
