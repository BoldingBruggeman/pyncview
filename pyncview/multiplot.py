#!/usr/bin/env python

# Import standard (i.e., non GOTM-GUI) modules.
import sys,os

def printVersion(option, opt, value, parser):
    importModules(False)
    print(r'$LastChangedRevision$'.strip('$'))
    print(r'$LastChangedDate$'.strip('$'))
    for n, v in xmlplot.common.getVersions():
        print('%s: %s' % (n,v))
    sys.exit(0)

def get_argv():
    """Uses shell32.GetCommandLineArgvW to get sys.argv as a list of Unicode
    strings.

    Versions 2.x of Python don't support Unicode in sys.argv on
    Windows, with the underlying Windows API instead replacing multi-byte
    characters with '?'.
    
    Taken from http://code.activestate.com/recipes/572200/
    """
    if sys.platform=='win32':
        try:
            from ctypes import POINTER, byref, cdll, c_int, windll
            from ctypes.wintypes import LPCWSTR, LPWSTR

            GetCommandLineW = cdll.kernel32.GetCommandLineW
            GetCommandLineW.argtypes = []
            GetCommandLineW.restype = LPCWSTR

            CommandLineToArgvW = windll.shell32.CommandLineToArgvW
            CommandLineToArgvW.argtypes = [LPCWSTR, POINTER(c_int)]
            CommandLineToArgvW.restype = POINTER(LPWSTR)

            cmd = GetCommandLineW()
            argc = c_int(0)
            argv = CommandLineToArgvW(cmd, byref(argc))
            if argc.value > 0:
                # Remove Python executable and commands if present
                start = argc.value - len(sys.argv)
                return [argv[i] for i in range(start, argc.value)]
        except:
            pass
    args = []
    for arg in sys.argv:
        try:
            arg = arg.decode(sys.getfilesystemencoding())
        except:
            pass
        args.append(arg)
    return args

