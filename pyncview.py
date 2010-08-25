#!/usr/bin/python

# -------------------------------------------------------------------
# Module import and configuration, plus command line parsing.
# -------------------------------------------------------------------

# Import standard (i.e., non GOTM-GUI) modules.
import sys,os,os.path,optparse,math,re,xml.dom.minidom

# Configure MatPlotLib backend and numerical library.
# (should be done before any modules that use MatPlotLib are loaded)
import matplotlib
#matplotlib.rcParams['numerix'] = 'numpy'
matplotlib.use('Qt4Agg')

import numpy

# Import PyQt libraries
from PyQt4 import QtCore,QtGui

# Get GOTM-GUI directory from environment.
if not hasattr(sys,'frozen'):
    if 'GOTMGUIDIR' in os.environ:
        relguipath = os.environ['GOTMGUIDIR']
    elif 'GOTMDIR' in os.environ:
        relguipath = os.path.join(os.environ['GOTMDIR'],'gui.py')
    else:
        print 'Cannot find GOTM-GUI directory. Please set environment variable "GOTMDIR" to the GOTM root (containing gui.py), or "GOTMGUIDIR" to the GOTM-GUI root, before running.'
        sys.exit(1)

    # Add the GOTM-GUI directory to the search path and import the common
    # GOTM-GUI module (needed for command line parsing).
    gotmguiroot = os.path.join(os.path.dirname(os.path.realpath(__file__)),relguipath)
    path = sys.path[:] 
    sys.path.append(gotmguiroot)
else:
    gotmguiroot = '.'
    import mpl_toolkits.basemap
    mpl_toolkits.basemap.basemap_datadir = os.path.join(os.path.dirname(unicode(sys.executable, sys.getfilesystemencoding())),'basemap-data')

# Import remaining GOTM-GUI modules
try:
    import xmlplot.data,xmlplot.plot,xmlplot.gui_qt4,xmlplot.expressions,xmlstore.gui_qt4
except ImportError,e:
    print 'Unable to import GOTM-GUI libraries from "%s": %s. Please ensure that environment variable GOTMDIR or GOTMGUIDIR is set to the correct path.' % (gotmguiroot,e)
    sys.exit(1)
    
def printVersion(option, opt, value, parser):
    print r'$LastChangedRevision$'.strip('$')
    print r'$LastChangedDate$'.strip('$')
    for n,v in xmlplot.common.getVersions(): print '%s: %s' % (n,v)
    sys.exit(0)

# Parse command line options
parser = optparse.OptionParser(description="""This utility may be used to visualize the
contents of a NetCDF file.
This script uses the GOTM-GUI libraries extensively. To find these libraries,
either the environment variable GOTMDIR must be set, pointing to a
directory that in turn contains the gui.py directory. Alternatively, the
environment variable GOTMGUIDIR may be set, pointing to the GOTM-GUI root
(normally gui.py).
""")
parser.add_option('--version', action='callback', callback=printVersion, help='show program\'s version number and exit')
parser.add_option('-q', '--quiet', action='store_true', help='suppress output of progress messages')
parser.add_option('--nc', type='string', help='NetCDF module to use')
parser.set_defaults(quiet=False,nc=None)
options,args = parser.parse_args()

if options.nc is not None:
    if xmlplot.data.selectednetcdfmodule is None: xmlplot.data.chooseNetCDFModule()
    for xmlplot.data.selectednetcdfmodule,(m,v) in enumerate(xmlplot.data.netcdfmodules):
        if m==options.nc: break
    else:
        print 'Forced NetCDF module "%s" is not available. Available modules: %s.' % (options.nc,', '.join([m[0] for m in xmlplot.data.netcdfmodules]))
        sys.exit(2)

# One or more nc files to open may be specified on the command line.
inputpaths = list(args)

# -------------------------------------------------------------------
# Actual code.
# -------------------------------------------------------------------

class LoadException(Exception): pass

class SettingsStore(xmlstore.xmlstore.TypedStore):
    """Maintains persistent settings of PyNcView in an XML file.
    For instance, the paths to recently opened files.
    """

    schemaxml = """<?xml version="1.0"?>
<element name="Settings">
	<element name="Paths">
		<element name="MostRecentlyUsed">
			<element name="Path" type="string" minOccurs="0" maxOccurs="4"/>
		</element>
	</element>
	<element name="WindowPosition">
	    <element name="Maximized" type="bool"/>
	    <element name="X"      type="int"/>
	    <element name="Y"      type="int"/>
	    <element name="Width"  type="int"/>
	    <element name="Height" type="int"/>
	</element>
	<element name="MaskValuesOutsideRange" type="bool"/>
</element>
"""
    defaultvalues = """<?xml version="1.0"?>
<Settings>
    <MaskValuesOutsideRange>True</MaskValuesOutsideRange>
</Settings>
        """

    def __init__(self,schema=None):
        if schema is None: schema = xmlstore.xmlstore.Schema(SettingsStore.schemaxml,sourceisxml=True)
        xmlstore.xmlstore.TypedStore.__init__(self,schema)
        
    def load(self):
        settingspath = self.getSettingsPath()
        if not os.path.isfile(settingspath): return
        try:
            xmlstore.xmlstore.TypedStore.load(self,settingspath)
        except Exception,e:
            raise LoadException('Failed to load settings from "%s".\nReason: %s.\nAll settings will be reset.' % (settingspath,e))
            self.setStore(None)
        defaultstore = xmlstore.xmlstore.TypedStore(self.schema,valueroot=xml.dom.minidom.parseString(SettingsStore.defaultvalues))
        self.setDefaultStore(defaultstore)
        
        self.removeNonExistent('Paths/MostRecentlyUsed','Path')

    @staticmethod    
    def getSettingsPath():
        if sys.platform == 'win32':
            from win32com.shell import shellcon, shell
            appdata = shell.SHGetFolderPath(0, shellcon.CSIDL_APPDATA, 0, 0)
            return os.path.join(appdata,'PyNcView','settings.xml')
        else:
            return os.path.expanduser('~/.pyncview')

    def save(self):
        if not self.changed: return
        settingspath = self.getSettingsPath()
        settingsdir = os.path.dirname(settingspath)
        if not os.path.isdir(settingsdir): os.mkdir(settingsdir)
        xmlstore.xmlstore.TypedStore.save(self,settingspath)
        
    def removeNonExistent(self,parentlocation,nodename):
        """Removes nodes below specified location if their value is not
        a path to an existing file. Used to filter defunct most-recently-used
        files.
        """
        parent = self[parentlocation]
        currentnodes = parent.getLocationMultiple([nodename])
        for i in range(len(currentnodes)-1,-1,-1):
            path = currentnodes[i].getValue()
            if not os.path.isfile(path):
                parent.removeChild(nodename,i)

    def addUniqueValue(self,parentlocation,nodename,nodevalue):
        parent = self[parentlocation]
        currentnodes = parent.getLocationMultiple([nodename])
        if currentnodes:
            maxcount = currentnodes[0].templatenode.getAttribute('maxOccurs')
            for i in range(len(currentnodes)-1,-1,-1):
                if currentnodes[i].getValue()==nodevalue:
                    parent.removeChild(nodename,i)
                    currentnodes.pop(i)
            if maxcount!='unbounded':
                if maxcount=='': maxcount=1
                parent.removeChildren(nodename,first=int(maxcount)-1)
        newnode = parent.addChild(nodename,position=0)
        newnode.setValue(nodevalue)
        
        
