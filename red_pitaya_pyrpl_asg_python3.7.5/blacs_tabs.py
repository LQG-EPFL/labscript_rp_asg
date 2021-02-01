import os

import labscript_utils.h5_lock
import h5py


from blacs.device_base_class import DeviceTab
from blacs.tab_base_classes import define_state, MODE_MANUAL, MODE_BUFFERED, MODE_TRANSITION_TO_MANUAL

from qtutils import UiLoader
import qtutils.icons
from qtutils.qt.QtCore import *
from qtutils.qt.QtGui import *


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

        # Launch worker process and pass RP IP address to worker process
        self.create_worker(
            'main_worker',
            'user_devices.red_pitaya_pyrpl_asg.blacs_workers.red_pitaya_pyrpl_asg_worker',
            {'ip_addr': ip_addr})
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
        self.ui.waveform0_box.setCurrentText(attr_dict['waveform'])

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
