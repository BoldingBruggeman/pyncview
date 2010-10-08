#!/usr/bin/python

# Import standard (i.e., non GOTM-GUI) modules.
import sys,os,re
import numpy

xmlplot = None
xmlstore = None

def importModules(verbose=True):
    global xmlstore,xmlplot

    # Get GOTM-GUI directory from environment.
    if 'GOTMGUIDIR' in os.environ:
        relguipath = os.environ['GOTMGUIDIR']
    elif 'GOTMDIR' in os.environ:
        relguipath = os.path.join(os.environ['GOTMDIR'],'gui.py')
    else:
        sys.stderr.write('Cannot find GOTM-GUI directory. Please set environment variable "GOTMDIR" to the GOTM root (containing gui.py), or "GOTMGUIDIR" to the GOTM-GUI root, before running.\n')
        sys.exit(1)
    if verbose:
        print 'Getting GOTM-GUI libraries from "%s".' % relguipath

    # Add the GOTM-GUI directory to the search path.
    gotmguiroot = os.path.join(os.path.dirname(os.path.realpath(__file__)),relguipath)
    path = sys.path[:] 
    sys.path.append(gotmguiroot)

    # Import GOTM-GUI modules
    try:
        import xmlstore.util
        import xmlplot.data,xmlplot.plot,xmlplot.gui_qt4
    except ImportError,e:
        sys.stderr.write('Unable to import GOTM-GUI libraries (%s). Please ensure that environment variable GOTMDIR or GOTMGUIDIR is set.\n' % e)
        sys.exit(1)
        
    sys.path = path
    
def main():
    import optparse

    parser = optparse.OptionParser(usage='%prog PATH1 EXPRESSION1 PATH2 EXPRESSION2',
    description="""This script calculates several statistics that describe the difference
between two one-dimensional NetCDF data series. The first data series will be used as reference,
and the second data series will be interpolated to the first one.

For all statistics, the first series is interpreted as the reference ("truth"), and
the second series as a corresponding model prediction. Specifically, the bias is
positive when the second series is on average higher than the first, and the
coefficient of determinination is calculated as 1-SSQ(series1-series2)/SSQ(series1-mean1).

NB The coefficient of determination only equals the explained variance for a very
limited class of models (notably, linear regression models)!

This script uses the GOTM-GUI libraries extensively. To find these libraries,
either the environment variable GOTMDIR must be set, pointing to a
directory that in turn contains the gui.py directory. Alternatively, the
environment variable GOTMGUIDIR may be set, pointing to the GOTM-GUI root
(normally gui.py).""")
    parser.set_defaults(quiet=False,autofix=True,dump=None,order=1)
    parser.add_option('-q','--quiet', action='store_true', help='suppress output of progress messages')
    parser.add_option('-d','--dump',  type='string', metavar='PATH',help='If provided, this is the path to which the difference between the data series is saved in NetCDF format.')
    parser.add_option('-o','--order',  type='int', metavar='ORDER',help='Use spline-based interpolation of the specified order.')

    options,args = parser.parse_args()

    if len(args)!=4:
        sys.stderr.write("""Four arguments must be provided:
- the path to the first [reference] NetCDF file
- the expression to plot from the first NetCDF file
- the path to the second NetCDF file
- the expression to plot from the second NetCDF file
""")
        return 2

    # Get the NetCDF paths and expressions to compare
    path1,exp1,path2,exp2 = args

    return compseries(path1,exp1,path2,exp2,quiet=options.quiet,dump=options.dump,order=options.order)

