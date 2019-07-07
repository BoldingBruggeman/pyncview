#!/usr/bin/python

# -------------------------------------------------------------------
# Module import and configuration, plus command line parsing.
# -------------------------------------------------------------------

from __future__ import print_function

# Import standard (i.e., non GOTM-GUI) modules.
import sys,os,optparse,math,numpy

# Parse command line options
parser = optparse.OptionParser(usage='%prog OPTIONS [OUTPUTPATH]',
description="""This script calculates several descriptive statistics for
an expression containing one or more NetCDF variables.

Note: at the moment all data are loaded into memory before statistics are
calculated. This will not work for expressions referencing very large
amounts of data. It does however allow for calculation of percentiles.

This script uses the GOTM-GUI libraries extensively. To find these libraries,
either the environment variable GOTMDIR must be set, pointing to a
directory that in turn contains the gui.py directory. Alternatively, the
environment variable GOTMGUIDIR may be set, pointing to the GOTM-GUI root
(normally gui.py).""")
parser.set_defaults(quiet=False,percentiles=False,maxslab=1000000,sources=[])
parser.add_option('-s', dest='sources', action='append',metavar='[SOURCENAME=]NCPATH', help='path to a NetCDF file from which variables will be used.')
parser.add_option('-q', '--quiet', action='store_true', help='suppress output of progress messages')
parser.add_option('-p', '--percentiles', action='store_true', help='whether to list percentiles in addition to mean, sd, min, max')
parser.add_option('--maxslab', type='int', help='maximum number of data point to keep in memory (default = 1000000)')
options,args = parser.parse_args()

assert len(options.sources)>0,'You must specify at least one NetCDF file with the -s switch.'
assert len(args)>0,'You must specify an expression to calculate statistics for.'
expression = args.pop(0)

# Get GOTM-GUI directory from environment.
if 'GOTMGUIDIR' in os.environ:
    relguipath = os.environ['GOTMGUIDIR']
elif 'GOTMDIR' in os.environ:
    relguipath = os.environ['GOTMDIR']+'/gui.py'
else:
    print('Cannot find GOTM-GUI directory. Please set environment variable "GOTMDIR" to the GOTM root (containing gui.py), or "GOTMGUIDIR" to the GOTM-GUI root, before running.')
    sys.exit(1)
if not options.quiet:
    print('Getting GOTM-GUI libraries from "%s".' % relguipath)

# Add the GOTM-GUI directory to the search path and import the common
# GOTM-GUI module (needed for command line parsing).
gotmguiroot = os.path.join(os.path.dirname(os.path.realpath(__file__)),relguipath)
path = sys.path[:] 
sys.path.append(gotmguiroot)

# Import GOTM-GUI modules
try:
    import xmlplot.common,xmlplot.data,xmlplot.expressions
except ImportError,e:
    print('Unable to import GOTM-GUI libraries (%s). Please ensure that environment variable GOTMDIR or GOTMGUIDIR is set.' % e)
    sys.exit(1)

# -------------------------------------------------------------------
# Actual code.
# -------------------------------------------------------------------

store = xmlplot.common.VariableStore()

# Open the data files.
firstsource = None
sourcecount = 0
for info in options.sources:
    info = info.split('=',1)
    path = info[-1]
    if len(info)==1:
        sourcename = 'source%i' % sourcecount
    else:
        sourcename = info[0]
    path = os.path.abspath(path)
    if not options.quiet:
        print('Opening "%s".' % path)
    res = xmlplot.data.NetCDFStore.loadUnknownConvention(path)
    store.addChild(res,sourcename)
    if firstsource is None: firstsource = sourcename
    sourcecount += 1

# Resolve the expression
try:
    var = store.getExpression(expression,firstsource)
except Exception as e:
    print(e)
    sys.exit(1)

if isinstance(var,xmlplot.expressions.VariableExpression):
    expressions = [e.getText(type=0,addparentheses=False) for e in var.root]
else:
    expressions = (expression,)

# Get the data
dims = var.getDimensions()
shape = var.getShape()

# Get unit specifier
unit = var.getUnit()
if unit is None:
    unit = ''
elif unit!='':
    unit = ' '+unit

if shape is not None and numpy.prod(shape)==1:
    value = var.getSlice((Ellipsis,),dataonly=True)
    if isinstance(value,(tuple,list)): value = value[0]
    if isinstance(value,numpy.ndarray): value = value.flatten()[0]
    print('Data consists of a scalar with value %g%s' % (value,unit))
    sys.exit(0)

# If we need percentiles, we need all data in memory
# Set the shape to None to prevent iterating over dimensions.
if options.percentiles: shape = None

n,sumx,sumx2,min,max = 0,0.,0.,None,None

def readdata(slic,idim=0):
    if shape is not None and idim<len(shape)-1 and numpy.prod(shape[idim:])>options.maxslab:
        #if not options.quiet:
        #    print('Iterating over dimension %s to prevent extreme memory consumption.' % dims[idim])
        for i in range(shape[idim]):
            newslic = list(slic)
            newslic[idim] = i
            readdata(newslic,idim+1)
    else:
        data = var.getSlice(slic,dataonly=True)
        if isinstance(data,(tuple,list)): data = data[0]
        if hasattr(data,'_mask'):
            data = data.compressed()
        else:
            data = data.ravel()
        if not data.size: return data
        data = numpy.asarray(data,dtype=numpy.float64)

        global n,sumx,sumx2,min,max
        sumx += data.sum()
        sumx2 += (data*data).sum()
        n += data.size
        curmin,curmax = data.min(), data.max()
        if min is None or min>curmin: min = curmin
        if max is None or max<curmax: max = curmax

        return data

data = readdata([slice(None)]*len(dims))

enc = 'utf-8'
if sys.stdout.isatty(): enc = sys.stdout.encoding
def printfn(s):
    print(s.encode(enc))

if n==0:
    print('No data available (or all are masked).')
    sys.exit(0)

def getPercentile(perc):
    index = float(n)*perc
    il = math.floor(index)
    lweight = (float(il+1)/n-perc)/(1./n)
    return data[il]*lweight + data[il+1]*(1.-lweight)

mean = sumx/n
std = math.sqrt(sumx2/n-mean*mean)

# Print statistics
printfn('Mean = %g%s' % (mean,unit))
printfn( 'S.d. = %g%s' % (std,unit))
printfn( 'Minimum = %g%s' % (min,unit))
if options.percentiles:
    data = numpy.sort(data)
    printfn( '2.5th percentile = %g%s' % (getPercentile(.025),unit))
    printfn( '25th percentile = %g%s' % (getPercentile(.25),unit))
    printfn( 'Median = %g%s' % (getPercentile(.5),unit))
    printfn( '75th percentile = %g%s' % (getPercentile(.75),unit))
    printfn( '97.5th percentile = %g%s' % (getPercentile(.975),unit))
printfn( 'Maximum = %g%s' % (max,unit))