class AboutDialog(QtGui.QDialog):
    def __init__(self,parent=None):
        QtGui.QDialog.__init__(self,parent,QtCore.Qt.MSWindowsFixedSizeDialogHint|QtCore.Qt.CustomizeWindowHint|QtCore.Qt.WindowTitleHint)

        layout = QtGui.QVBoxLayout()

        self.label = QtGui.QLabel('PyNcView was developed by <a href="mailto:jorn.bruggeman@xs4all.nl">Jorn Bruggeman</a> from funding by <a href="http://www.bolding-burchard.com">Bolding & Burchard</a>.',self)
        layout.addWidget(self.label)

        versions = []
        versions.append(('Python','%i.%i.%i %s %i' % sys.version_info))
        versions.append(('Qt4',QtCore.qVersion()))
        versions.append(('PyQt4',QtCore.PYQT_VERSION_STR))
        versions.append(('numpy',numpy.__version__))
        versions.append(('matplotlib',matplotlib.__version__))
        try:
            import mpl_toolkits.basemap
            versions.append(('basemap',mpl_toolkits.basemap.__version__))
        except: pass
        
        strversions = ''
        if not hasattr(sys,'frozen'): strversions += 'GOTM-GUI libraries: %s<br><br>' % relguipath

        # Build table with module versions.
        strversions += 'Module versions:'
        strversions += '<table cellspacing="0" cellpadding="0">'
        for v in versions:
            strversions += '<tr><td>%s</td><td>&nbsp;</td><td>%s</td></tr>' % v
        strversions += '</table>'

        # Enumerate available NetCDF modules.
        if xmlplot.data.selectednetcdfmodule is None: xmlplot.data.chooseNetCDFModule()
        strversions += '<br><br>NetCDF modules:<table cellspacing="0" cellpadding="0">'
        for i,(m,v) in enumerate(xmlplot.data.netcdfmodules):
            act = '&nbsp;'
            if i==xmlplot.data.selectednetcdfmodule: act = '(active)'
            strversions += '<tr><td>%s</td><td>&nbsp;</td><td>%s</td><td>&nbsp;</td><td>%s</td></tr>' % (m,v,act)
        strversions += '</table>'

        self.labelVersions = QtGui.QLabel('Diagnostics:',self)
        self.textVersions = QtGui.QTextEdit(strversions,self)
        self.textVersions.setMaximumHeight(120)
        self.textVersions.setReadOnly(True)
        layout.addWidget(self.labelVersions)
        layout.addWidget(self.textVersions)

        self.bnOk = QtGui.QPushButton('OK',self)
        self.connect(self.bnOk, QtCore.SIGNAL('clicked()'), self.accept)
        self.bnOk.setSizePolicy(QtGui.QSizePolicy.Fixed,QtGui.QSizePolicy.Fixed)
        layout.addWidget(self.bnOk,0,QtCore.Qt.AlignRight)

        self.setLayout(layout)

        self.setWindowTitle('About PyNcView')
        self.setMinimumWidth(400)

class BuildExpressionDialog(QtGui.QDialog):
    
    def __init__(self,parent=None,variables=None,stores=None):
        QtGui.QDialog.__init__(self,parent)
        
        if variables is None: variables={}
        if stores    is None: stores={}

        self.variables,self.stores = variables,stores
        
        self.label = QtGui.QLabel('Here you can enter an expression of variables.',self)
        self.label.setWordWrap(True)

        self.labelVariables = QtGui.QLabel('The following variables are available. You can insert a variable into the expression by double-clicking it.',self)
        self.labelVariables.setWordWrap(True)

        self.treeVariables = QtGui.QTreeWidget(self)        
        self.treeVariables.setColumnCount(2)
        self.treeVariables.setHeaderLabels(['variable','description'])
        self.treeVariables.setRootIsDecorated(False)
        self.treeVariables.setSortingEnabled(True)
        
        self.edit = QtGui.QLineEdit(self)

        self.bnOk = QtGui.QPushButton('OK',self)
        self.bnCancel = QtGui.QPushButton('Cancel',self)
        
        self.connect(self.bnOk, QtCore.SIGNAL('clicked()'), self.accept)
        self.connect(self.bnCancel, QtCore.SIGNAL('clicked()'), self.reject)
        self.connect(self.treeVariables, QtCore.SIGNAL('itemDoubleClicked(QTreeWidgetItem *,int)'), self.itemDoubleClicked)

        layout = QtGui.QGridLayout()
        layout.addWidget(self.label,0,0,1,2)
        layout.addWidget(self.labelVariables,1,0,1,2)
        layout.addWidget(self.treeVariables,2,0,1,2)
        layout.addWidget(self.edit,3,0,1,2)
        layout.addWidget(self.bnOk,4,0)
        layout.addWidget(self.bnCancel,4,1)
        self.setLayout(layout)

        self.setWindowTitle('Build expression')
        self.setMinimumWidth(400)
        
        self.setVariables()
        
        self.treeVariables.resizeColumnToContents(0)
        
    def setVariables(self):
        self.treeVariables.clear()
        for name,longname in self.variables.iteritems():
            self.treeVariables.addTopLevelItem(QtGui.QTreeWidgetItem([name,longname]))
        self.treeVariables.sortItems(0,QtCore.Qt.AscendingOrder)
    
    def itemDoubleClicked(self,item,column):
        self.edit.insert(item.text(0))
        self.edit.setFocus()
        
    def showEvent(self,event):
        self.edit.setFocus()

class AnimateToolBar(QtGui.QToolBar):
    def __init__(self,parent,dim,spin):
        QtGui.QToolBar.__init__(self,parent)
        
        self.setIconSize(QtCore.QSize(16,16))

        labelStride = QtGui.QLabel('Stride:',self)
        self.spinStride = QtGui.QSpinBox(self)
        self.spinStride.setRange(1,spin.maximum()-spin.minimum())

        self.actBegin     = self.addAction(xmlplot.gui_qt4.getIcon('player_start.png'),'Move to begin',   self.onBegin)
        self.actPlayPause = self.addAction(xmlplot.gui_qt4.getIcon('player_play.png' ),'Play',            self.onPlayPause)
        self.actEnd       = self.addAction(xmlplot.gui_qt4.getIcon('player_end1.png' ),'Move to end',     self.onEnd)
        self.addWidget(labelStride)
        self.addWidget(self.spinStride)
        self.actRecord    = self.addAction(xmlplot.gui_qt4.getIcon('camera.png'      ),'Record animation',self.onRecord)
        
        self.dim = dim
        self.spin = spin
        self.timer = QtCore.QTimer()
        self.connect(self.timer, QtCore.SIGNAL('timeout()'), self.step)

        self.connect(self.spin, QtCore.SIGNAL('valueChanged(int)'), self.onSpinChanged)
        self.onSpinChanged()
        
        self.group = []
        
    def hideEvent(self,event):
        self.ensureStop()
        QtGui.QToolBar.hideEvent(self,event)
        
    def onBegin(self):
        self.ensureStop()
        self.spin.setValue(self.spin.minimum())
        
    def onEnd(self):
        self.ensureStop()
        self.spin.setValue(self.spin.maximum())
        
    def ensureStop(self):
        if self.timer.isActive(): self.onPlayPause()

    def onPlayPause(self):
        if self.timer.isActive():
            self.timer.stop()
            self.emit(QtCore.SIGNAL('stopAnimation()'))
            self.actPlayPause.setIcon(xmlplot.gui_qt4.getIcon('player_play.png'))
            self.actPlayPause.setText('Play')
        else:
            for tb in self.group: tb.ensureStop()
            self.emit(QtCore.SIGNAL('startAnimation()'))
            self.timer.start()
            self.actPlayPause.setIcon(xmlplot.gui_qt4.getIcon('player_pause.png'))
            self.actPlayPause.setText('Pause')

    def onRecord(self):
        self.emit(QtCore.SIGNAL('onRecord(PyQt_PyObject)'),self.dim)

    def onSpinChanged(self,value=None):
        if value is None: value = self.spin.value()
        self.actBegin.setEnabled(value>self.spin.minimum())
        self.actEnd.setEnabled(value<self.spin.maximum())
        self.actPlayPause.setEnabled(value<self.spin.maximum())

    def step(self):
        self.spin.stepBy(self.spinStride.value())
        value = self.spin.value()
        if value==self.spin.maximum(): self.onPlayPause()

class AnimationController(QtGui.QWidget):
    def __init__(self,parent,dim,spin,callback=None):
        QtGui.QWidget.__init__(self,parent,QtCore.Qt.Tool)
        
        self.toolbar = AnimateToolBar(self,dim,spin)
        self.connect(self.toolbar,QtCore.SIGNAL('onRecord(PyQt_PyObject)'), QtCore.SIGNAL('onRecord(PyQt_PyObject)'))
        self.connect(self.toolbar,QtCore.SIGNAL('startAnimation()'), QtCore.SIGNAL('startAnimation()'))
        self.connect(self.toolbar,QtCore.SIGNAL('stopAnimation()'),  QtCore.SIGNAL('stopAnimation()'))
        
        gridlayout = QtGui.QGridLayout()
        
        self.checkboxFormat = QtGui.QCheckBox('Dynamic title:',self)
        self.checkboxFormat.setChecked(True)
        self.editFormat = QtGui.QLineEdit(self)
        self.connect(self.editFormat,QtCore.SIGNAL('editingFinished()'), self.onFormatChanged)
        self.connect(self.checkboxFormat,QtCore.SIGNAL('clicked(bool)'), self.onFormatChanged)
        gridlayout.addWidget(self.checkboxFormat,0,0)
        gridlayout.addWidget(self.editFormat,0,1,1,2)
        
        lab1 = QtGui.QLabel('Target framerate:',self)
        self.spinInterval = QtGui.QSpinBox(self)
        self.spinInterval.setRange(1,50)
        self.spinInterval.setSingleStep(1)
        self.spinInterval.setValue(24)
        self.onIntervalChanged(self.spinInterval.value())
        self.connect(self.spinInterval,QtCore.SIGNAL('valueChanged(int)'), self.onIntervalChanged)
        lab2 = QtGui.QLabel('fps',self)
        gridlayout.addWidget(lab1,1,0)
        gridlayout.addWidget(self.spinInterval,1,1)
        gridlayout.addWidget(lab2,1,2)

        layout = QtGui.QVBoxLayout()
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(0)
        layout.addWidget(self.toolbar)
        layout.addLayout(gridlayout)
        self.setLayout(layout)
        
        self.dimension = dim
        self.callback = callback

        self.callback(self)
        
    def onIntervalChanged(self,value):
        self.toolbar.timer.setInterval(1000./value)

    def onFormatChanged(self):
        self.callback(self)
        self.editFormat.setEnabled(self.checkboxFormat.isChecked())

    def closeEvent(self,event):
        QtGui.QWidget.closeEvent(self,event)
        self.callback(None)
           
