import labscript_utils.h5_lock
import h5py

import numpy as np

import labscript_utils.properties
from blacs.tab_base_classes import Worker

class red_pitaya_pyrpl_asg_worker(Worker):
    """
     The class 'red_pitaya_pyrpl_asg_worker' subclasses 'Worker' and
     handles all the communication with hardware of the Red Pitaya via
     the PYRPL API.

     The worker class is instantiated as separate process, which can be
     restarted by the user if the RP becomes unresponsive.

    For more information see:
    'labscript_suite/blacs/docs/How\ to\ add\ a\ new\ device'
    """

    def init(self):
        """
        The init function does not override __init__. We load 'pyrpl' inside
        'init' such that it only exists in worker process and not within
        BLACS process.
        """
        # Import Leonhard Neuhaus PYRPL for Red Pitaya
        # https://pyrpl.readthedocs.io/en/latest/
        # Import inside 'init' such that PYRPL exists only inside worker process
        from pyrpl import Pyrpl

        # Create PYRPL object connecting to Red Pitaya with given IP address
        # No config file
        self.connection = Pyrpl(hostname=self.ip_addr, config="")

        # Turn on LED 0 to indicate that PYRPl is set up
        self.connection.rp.hk.led = 0b00000001

        # Hide PYRPl GUI
        self.connection.hide_gui()

        # Prevent timeout of connection
        self.connection.rp.client.socket.settimeout(None)
        # print("timeout = ", self.connection.rp.client.socket.timeout)

        # Set default values for ASG0 attributes
        self.waveform = 'dc'
        self.frequency = 0.0
        self.amplitude = 0.0
        self.offset = -1.0
        self.cycles_per_burst = 0

        # Initialize analog outputs 'out1' to zero
        # given that we are using a modified RP with output 0-2V
        self.connection.rp.asg0.output_direct = 'out1'

        self.connection.rp.asg0.setup(waveform=self.waveform,
                                      frequency=self.frequency,
                                      offset=self.offset,
                                      trigger_source='immediately',
                                      cycles_per_burst=self.cycles_per_burst)

        # Each shot, we will remember the shot file
        # for the duration of that shot
        self.shot_file = None

    def program_manual(self, values):
        """
         Not used, but needs to be defined. Is used, when a value of a
         digital, analog or DDS output widget on the front panel is changed.
         However, we don't use these widgets in the device Tab.

        """
        return {}

    def transition_to_buffered(self, device_name, h5_file, initial_values,
                               fresh):
        """
        State-function 'transition_to_buffered' is called, when Queue Manager
        requests the RP to move into buffered mode in preparation for
        executing a buffered sequence.

        The PYRPL asg0 is set up according to the parameters given
        as device_properties.
        """
        # Turn on LED 2 to indicate that PYRPl is in
        # transition_to_buffered_state
        self.connection.rp.hk.led = 0b00000100

        # Set up attributes according to device_properties in shot file
        self.shot_file = h5_file
        with h5py.File(self.shot_file, 'r') as f:
            device_properties = labscript_utils.properties.get(
                f, self.device_name, "device_properties"
            )
        self.waveform = device_properties['waveform']
        # Frequency is more natural to PYRPL API
        self.frequency = 1 / device_properties['cycle_duration']
        self.amplitude = device_properties['amplitude']
        # Substract -1.0 from Offset due to RP output mod 0-2V
        self.offset = device_properties['offset'] - 1.0
        self.cycles_per_burst = device_properties['cycles_per_burst']

        def evaporation_ramp(freq, time_const, ratio_trap_temp):
            """
            This function defines the evaporation ramp used in the
            experimental shot. See PhD Thesis Florian Huber:
            "Site-Resolved Imaging with the Fermi Gas Microscope" from 2014
            for details.
            """
            # PYRPL expects 2**14 data points
            ts = np.linspace(0.0, 1/freq, 2**14-1)

            ratio_trap_temp = (ratio_trap_temp +
                                (ratio_trap_temp-5) / (ratio_trap_temp-4))
            ramp_exp = 2 * (ratio_trap_temp-3) / (ratio_trap_temp-6)
            out_values = (1-ts/time_const)**ramp_exp

            # Start out_values with 0.0 such that after the shot is run
            # PYRPL outputs 0.0
            out_values = np.append([0.0], out_values)
            return out_values

        if self.waveform == 'evaporation_ramp':
            self.time_const = device_properties['time_const']
            self.ratio_trap_temp = device_properties['ratio_trap_temp']

            self.connection.rp.asg0.setup(frequency=self.frequency,
                                        amplitude=self.amplitude,
                                        offset=self.offset,
                                        trigger_source='immediately',
                                        cycles_per_burst=self.cycles_per_burst)

            # Send arbitrary evaporation_ramp to Red Pitaya
            self.connection.rp.asg0.data = evaporation_ramp(self.frequency,
                                                            self.time_const,
                                                            self.ratio_trap_temp)

        else:
            self.connection.rp.asg0.setup(waveform=self.waveform,
                                          frequency=self.frequency,
                                          amplitude=self.amplitude,
                                          offset=self.offset,
                                          trigger_source='immediately',
                                          cycles_per_burst=self.cycles_per_burst)

        # Return empty dictionary due to empty channels
        return {}

    def transition_to_manual(self):
        """
        The state-function 'transition_to_manual' places the device back in
        the correct mode for operation by the front panel.
        """
        # Turn on LED 1 to indicate that PYRPl is in transition_to_manual
        self.connection.rp.hk.led = 0b00000010


        # Set default values for ASG0 attributes in manual mode
        # And forget the values in buffered mode
        self.waveform = 'dc'
        self.frequency = 0.0
        self.amplitude = 0.0
        self.offset = -1.0
        self.cycles_per_burst = 0

        self.connection.rp.asg0.setup(waveform=self.waveform,
                                      frequency=self.frequency,
                                      amplitude=self.amplitude,
                                      offset=self.offset,
                                      trigger_source = 'immediately',
                                      cycles_per_burst=self.cycles_per_burst)

        # Forget the shot file:
        self.shot_file = None

        # Modify behaviour of 'transition_to_manual' to also return dict of
        # initial values in manual mode
        attr_dict = {'waveform': 'dc',
                     'frequency': self.frequency,
                     'amplitude': self.amplitude,
                     'offset': self.offset}

        # Expected by BLACS. Indicate success.
        return True, attr_dict

    def update_asg(self, attr_value, which_attr):
        """
        Update PYRPL asg0 values according to front panel.

        Called by 'update_attributes' in device Tab.
        """
        # Turn on LED 3 to indicate that PYRPl is updating attributes in
        # Manual Mode
        self.connection.rp.hk.led = 0b00001000

        if which_attr == 'waveform':
            self.waveform = str(attr_value)
        elif which_attr == 'amplitude':
            self.amplitude = attr_value
        elif which_attr == 'offset':
            self.offset = attr_value - 1.0
        elif which_attr == "frequency":
            self.frequency = attr_value

        self.connection.rp.asg0.setup(waveform = self.waveform,
                                      frequency = self.frequency,
                                      amplitude = self.amplitude,
                                      offset = self.offset)


    def shutdown(self):
        """
        Called when BLACS closes.
        """
        # Turn on LED 0 to indicate that PYRPl is in default state
        self.connection.rp.hk.led = 0b00000001

        # Set default values for ASG0 when BLACS closes
        self.waveform = 'dc'
        self.frequency = 0.0
        self.amplitude = 0.0
        self.offset = -1.0
        self.cycles_per_burst = 0

        self.connection.rp.asg0.setup(waveform=self.waveform,
                                      frequency=self.frequency,
                                      amplitude=self.amplitude,
                                      offset=self.offset,
                                      trigger_source = 'immediately',
                                      cycles_per_burst=self.cycles_per_burst)


    def abort_buffered(self):
        """
        Called when a shot is aborted. In this case, we simply run
        transition_to_manual.
        """
        return self.transition_to_manual()

    def abort_transition_to_buffered(self):
        """ This is called if transition_to_buffered fails with an exception or
        returns False.
        """
        # Forget the shot file:
        self.shot_file = None
        return True # Indicates success
