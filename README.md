# PyNcView
PyNcView is a cross-platform [NetCDF](https://www.unidata.ucar.edu/software/netcdf/)
viewer written in Python. It provides an easy-to-use graphical user interface
to the creation of animations and publication-quality figures. It can open
multiple NetCDF files side-by-side and can plot expressions containing NetCDF
variables and mathematical operators.

## Installation (Windows, Mac, Linux)

If you use [Anaconda](https://docs.anaconda.com/free/anaconda/) or
[Miniconda](https://docs.anaconda.com/free/miniconda/), the easiest way to
install PyNcView is:

```bash
conda install -c conda-forge pyncview
```

Alternatively, PyNcView can be installed with pip:

```bash
pip install pyncview
```

In that case, you will also need to have PySide6, PyQt6, PyQt5, or PySide2 installed. PySide6 can be installed with `pip install pyside6`.

## Use

To use PyNcView, start it from the command line with

```bash
pyncview
```

If you add the path to the NetCDF file you want to open, PyNcView will show
that right away, for instance:

```bash
pyncview result.nc
```
