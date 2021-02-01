import sys
import os

import numpy as np
import labscript_utils.h5_lock
import h5py
import re

from labscript import *

from blacs.device_base_class import DeviceTab
from blacs.tab_base_classes import define_state, MODE_MANUAL, MODE_BUFFERED, MODE_TRANSITION_TO_MANUAL, Worker

from qtutils import UiLoader
import qtutils.icons
from qtutils import *

import labscript_utils.properties
from labscript_devices import labscript_device, BLACS_tab, BLACS_worker, runviewer_parser 

@labscript_device
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
    @set_passed_properties({'connection_table_properties': ['ip_addr',
                            'out_channel', 'peak_volt', 'offset_calib'],
                            'device_properties': ['trig_duration']})

    def __init__(self,
                 name,
                 trigger_device=None,
                 trigger_connection=None,
                 ip_addr=None,
                 out_channel='out1',
                 trig_duration=None,
                 peak_volt=10,
                 offset_calib=0,
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
        self.trig_duration = trig_duration

        # Commands and their parameters are appended to the list in the
        # order given in the shot file. The first command triggers the parent
        # device. From the commands the method 'generate_code' creates
        # the output data of the ASG.
        self.commands = []

    def trigger(self, t):
        """
        Trigger triggers parent_device at time 't'
        for duration 'cycle_duration'.
        """
        self.trigger_device.trigger(t, self.trig_duration)

    def power_ramp(self, t, duration, time_const,
                   init_volt, final_volt, ratio_trap_temp):
        """
        This function defines a power law evaporation ramp.
        See PhD Thesis Florian Huber:
        "Site-Resolved Imaging with the Fermi Gas Microscope" from 2014
        for details.
        """
        # insert trigger if this is the first command
        if not self.commands:
            self.trigger(t)

        if time_const < duration :
            raise LabscriptError("""{}: 'power_ramp' requires
                                time_const > duration.""".format(self.name))

        if final_volt >= init_volt :
            raise LabscriptError("""{}: 'power_ramp' requires
                                final_volt < init_volt.""".format(self.name))

        # command is dict with parameters
        self.commands.append({'name': 'power_ramp', 't': t,
                              'duration': duration, 'time_const': time_const,
                              'init_volt': init_volt, 'final_volt': final_volt,
                              'ratio_trap_temp': ratio_trap_temp})

    def linear_ramp(self, t, duration, init_volt, final_volt):
        """
        Linear ramp at time 't' with length 'duration' from the initival
        voltage 'init_volt' to final voltage 'final_volt'
        """
        # insert trigger if this is the first command
        if not self.commands:
            self.trigger(t)
        # command is dict with parameters
        self.commands.append({'name': 'linear_ramp','t': t,
                              'duration': duration, 'init_volt': init_volt,
                              'final_volt': final_volt})

    def constant(self, t, duration, volt):
        """
        Constant output voltage 'volt' at time 't'
        for duration 'duration' or if duration = 0 until value is changed.
        If this is the last command a fixed duration must be specified.
        """
        # insert trigger if this is the first command
        if not self.commands:
            self.trigger(t)
        # command is dict with parameters
        self.commands.append({'name': 'constant', 't': t,
                              'duration': duration, 'volt': volt})


    def sine(self, t, duration, freq, amplitude, offset):
        """
        Sinusoidal Output Voltage of Amplitude 'amplitude' at time 't'
        for a time duration 'duration' with frequency 'freq'
        """
        if not self.commands:
            self.trigger(t)
        self.commands.append({'name': 'sine', 't': t,
                              'duration': duration,
                              'frequency': freq,
                              'amplitude': amplitude,
                              'offset': offset})
        
    def generate_code(self, hdf5_file):
        """
        Generate_code method, which creates hardware instructions
        for PYRPL ASG.
        """
        # end exectuion of generate_code if there are no commands
        if not self.commands:
            return
            
        # get time stamps of commands from shot file
        times = [command['t'] for command in self.commands]

        # get time differences between commands
        time_diffs = np.diff(times)

        # get duration of commands from shot file
        durations = [command['duration'] for command in self.commands]

        # check if there is duration = 0 and replace by time difference
        # until next command
        if durations[-1] == 0:
            raise LabscriptError("""{}: Last command needs
                                fixed duration""".format(self.name))
        else:
            zero_dur = [i for i, dur in enumerate(durations) if dur == 0]

            for i in zero_dur:
                durations[i] = time_diffs[i]
            
        t_init = min(times)
        t_final = max(times) + durations[times.index(max(times))]
        total_duration = t_final - t_init
        
        # Convert total duration into frequency
        frequency = 1/total_duration
        
        # frequency increment from PYRPL
        freq_increment = 1.16415e-1
        
        # round down frequency to multiple of freq_increment
        # and set total duration to rounded value
        rounded_freq = np.floor(frequency/freq_increment) * freq_increment 
        total_duration = 1/rounded_freq
        
        # PYRPL expects exactly 2**14 data points
        ts = np.linspace(0.0, total_duration, 2**14)

        # Create np.array for output values of length 2**14
        out_values = np.zeros(2**14)

        # Generate output values from commands list
        for i, command in enumerate(self.commands):
            # find index of inital time
            t_init_idx = (np.abs(ts-(times[i]-t_init))).argmin()
            # find index of final time
            t_end_idx = (np.abs(ts-(durations[i]+times[i]-t_init))).argmin()
            # generate steps in between inital and final time
            steps = np.linspace(0, 1, t_end_idx-t_init_idx)

            # linear ramp
            if command['name'] == 'linear_ramp':
                out = ((command['final_volt']-command['init_volt'])
                       *steps+command['init_volt'])
                out_values[t_init_idx:t_end_idx] = out

            # power law ramp
            if command['name'] == 'power_ramp':
                ratio_trap_temp = (command['ratio_trap_temp']+
                                   (command['ratio_trap_temp']-5)
                                   /(command['ratio_trap_temp']-4))

                ramp_exp = 2 * (ratio_trap_temp-3) / (ratio_trap_temp-6)

                coeff = (1-durations[i]/command['time_const'])**ramp_exp

                coeff2 = ((command['init_volt']*coeff-command['final_volt'])
                          /(coeff-1))

                pow_ramp_out = ((command['init_volt']-coeff2)
                                *(1-steps*durations[i]
                                /command['time_const'])**ramp_exp+coeff2)

                out_values[t_init_idx:t_end_idx] = pow_ramp_out

            # constant value
            if command['name'] == 'constant':
                out_values[t_init_idx:t_end_idx] = [command['volt']]*len(steps)
            
            # sine
            if command['name'] == 'sine':
                out_values[t_init_idx:t_end_idx] = (np.sin(2*np.pi*command['frequency']*command['duration']*steps)
                                                   *command['amplitude'] + command['offset'])
        
        
        group = self.init_device_group(hdf5_file)

        if self.commands:
            print('rp tot dur: {}'.format(total_duration))
            group.create_dataset('total_duration', data=total_duration)
            group.create_dataset('out_values', data=out_values)

        TriggerableDevice.generate_code(self, hdf5_file)

@BLACS_tab
class red_pitaya_pyrpl_asg_tab(DeviceTab):
    """
    The class red_pitaya_pyrpl_asg_tab subclasses DeviceTab class
    handles GUI and related events.

    For more information see:
    'labscript_suite/blacs/docs/How\ to\ add\ a\ new\ device'
    """

    def initialise_GUI(self):
        """
        Define output capabilities of RP and generate UI for manual control
        of the RP through the front panel.
        """
        # Add widgets from 'red_pitaya_pyrpl.ui'
        # For editting widgets use Qt designer
        layout = self.get_tab_layout()
        ui_filepath = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                   'red_pitaya_pyrpl.ui')
        self.ui = UiLoader().load(ui_filepath)
        layout.addWidget(self.ui)

        # Interact with widgets
        self.ui.waveform0_box.currentIndexChanged.connect(
            lambda: self.update_attributes('waveform'))
        self.ui.amplitude0_spinbox.editingFinished.connect(
            lambda: self.update_attributes('amplitude'))
        self.ui.offset0_spinbox.editingFinished.connect(
            lambda: self.update_attributes('offset'))
        self.ui.frequency0_spinbox.editingFinished.connect(
            lambda: self.update_attributes('frequency'))


    def initialise_workers(self):
        """
        Tell device Tab to launch 'main_worker' as primary worker process
        as described in class
        'user_devices.red_pitaya_pyrpl.blacs_workers.red_pitaya_pyrpl_worker'.

        When the device tab enters one of the states of the state machine
        built into 'DeviceTab' such as 'transition_to_buffered',
        the primary worker is communicated with first.
        """
        # Look up connection_table_properties in the connection table:
        connection_table = self.settings['connection_table']
        device = connection_table.find_by_name(self.device_name)
        ip_addr = device.properties['ip_addr']
        peak_volt = device.properties['peak_volt']
        offset_calib = device.properties['offset_calib']

        # Launch worker process and pass RP IP address to worker process
        self.create_worker(
            'main_worker',
            red_pitaya_pyrpl_asg_worker,
            {'ip_addr': ip_addr, 'peak_volt': peak_volt, 'offset_calib': offset_calib})
        self.primary_worker = 'main_worker'

    # Decorate 'update_attributes' with @define_state decorator to promote it
    # to a state-function such that when called it is placed in a queue and
    # executed accordingly
    @define_state(MODE_MANUAL, queue_state_indefinitely=True,
                  delete_stale_states=True)
    def update_attributes(self, which_attr):
        """
        Additional state-function 'update_attributes' in manual mode
        communicates with 'update_asg' in worker process to set the PYRPL
        asg0 according to the front panel.

        """

        if which_attr == 'waveform':
            attr_value = self.ui.waveform0_box.currentText()

        elif which_attr == 'amplitude':
            attr_value_check = self.ui.amplitude0_spinbox.value()
            # only allow multiples of stepsize 1.22070e-4 given in PYRPL
            nearest_multiple = 1.22070e-4 * round(attr_value_check/1.22070e-4)
            attr_value = nearest_multiple
            self.ui.amplitude0_spinbox.setValue(attr_value)

        elif which_attr == 'offset':
            attr_value_check = self.ui.offset0_spinbox.value()
            # only allow multiples of stepsize 1.22070e-4 given in PYRPL
            nearest_multiple = 1.22070e-4 * round(attr_value_check/1.22070e-4)
            attr_value = nearest_multiple
            self.ui.offset0_spinbox.setValue(attr_value)

        elif which_attr == 'frequency':
            attr_value_check = self.ui.frequency0_spinbox.value()
            # only allow multiples of stepsize 1.16415e-1 given in PYRPL
            nearest_multiple = 1.16415e-1 * round(attr_value_check/1.16415e-1)
            attr_value = nearest_multiple
            self.ui.frequency0_spinbox.setValue(attr_value)

        else:
            raise TypeError("\'which_attr\' has to be one of the following:"
                            "\'waveform\', \'amplitude\',"
                            "\'offset\', \'frequency\'")

        # Communicate with 'main_worker' and call 'update_asg'
        yield (self.queue_work(self.primary_worker, 'update_asg', attr_value,
                            which_attr))

    @define_state(MODE_BUFFERED,False)
    def transition_to_manual(self,notify_queue,program=False):
        """
        Modified version of transition_to_manual method, which also resets
        red_pitaya_pyrp_asg UI
        """

        self.mode = MODE_TRANSITION_TO_MANUAL

        # Modified behaviour of 'transition_to_manual' to also return
        # attribute dictionary for resetting UI
        success, attr_dict = yield(self.queue_work(self._primary_worker,'transition_to_manual'))

        # Update UI
        self.ui.amplitude0_spinbox.setValue(attr_dict['amplitude'])
        self.ui.offset0_spinbox.setValue(attr_dict['offset'])
        self.ui.frequency0_spinbox.setValue(attr_dict['frequency'])
        self.ui.waveform0_box.setCurrentIndex(0)

        for worker in self._secondary_workers:
            transition_success = yield(self.queue_work(worker,'transition_to_manual'))
            if not transition_success:
                success = False
                # don't break here, so that as much of the device is returned to normal

        # Update the GUI with the final values of the run:
        for channel, value in self._final_values.items():
            if channel in self._AO:
                self._AO[channel].set_value(value,program=False)
            elif channel in self._DO:
                self._DO[channel].set_value(value,program=False)
            elif channel in self._image:
                self._image[channel].set_value(value,program=False)
            elif channel in self._DDS:
                self._DDS[channel].set_value(value,program=False)



        if success:
            notify_queue.put([self.device_name,'success'])
            self.mode = MODE_MANUAL
        else:
            notify_queue.put([self.device_name,'fail'])
            raise Exception('Could not transition to manual. You must restart this device to continue')

        if program:
            self.program_device()
        else:
            self._last_programmed_values = self.get_front_panel_values()

    