def compseries(path1,exp1,path2,exp2,dump=None,quiet=False,order=1):
    """Compares two data series that reside in NetCDF files. Series are expressions
    that can contain NetCDF variables as well as constants and many NumPy
    functions.
        
    The first series is used as reference, and the second series is
    interpolated to the first. Points  of the first series that lay outside
    the coordinate range of the second series are discarded - thus,
    extrapolation of the second series is not needed. The order of
    interpolation can be controlled by the "order" argument, which
    defaults to 1 (linear interpolation).

    Optionally, the data series used in the comparison can be dumped to
    NetCDF, along with the difference between the series. This is done by
    specifying the path to dump to via the "dump" argument.
"""
    # Import GOTM-GUI modules
    importModules(verbose=not quiet)

    # Open NetCDF files.
    path1,path2 = map(os.path.abspath,(path1,path2))
    store1 = xmlplot.data.NetCDFStore.loadUnknownConvention(path1)
    if path2==path1:
        store2 = store1
    else:
        store2 = xmlplot.data.NetCDFStore.loadUnknownConvention(path2)

    # Retrieve the expressions to compare.
    var1 = store1[exp1]
    var2 = store2[exp2]
    
    # Get unit for the difference between series.
    unit1 = var1.getUnit()
    unit2 = var2.getUnit()
    if unit1==unit2:
        unit = unit1
    else:
        unit = unit2+'-'+unit1
    
    # Retrieve the actual data (as Slice objects)
    data1 = var1.getSlice()
    data2 = var2.getSlice()
    
    # If the retrieved objects are sequences, quietly use the first element in the sequence.
    if isinstance(data1,(list,tuple)): data1 = data1[0]
    if isinstance(data2,(list,tuple)): data2 = data2[0]
    
    # Check if the data are at least one-dimensional.
    if data1.ndim==0:
        sys.stderr.write('Data series 1 is a scalar without coordinates, and therefore cannot be used for comparisons.')
        return 1
    if data2.ndim==0:
        sys.stderr.write('Data series 2 is a scalar without coordinates, and therefore cannot be used for comparisons.')
        return 1

    # Squeeze out singleton dimensions (with length 1)
    if data1.ndim>1: data1 = data1.squeeze()
    if data2.ndim>1: data2 = data2.squeeze()
            
    # Check if we now have 2 one-dimensional data series.
    if len(data1.dimensions)!=1:
        sys.stderr.write('First data series has %i dimensions, but only 1-dimensional data series are currently supported.\n' % len(data1.dimensions))
        return 1
    if len(data2.dimensions)!=1:
        sys.stderr.write('Second data series has %i dimensions, but only 1-dimensional data series are currently supported.\n' % len(data2.dimensions))
        return 1

    # Remove masked data
    data1 = data1.compressed()
    data2 = data2.compressed()

    # Make sure that coordinates of the first (reference) data series are completed contained
    # within the coordinates of the second series, because we allow interpolation of the second
    # series only, not extrapolation.
    c1,c2 = data1.coords[0],data2.coords[0]
    istart,istop = 0,len(c1)
    if c2[ 0]>c1[ 0]:
        istart = c1.searchsorted(c2[0])
        if istart==len(c1):
            sys.stderr.write('FATAL ERROR: first coordinate of second series (%s) lies beyond the end of the first [reference] series (%s).\n' % (c2[0],c1[-1]))
            return 1
        sys.stderr.write('WARNING: first coordinate of second data series (%s) lies beyond the start of the first [reference] series (%s). The first %i points of the first series will be ignored.\n' % (c2[0],c1[0],istart))
    if c2[-1]<c1[-1]:
        istop = c1.searchsorted(c2[-1])
        if istop==0:
            sys.stderr.write('FATAL ERROR: last coordinate of second series (%s) lies before the beginning of the first [reference] series (%s).\n' % (c2[-1],c1[0]))
            return 1
        sys.stderr.write('WARNING: last coordinate of second data series (%s) lies before the end of the first [reference] series (%s). The last %i points of the first series will be ignored.\n' % (c2[-1],c1[-1],len(c1)-istop))
    if istart!=0 or istop!=len(c1):
        # Select a subset of the reference (observed) coordinates that is contained within the set of model coordinates.
        data1 = data1[istart:istop]
        c1 = data1.coords[0]
        
    # Get the name of the coordinate dimension
    cdimname = data2.dimensions[0]
    
    # Linearly interpolate the second series to the coordinates of the first, and
    # take out the raw data from the slice (i.e., discard coordinates, dimension names, etc.)
    ipargs = {cdimname:c1}
    if order!=1:        
        import scipy.interpolate
        tck2 = scipy.interpolate.splrep(c2,data2.data,k=order,s=0.)
        data2 = scipy.interpolate.splev(c1, tck2)
    else:
        data2 = data2.interp(**ipargs).data
    data1 = data1.data
    
    # Show information on input data if in Verbose mode.
    if not quiet:
        print 'Using %i data points.' % len(data1)
        print 'Range for series 1: %s - %s' % (c1[0],c1[-1])
        print 'Range for series 2: %s - %s' % (c2[0],c2[-1])

    # Calculate statistics
    mean1 = data1.mean()
    mean2 = data2.mean()
    sd1 = data1.std()
    sd2 = data2.std()
    delta = data2-data1
    R2 = 1.-((data1-data2)**2).sum()/((data1-mean1)**2).sum()
    
    # Print statistics
    print ('Bias = %s %s' % (mean2-mean1,unit)).encode('utf-8')
    print ('RMSE = %s %s' % (numpy.sqrt((delta**2).mean()),unit)).encode('utf-8')
    print ('MAE = %s %s' % (numpy.abs(delta).mean(),unit)).encode('utf-8')
    print 'Correlation = %s' % (((data1-mean1)*(data2-mean2)).mean()/sd1/sd2)
    print 'Coefficient of determination (R2) = %s' % R2
    
    # Dump the difference between the data series to NetCDF if desired.
    if dump is not None:
        nc = xmlplot.data.NetCDFStore(dump,'w')
        nc.createDimension(cdimname,len(c1))
        var = nc.addVariable(cdimname,(cdimname,))
        cvar = store1[cdimname]
        if cvar is not None:
            for k,v in cvar.getProperties().iteritems():
                var.setProperty(k,v)
        var.setData(c1)
        var = nc.addVariable('difference',(cdimname,))
        var.setData(delta)
        var.setProperty('long_name','%s - %s' % (var1.getLongName(),var2.getLongName()))
        var.setProperty('units',str(unit))

        var = nc.addVariable('source1',(cdimname,))
        var.setData(data1)
        var.setProperty('long_name',str(var1.getLongName()))
        var.setProperty('units',str(var1.getUnit()))
        var.setProperty('source',str(path1))
        var.setProperty('expression',str(var1.getName()))

        var = nc.addVariable('source2',(cdimname,))
        var.setData(data2)
        var.setProperty('long_name',str(var2.getLongName()))
        var.setProperty('units',str(var2.getUnit()))
        var.setProperty('source',str(path2))
        var.setProperty('expression',str(var2.getName()))

        nc.unlink()

if __name__=='__main__':
    ret = main()
    sys.exit(ret)
