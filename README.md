
# labscript_rp_asg

This project integrates the [PYRPL](https://pyrpl.readthedocs.io/en/latest/#) Arbitrary Signal Generator (ASG) into the [labscript suite](http://labscriptsuite.org/),
which is a control system for autonomous, hardware timed experiments.
The project is used as ASG for controlling the set-point of an optical dipole trap in our Fermi gas experiment.


## Notes:

* Two versions are available Python 3.7.5 & Python 2.7 (still running on the computer responsible for experimental control in the Fermi gas experiment)

### red_pitaya_pyrpl_asg_python3.7.5

* Installation of labscript_suite February 2020 worked perfectly
  with Python=3.7.5 but not newest version Python=3.8.1

* Place user device 'red_pitaya_pyrpl_asg' folder in
  labscript_suite/userlib/user_devices folder
  to be able to import device to connection_table and shotfile

* The red_pitaya_pyrpl_asg relies on the PYRPL API, which has to be installed 
  to be able to run it

## PYRPL

* PYRPL API runs under python 3.7.5 as well as python 2.7

### Install and run Pyrpl using Anaconda

*install Anaconda and install packages in virtual environment of labscript

<$conda install numpy scipy paramiko pandas nose pip pyqt qtpy pyqtgraph pyyaml>

*install pyrpl see [Installing PYRPL](https://pyrpl.readthedocs.io/en/latest/user_guide/installation/pyrpl_installation.html)

<$pip install pyrpl>

or

<$git clone https://github.com/lneuhaus/pyrpl.git YOUR_PYRPL_DESTINATION_FOLDER>

$python setup.py develop

*to run pyrpl activate virtual environment and go to /scripts

<$python run_pyrpl.py>