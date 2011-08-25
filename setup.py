import sys,os

# Windows finds the CRT in the side-by-side assembly store (SxS), but Python does not look there.
# Therefore we add a location of the CRT to the Python path.
sys.path.append('C:\\Program Files\\Microsoft Visual Studio 8\\VC\\redist\\x86\\Microsoft.VC80.CRT')
sys.path.append('C:\\Program Files (x86)\\Microsoft Visual Studio 9.0\\VC\\redist\\x86\\Microsoft.VC90.CRT')

# win32com [Python for Windows extensions] makes additional submodules available
# by modifying its __path__ attribute. Distutils cannot handle runtime modification
# of __path__. Therefore, we explicitly register its additional paths here.
try:
    import modulefinder
    for extra in ('win32com','win32com.shell'):
        __import__(extra)
        m = sys.modules[extra]
        for p in m.__path__[1:]:
            modulefinder.AddPackagePath(extra, p)
except ImportError:
    # win32com not found. This is supported on non-Windows systems.
    pass

# ScientificPython makes additional [binary] modules available by modifying sys.path.
# during import. Make this happen now, so that distutils can pick up these additional
# modules at a later stage.
try:
    import Scientific
except ImportError:
    # ScientificPython not found. This is supported if another NetCDF module is available.
    pass

from distutils.core import setup
import py2exe

from distutils.filelist import findall
import os, os.path,glob

def adddir(path,localtarget=None):
    if localtarget is None: localtarget = path
    for f in findall(path):
        localname = os.path.join(localtarget, f[len(path)+1:])
        if 'CVS' in localname: continue
        own_data_files.append((os.path.dirname(localname),[f]))

def addtreewithwildcard(sourceroot,path,localtarget):
    cwd = os.getcwd()
    os.chdir(sourceroot)
    for f in glob.glob(path):
        if os.path.isfile(f):
            own_data_files.append((os.path.join(localtarget,os.path.dirname(f)),[os.path.join(sourceroot,f)]))
    os.chdir(cwd)

own_data_files = [('',['pyncview.png'])]

# Let MatPlotLib add its own data files.
import matplotlib
own_data_files += matplotlib.get_py2exe_datafiles()

# Let our xmlplot module add its own data files.
import xmlplot.common
own_data_files += xmlplot.common.get_py2exe_datafiles()

import mpl_toolkits.basemap
adddir(mpl_toolkits.basemap.basemap_datadir,'basemap-data')

#own_data_files.append(('',['C:\\Windows\\System32\\MSVCP71.dll']))
#own_data_files.append(('',[os.path.join(os.environ['VS80COMNTOOLS'],'..\\..\\VC\\redist\\x86\\Microsoft.VC80.CRT\\MSVCR80.dll')]))
#own_data_files.append(('',[os.path.join(os.environ['VS80COMNTOOLS'],'..\\..\\VC\\redist\\x86\\Microsoft.VC80.CRT\\Microsoft.VC80.CRT.manifest')]))

setup(
    windows=[{'script':'pyncview.py','icon_resources':[(0,'pyncview.ico')]}],
    console=[{'script':'multiplot.py'}],
    options={'py2exe': {
                'packages' : ['matplotlib', 'pytz'],
#                'includes' : ['sip','PyQt4._qt'],
                'includes' : ['sip','netCDF4_utils','netcdftime','ordereddict'],
                'excludes' : ['_gtkagg', '_tkagg', '_wxagg','Tkconstants','Tkinter','tcl','wx','pynetcdf','cProfile','pstats','modeltest','pupynere','Scientific','scipy'],
                'dll_excludes': ['libgdk-win32-2.0-0.dll', 'libgobject-2.0-0.dll', 'libgdk_pixbuf-2.0-0.dll','wxmsw26uh_vc.dll','tcl84.dll','tk84.dll','powrprof.dll'],
            }},
    data_files=own_data_files
)

