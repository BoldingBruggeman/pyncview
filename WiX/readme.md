This directory contains everything needed to build a PyNcView installation
package for Windows.

Here comes the necessary steps do create a Windows installer.

1. set PYTHONPATH=%PYTHONPATH%;$USERPROFILE%\Documents\GOTM\code\gui.py (assuming a standard install).
2. python setup.py py2exe
3. cd WiX
4. python buildmsi.py <version> - version must be larger than what is listed in *lastversion.dat*

The first point allows *python* to locate the *GOTM* contained python modules.

The second point creates a ./dist directory containing a Windows application based on the PyNcView python code.

The third point just enters the installer configuration directory.

The fourth point creates the single Windows Installer MSI file based on the application in the ../dist directory.

For this purpose the open-source [Windows Installer XML (WiX) toolset](http://wixtoolset.org).
This is a freely distributed, stand-alone program
(it does not require Visual Studio) that takes a XML-based description of an
application setup and converts it into a single MSI file. Some Python
(buildmsi.py) is used as well to enumerate all files in the application
directory and add these to the XML that describes the application setup.

Building an MSI package from the ../dist application directory now is as simple
as executing

    "buildmsi.py VERSION"

where VERSION must be of the format x.x.x, each x being an integer number. The
version number of the last successfully built setup package is saved in
versioncache.dat. Newer packages MUST ALWAYS have a higher version number than
the one contained in this file. Commit to SVN after building a new package to
ensure versioncache.dat is updated.

Note that you have to have the [Windows Installer XML (WiX) toolset](http://wixtoolset.org) installed,
as well as the [Win32 extensions for Python](https://sourceforge.net/projects/pywin32/).

# Testing

The best test of a newly compiled installation package is installation on a
virgin Windows XP, e.g., via VirtualPC/Windows XP Mode on Windows 7. PyNcView
should install correctly, and open NetCDF and HDF4 files correctly. It is also
recommended to test the mapping/projection functionality.

# Potential pitfalls

* Python's distutils appears to grab necessarily DLLs wherever it finds them in
the system path. On 64-bit systems, this may lead to 64-bit DLLs being included
in the 32-bit package, thus breaking pyncview on any other system (it may still
run on the 64-bit system!). This has been observed for zlib1.dll.