def main():
    """Parses command line, creates multiplot.Plotter object, and calls plot.
    """
    
    import optparse

    # Parse command line options
    def newsource(option, opt_str, value, parser):
        info = value.split('=',1)
        name,path = info[0],info[-1]
        if len(info)==1 or (len(info)>1 and not info[0].isalnum()): name = 'source%i' % len(parser.values.sources)
        parser.values.sources[name] = path
        parser.values.lastsource = name
        
    def newexpression(option, opt_str, value, parser):
        if parser.values.lastsource is None: raise optparse.OptionValueError('%s must be preceded by a -s/--source option.' % option)
        if not isinstance(value,tuple): value = (None,value)
        parser.values.expressions.append((value[0],parser.values.lastsource,value[1]))

    parser = optparse.OptionParser(usage='%prog OPTIONS [PROPERTY=VALUE ...]',
description="""This script plots one or more variables from different NetCDF
files. Series to plot are specified by a combination of one or more -s
and -e/-E switches.

An XML file with figure settings may be provided to configure many aspects of the plot.
This file can also contain one or more expressions to plot (replacing or adding to the
-e/-E switches). Additionally you can configure plot properties by
adding space-separated assignments to the argument list, e.g., Title="my plot title",
Width=10, Height=8, /Font/Family="Times New Roman", or /Axes/Axis[y]/Maximum=10.

The plot is exported to file if a file name is provided (-o/--output).
Otherwise it is shown on screen.

This script uses the GOTM-GUI libraries extensively. To find these libraries,
either the environment variable GOTMDIR must be set, pointing to a
directory that in turn contains the gui.py directory. Alternatively, the
environment variable GOTMGUIDIR may be set, pointing to the GOTM-GUI root
(normally gui.py).""")
    parser.add_option('--version',  action='callback', help='show program\'s version number and exit',callback=printVersion)
    parser.add_option('-s','--source',         type='string',action='callback',callback=newsource,            metavar='[SOURCENAME=]NCPATH', help='Specifies a NetCDF file from which to plot data. SOURCENAME: name of the data source that may be used in expressions (if omitted the default "source#" is used), NCPATH: path to the NetCDF file.')
    parser.add_option('-e','--expression',     type='string',action='callback',callback=newexpression,        metavar='EXPRESSION', help='Data series to plot. This can be the name of a NetCDF variable, or mathematical expression that can contain variables from NetCDF files, as well as several standard functions (e.g., sum, mean, min, max) and named constants (e.g., pi).')
    parser.add_option('-E','--namedexpression',type='string',action='callback',callback=newexpression,nargs=2,metavar='SERIESNAME EXPRESSION', help='Data series to plot. SERIESNAME: name for the data series (currently used in the default plot title and legend), EXPRESSION: variable name or mathematical expression that can contain variables from NetCDF files, as well as several standard functions (e.g., sum, mean, min, max) and named constants (e.g., pi).')
    parser.add_option('-x','--figurexml',      type='string',metavar='PATH',help='Path to XML file with figure settings. Typically this file is created by first running multiplot.py without the -o/--output option, changing figure settings through the graphical user interface, and then saving these to file.')
    parser.add_option('-q','--quiet',  action='store_true', help='suppress output of progress messages')
    parser.add_option('-a','--animate',type='string',metavar='DIMENSION', help='Create an animation by varying the index of this dimension. Stills for each index will be exported to the output path, which should be an existing directory or a Python formatting template for file names accepting an integer (e.g. "./movie/still%05i.png"). If this switch is provided without the -o/--output option, only the first frame of the animation will be shown on screen.')
    parser.add_option('-o','--output', type='string',metavar='PATH', help='Output path. This should be the name of the file to be created, unless --animate/-a is specified - in that case it can either be an existing directory or a formatting template for file names (see -a/--animate option). If this argument is ommitted, a dialog displaying the plot will be shown on-screen.')
    parser.add_option(     '--reassign', type='string',help='Dimension reassignments. This should be a comma-separated list of olddimension=newdimension pairs.')
    parser.add_option('-d','--dpi',    type='int', help='Resolution of exported figure in dots per inch (integer). The default resolution is 96 dpi. Only used in combination with -o/--output.')
    parser.add_option('-i','--id',     type='string', action='append',help='Plot identifier to be shown in corner of the figure.')
    parser.add_option('--debug',       action='store_true', help='Activate debugging (more elaborate error messages).')
    parser.add_option('--nc', type='string', help='NetCDF module to use')
    parser.add_option('--nosqueeze',action='store_true',help='prevent squeezing out of singleton dimensions (with length 1)')
    parser.add_option('--nomask',action='store_true',help='prevent masking of values outside their valid range as defined in NetCDF')
    parser.set_defaults(dpi=96,quiet=False,sources={},animate=None,output=None,expressions=[],lastsource=None,id=[],debug=False,nc=None,reassign=None,nosqueeze=False,nomask=False)

    # Add old deprecated options (not shown in help text)
    parser.add_option('-f','--font',     type='string',help=optparse.SUPPRESS_HELP)
    parser.add_option('-W','--width',    type='float', help=optparse.SUPPRESS_HELP)
    parser.add_option('-H','--height',   type='float', help=optparse.SUPPRESS_HELP)
    parser.add_option('-t','--title',    type='string',help=optparse.SUPPRESS_HELP)

    options,args = parser.parse_args(get_argv()[1:])

    if options.figurexml is None and not options.expressions:
        print('No data to plot specified via -e or -x switch. Exiting.')
        return 2

    # One unnamed argument: output path
    if options.output is None:
        for arg in args:
            if '=' not in arg:
                print('Error: "%s" does not contain = and therefore cannot be a property assignment. If it is meant as the output path (as in previous versions of multiplot), you now need to specify that with the -o/--output switch.' % arg)
                return 2

    # Parse remaining arguments as plot property assignments.
    assignments = {}
    for arg in args:
        if '=' not in arg:
            print('Optional arguments should be PROPERTY=VALUE assignments for plot properties, e.g., Font/Size=12. "%s" is not an assignment.' % arg)
            return 2
        name,val = arg.split('=',1)
        assignments[name] = val
        
    # Parse dimension reassignments (if any)
    dimassignments = {}
    if options.reassign is not None:
        for assign in options.reassign.split(','):
            if '=' not in assign:
                print('Error: "%s" does not contain = and therefore cannot be a dimension reassignment. Dimension reassignments must be specified as OLDDIMENSIONNAME=NEWDIMENSIONNAME.' % assign)
                return 2
            old,new = assign.split('=')
            dimassignments[old] = new
    
    # Translate deprecated options into plot property assignments.
    if options.title  is not None: assignments['/Title'      ]=options.title
    if options.font   is not None: assignments['/Font/Family']=options.font
    if options.width  is not None: assignments['/Width'      ]=str(options.width)
    if options.height is not None: assignments['/Height'     ]=str(options.height)
                
    # Create plotter object
    plt = Plotter(options.sources,options.expressions,assignments=assignments,verbose=not options.quiet,output=options.output,
                  figurexml=options.figurexml,animate=options.animate,dpi=options.dpi,id=options.id,debug=options.debug,
                  nc=options.nc,reassign=dimassignments,autosqueeze=not options.nosqueeze,maskoutsiderange=not options.nomask)
                  
    # Plot
    try:
        plt.plot()
    except Exception as e:
        if options.debug:
            raise
        print(e)
        return 1
        
    # Return success
    return 0