class SliceWidget(QtGui.QWidget):

    def __init__(self,parent=None,variable=None,figure=None,defaultslices=None,dimnames=None,animatecallback=None):
        QtGui.QDialog.__init__(self,parent)
        
        assert variable is not None,'Variable must be specified.'
        
        if defaultslices is None: defaultslices = {}
        if dimnames      is None: dimnames = {}
        
        dims = variable.getDimensions()
        shape = variable.getShape()
        if shape is None: shape = [1e6]*len(dims)
        #ndim = len([1 for l in shape if l>1])
        ndim = len(shape)
        
        # Automatically slice through singleton dimensions.
        if shape is not None:
            for d,l in zip(dims,shape):
                if l==1: defaultslices[d] = 0

        layout = QtGui.QGridLayout()

        self.label = QtGui.QLabel('Dimensions to slice:',self)
        self.label.setWordWrap(True)
        layout.addWidget(self.label,0,0,1,2)
        
        self.dimcontrols = []
        for i,dim in enumerate(dims):
            #if shape[i]==1: continue
            checkbox = QtGui.QCheckBox(dimnames.get(dim,dim),self)
            spin = QtGui.QSpinBox(self)
            spin.setRange(0,shape[i]-1)
            if dim in defaultslices:
                checkbox.setChecked(True)
                spin.setValue(defaultslices[dim])

            layout.addWidget(checkbox,i+1,0)
            layout.addWidget(spin,i+1,1)
            self.connect(checkbox, QtCore.SIGNAL('stateChanged(int)'), self.onCheckChanged)
            self.connect(spin,     QtCore.SIGNAL('valueChanged(int)'), self.onSpinChanged)
            #self.connect(animatetb,QtCore.SIGNAL('onRecord(PyQt_PyObject)'), self.onRecordAnimation)

            # Add animate button unless the dimension has length 1.
            bnAnimate = None
            if shape is not None and shape[i]>1:
                bnAnimate = QtGui.QPushButton(xmlplot.gui_qt4.getIcon('agt_multimedia.png'),QtCore.QString(),self)
                layout.addWidget(bnAnimate,i+1,2)
                self.connect(bnAnimate,QtCore.SIGNAL('clicked()'), self.onAnimate)

            self.dimcontrols.append((dim,checkbox,spin,bnAnimate))
            
        # Combine all animation toolbars in one group, so we can guarantee that only
        # one is playing at a time.
        tbs = [c[3] for c in self.dimcontrols if c[3] is not None]
        for tb in tbs: tb.group = tbs
            
        self.bnChangeAxes = QtGui.QPushButton('Set axes boundaries',self)
        self.menuAxesBounds = QtGui.QMenu(self)
        self.bnChangeAxes.setMenu(self.menuAxesBounds)
        #self.bnAnimate = QtGui.QPushButton('Create animation...',self)
        #self.connect(self.bnAnimate, QtCore.SIGNAL('clicked()'), self.onAnimate)

        self.menuDims = None
        self.windowAnimate = None

        layout.addWidget(self.bnChangeAxes,2+len(dims),0,1,2)
        #layout.addWidget(self.bnAnimate,   3+len(dims),0,1,2)

        layout.setRowStretch(4+len(dims),1)
        
        self.setLayout(layout)

        self.dimnames = dimnames
        self.variable = variable
        self.animatecallback = animatecallback
        
        self.onCheckChanged()

        self.setWindowTitle('Specify slice')
        
        self.figure = figure
        
    def closeEvent(self,event):
        # Make sure that the slice widget behaves as if no slices are specified, while
        # the widget is closing and after it is closed.
        self.dimcontrols = ()
        
        if self.windowAnimate is not None: self.windowAnimate.close()
        
    class ChangeAxesBoundsAction:
        def __init__(self,slicewidget,dim):
            self.slicewidget = slicewidget
            self.dim = dim
        def event(self):
            self.slicewidget.onAxesBounds(self.dim)
            
    def getRange(self,dim):
        for c in self.dimcontrols:
            if c[0]==dim:
                return (c[2].minimum(),c[2].maximum())
            
    def onAnimate(self):
        sender = self.sender()
        for dim,checkbox,spin,bn in self.dimcontrols:
            if bn is not None and bn is sender: break

        if self.windowAnimate is not None: self.windowAnimate.close()
        self.windowAnimate = AnimationController(sender,dim,spin,self.animatecallback)
        self.connect(self.windowAnimate,QtCore.SIGNAL('onRecord(PyQt_PyObject)'), QtCore.SIGNAL('onRecord(PyQt_PyObject)'))
        self.connect(self.windowAnimate,QtCore.SIGNAL('startAnimation()'), QtCore.SIGNAL('startAnimation()'))
        self.connect(self.windowAnimate,QtCore.SIGNAL('stopAnimation()'),  QtCore.SIGNAL('stopAnimation()'))
        pos = sender.parent().mapToGlobal(sender.pos())
        self.windowAnimate.move(pos)
        self.windowAnimate.show()
        self.windowAnimate.setFocus()
        self.windowAnimate.setWindowTitle('Animate %s' % self.dimnames.get(dim,dim))

        # Make sure that the toolbar does not extend beyond the desktop
        # Qt 4.3 does not show the toolbar at all if that happens...
        pos = self.windowAnimate.pos()
        desktopgeometry = QtGui.QApplication.desktop().availableGeometry(sender)
        minx = desktopgeometry.left()
        maxx = desktopgeometry.right()-self.windowAnimate.frameGeometry().width()
        miny = desktopgeometry.top()
        maxy = desktopgeometry.bottom()-self.windowAnimate.frameGeometry().height()
        pos.setX(min(maxx,max(minx,pos.x())))
        pos.setY(min(maxy,max(miny,pos.y())))
        self.windowAnimate.move(pos)

    def onAxesBounds(self,dim=None):
        self.emit(QtCore.SIGNAL('setAxesBounds(PyQt_PyObject)'),dim)

    def onCheckChanged(self,state=None):
        sliceddims = []
        for (dim,checkbox,spin,bnanimate) in self.dimcontrols:
            checked = checkbox.isChecked()
            spin.setEnabled(checked)
            if bnanimate is not None: bnanimate.setVisible(checked)
            if self.windowAnimate is not None and self.windowAnimate.dimension==dim and not checked: 
                self.windowAnimate.close()
                self.windowAnimate = None
            if checked and spin.maximum()>0: sliceddims.append(dim)

        self.bnChangeAxes.setVisible(len(sliceddims)>0)
        self.menuAxesBounds.clear()
        self.actGlobalAxesBounds = self.menuAxesBounds.addAction('based on global value range',self.onAxesBounds)
        if len(sliceddims)>1:
            self.changeboundsactions = []
            if self.menuDims is None:
                self.menuDims = self.menuAxesBounds.addMenu('based on value range across')
            else:
                self.menuDims.clear()
            for dim in sliceddims:
                a = SliceWidget.ChangeAxesBoundsAction(self,dim)
                self.menuDims.addAction(self.dimnames.get(dim,dim),a.event)
                self.changeboundsactions.append(a)
        else:
            self.menuDims = None
        
        self.emit(QtCore.SIGNAL('sliceChanged(bool)'),True)

    def onSpinChanged(self,value):
        self.emit(QtCore.SIGNAL('sliceChanged(bool)'),False)

    def getSlices(self):
        slics = {}
        for (dim,checkbox,spin,bnAnimate) in self.dimcontrols:
            if checkbox.isChecked():
                slics[dim] = int(spin.value())
        return slics

