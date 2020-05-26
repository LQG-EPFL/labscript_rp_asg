
# labscript_rp_asg

This project integrates the [PYRPL](https://pyrpl.readthedocs.io/en/latest/#) Arbitrary Signal Generator (ASG) into the [labscript suite](http://labscriptsuite.org/),
which is a control system for autonomous, hardware timed experiments.
It is specifically intended to be used as ASG for controlling the evaporation ramp in a optical dipole trap.


## Notes:

* Created and tested with Python 3.7.5

* Installation of labscript_suite February 2020 worked perfectly
  with Python=3.7.5 but not newest version Python=3.8.1

* Place user device 'red_pitaya_pyrpl_asg' folder in
  labscript_suite/userlib/user_devices folder
  to be able to import device to connection_table and shotfile

* The red_pitaya_pyrpl_asg relies on the PYRPL API, which has to be installed 
  to be able to run it

## PYRPL Installation

//Install and run Pyrpl from source

*install Anaconda and install packages in virtual environment of labscript

<$conda install numpy scipy paramiko pandas nose pip pyqt qtpy pyqtgraph pyyaml>

*install pyrpl after cloning git repository

<$git clone https://github.com/lneuhaus/pyrpl.git YOUR_PYRPL_DESTINATION_FOLDER>

$python setup.py develop

*to run pyrpl activate virtual environment and go to /scripts

<$python run_pyrpl.py>