@BLACS_worker
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
        self.amplitude = self.__out_amp_volt_conv(0.0)
        self.offset = self.__offset_calib(self.__out_amp_volt_conv(0.0))
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

    def __out_amp_volt_conv(self, amp_out):
        """
        Private method to handle the conversion of the output of the amplifier
        [-peak_volt, peak_volt]V to [-1,1]V output values of PYRPL. The optional
        -1V offset in the amplifier can compensate for the
        [0, 2V] output of the modified Red Pitaya.
        """
        gain = self.peak_volt
        rp_out = amp_out/gain
        return rp_out

    def __offset_calib(self, offset):
        """
        Private method to calibrate the RP analog out and introduce
        a calibration offset voltage.
        """

        rp_calib_offset = offset + self.offset_calib
        return rp_calib_offset
        
    def program_manual(self, values):
        """
         Not used, but needs to be defined. Is used, when a value of a
         digital, analog or DDS output widget on the front panel is changed.
         However, we don't use these widgets in the device Tab.

        """
        return {}

    def transition_to_buffered(self, device_name, hdf5_file, initial_values,
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
        self.shot_file = hdf5_file
        with h5py.File(self.shot_file, 'r') as f:
            group = f['devices/{}'.format(self.device_name)]
            if 'out_values' in group:
                out_values = group['out_values'][:]

            else:
                out_values = None

            if 'total_duration' in group:
                print(group['total_duration'])
                frequency = 1/group['total_duration'][()]
            else:
                frequency = None

        # Frequency is more natural to PYRPL API
        self.frequency = frequency
        self.amplitude = self.__out_amp_volt_conv(self.peak_volt)
        self.offset = self.__offset_calib(self.__out_amp_volt_conv(0.0))
        self.cycles_per_burst = 1

        self.connection.rp.asg0.setup(frequency=self.frequency,
                                    amplitude=self.amplitude,
                                    offset=self.offset,
                                    trigger_source='ext_positive_edge',
                                    cycles_per_burst=self.cycles_per_burst)

        # Send arbitrary evaporation_ramp to Red Pitaya
        self.connection.rp.asg0.data = self.__out_amp_volt_conv(out_values)

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
        self.amplitude = self.__out_amp_volt_conv(0.0)
        self.offset = self.__offset_calib(self.__out_amp_volt_conv(0.0))
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
        attr_dict = {'waveform': self.waveform,
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
            self.amplitude = self.__out_amp_volt_conv(attr_value)
        elif which_attr == 'offset':
            self.offset = self.__offset_calib(self.__out_amp_volt_conv(attr_value))
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
        self.amplitude = self.__out_amp_volt_conv(0.0)
        self.offset = self.__offset_calib(self.__out_amp_volt_conv(0.0))
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
        """
        This is called if transition_to_buffered fails with an exception or
        returns False.
        """
        # Forget the shot file:
        self.shot_file = None
        return True # Indicates success
    
@runviewer_parser
class Parser(object):
    """
    So far there is nothing to see in the runviewer.
    """
    pass