class NcFilePropertiesDialog(QtGui.QDialog):
    def __init__(self,store,parent,flags=QtCore.Qt.Dialog):
        QtGui.QDialog.__init__(self,parent,flags)
        layout = QtGui.QGridLayout()
        irow = 0
        
        nc = store.getcdf()

        # Show dimensions
        lab = QtGui.QLabel('Dimensions:',self)
        layout.addWidget(lab,irow,0,1,3)
        irow += 1
        ncdims = store.getDimensions()
        for dim in ncdims:
            description = []
            
            # Get the length of the dimension, and find out whether it is unlimited.
            length = nc.dimensions[dim]
            isunlimited = length is None
            if not (length is None or isinstance(length,int)):
                # NetCDF4 uses dimension objects.
                isunlimited = length.isunlimited()
                length = len(length)
            elif isunlimited:
                # NetCDF3: locate length of unlimited dimension manually.
                for vn in nc.variables.keys():
                    v = nc.variables[vn]
                    if dim in v.dimensions:
                        curdims = list(v.dimensions)
                        length = v.shape[curdims.index(dim)]
                        break
                        
            # Add info on this dimension
            if isunlimited:
                description.append('length = UNLIMITED (currently %i)' % length)
            else:
                description.append('length = %i' % length)
            if dim in store.reassigneddims:
                description.append('coordinate variable: %s' % store.reassigneddims[dim])
                
            # Add GUI controls
            labk = QtGui.QLabel(dim,self)
            labv = QtGui.QLabel(', '.join(description),self)
            layout.addWidget(labk,irow,0)
            layout.addWidget(labv,irow,1)
            irow += 1
            
        layout.setRowMinimumHeight(irow,10)
        irow += 1

        # Show attributes
        props = xmlplot.data.getNcAttributes(nc)
        if props:
            lab = QtGui.QLabel('Global NetCDF attributes:',self)
            layout.addWidget(lab,irow,0,1,3)
            irow += 1
            for k in sorted(props,key=str.lower):
                v = getattr(nc,k)
                labk = QtGui.QLabel(k,self)
                labv = QtGui.QLabel(str(v),self)
                layout.addWidget(labk,irow,0)
                layout.addWidget(labv,irow,1)
                irow += 1
        else:
            lab = QtGui.QLabel('This NetCDF file has no global attributes.',self)
            layout.addWidget(lab,irow,0,1,3)
            irow += 1
            
        # Add buttons
        bnLayout = QtGui.QHBoxLayout()
        bnOk = QtGui.QPushButton('OK',self)
        self.connect(bnOk, QtCore.SIGNAL('clicked()'), self.accept)
        bnLayout.addStretch(1)
        bnLayout.addWidget(bnOk)
        layout.addLayout(bnLayout,irow+1,0,1,3)
        
        # Set stretching row and column
        layout.setColumnStretch(2,1)
        layout.setRowStretch(irow,1)
        
        self.setLayout(layout)
        self.setWindowTitle('NetCDF properties')
        self.setMinimumWidth(200)

class NcVariablePropertiesDialog(QtGui.QDialog):
    def __init__(self,variable,parent,flags=QtCore.Qt.Dialog):
        QtGui.QDialog.__init__(self,parent,flags)
        layout = QtGui.QGridLayout()
        irow = 0
        
        # Show dimensions
        dims = variable.getDimensions()
        if dims:
            shape = variable.getShape()
            assert shape is not None,'getShape returned None.'
            lab = QtGui.QLabel('NetCDF dimensions:',self)
            layout.addWidget(lab,irow,0,1,3)
            irow += 1
            for dim,length in zip(dims,shape):
                labk = QtGui.QLabel(dim,self)
                labv = QtGui.QLabel('length = %i' % length,self)
                layout.addWidget(labk,irow,0)
                layout.addWidget(labv,irow,1)
                irow += 1
        else:
            lab = QtGui.QLabel('This NetCDF variable has no dimensions.',self)
            layout.addWidget(lab,irow,0,1,3)
            irow += 1

        layout.setRowMinimumHeight(irow,10)
        irow += 1

        lab = QtGui.QLabel('NetCDF data type: %s' % variable.getDataType(),self)
        layout.addWidget(lab,irow,0,1,3)
        irow += 1
            
        layout.setRowMinimumHeight(irow,10)
        irow += 1

        # Show attributes
        props = variable.getProperties()
        if props:
            lab = QtGui.QLabel('NetCDF attributes:',self)
            layout.addWidget(lab,irow,0,1,3)
            irow += 1
            for k in sorted(props.iterkeys(),key=str.lower):
                v = props[k]
                labk = QtGui.QLabel(k,self)
                labv = QtGui.QLabel(str(v),self)
                layout.addWidget(labk,irow,0)
                layout.addWidget(labv,irow,1)
                irow += 1
        else:
            lab = QtGui.QLabel('This NetCDF variable has no attributes.',self)
            layout.addWidget(lab,irow,0,1,3)
            irow += 1
            
        # Add buttons
        bnLayout = QtGui.QHBoxLayout()
        bnOk = QtGui.QPushButton('OK',self)
        self.connect(bnOk, QtCore.SIGNAL('clicked()'), self.accept)
        bnLayout.addStretch(1)
        bnLayout.addWidget(bnOk)
        layout.addLayout(bnLayout,irow+1,0,1,3)
        
        # Set stretching row and column
        layout.setColumnStretch(2,1)
        layout.setRowStretch(irow,1)
        
        self.setLayout(layout)
        self.setWindowTitle('Properties for variable %s' % variable.getName())
        self.setMinimumWidth(200)

class ReassignDialog(QtGui.QDialog):
    """Dialog for reassigning coordinate dimensions of a NetCDF file.
    """

    def __init__(self,store,parent,flags=QtCore.Qt.Dialog):
        QtGui.QDialog.__init__(self,parent,flags)
        layout = QtGui.QGridLayout()
        irow = 0
        nc = store.getcdf()
        
        ncdims = store.getDimensions()
        vars = dict((name,store.getVariable(name)) for name in store.getVariableNames())
        self.dim2combo = {}
        for dim in ncdims:
            labk = QtGui.QLabel(dim,self)
            combo = QtGui.QComboBox(self)
            self.dim2combo[dim] = combo
            added = []
            for vn in sorted(vars.iterkeys(),key=str.lower):
                v = vars[vn]
                if dim in v.getDimensions_raw(reassign=False):
                    added.append(vn)
                    title = v.getLongName()
                    if vn!=title: title += ' (%s)' % vn
                    combo.addItem(title,QtCore.QVariant(vn))
            if dim not in added:
                combo.addItem(dim,QtCore.QVariant(dim))
            layout.addWidget(labk,irow,0)
            layout.addWidget(combo,irow,1)
            irow += 1

        # Add buttons
        bnLayout = QtGui.QHBoxLayout()
        bnLayout.addStretch(1)
        
        bnReset = QtGui.QPushButton('Reset',self)
        self.menuReset = QtGui.QMenu(self)
        self.actResetToDefault = self.menuReset.addAction('Restore default reassignments',self.onResetToDefault)
        self.actResetRemoveAll = self.menuReset.addAction('Undo all reassignments',self.onResetRemoveAll)
        bnReset.setMenu(self.menuReset)
        bnLayout.addWidget(bnReset)
        
        bnOk = QtGui.QPushButton('OK',self)
        self.connect(bnOk, QtCore.SIGNAL('clicked()'), self.accept)
        bnLayout.addWidget(bnOk)
        
        bnCancel = QtGui.QPushButton('Cancel',self)
        self.connect(bnCancel, QtCore.SIGNAL('clicked()'), self.reject)
        bnLayout.addWidget(bnCancel)

        layout.addLayout(bnLayout,irow+1,0,1,3)
        
        # Set stretching row and column
        layout.setColumnStretch(2,1)
        layout.setRowStretch(irow,1)
        
        self.setLayout(layout)
        self.setWindowTitle('Re-assign coordinate dimensions')
        self.setMinimumWidth(300)
        
        self.store = store
        self.selectComboValues()
        
    def selectComboValues(self):
        for dim,combo in self.dim2combo.iteritems():
            options = []
            for i in range(combo.count()):
                options.append(str(combo.itemData(i).toString()))
            dim = self.store.reassigneddims.get(dim,dim)
            try:
                sel = options.index(dim)
            except:
                print dim
                print options
            combo.setCurrentIndex(sel)
        
    def accept(self):
        for dim,combo in self.dim2combo.iteritems():
            var = str(combo.itemData(combo.currentIndex()).toString())
            if var==dim:
                if dim in self.store.reassigneddims: del self.store.reassigneddims[dim]
            else:
                self.store.reassigneddims[dim] = var
        return QtGui.QDialog.accept(self)
        
    def onResetToDefault(self):
        self.store.autoReassignCoordinates()
        self.selectComboValues()

    def onResetRemoveAll(self):
        self.store.reassigneddims = {}
        self.selectComboValues()
                                
