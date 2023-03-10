# PyNcView
PyNcView is a cross-platform [NetCDF](https://www.unidata.ucar.edu/software/netcdf/) viewer written in Python. 
It provides an easy-to-use graphical user interface to the creation of animations and publication-quality figures.

## Installation
The easiest way to install PyNcView is via [PyPi](https://pypi.org/):

```bash
pip install pyncview
```

To run PyNcView you will need to have PyQt or PySide installed. To install the former, use `pip install pyqt5` or, if using the [Anaconda Python distribution](https://www.anaconda.com/products/distribution), `conda install pyqt`.

## Use

To use PyNcView, start it from the command line with

```bash
pyncview
```

If you add the path to the NetCDF file you want to open, PyNcView will show that right away, for instance:

```bash
pyncview result.nc
```
