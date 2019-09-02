import sys
import os
import glob

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

if sys.argv[1] == 'py2exe':
    from distutils.core import setup
    from distutils.filelist import findall
    import py2exe
    import numpy

    # Windows finds the CRT in the side-by-side assembly store (SxS), but Python does not look there.
    # Therefore we add a location of the CRT to the Python path.
    sys.path.append('C:\\Program Files\\Microsoft Visual Studio 8\\VC\\redist\\x86\\Microsoft.VC80.CRT')
    sys.path.append('C:\\Program Files (x86)\\Microsoft Visual Studio 9.0\\VC\\redist\\x86\\Microsoft.VC90.CRT')
    sys.path.append('C:\\Program Files (x86)\\Common Files\\microsoft shared\\VSTO\\10.0')

    # Make sure NumPy DLLs are found
    # http://stackoverflow.com/questions/36191770/py2exe-errno-2-no-such-file-or-directory-numpy-atlas-dll
    paths = set()
    np_path = numpy.__path__[0]
    for dirpath, _, filenames in os.walk(np_path):
        for item in filenames:
            if item.endswith('.dll'):
                paths.add(dirpath)
    sys.path.append(*list(paths))

    # win32com [Python for Windows extensions] makes additional submodules available
    # by modifying its __path__ attribute. Distutils cannot handle runtime modification
    # of __path__. Therefore, we explicitly register its additional paths here.
    # http://www.py2exe.org/index.cgi/win32com.shell
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

    own_data_files = [('',['pyncview.png'])]

    # Let MatPlotLib add its own data files.
    import matplotlib
    own_data_files += matplotlib.get_py2exe_datafiles()

    # Let our xmlplot module add its own data files.
    import xmlplot.common
    own_data_files += xmlplot.common.get_py2exe_datafiles()

    import mpl_toolkits.basemap
    adddir(mpl_toolkits.basemap.basemap_datadir,'basemap-data')

    #own_data_files.append(('',['C:\\Program Files (x86)\\Common Files\\microsoft shared\\VSTO\\10.0']))
    #own_data_files.append(('',['C:\\Windows\\System32\\MSVCP71.dll']))
    #own_data_files.append(('',[os.path.join(os.environ['VS80COMNTOOLS'],'..\\..\\VC\\redist\\x86\\Microsoft.VC80.CRT\\MSVCR80.dll')]))
    #own_data_files.append(('',[os.path.join(os.environ['VS80COMNTOOLS'],'..\\..\\VC\\redist\\x86\\Microsoft.VC80.CRT\\Microsoft.VC80.CRT.manifest')]))

    setup(
        windows=[{'script':'pyncview.py','icon_resources':[(0,'pyncview.ico')]}],
        console=[{'script':'multiplot.py'}],
        options={'py2exe': {
                    'packages' : ['matplotlib','netCDF4', 'pytz'],
    #                'includes' : ['sip','PyQt4._qt'],
                    'includes' : ['sip','netCDF4','netcdftime','ordereddict'],
                    'excludes' : ['_gtkagg', '_tkagg', '_wxagg','Tkconstants','Tkinter','tcl','wx','pynetcdf','cProfile','pstats','modeltest','pupynere','Scientific','scipy'],
                    'dll_excludes': ['libgdk-win32-2.0-0.dll', 'libgobject-2.0-0.dll', 'libgdk_pixbuf-2.0-0.dll','wxmsw26uh_vc.dll','tcl84.dll','tk84.dll','powrprof.dll'],
                }},
        data_files=own_data_files
    )
else:
    from setuptools import setup

    setup(name='pyncview',
        version='0.99.19',
        description='NetCDF viewer written in Python',
        url='http://github.com/BoldingBruggeman/pyncview',
        author='Jorn Bruggeman',
        author_email='jorn@bolding-bruggeman.com',
        license='GPL',
        install_requires=['xmlplot>=0.9.13'],
        classifiers=[
            'Development Status :: 4 - Beta',
            'Intended Audience :: Science/Research',
            'Topic :: Scientific/Engineering :: Visualization',
            'License :: OSI Approved :: GNU General Public License (GPL)',
            'Programming Language :: Python :: 2.7',
        ],
        entry_points={
            'console_scripts': [
                    'pyncview=pyncview.pyncview:main',
                    'multiplot=pyncview.multiplot:main',
            ]
        },
        packages=['pyncview'],
        package_data={'pyncview': ['pyncview.png']})