class VisualizeDialog(QtGui.QMainWindow):
    """Main PyNCView window.
    """
    
    def __init__(self,parent=None):
        QtGui.QMainWindow.__init__(self,parent,QtCore.Qt.Window | QtCore.Qt.WindowMaximizeButtonHint | QtCore.Qt.WindowMinimizeButtonHint| QtCore.Qt.WindowSystemMenuHint )

        # Load persistent settings
        self.settings = SettingsStore()
        try:
            self.settings.load()
        except LoadException,e:
            print e
            pass

        closebutton = xmlstore.gui_qt4.needCloseButton()

        central = QtGui.QWidget(self)

        self.tree = QtGui.QTreeWidget(central)
        self.tree.header().hide()
        self.tree.setSizePolicy(QtGui.QSizePolicy.Minimum,QtGui.QSizePolicy.Expanding)
        self.tree.setMaximumWidth(250)
        self.tree.setSelectionMode(QtGui.QAbstractItemView.SingleSelection)
        self.tree.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        
        self.connect(self.tree, QtCore.SIGNAL('itemSelectionChanged()'), self.onSelectionChanged)
        self.connect(self.tree, QtCore.SIGNAL('itemDoubleClicked(QTreeWidgetItem *, int)'), self.onVarDoubleClicked)
        self.connect(self.tree, QtCore.SIGNAL('customContextMenuRequested(const QPoint &)'), self.onTreeContextMenuEvent)
        self.bnAddExpression = QtGui.QPushButton('Add custom expression...',central)
        self.connect(self.bnAddExpression, QtCore.SIGNAL('clicked()'), self.editExpression)

        self.figurepanel = xmlplot.gui_qt4.FigurePanel(central)
        self.figurepanel.setMinimumSize(500,350)
        self.figurepanel.figure.autosqueeze = False
        self.store = self.figurepanel.figure.source
        
        self.labelMissing = QtGui.QLabel('',central)
        self.labelMissing.setWordWrap(True)
        self.labelMissing.setVisible(False)

        #self.label = QtGui.QLabel('Here you can view the results of the simulation. Please choose a variable to be plotted from the menu.',self)
        
        addspannedrow = 1
        if closebutton: addspannedrow = 0

        layout = QtGui.QGridLayout()
        #layout.addWidget(self.label,0,0,1,2)
        layout.addWidget(self.tree,1,0,2,1)
        layout.addWidget(self.bnAddExpression,3,0)
        layout.addWidget(self.labelMissing,1,1,1,1,QtCore.Qt.AlignTop)
        layout.addWidget(self.figurepanel,2,1,1+addspannedrow,1)

        if closebutton:
            self.bnClose = QtGui.QPushButton(xmlplot.gui_qt4.getIcon('exit.png'),'Close',central)
            self.connect(self.bnClose, QtCore.SIGNAL('clicked()'), self.close)
            layout.addWidget(self.bnClose,3,2,1,1,QtCore.Qt.AlignRight)

        layout.setColumnStretch(1,1)
        layout.setRowStretch(2,1)
        
        central.setLayout(layout)
        self.setCentralWidget(central)

        self.setWindowTitle('PyNcView')
        
        class SliceDockWidget(QtGui.QDockWidget):
            def __init__(self,title,parent):
                QtGui.QDockWidget.__init__(self,title,parent)
            def hideEvent(self,event):
                self.emit(QtCore.SIGNAL('hidden()'))
                
        self.dockSlice = SliceDockWidget('Slicing',self)
        self.dockSlice.setFeatures(QtGui.QDockWidget.DockWidgetMovable|QtGui.QDockWidget.DockWidgetFloatable|QtGui.QDockWidget.DockWidgetClosable)
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.dockSlice)
        self.dockSlice.setVisible(False)
        self.connect(self.dockSlice, QtCore.SIGNAL('hidden()'), self.onHideSliceDockWidget)
        self.slicetab = None

        self.expressionroot = None
        self.allowupdates = True
        self.defaultslices = {}
        self.animation = None
        self.animatedtitle = False
        
        self.lastpath = ''
        if self.settings['Paths/MostRecentlyUsed'].children: self.lastpath = self.settings['Paths/MostRecentlyUsed'].children[0].getValue()
        self.mruactions = []

        self.createMenu()
        
        self.statusBar()
        
        if self.settings['WindowPosition/Maximized'].getValue():
            self.showMaximized()
        elif self.settings['WindowPosition/Width'].getValue():
            desktoprct = QtGui.QApplication.desktop().availableGeometry()
            w = min(desktoprct.width(), self.settings['WindowPosition/Width'].getValue())
            h = min(desktoprct.height(),self.settings['WindowPosition/Height'].getValue())
            x = max(0,min(desktoprct.width() -w,self.settings['WindowPosition/X'].getValue()))
            y = max(0,min(desktoprct.height()-h,self.settings['WindowPosition/Y'].getValue()))
            if x is not None and y is not None and w is not None and h is not None: self.setGeometry(x,y,w,h)
        
    def onHideSliceDockWidget(self):
        """Called when the slice widget is hidden (e.g., closed by the user.
        """
        self.actSliceWindow.setChecked(False)
        
    def createMenu(self):
        """Create the menu bar.
        """
        bar = self.menuBar()
        self.menuFile = bar.addMenu('File')
        self.menuFile.addAction('Open...',self.onFileOpen)
        self.menuFile.addSeparator()
        #menuFile.addAction('Properties...',self.onFileProperties)
        menuEdit = bar.addMenu('Edit')
        menuEdit.addAction('Options...',self.onEditOptions)
        menuView = bar.addMenu('View')
        self.actSliceWindow = menuView.addAction('Slice window',self.onShowSliceWindow)
        self.actSliceWindow.setCheckable(True)
        #menuTools = bar.addMenu('Tools')
        #menuTools.addAction('Re-assign coordinates...',self.onReassignCoordinates)

        menuHelp = bar.addMenu('Help')
        menuHelp.addAction('About PyNcView...',self.onAbout)
        
        # Update the list of most recently used files in the "File" menu.
        self.updateMRU()
        
    def updateMRU(self):
        """Updates the list of Most Recently Used files at the bottom of the "File" menu.
        """
        for act in self.mruactions: self.menuFile.removeAction(act)
        self.mruactions = []
        
        class MRUTrigger:
            def __init__(self,path,target):
                self.path = path
                self.target = target
            def __call__(self):
                self.target(self.path)
                
        for i,node in enumerate(self.settings['Paths/MostRecentlyUsed'].children):
            path = node.getValue()
            act = self.menuFile.addAction(os.path.basename(path),MRUTrigger(path,self.load))
            #act.setToolTip(path)
            act.setStatusTip(path)
            self.mruactions.append(act)
        
    def onFileOpen(self):
        """Called when the user clicks "open" in the "File" menu.
        """
        filter = 'NetCDF files (*.nc);;All files (*.*)'
        paths = QtGui.QFileDialog.getOpenFileNames(self,'',os.path.dirname(self.lastpath),filter)
        paths = map(unicode,paths)
        if not paths: return
        if len(paths)==1: paths = paths[0]
        self.load(paths)
        
    def onEditOptions(self):
        dlg = QtGui.QDialog(self,QtCore.Qt.Dialog|QtCore.Qt.CustomizeWindowHint|QtCore.Qt.WindowTitleHint|QtCore.Qt.WindowCloseButtonHint)
        dlg.setWindowTitle('Options')
        
        layout = QtGui.QVBoxLayout()
        cb = QtGui.QCheckBox('Treat values outside prescribed valid range as missing data.',dlg)
        cb.setChecked(self.settings['MaskValuesOutsideRange'].getValue(usedefault=True))
        layout.addWidget(cb)
        
        layoutButtons = QtGui.QHBoxLayout()
        bnOk = QtGui.QPushButton('OK',dlg)
        bnCancel = QtGui.QPushButton('Cancel',dlg)
        layoutButtons.addStretch()
        layoutButtons.addWidget(bnOk)
        layoutButtons.addWidget(bnCancel)
        layout.addLayout(layoutButtons)
        
        dlg.setLayout(layout)
        
        self.connect(bnOk,     QtCore.SIGNAL('clicked()'), dlg.accept)
        self.connect(bnCancel, QtCore.SIGNAL('clicked()'), dlg.reject)
        
        if dlg.exec_()!=QtGui.QDialog.Accepted: return
        
        mask = cb.isChecked()
        self.settings['MaskValuesOutsideRange'].setValue(mask)
        
        for store in self.figurepanel.figure.getDataSources().itervalues():
            store.maskoutsiderange = mask
        self.figurepanel.figure.update()
        for dlg in self.figurepanel.detachedfigures: dlg.getFigure().update()

    def onAbout(self):
        """Called when the user clicks "About..." in the "Help" menu.
        """
        dlg = AboutDialog(self)
        dlg.exec_()

    def onShowSliceWindow(self):
        """Called when the user check or unchecks "Slice window" in the "View" menu.
        """
        if self.actSliceWindow.isChecked():
            self.dockSlice.show()
        else:
            self.dockSlice.hide()
        
    def onReassignCoordinates(self,store):
        """Called when the user clicks "Re-assign coordinate dimensions" in the context menu
        of a NetCDF file (root) node.
        """
        dialog = ReassignDialog(store,parent=self)
        if dialog.exec_()==QtGui.QDialog.Accepted:
            self.figurepanel.figure.update()

    def onFileProperties(self,store):
        """Called when the user clicks "Properties" in the context menu
        of a NetCDF file (root) node.
        """
        dialog = NcFilePropertiesDialog(store,parent=self)
        dialog.exec_()
        
    def load(self,paths):
        """Loads a new NetCDF file.
        """
        path = paths
        if isinstance(paths,(list,tuple)): path = paths[0]
        
        path = os.path.abspath(path)
    
        # First check if the file is already open.
        # If so, just select the corresponding root node and return.
        curstorenames = []
        for i in range(self.tree.topLevelItemCount()):
            curnode = self.tree.topLevelItem(i)
            curpath = unicode(curnode.data(0,QtCore.Qt.UserRole+1).toString())
            if path==curpath:
                self.tree.clearSelection()
                curnode.setSelected(True)
                QtGui.QMessageBox.information(self,'Already open','"%s" has already been opened.' % path)
                return
            curstorenames.append(unicode(curnode.data(0,QtCore.Qt.UserRole).toString()))

        # Try to load the NetCDF file.
        try:
            store = xmlplot.data.NetCDFStore.loadUnknownConvention(paths)
        except xmlplot.data.NetCDFError,e:
            QtGui.QMessageBox.critical(self,'Error opening NetCDF file',unicode(e))
            return
            
        # Determine whether to mask values otuside their valid range.
        store.maskoutsiderange = self.settings['MaskValuesOutsideRange'].getValue(usedefault=True)
        
        # Create a name for the data store based on the file name,
        # but make sure it is unique.
        basestorename,ext = os.path.splitext(os.path.basename(path))
        basestorename = re.sub('\W','_',basestorename)
        if basestorename[0].isdigit(): basestorename = '_'+basestorename
        storename,i = basestorename,0
        while storename in curstorenames:
            storename = '%s_%02i' % (basestorename,i)
            i += 1
        
        # Add the store to the data sources for the figure.
        self.figurepanel.figure.addDataSource(storename,store)
        
        # Get all variables in the data store.
        variables = [store.getVariable(name) for name in store.getVariableNames()]
        
        # Build dictionary linking combinations of dimensions to lists of variables.
        dim2var = {}
        for variable in variables:
            dim2var.setdefault(tuple(variable.getDimensions()),[]).append(variable)
            
        # Create root node for this file
        fileroot = QtGui.QTreeWidgetItem([storename],QtGui.QTreeWidgetItem.Type)
        fileroot.setData(0,QtCore.Qt.UserRole,QtCore.QVariant(storename))
        fileroot.setData(0,QtCore.Qt.UserRole+1,QtCore.QVariant(path))
        fileroot.setToolTip(0,path)

        # Function for comparing dimension sets
        def cmpdim(x,y):
            lc = cmp(len(x),len(y))
            if lc!=0: return lc
            return cmp(','.join(x),','.join(y))

        # Add a node for each dimension set and add dependent variables.
        for dims in sorted(dim2var.keys(),cmp=cmpdim):
            vars = dim2var[dims]
            nodename = ','.join(dims)
            if nodename=='': nodename = '[none]'
            curdimroot = QtGui.QTreeWidgetItem(QtCore.QStringList([nodename]),QtGui.QTreeWidgetItem.Type)
            items = []
            for variable in sorted(vars,cmp=lambda x,y: cmp(x.getLongName().lower(),y.getLongName().lower())):
                varname, longname = variable.getName(),variable.getLongName()
                item = QtGui.QTreeWidgetItem(QtCore.QStringList([longname]),QtGui.QTreeWidgetItem.Type)
                item.setData(0,QtCore.Qt.UserRole,QtCore.QVariant('%s[\'%s\']' % (storename,varname)))
                curdimroot.addChild(item)
            if curdimroot.childCount()>0: fileroot.addChild(curdimroot)
            
        # Add the file to the tree
        index = self.tree.topLevelItemCount()
        if self.expressionroot is not None: index -= 1
        self.tree.insertTopLevelItem(index,fileroot)
        fileroot.setExpanded(True)

        # Store the path (to be used for consecutive open file dialogs)
        self.lastpath = path
        
        # Add the newly opened file to the list of Most Recently Used files.
        self.settings.addUniqueValue('Paths/MostRecentlyUsed','Path',path)
        self.updateMRU()
        
    def getSelectedVariable(self):
        """Returns the currently selected variable as an expression (string), that
        can be used to obtain the variable from the figure's data store.
        """
        selected = self.tree.selectedItems()
        if len(selected)==0: return None
        
        if selected[0].parent() is None: return None
        
        # Get name and path of variable about to be shown.
        userdata = selected[0].data(0,QtCore.Qt.UserRole)
        if not userdata.isValid(): return None
        return str(userdata.toString())
        
    def onSliceChanged(self,dimschanged):
        """Called when the slice specification changes in the slice widget.
        """
        self.redraw(preserveproperties=True,preserveaxesbounds=not dimschanged)

    def onTreeContextMenuEvent(self,point):
        """Called when the user right-clicks a node (file or variable) in the tree.
        """
        # Get the node that was clicked
        index = self.tree.indexAt(point)
        
        # Get the internal expression (as opposed to the pretty name)
        userdata = index.data(QtCore.Qt.UserRole)
        
        # If there is not internal expression, it is not variable or file (but a container only).
        # Return without showing the context menu.
        if not userdata.isValid(): return
        
        # Get the selected variable
        varname = str(userdata.toString())
        item = self.store[varname]

        # Build and show the context menu
        menu = QtGui.QMenu(self)
        actReassign,actClose,actProperties = None,None,None
        if isinstance(item,(xmlplot.data.NetCDFStore,xmlplot.data.NetCDFStore.NetCDFVariable)):
            actProperties = menu.addAction('Properties...')
        if isinstance(item,xmlplot.common.VariableStore):
            actReassign = menu.addAction('Reassign coordinates...')
            actClose    = menu.addAction('Close')
        if menu.isEmpty(): return
        actChosen = menu.exec_(self.tree.mapToGlobal(point))
        if actChosen is None: return
        
        # Interpret and execute the action chosen in the menu.
        if actChosen is actProperties:
            if isinstance(item,xmlplot.common.Variable):
                dialog = NcVariablePropertiesDialog(item,parent=self,flags=QtCore.Qt.CustomizeWindowHint|QtCore.Qt.Dialog|QtCore.Qt.WindowTitleHint)
            else:
                dialog = NcFilePropertiesDialog(item,parent=self,flags=QtCore.Qt.CustomizeWindowHint|QtCore.Qt.Dialog|QtCore.Qt.WindowTitleHint)
            dialog.exec_()
        elif actChosen is actReassign:
            self.onReassignCoordinates(item)
        elif actChosen is actClose:
            self.tree.takeTopLevelItem(index.row())
            self.figurepanel.figure.clearVariables()
            item = self.figurepanel.figure.removeDataSource(varname)
            item.unlink()
            self.redraw()
            
    def addSliceSpec(self,varname,var,ignore=None,slices=None):
        """Appends a slice specification to the variable name, based on the
        selection in the slice widget.
        """
        if slices is None: slices = self.slicetab.getSlices()
        if not slices: return varname
        if ignore is not None:
            for d in ignore: del slices[d]
        if isinstance(var,xmlplot.expressions.VariableExpression):
            # This is an expression that natively supports slicing:
            # let the object itself handle it.
            slicedvar = var[tuple([slices.get(dim,slice(None)) for dim in var.getDimensions()])]
            return slicedvar.buildExpression()
        else:
            # This is a variable that does not natively support slicing:
            # append a slice specification to the variable name.
            slictexts = ','.join(map(str,[slices.get(dim,':') for dim in var.getDimensions()]))
            return '%s[%s]' % (varname,slictexts)
        
    def redraw(self,preserveproperties=True,preserveaxesbounds=True):
        """Redraws the currently selected variable.
        """
        varname = self.getSelectedVariable()
        if varname is None: return

        # Get unsliced variable
        var = self.store.getExpression(varname)
        varshape = var.getShape()
        slcs = self.slicetab.getSlices()
        nsliced = len(slcs)
        if varshape is not None:
            ndim = len(varshape) - nsliced
        else:
            ndim = 1
        if ndim not in (1,2):
            if ndim>2:
                # More than 2 dimensions
                self.labelMissing.setText('This variable has %i dimensions, but only 1 or 2 dimensions can be used in plots. You will have to select at least %i additional slice dimensions in the right-hand panel.' % (ndim,ndim-2))
            else:
                # Zero dimensions: scalar
                scalarvar = self.store.getExpression(self.addSliceSpec(varname,var))
                varslice = scalarvar.getSlice(())
                if not isinstance(varslice,(list,tuple)): varslice = (varslice,)
                suffix = scalarvar.getUnit()
                if suffix:
                    suffix = ' %s' % suffix
                else:
                    suffix = ''
                dat = []
                for s in varslice:
                    if isinstance(s,xmlplot.common.Variable.Slice): s = s.data
                    dat.append('%s%s' % (s,suffix))
                self.labelMissing.setText('This variable is a scalar with value %s. It cannot be shown: only variables with 1 or 2 dimensions can be plotted.' % (', '.join(dat),))
            showslicer = ndim>2 or nsliced>0
            self.dockSlice.setVisible(showslicer)
            self.actSliceWindow.setChecked(showslicer)
            self.labelMissing.setVisible(True)
            self.figurepanel.setVisible(False)
            return

        self.labelMissing.setVisible(False)
        self.figurepanel.setVisible(True)
        self.dockSlice.setVisible(True)
        self.actSliceWindow.setChecked(True)

        varname = self.addSliceSpec(varname,var)
        #self.defaultslices = slics

        # Show wait cursor
        QtGui.QApplication.setOverrideCursor(QtGui.QCursor(QtCore.Qt.WaitCursor))

        # Disable figure updating while we make changes.
        oldupdating = self.figurepanel.figure.setUpdating(False)
        
        try:
            varname = self.store.normalizeExpression(varname)
            if preserveproperties:
                oldseries = self.figurepanel.figure['Data/Series']
                if oldseries is None or varname!=oldseries.getSecondaryId():
                    newseries = self.figurepanel.figure.addVariable(varname,replace=False)
                    if oldseries is not None:
                        newseries.copyFrom(oldseries)
                        self.figurepanel.figure['Data'].removeChildNode(oldseries)
                if not preserveaxesbounds:
                    for axisnode in self.figurepanel.figure['Axes'].children:
                        axisnode['Minimum'].clearValue()
                        axisnode['Maximum'].clearValue()
                        axisnode['MinimumTime'].clearValue()
                        axisnode['MaximumTime'].clearValue()
            else:
                self.figurepanel.plot(varname)

            if self.animation and self.animation.checkboxFormat.isChecked():
                self.animatedtitle = True
                self.figurepanel.figure['Title'].setValue(self.getDynamicTitle(var,slcs))

            # Re-enable figure updating (this will force a redraw because things changed)
            self.figurepanel.figure.setUpdating(oldupdating)
        finally:
            # Restore original cursor
            QtGui.QApplication.restoreOverrideCursor()

    def getDynamicTitle(self,var,slcs=None):
        """Returns the dynamically generated title based on the current slice in an animation.
        """
        dim = self.animation.dimension
        if slcs is None: slcs = self.slicetab.getSlices()
        if isinstance(var,xmlplot.expressions.VariableExpression):
            store = var.variables[0].store
        else:
            store = var.store
        coordvariable = store.getVariable(dim)
        if coordvariable is not None:
            coorddims = list(coordvariable.getDimensions())
            assert dim in coorddims, 'Coordinate variable %s does not use its own dimension (dimensions: %s).' % (dim,', '.join(coorddims))
            coordslice = [slice(None)]*len(coorddims)
            for icd,cd in enumerate(coorddims):
                if cd in slcs: coordslice[icd] = slcs[cd]
            meanval = coordvariable.getSlice(coordslice,dataonly=True).mean()
            
            # Convert the coordinate value to a string
            fmt = str(self.animation.editFormat.text())
            try:
                if var.getDimensionInfo(dim).get('datatype','float')=='datetime':
                    return xmlplot.common.num2date(meanval).strftime(fmt)
                else:
                    return fmt % meanval
            except:
                raise
        
    def setAxesBounds(self,dim=None):        
        varname = self.getSelectedVariable()
        if varname is None: return

        # Show wait cursor and progress dialog
        QtGui.QApplication.setOverrideCursor(QtGui.QCursor(QtCore.Qt.WaitCursor))
        
        progdialog = QtGui.QProgressDialog('Examining data range...',QtCore.QString(),0,100,self,QtCore.Qt.Dialog|QtCore.Qt.WindowTitleHint)
        progdialog.setWindowModality(QtCore.Qt.WindowModal)
        progdialog.setWindowTitle('Please wait')

        try:
            # Choose dimensions to keep fixed.
            slics = self.slicetab.getSlices()
            if dim is None:
                curslices = {}
            else:
                curslices = dict(slics)
                del curslices[dim]
                        
            # Get the variable name and variable without any slices applied.
            # This will serve as the base name/variable to which we apply slices.
            basevarname = self.store.normalizeExpression(varname)
            basevar = self.store.getExpression(basevarname)
            
            # Get the variable name and variable with the start slice applied.
            # The variable will have the number of dimensions of the slabs that will be taken.
            varname = self.addSliceSpec(basevarname,basevar,slices=curslices)
            var = self.store.getExpression(varname)
            slabdims = var.getDimensions()
            dim2length = dict(zip(slabdims,var.getShape()))

            if dim is None:
                # All dimensions that were set to a single index now need to be iterated over.
                todoslices = slics.keys()
            else:
                # Only the selected dimension needs to be iterated over.
                todoslices = [dim]

            def iterdim(curslices,todoslices,progweight=1.,cumprog=0.):
                if todoslices:
                    # We have to iterate over at least one dimension more.
                    curdim = todoslices[0]
                    length = dim2length[curdim]
                    vmin,vmax = [None]*(len(slabdims)+1),[None]*(len(slabdims)+1)
                    newcurslices = dict(curslices)
                    for i in range(length):
                        #newcurslices[curdim] = '%i:%i' % (i,i+1)
                        newcurslices[curdim] = slice(i,i+1)
                        curmin,curmax = iterdim(newcurslices,todoslices[1:],progweight=progweight/length,cumprog=cumprog)
                        for i in range(len(curmin)):
                            if curmin[i] is not None and (vmin[i] is None or vmin[i]>curmin[i]): vmin[i] = curmin[i]
                            if curmax[i] is not None and (vmax[i] is None or vmax[i]<curmax[i]): vmax[i] = curmax[i]
                        cumprog += (1./length)*progweight
                        progdialog.setValue(100*cumprog)
                    return vmin,vmax
                else:
                    # No iteration needed: just obtain the data using the current slice, and
                    # read minimum and maximum values.
                    curvarname = self.addSliceSpec(basevarname,basevar,slices=curslices)
                    curvar = self.store.getExpression(curvarname)
                    curvardata = curvar.getSlice([slice(None)]*len(slabdims))
                    if isinstance(curvardata,(list,tuple)): curvardata = curvardata[0]
                    vmin,vmax = [],[]
                    for idim in range(len(slabdims)):
                        vmin.append(curvardata.coords_stag[idim].min())
                        vmax.append(curvardata.coords_stag[idim].max())
                    datamin,datamax = None,None
                    if not (hasattr(curvardata.data,'_mask') and curvardata.data._mask.all()):
                        datamin,datamax = curvardata.data.min(),curvardata.data.max()
                    vmin.append(datamin)
                    vmax.append(datamax)
                    return vmin,vmax

            # Find minimum and maximum or coordinates and values over selected dimensions.
            vmin,vmax = iterdim(curslices,todoslices)
            
            # Show complete progress
            progdialog.setValue(100)
            
            # Get the name of the data dimension as used by the current plot.
            # (this is based on the originally configured slice)
            plottedvarname = self.addSliceSpec(basevarname,basevar,slices=slics)
            plottedvarname = self.store.normalizeExpression(plottedvarname)

            # Register that the last min/max value apply to the data dimension.
            minmaxdims = list(slabdims) + [plottedvarname]
            
            oldupdating = self.figurepanel.figure.setUpdating(False)
            ismap = self.figurepanel.figure['Map'].getValue(usedefault=True)
            for axisnode in self.figurepanel.figure['Axes'].children:
                # If we are dealing with a map, the x and y coordinates will change according to the selected
                # projection. Therefore, the x and y bounds in the data are useless - skip these axes.
                if axisnode.getSecondaryId() in 'xy' and ismap: continue
                
                vamin,vamax = None,None
                axisdims = axisnode['Dimensions'].getValue(usedefault=True)
                for axisdim in axisdims.split(';'):
                    if axisdim in minmaxdims:
                        iadim = minmaxdims.index(axisdim)
                        curmin,curmax = vmin[iadim],vmax[iadim]
                        if vamin is None or vamin>curmin: vamin=curmin
                        if vamax is None or vamax<curmax: vamax=curmax
                #print '%s (%s): %s - %s' % (axisnode.getSecondaryId(),axisdims,vamin,vamax)
                if axisnode['Minimum'].getValue(usedefault=True)>axisnode['Maximum'].getValue(usedefault=True): vamin,vamax = vamax,vamin
                axisnode['Minimum'].setValue(vamin)
                axisnode['Maximum'].setValue(vamax)
            self.figurepanel.figure.setUpdating(oldupdating)
                
        finally:
            progdialog.close()
            
            # Restore original cursor
            QtGui.QApplication.restoreOverrideCursor()
            
    def onRecordAnimation(self,dim):
        # Get the string specifying the currently selected variable (without slices applied!)
        varname = self.getSelectedVariable()
        if varname is None: return

        # Get unsliced variable, and its shape.
        var = self.store.getExpression(varname)
        varshape = var.getShape()

        # Check the number of slice dimensions
        slics = self.slicetab.getSlices()
        nsliced = len(slics)
        #nfree = len([1 for l in varshape if l>1]) - nsliced
        nfree = len(varshape) - nsliced
        if nsliced==0:
            QtGui.QMessageBox.critical(self,'No slice dimension selected','Before creating an animation you must first select one or more dimensions you want to take slices from. The index of one of these will be varied to build the animation.')
            return
        elif nfree>2:
            QtGui.QMessageBox.critical(self,'Insufficient slice dimensions selected','Before creating an animation you must first select at least %i more dimensions you want to take slices from. For the animation, only 1 or 2 free (non-sliced) dimensions should remain.' % (nfree-2))
            return
        elif nfree<1:
            QtGui.QMessageBox.critical(self,'Too many slice dimensions selected','Before creating an animation you must first deselect at least %i slice dimensions. For the animation, 1 or 2 free (non-sliced) dimensions should remain.' % (1-nfree))
            return
                
        # Get the directory to export PNG images to.
        targetdir = unicode(QtGui.QFileDialog.getExistingDirectory(self,'Select directory for still images'))
        if targetdir=='': return

        # Show wait cursor
        QtGui.QApplication.setOverrideCursor(QtGui.QCursor(QtCore.Qt.WaitCursor))

        try:
            # Get the slice selection, and the range across we will vary for the animation.
            imin,imax = self.slicetab.getRange(dim)

            sourcefigure = self.figurepanel.figure

            # Create figure
            fig = xmlplot.plot.Figure(defaultfont=sourcefigure.defaultproperties['Font/Family'].getValue())
            fig.copyFrom(sourcefigure)
            fig['Width'].setValue(sourcefigure['Width'].getValue(usedefault=True))
            fig['Height'].setValue(sourcefigure['Height'].getValue(usedefault=True))

            # Create progress dialog
            dlgProgress = QtGui.QProgressDialog('Please wait while stills are generated.','Cancel',imin,imax,self,QtCore.Qt.Dialog|QtCore.Qt.WindowTitleHint)
            dlgProgress.setWindowModality(QtCore.Qt.WindowModal)
            dlgProgress.setWindowTitle('Please wait...')
            
            try:
                oldseries = fig['Data/Series']
                
                # Create template for filename, ensuring the right number of zeros
                # is prefixed to each frame number.
                nametemplate = '%%0%ii.png' % (1+math.floor(math.log10(imax)))

                # Create stills
                for i in range(imin,imax+1):
                    if dlgProgress.wasCanceled(): break
                    
                    slics[dim] = i
                    curvarname = self.addSliceSpec(varname,var,slices=slics)
                    curvarname = fig.source.normalizeExpression(curvarname)
                        
                    if oldseries.getSecondaryId()!=curvarname:
                        oldupdating = fig.setUpdating(False)
                        newseries = fig.addVariable(curvarname)
                        newseries.copyFrom(oldseries)
                        fig['Data'].removeChildNode(oldseries)
                        if self.animation.checkboxFormat.isChecked():
                            fig['Title'].setValue(self.getDynamicTitle(var,slics))
                        fig.setUpdating(oldupdating)
                        oldseries = newseries
                        
                    path = os.path.join(targetdir,nametemplate % i)
                    fig.exportToFile(path,dpi=self.logicalDpiX())
                    
                    dlgProgress.setValue(i)
            finally:
                # Make sure progress dialog is closed
                dlgProgress.close()
        finally:
            # Restore original cursor
            QtGui.QApplication.restoreOverrideCursor()

    def onSelectionChanged(self):
        if not self.allowupdates: return
        
        varname = self.getSelectedVariable()
        if varname is None:
            self.labelMissing.setVisible(False)
            self.figurepanel.setVisible(False)
            self.dockSlice.setVisible(False)
            self.actSliceWindow.setChecked(False)
            return
        
        # Get the number of dimensions used by the variable
        var = self.store.getExpression(varname)

        # Note: closing the slice tab can trigger figure updates. Make sure these are not processed until we are done.
        oldupdating = self.figurepanel.figure.setUpdating(False)

        # Add slicing tab
        if self.slicetab is not None: self.slicetab.close()
        self.slicetab = SliceWidget(None,var,figure=self.figurepanel.figure,defaultslices=self.defaultslices,dimnames=self.store.getVariableLongNames(),animatecallback=self.onAnimation)
        self.connect(self.slicetab, QtCore.SIGNAL('sliceChanged(bool)'), self.onSliceChanged)
        self.connect(self.slicetab, QtCore.SIGNAL('setAxesBounds(PyQt_PyObject)'), self.setAxesBounds)
        self.connect(self.slicetab,QtCore.SIGNAL('onRecord(PyQt_PyObject)'), self.onRecordAnimation)
        self.connect(self.slicetab,QtCore.SIGNAL('startAnimation()'), self.figurepanel.startAnimation)
        self.connect(self.slicetab,QtCore.SIGNAL('stopAnimation()'), self.figurepanel.stopAnimation)
        self.dockSlice.setWidget(self.slicetab)
                    
        self.redraw(preserveproperties=False)

        self.figurepanel.figure.setUpdating(oldupdating)
        
    def onVarDoubleClicked(self,item,column):
        if item.parent()!=self.expressionroot: return
        self.editExpression(item)
        
    def onAnimation(self,dlg):
        if self.animation is None and dlg is not None:
            varname = self.getSelectedVariable()
            var = self.store.getExpression(varname)
            diminfo = var.getDimensionInfo(dlg.dimension)
            if diminfo.get('datatype','float')=='datetime':
                dlg.editFormat.setText(diminfo['label']+': %Y-%m-%d %H:%M:%S')
            else:
                dlg.editFormat.setText(diminfo['label']+': %.4f')

        self.animation = dlg
        oldupdating = self.figurepanel.figure.setUpdating(False)
        if self.animatedtitle and (dlg is None or not dlg.checkboxFormat.isChecked()):
            self.figurepanel.figure['Title'].setValue(None)
            self.animatedtitle = False
        self.onSliceChanged(False)
        self.figurepanel.figure.setUpdating(oldupdating)
        
    def editExpression(self,item=None):
        dlg = BuildExpressionDialog(self,variables=self.store.getVariableLongNames(alllevels=True))
        
        if item is not None:
            expression = str(item.data(0,QtCore.Qt.UserRole).toString())
            dlg.edit.setText(expression)
        
        valid = False
        while not valid:
            if dlg.exec_()!=QtGui.QDialog.Accepted: return
            expression = str(dlg.edit.text())
            try:
                var = self.store[expression]
                valid = True
            except Exception,e:
                QtGui.QMessageBox.critical(self,'Unable to parse expression',str(e))
                dlg.edit.selectAll()
   
        if item is None:
            if self.expressionroot is None:
                self.expressionroot = QtGui.QTreeWidgetItem(['expressions'],QtGui.QTreeWidgetItem.Type)
                self.tree.addTopLevelItem(self.expressionroot)
            item = QtGui.QTreeWidgetItem(QtGui.QTreeWidgetItem.Type)
            self.expressionroot.addChild(item)
        item.setData(0,QtCore.Qt.DisplayRole,QtCore.QVariant(expression))
        item.setData(0,QtCore.Qt.UserRole,QtCore.QVariant(expression))
        
        if not item.isSelected():
            self.allowupdates = False
            self.tree.clearSelection()
            item.setSelected(True)
            self.allowupdates = True
        self.onSelectionChanged()
            
        par = item.parent()
        while par is not None:
            par.setExpanded(True)
            par = par.parent()

    def closeEvent(self,event):
        rct = self.geometry()
        x,y,w,h = rct.left(),rct.top(),rct.width(),rct.height()
        self.settings['WindowPosition/Maximized'].setValue(self.isMaximized())
        self.settings['WindowPosition/X'].setValue(x)
        self.settings['WindowPosition/Y'].setValue(y)
        self.settings['WindowPosition/Width'].setValue(w)
        self.settings['WindowPosition/Height'].setValue(h)
        
if __name__=='__main__':
    # Start Qt
    createQApp = QtGui.QApplication.startingUp()
    if createQApp:
        app = QtGui.QApplication([' '])
    else:
        app = QtGui.qApp

    dialog = VisualizeDialog()
    for path in inputpaths:
        try:
            dialog.load(path)
        except Exception,e:
            print 'Error: %s' % e

    # Show dialog and wait for it to close
    dialog.show()
    ret = app.exec_()
    dialog.settings.save()