matplotlib = None
xmlplot = None
QtWidgets = None

def importModules(verbose=True):
    global matplotlib,xmlplot

    # If MatPlotLib if already loaded, we are done: return.
    if matplotlib is not None: return

    # Configure MatPlotLib backend and numerical library.
    # (should be done before any modules that use MatPlotLib are loaded)
    import matplotlib
    #matplotlib.rcParams['numerix'] = 'numpy'
    matplotlib.use('Qt5Agg')

    # Add the GOTM-GUI directory to the search path and import the common
    # GOTM-GUI module (needed for command line parsing).
    path = sys.path[:] 
    if not hasattr(sys,'frozen'):
        rootdir = os.path.dirname(os.path.realpath(__file__))
        sys.path.append(os.path.join(rootdir, '../xmlstore'))
        sys.path.append(os.path.join(rootdir, '../xmlplot'))

    # Import remaining GOTM-GUI modules
    try:
        import xmlplot.data,xmlplot.plot,xmlplot.gui_qt4
    except ImportError as e:
        print('Unable to import xmlplot (%s). Please ensure that it is installed.' % e)
        sys.exit(1)

    sys.path = path

class Plotter(object):
    def __init__(self,sources=None,expressions=None,assignments=None,output=None,verbose=True,figurexml=None,dpi=None,animate=None,id=[],debug=False,nc=None,reassign={},autosqueeze=False,maskoutsiderange=True):
        if sources     is None: sources = {}
        if expressions is None: expressions = []
        if assignments is None: assignments = {}

        self.sources = sources
        self.expressions = expressions
        self.assignments = assignments
        self.output = output
        self.reassign = reassign
        self.autosqueeze = autosqueeze
        self.maskoutsiderange = maskoutsiderange

        self.figurexml = figurexml
        self.animate = animate
        self.dpi = dpi
        self.id = id
        self.verbose = verbose
        self.debug = debug

        if isinstance(self.id, (str, u''.__class__)):
            self.id = (self.id,)

        importModules(verbose)

        if nc is not None:
            if xmlplot.data.netcdf.selectednetcdfmodule is None: xmlplot.data.netcdf.chooseNetCDFModule()
            for xmlplot.data.netcdf.selectednetcdfmodule,(m,v) in enumerate(xmlplot.data.netcdf.netcdfmodules):
                if m==nc: break
            else:
                raise Exception('Forced NetCDF module "%s" is not available. Available modules: %s.' % (nc,', '.join([m[0] for m in xmlplot.data.netcdf.netcdfmodules])))

    def addExpression(self,expression,defaultsource=None,label=None):
        if defaultsource is None:
            defaultsource = self.sources.keys()[0]
        else:
            assert defaultsource in self.sources,'Default source "%s" has not been defined.' % defaultsource
        self.expressions.append((label,defaultsource,expression))

    def plot(self,startmessageloop=True):
        gui = self.output is None

        if gui:
            # We have to show figure in GUI.

            # Import PyQt libraries if not doen already.
            global QtWidgets
            if QtWidgets is None:
                from xmlstore.qt_compat import QtWidgets
            
            # Start Qt if needed
            createQApp = QtWidgets.QApplication.startingUp()
            if createQApp:
                app = QtWidgets.QApplication([' '])
            else:
                app = QtWidgets.qApp

            # Create figure dialog
            dialog = xmlplot.gui_qt4.FigureDialog(None,quitonclose=True)
            fig = dialog.getFigure()
        else:
            # We have to export figure to file.
            fig = xmlplot.plot.Figure()

        # Set autosqueeze (of singleton dimensions) behavior
        fig.autosqueeze = self.autosqueeze

        # Enumerate over data sources and add these to the plot.
        # (these will only be used if the -x option specifies an XML file, and
        # that file references one of the supplementary data sources)
        sources = {}
        for sourcename,path in self.sources.items():
            path = os.path.abspath(path)
            oldsourcename,res = sources.get(path,(None,None))
            if res is None:
                if self.verbose:
                    print('Opening "%s".' % path)
                res = xmlplot.data.open(path)
                for old,new in self.reassign.items():
                    if new=='':
                        if old in res.defaultcoordinates: del res.defaultcoordinates[old]
                    else:
                        res.defaultcoordinates[old] = new
                res.maskoutsiderange = self.maskoutsiderange
                sources[path] = (sourcename,res)
            fig.addDataSource(sourcename,res)

        # Plot
        fig.setUpdating(False)

        # Initialize with settings from XML (if a path to an XML file was provided).
        unlinkedseries = []
        if self.figurexml is not None:
            fig.setProperties(self.figurexml)
            for child in fig['Data'].children:
                if child.getSecondaryId()=='': unlinkedseries.append(child)

        # Add figure identifier to plot
        for id in self.id:
            textnode = fig['FigureTexts'].addChild('Text')
            textnode['X'].setValue(.99)
            textnode['Y'].setValue(.01)
            textnode['HorizontalAlignment'].setValue('right')
            textnode['VerticalAlignment'].setValue('bottom')
            textnode.setValue(id)

        # Enumerate over expressions, and add series to the plot.
        for label,sourcename,expression in self.expressions:
            if self.debug:
                series = fig.addVariable(expression,sourcename)
            else:
                try:
                    series = fig.addVariable(expression,sourcename)
                except Exception as e:
                    for name,source in sources.values():
                        if name==sourcename: break
                    raise Exception('%s\nVariables present in NetCDF file: %s.' % (str(e),', '.join(source.getVariableNames())))
            if unlinkedseries:
                # If we have data series properties in the figure settings for a data series without name,
                # then use those for this new series.
                uls = unlinkedseries.pop(0)
                series.copyFrom(uls)
                fig['Data'].removeChildNode(uls)
            series['Label'].setValue(label)
            
        # Process assignments to plot properties.
        for name,val in self.assignments.items():
            node = fig.properties.findNode(name,create=True)
            if node is None:
                raise Exception('"%s" was not found in plot properties.' % name)
            fullname = '/'.join(node.location)
            if len(val)>1 and val[0] in '\'"' and val[0]==val[-1]: val = val[1:-1]
            tp = node.getValueType(returnclass=True)
            try:
                val = tp.fromXmlString(val,{},node.templatenode)
                if self.verbose:
                    print('"%s": assigning value "%s".' % (fullname,val.toPrettyString()))
                node.setValue(val)
            except Exception as e:
                raise Exception('"%s": cannot assign value "%s". %s' % (fullname,val,e))

        # Unless we are making an animation (in that case the still frame is not set yet), update the plot.
        fig.setUpdating(self.animate is None)

        # If we are making an animation, create the animator object that will control the frame and title.
        if self.animate is not None:
            animator = xmlplot.plot.FigureAnimator(fig,self.animate)

        # Show or export the figure
        if gui:
            # If this is meant for an animation, show the first frame.
            if self.animate is not None:
                animator.nextFrame()
                fig.setUpdating(True)

            # Show dialog and wait for it to close
            dialog.show()
            if startmessageloop: ret = app.exec_()
        else:
            if self.animate is None:
                # Export figure to file
                if self.verbose:
                    print('Exporting figure to "%s".' % self.output)
                fig.exportToFile(self.output,dpi=self.dpi)
            else:
                animator.animateAndExport(self.output,dpi=self.dpi,verbose=self.verbose)

        # Close NetCDF files, unless we leave an open dialog on screen.
        if not (gui and not startmessageloop):
            for name,source in sources.values():
                source.unlink()

if __name__ == '__main__':
    ret = main()
    sys.exit(ret)
