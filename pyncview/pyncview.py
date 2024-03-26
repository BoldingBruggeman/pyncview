#!/usr/bin/env python

# -------------------------------------------------------------------
# Module import and configuration, plus command line parsing.
# -------------------------------------------------------------------

from __future__ import print_function

# Import standard (i.e., non GOTM-GUI) modules.
import sys,os,os.path,argparse,math,re,xml.dom.minidom,warnings

# Ignore DeprecationWarnings, which are interesting for developers only.
warnings.simplefilter('ignore', DeprecationWarning)

# Import third-party Python modules.
import numpy

# Get GOTM-GUI directory from environment.
if not hasattr(sys,'frozen'):
    # Auto-discover xmlstore and xmlplot in bbpy directory structure
    rootdir = os.path.dirname(os.path.realpath(__file__))
    path = sys.path[:]
    if os.path.isdir(os.path.join(rootdir, '../../xmlstore/xmlstore')):
        print('Detected that we are running from BBpy source. Using local xmlstore/xmlplot.')
        sys.path.insert(0, os.path.join(rootdir, '../../xmlstore'))
        sys.path.insert(0, os.path.join(rootdir, '../../xmlplot'))
else:
    rootdir = os.path.dirname(unicode(sys.executable, sys.getfilesystemencoding()))
    gotmguiroot = '.'

# Import PyQt libraries
try:
    from xmlstore.qt_compat import QtCore,QtGui,QtWidgets,mpl_qt4_backend,qt4_backend,qt4_backend_version
except ImportError as e:
    print('Unable to import xmlstore (https://pypi.python.org/pypi/xmlstore) Try "pip install xmlstore". Error: %s' % e)
    sys.exit(1)

# Configure MatPlotLib backend..
# (should be done before any modules that use MatPlotLib are loaded)
import matplotlib
#matplotlib.rcParams['backend.qt4'] = mpl_qt4_backend
matplotlib.use('agg')

# Override basemap data directory if running from binary distribution.
if hasattr(sys,'frozen'):
    import mpl_toolkits.basemap
    mpl_toolkits.basemap.basemap_datadir = os.path.join(rootdir,'basemap-data')

# Import remaining GOTM-GUI modules
try:
    import xmlplot.data,xmlplot.plot,xmlplot.gui_qt4,xmlplot.expressions,xmlstore.gui_qt4,xmlplot.errortrap
except ImportError as e:
    print('Unable to import xmlplot (https://pypi.python.org/pypi/xmlplot) Try "pip install xmlplot". Error: %s' % e)
    sys.exit(1)
   
def printVersion():
    for n,v in xmlplot.common.getVersions():
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
        except Exception as e:
            raise LoadException('Failed to load settings from "%s".\nReason: %s.\nAll settings will be reset.' % (settingspath,e))
            self.setStore(None)
        defaultstore = xmlstore.xmlstore.TypedStore(self.schema,valueroot=xml.dom.minidom.parseString(SettingsStore.defaultvalues))
        self.setDefaultStore(defaultstore)

        self.removeNonExistent('Paths/MostRecentlyUsed','Path')

    @staticmethod    
    def getSettingsPath():
        if sys.platform == 'win32':
            import ctypes.wintypes
            CSIDL_APPDATA = 26
            SHGFP_TYPE_CURRENT = 0
            buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
            ctypes.windll.shell32.SHGetFolderPathW(None, CSIDL_APPDATA, None, SHGFP_TYPE_CURRENT, buf)
            return os.path.join(buf.value, 'PyNcView', 'settings.xml')
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

class AboutDialog(QtWidgets.QDialog):
    def __init__(self,parent=None):
        QtWidgets.QDialog.__init__(self,parent,QtCore.Qt.MSWindowsFixedSizeDialogHint|QtCore.Qt.CustomizeWindowHint|QtCore.Qt.WindowTitleHint)

        layout = QtWidgets.QVBoxLayout()

        self.label = QtWidgets.QLabel('PyNcView is developed by <a href="http://www.bolding-bruggeman.com/">Bolding & Bruggeman ApS</a>, formerly Bolding & Burchard.',self)
        self.label.setOpenExternalLinks(True)
        layout.addWidget(self.label)

        versions = []
        versions.append(('Python','%i.%i.%i %s %i' % tuple(sys.version_info)))
        versions.append(('Qt',QtCore.qVersion()))
        versions.append((qt4_backend,qt4_backend_version))
        versions.append(('numpy',numpy.__version__))
        versions.append(('matplotlib',matplotlib.__version__))
        try:
            import mpl_toolkits.basemap
            versions.append(('basemap',mpl_toolkits.basemap.__version__))
        except: pass

        strversions = ''

        # Build table with module versions.
        strversions += 'Module versions:'
        strversions += '<table cellspacing="0" cellpadding="0">'
        for v in versions:
            strversions += '<tr><td>%s</td><td>&nbsp;</td><td>%s</td></tr>' % v
        strversions += '</table>'

        # Enumerate available NetCDF modules.
        if xmlplot.data.netcdf.selectednetcdfmodule is None: xmlplot.data.netcdf.chooseNetCDFModule()
        strversions += '<br><br>NetCDF modules:<table cellspacing="0" cellpadding="0">'
        for i,(m,v) in enumerate(xmlplot.data.netcdf.netcdfmodules):
            act = '&nbsp;'
            if i==xmlplot.data.netcdf.selectednetcdfmodule: act = '(active)'
            strversions += '<tr><td>%s</td><td>&nbsp;</td><td>%s</td><td>&nbsp;</td><td>%s</td></tr>' % (m,v,act)
        strversions += '</table>'

        self.labelVersions = QtWidgets.QLabel('Diagnostics:',self)
        self.textVersions = QtWidgets.QTextEdit(strversions,self)
        self.textVersions.setMaximumHeight(120)
        self.textVersions.setReadOnly(True)
        layout.addWidget(self.labelVersions)
        layout.addWidget(self.textVersions)

        self.bnOk = QtWidgets.QPushButton('OK',self)
        self.bnOk.clicked.connect(self.accept)
        self.bnOk.setSizePolicy(QtWidgets.QSizePolicy.Fixed,QtWidgets.QSizePolicy.Fixed)
        layout.addWidget(self.bnOk,0,QtCore.Qt.AlignRight)

        self.setLayout(layout)

        self.setWindowTitle('About PyNcView')
        self.setMinimumWidth(400)

class BuildExpressionDialog(QtWidgets.QDialog):

    def __init__(self,parent=None,variables=None,stores=None):
        QtWidgets.QDialog.__init__(self,parent)

        if variables is None: variables={}
        if stores    is None: stores={}

        self.variables,self.stores = variables,stores

        self.label = QtWidgets.QLabel('Here you can enter an expression of variables.',self)
        self.label.setWordWrap(True)

        self.labelVariables = QtWidgets.QLabel('The following variables are available. You can insert a variable into the expression by double-clicking it.',self)
        self.labelVariables.setWordWrap(True)

        self.treeVariables = QtWidgets.QTreeWidget(self)        
        self.treeVariables.setColumnCount(2)
        self.treeVariables.setHeaderLabels(['variable','description'])
        self.treeVariables.setRootIsDecorated(False)
        self.treeVariables.setSortingEnabled(True)

        self.edit = QtWidgets.QLineEdit(self)

        self.bnOk = QtWidgets.QPushButton('OK',self)
        self.bnCancel = QtWidgets.QPushButton('Cancel',self)

        self.bnOk.clicked.connect(self.accept)
        self.bnCancel.clicked.connect(self.reject)
        self.treeVariables.itemDoubleClicked.connect(self.itemDoubleClicked)

        layout = QtWidgets.QGridLayout()
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
        for name, longname in self.variables.items():
            self.treeVariables.addTopLevelItem(QtWidgets.QTreeWidgetItem([name,longname]))
        self.treeVariables.sortItems(0,QtCore.Qt.AscendingOrder)

    def itemDoubleClicked(self,item,column):
        self.edit.insert(item.text(0))
        self.edit.setFocus()

    def showEvent(self,event):
        self.edit.setFocus()

class AnimateToolBar(QtWidgets.QToolBar):
    startAnimation = QtCore.Signal()
    stopAnimation = QtCore.Signal()
    onRecord = QtCore.Signal(object)

    def __init__(self,parent,dim,spin):
        QtWidgets.QToolBar.__init__(self,parent)

        self.setIconSize(QtCore.QSize(16,16))

        labelStride = QtWidgets.QLabel('Stride:',self)
        self.spinStride = QtWidgets.QSpinBox(self)
        self.spinStride.setRange(1,spin.maximum()-spin.minimum())

        self.actBegin     = self.addAction(xmlplot.gui_qt4.getIcon('player_start.png'),'Move to begin',   self.onBegin)
        self.actPlayPause = self.addAction(xmlplot.gui_qt4.getIcon('player_play.png' ),'Play',            self.onPlayPause)
        self.actEnd       = self.addAction(xmlplot.gui_qt4.getIcon('player_end1.png' ),'Move to end',     self.onEnd)
        self.addWidget(labelStride)
        self.addWidget(self.spinStride)
        self.actRecord    = self.addAction(xmlplot.gui_qt4.getIcon('camera.png'      ),'Record animation',lambda: self.onRecord.emit(self.dim))

        self.dim = dim
        self.spin = spin
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.step)

        self.spin.valueChanged.connect(self.onSpinChanged)
        self.onSpinChanged()

        self.group = []

    def hideEvent(self,event):
        self.ensureStop()
        QtWidgets.QToolBar.hideEvent(self,event)

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
            self.stopAnimation.emit()
            self.actPlayPause.setIcon(xmlplot.gui_qt4.getIcon('player_play.png'))
            self.actPlayPause.setText('Play')
        else:
            for tb in self.group: tb.ensureStop()
            self.startAnimation.emit()
            self.timer.start()
            self.actPlayPause.setIcon(xmlplot.gui_qt4.getIcon('player_pause.png'))
            self.actPlayPause.setText('Pause')

    def onSpinChanged(self,value=None):
        if value is None: value = self.spin.value()
        self.actBegin.setEnabled(value>self.spin.minimum())
        self.actEnd.setEnabled(value<self.spin.maximum())
        self.actPlayPause.setEnabled(value<self.spin.maximum())

    def step(self):
        self.spin.stepBy(self.spinStride.value())
        value = self.spin.value()
        if value==self.spin.maximum(): self.onPlayPause()

class AnimationController(QtWidgets.QWidget):
    def __init__(self,parent,dim,spin,callback=None):
        QtWidgets.QWidget.__init__(self,parent,QtCore.Qt.Tool)

        self.toolbar = AnimateToolBar(self,dim,spin)
        self.onRecord = self.toolbar.onRecord
        self.startAnimation = self.toolbar.startAnimation
        self.stopAnimation = self.toolbar.stopAnimation

        gridlayout = QtWidgets.QGridLayout()

        self.checkboxFormat = QtWidgets.QCheckBox('Dynamic title:',self)
        self.checkboxFormat.setChecked(True)
        self.editFormat = QtWidgets.QLineEdit(self)
        self.editFormat.editingFinished.connect(self.onFormatChanged)
        self.checkboxFormat.clicked.connect(self.onFormatChanged)
        gridlayout.addWidget(self.checkboxFormat,0,0)
        gridlayout.addWidget(self.editFormat,0,1,1,2)

        lab1 = QtWidgets.QLabel('Target framerate:',self)
        self.spinInterval = QtWidgets.QSpinBox(self)
        self.spinInterval.setRange(1,50)
        self.spinInterval.setSingleStep(1)
        self.spinInterval.setValue(24)
        self.onIntervalChanged(self.spinInterval.value())
        self.spinInterval.valueChanged.connect(self.onIntervalChanged)
        lab2 = QtWidgets.QLabel('fps',self)
        gridlayout.addWidget(lab1,1,0)
        gridlayout.addWidget(self.spinInterval,1,1)
        gridlayout.addWidget(lab2,1,2)

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(0)
        layout.addWidget(self.toolbar)
        layout.addLayout(gridlayout)
        self.setLayout(layout)

        self.dimension = dim
        self.callback = callback

        self.callback(self)

    def onIntervalChanged(self,value):
        self.toolbar.timer.setInterval(int(round(1000./value)))

    def onFormatChanged(self):
        self.callback(self)
        self.editFormat.setEnabled(self.checkboxFormat.isChecked())

    def closeEvent(self,event):
        QtWidgets.QWidget.closeEvent(self,event)
        self.callback(None)
           
class SliceWidget(QtWidgets.QWidget):

    setAxesBounds = QtCore.Signal(object)
    startAnimation = QtCore.Signal()
    stopAnimation = QtCore.Signal()
    onRecord = QtCore.Signal(object)
    sliceChanged = QtCore.Signal(bool)
    makeSymmetric = QtCore.Signal()
    changeColormap = QtCore.Signal(str)

    def __init__(self,parent=None,variable=None,figure=None,defaultslices=None,dimnames=None,animatecallback=None):
        super(SliceWidget,self).__init__(parent)

        self.figure = figure

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

        layout = QtWidgets.QGridLayout()

        self.label = QtWidgets.QLabel('Dimensions to slice:',self)
        self.label.setWordWrap(True)
        layout.addWidget(self.label,0,0,1,2)

        self.dimcontrols = []
        for i,dim in enumerate(dims):
            #if shape[i]==1: continue
            checkbox = QtWidgets.QCheckBox(dimnames.get(dim,dim),self)
            spin = QtWidgets.QSpinBox(self)
            spin.setRange(0,shape[i]-1)
            if dim in defaultslices:
                checkbox.setChecked(True)
                spin.setValue(defaultslices[dim])

            layout.addWidget(checkbox,i+1,0)
            layout.addWidget(spin,i+1,1)
            checkbox.stateChanged.connect(self.onCheckChanged)
            spin.valueChanged.connect(self.onSpinChanged)
            #self.connect(animatetb,QtCore.SIGNAL('onRecord(PyQt_PyObject)'), self.onRecordAnimation)

            # Add animate button unless the dimension has length 1.
            bnAnimate = None
            if shape is not None and shape[i]>1:
                bnAnimate = QtWidgets.QPushButton(xmlplot.gui_qt4.getIcon('agt_multimedia.png'),None,self)
                layout.addWidget(bnAnimate,i+1,2)
                bnAnimate.clicked.connect(self.onAnimate)

            self.dimcontrols.append((dim,checkbox,spin,bnAnimate))

        # Combine all animation toolbars in one group, so we can guarantee that only
        # one is playing at a time.
        tbs = [c[3] for c in self.dimcontrols if c[3] is not None]
        for tb in tbs: tb.group = tbs

        self.bnChangeAxes = QtWidgets.QPushButton('Set axes boundaries',self)
        self.menuAxesBounds = QtWidgets.QMenu(self)
        self.bnChangeAxes.setMenu(self.menuAxesBounds)
        #self.bnAnimate = QtWidgets.QPushButton('Create animation...',self)
        #self.connect(self.bnAnimate, QtCore.SIGNAL('clicked()'), self.onAnimate)

        self.menuDims = None
        self.windowAnimate = None

        layout.addWidget(self.bnChangeAxes,2+len(dims),0,1,2)
        #layout.addWidget(self.bnAnimate,   3+len(dims),0,1,2)

        # Add button for making the colorbar symmetric
        self.bnSymmetric = QtWidgets.QPushButton('Make colorbar symmetric about 0',self)
        self.bnSymmetric.clicked.connect(self.onColorbarSymmetric)
        layout.addWidget(self.bnSymmetric,3+len(dims),0,1,2)

        # Add button with menu for choosing a colormap
        self.bnColormap = QtWidgets.QPushButton('Choose colormap ...',self)
        self.menuColormap = QtWidgets.QMenu(self)
        self.bnColormap.setMenu(self.menuColormap)
        layout.addWidget(self.bnColormap,4+len(dims),0,1,2)
        self.colormapActions = {}
        self.updateColormapMenu()

        layout.setRowStretch(6+len(dims),1)

        self.setLayout(layout)

        self.dimnames = dimnames
        self.variable = variable
        self.animatecallback = animatecallback

        self.onCheckChanged()

        self.setWindowTitle('Specify slice')

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

    class ChangeColormapAction:
        def __init__(self,slicewidget,colormap):
            self.slicewidget = slicewidget
            self.colormap = colormap
        def event(self):
            self.slicewidget.chooseColormap(self.colormap)

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
        self.windowAnimate.onRecord.connect(self.onRecord)
        self.windowAnimate.startAnimation.connect(self.startAnimation)
        self.windowAnimate.stopAnimation.connect(self.stopAnimation)
        pos = sender.parent().mapToGlobal(sender.pos())
        self.windowAnimate.move(pos)
        self.windowAnimate.show()
        self.windowAnimate.setFocus()
        self.windowAnimate.setWindowTitle('Animate %s' % self.dimnames.get(dim,dim))

        # Make sure that the toolbar does not extend beyond the desktop
        # Qt 4.3 does not show the toolbar at all if that happens...
        pos = self.windowAnimate.pos()
        desktopgeometry = QtWidgets.QApplication.desktop().availableGeometry(sender)
        minx = desktopgeometry.left()
        maxx = desktopgeometry.right()-self.windowAnimate.frameGeometry().width()
        miny = desktopgeometry.top()
        maxy = desktopgeometry.bottom()-self.windowAnimate.frameGeometry().height()
        pos.setX(min(maxx,max(minx,pos.x())))
        pos.setY(min(maxy,max(miny,pos.y())))
        self.windowAnimate.move(pos)

    def onAxesBounds(self,dim=None):
        self.setAxesBounds.emit(dim)

    def onColorbarSymmetric(self):
        """Make the colorbar symmetric and choose a diverging colormap."""
        self.makeSymmetric.emit()
        self.chooseColormap('RdBu_r')

    def chooseColormap(self, colormap):
        self.changeColormap.emit(colormap)
        self.updateColormapMenu()

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

        self.sliceChanged.emit(True)

    def onSpinChanged(self,value):
        self.sliceChanged.emit(False)

    def getSlices(self):
        slics = {}
        for (dim,checkbox,spin,bnAnimate) in self.dimcontrols:
            if checkbox.isChecked():
                slics[dim] = int(spin.value())
        return slics

    def updateColormapMenu(self):
        """Add new entries (actions) to the colormap menu."""
        for colormap, description in self.figure.colormapQuickList.items():
            if colormap not in self.colormapActions:
                action = SliceWidget.ChangeColormapAction(self, colormap)
                self.menuColormap.addAction(colormap + ": " + description, action.event)
                # Save action-object for colormap-event, otherwise
                # the object is lost and the event cannot be triggered
                self.colormapActions[colormap] = action

class NcPropertiesDialog(QtWidgets.QDialog):
    def __init__(self,item,parent,flags=QtCore.Qt.Dialog):
        QtWidgets.QDialog.__init__(self,parent,flags)
        layout = QtWidgets.QVBoxLayout()

        def createList(parent,rows,headers):
            list = QtWidgets.QTreeWidget(self)
            list.setUniformRowHeights(True)
            list.setSortingEnabled(True)
            list.sortByColumn(-1,QtCore.Qt.AscendingOrder)
            list.addTopLevelItems([QtWidgets.QTreeWidgetItem(items) for items in rows])
            list.setHeaderLabels(headers)
            header = list.header()
            if hasattr(header, 'setMovable'):
                # Qt4
                header.setMovable(False)
            else:
                # Qt5
                header.setSectionsMovable(False)
            list.setColumnCount(len(headers))
            for i in range(len(headers)): list.resizeColumnToContents(i)
            list.setRootIsDecorated(False)
            list.setMaximumHeight(len(rows)*list.rowHeight(list.indexFromItem(list.topLevelItem(0)))
                                  +list.header().height()
                                  +2*list.frameWidth()
                                  +list.horizontalScrollBar().height())
            return list

        # Show dimensions
        dimnames = item.getDimensions()
        if dimnames:
            lab = QtWidgets.QLabel('Dimensions:',self)
            layout.addWidget(lab)
            hasunlimited = False
            if isinstance(item,xmlplot.common.VariableStore):
                rows = []
                labels = ('name','length','coordinate variable')
                for dimname in dimnames:
                    items = [dimname,'','']

                    # Get the length of the dimension, and find out whether it is unlimited.
                    length,isunlimited = item.getDimensionLength(dimname)

                    # Add info on this dimension
                    hasunlimited |= isunlimited
                    items[1] = str(length)
                    if isunlimited: items[1] += '*'
                    if dimname in item.defaultcoordinates:
                        items[2] = item.defaultcoordinates[dimname]

                    rows.append(items)
            else:
                labels = ('name','length')
                rows = tuple(map(list,zip(dimnames,map(str,item.getShape()))))

            self.listDimensions = createList(self,rows,labels)
            layout.addWidget(self.listDimensions)
            if hasunlimited:
                lab = QtWidgets.QLabel('* This dimension is unlimited. It can grow as required.',self)
                layout.addWidget(lab)

            layout.addSpacing(10)
        elif isinstance(item,xmlplot.common.Variable):
            lab = QtWidgets.QLabel('This variable is a scalar.')
            layout.addWidget(lab)
            layout.addSpacing(10)

        if isinstance(item,xmlplot.common.Variable):
            lab = QtWidgets.QLabel('Data type: %s' % numpy.dtype(item.getDataType()).name,self)
            layout.addWidget(lab)
            layout.addSpacing(10)

        # Show attributes
        props = item.getProperties()
        if props:
            lab = QtWidgets.QLabel('Attributes:',self)
            layout.addWidget(lab)
            keys = sorted(props.keys(),key=lambda x: x.lower())
            self.listProperties = createList(self,[(k,u''.__class__(props[k])) for k in keys],('name','value'))
            layout.addWidget(self.listProperties)
        else:
            if isinstance(item,xmlplot.common.Variable):
                lab = QtWidgets.QLabel('This variable has no attributes.',self)
            else:
                lab = QtWidgets.QLabel('This file has no global attributes.',self)
            layout.addWidget(lab)

        # Add buttons
        bnLayout = QtWidgets.QHBoxLayout()
        bnOk = QtWidgets.QPushButton('OK',self)
        bnOk.clicked.connect(self.accept)
        bnLayout.addStretch(1)
        bnLayout.addWidget(bnOk)
        layout.addLayout(bnLayout)

        self.setLayout(layout)
        if isinstance(item,xmlplot.common.Variable):
            self.setWindowTitle('Properties for variable %s' % item.getName())
        else:
            self.setWindowTitle('File properties')
        self.setMinimumWidth(200)

class ReassignDialog(QtWidgets.QDialog):
    """Dialog for reassigning coordinate dimensions of a NetCDF file.
    """

    def __init__(self,store,parent,flags=QtCore.Qt.Dialog):
        QtWidgets.QDialog.__init__(self,parent,flags)
        layout = QtWidgets.QGridLayout()
        irow = 0
        nc = store.getcdf()

        ncdims = store.getDimensions()
        vars = dict((name,store.getVariable(name)) for name in store.getVariableNames())
        self.dim2combo = {}
        for dim in ncdims:
            labk = QtWidgets.QLabel(dim,self)
            combo = QtWidgets.QComboBox(self)
            self.dim2combo[dim] = combo
            added = []
            for vn in sorted(vars.keys(),key=lambda x: x.lower()):
                v = vars[vn]
                if dim in v.getDimensions():
                    added.append(vn)
                    title = v.getLongName()
                    if vn!=title: title += ' (%s)' % vn
                    combo.addItem(title,vn)
            if dim not in added:
                combo.addItem(dim,dim)
            layout.addWidget(labk,irow,0)
            layout.addWidget(combo,irow,1)
            irow += 1

        # Add buttons
        bnLayout = QtWidgets.QHBoxLayout()
        bnLayout.addStretch(1)

        bnReset = QtWidgets.QPushButton('Reset',self)
        self.menuReset = QtWidgets.QMenu(self)
        self.actResetToDefault = self.menuReset.addAction('Restore default reassignments',self.onResetToDefault)
        self.actResetRemoveAll = self.menuReset.addAction('Undo all reassignments',self.onResetRemoveAll)
        bnReset.setMenu(self.menuReset)
        bnLayout.addWidget(bnReset)

        bnOk = QtWidgets.QPushButton('OK',self)
        bnOk.clicked.connect(self.accept)
        bnLayout.addWidget(bnOk)

        bnCancel = QtWidgets.QPushButton('Cancel',self)
        bnCancel.clicked.connect(self.reject)
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
        for dim, combo in self.dim2combo.items():
            options = []
            for i in range(combo.count()):
                options.append(combo.itemData(i))
            dim = self.store.defaultcoordinates.get(dim,dim)
            try:
                sel = options.index(dim)
            except:
                print(dim)
                print(options)
            combo.setCurrentIndex(sel)

    def accept(self):
        for dim,combo in self.dim2combo.items():
            var = combo.itemData(combo.currentIndex())
            if var==dim:
                if dim in self.store.defaultcoordinates: del self.store.defaultcoordinates[dim]
            else:
                self.store.defaultcoordinates[dim] = var
        return QtWidgets.QDialog.accept(self)

    def onResetToDefault(self):
        self.store.autoReassignCoordinates()
        self.selectComboValues()

    def onResetRemoveAll(self):
        self.store.defaultcoordinates = {}
        self.selectComboValues()

class NcTreeWidget(QtWidgets.QTreeWidget):
    fileDropped = QtCore.Signal(str)
    def __init__(self,parent):
        QtWidgets.QTreeWidget.__init__(self,parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self,event):
        if event.mimeData().hasUrls():
            event.setDropAction(QtCore.Qt.CopyAction)
            event.accept()
        else:
            QtWidgets.QTreeWidget.dragEnterEvent(self,event)

    def dragMoveEvent(self,event):
        if event.mimeData().hasUrls():
            event.setDropAction(QtCore.Qt.CopyAction)
            event.accept()
        else:
            QtWidgets.QTreeWidget.dragMoveEvent(self,event)

    def dropEvent(self,event):
        data = event.mimeData()
        if event.mimeData().hasUrls():
            for url in data.urls():
                self.fileDropped.emit(u''.__class__(url.toLocalFile()))
            event.accept()
        else:
            QtWidgets.QTreeWidget.dropEvent(self,event)

class VisualizeDialog(QtWidgets.QMainWindow):
    """Main PyNCView window.
    """

    def __init__(self,parent=None):
        QtWidgets.QMainWindow.__init__(self,parent,QtCore.Qt.Window | QtCore.Qt.WindowMaximizeButtonHint | QtCore.Qt.WindowCloseButtonHint | QtCore.Qt.WindowMinimizeButtonHint| QtCore.Qt.WindowSystemMenuHint )

        # Load persistent settings
        self.settings = SettingsStore()
        try:
            self.settings.load()
        except LoadException as e:
            print(e)
            pass

        central = QtWidgets.QWidget(self)

        self.figurepanel = xmlplot.gui_qt4.FigurePanel(central)
        self.figurepanel.setMinimumSize(500,350)
        self.figurepanel.figure.autosqueeze = False
        self.store = self.figurepanel.figure.source

        # Create a collection of often used colormaps (will be extended as the user chooses other colormaps)
        self.figurepanel.figure.colormapQuickList = {
            'jet': 'rainbow colormap (PyNcView default)',
            'viridis': 'sequential colormap (matplotlib default)',
            'RdBu_r': 'diverging colormap',
            'binary': 'grayscale colormap',
        }

        self.labelMissing = QtWidgets.QLabel('',central)
        self.labelMissing.setWordWrap(True)
        self.labelMissing.setVisible(False)

        layout = QtWidgets.QVBoxLayout(central)
        layout.addWidget(self.labelMissing,alignment=QtCore.Qt.AlignTop)
        layout.addWidget(self.figurepanel)

        self.setCentralWidget(central)

        browserwidget = QtWidgets.QWidget(self)

        self.browsertoolbar = QtWidgets.QToolBar(browserwidget)

        self.tree = NcTreeWidget(browserwidget)
        self.tree.header().hide()
        self.tree.setSizePolicy(QtWidgets.QSizePolicy.Minimum,QtWidgets.QSizePolicy.Expanding)
        self.tree.setMinimumWidth(75)
        self.tree.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.tree.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)

        self.tree.itemSelectionChanged.connect(self.onSelectionChanged)
        self.tree.fileDropped.connect(self.load)
        self.tree.itemDoubleClicked.connect(self.onVarDoubleClicked)
        self.tree.customContextMenuRequested.connect(self.onTreeContextMenuEvent)
        #self.bnAddExpression = QtWidgets.QPushButton('Add custom expression...',browserwidget)
        #self.connect(self.bnAddExpression, QtCore.SIGNAL('clicked()'), self.editExpression)

        browserlayout = QtWidgets.QVBoxLayout(browserwidget)
        browserlayout.setSpacing(0)
        browserlayout.addWidget(self.browsertoolbar)
        browserlayout.addWidget(self.tree)
        #browserlayout.addWidget(self.bnAddExpression)

        browserlayout.setContentsMargins(0,0,0,0)

        self.setWindowTitle('PyNcView')

        class SliceDockWidget(QtWidgets.QDockWidget):
            hidden = QtCore.Signal()
            def __init__(self,title,parent):
                QtWidgets.QDockWidget.__init__(self,title,parent)
            def hideEvent(self,event):
                self.hidden.emit()

        self.dockSlice = SliceDockWidget('Slicing',self)
        self.dockSlice.setFeatures(QtWidgets.QDockWidget.DockWidgetMovable|QtWidgets.QDockWidget.DockWidgetFloatable|QtWidgets.QDockWidget.DockWidgetClosable)
        self.dockSlice.setAllowedAreas(QtCore.Qt.LeftDockWidgetArea|QtCore.Qt.RightDockWidgetArea)
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.dockSlice)
        self.dockSlice.setVisible(False)
        self.dockSlice.hidden.connect(self.onHideSliceDockWidget)
        self.slicetab = None

        self.dockFileBrowser = QtWidgets.QDockWidget('Workspace explorer',self)
        self.dockFileBrowser.setFeatures(QtWidgets.QDockWidget.DockWidgetMovable|QtWidgets.QDockWidget.DockWidgetFloatable)
        self.dockFileBrowser.setAllowedAreas(QtCore.Qt.LeftDockWidgetArea|QtCore.Qt.RightDockWidgetArea)
        self.addDockWidget(QtCore.Qt.LeftDockWidgetArea, self.dockFileBrowser)
        self.dockFileBrowser.setWidget(browserwidget)

        self.expressionroot = None
        self.allowupdates = True
        self.defaultslices = {}
        self.animation = None
        self.animatedtitle = False

        self.lastpath = ''
        if self.settings['Paths/MostRecentlyUsed'].children: self.lastpath = self.settings['Paths/MostRecentlyUsed'].children[0].getValue()

        self.createMenu()

        self.bnopen = QtWidgets.QToolButton(self.browsertoolbar)
        act = QtWidgets.QAction(xmlplot.gui_qt4.getIcon('fileopen.png'),'Open',self.browsertoolbar)
        self.bnopen.setPopupMode(QtWidgets.QToolButton.MenuButtonPopup)
        act.triggered.connect(self.onFileOpen)
        self.bnopen.setDefaultAction(act)
        self.bnopen.setMenu(self.menuRecentFile)
        self.browsertoolbar.addWidget(self.bnopen)
        self.browsertoolbar.addAction(xmlplot.gui_qt4.getIcon('funct.png'),'Add custom expression',self.editExpression)
        self.browsertoolbar.setIconSize(QtCore.QSize(16,16))

        self.statusBar()

        if self.settings['WindowPosition/Maximized'].getValue():
            self.showMaximized()
        elif self.settings['WindowPosition/Width'].getValue():
            desktoprct = QtWidgets.QApplication.desktop().availableGeometry()
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
        self.menuFile.addAction(xmlplot.gui_qt4.getIcon('fileopen.png'),'Open...',self.onFileOpen,QtGui.QKeySequence.Open)
        self.menuFile.addAction('Open Link...',self.onLinkOpen)
        self.menuRecentFile = self.menuFile.addMenu('Open Recent')
        self.menuFile.addAction(xmlplot.gui_qt4.getIcon('exit.png'),'Exit',self.close,QtGui.QKeySequence.Quit)
        self.menuFile.addSeparator()
        menuEdit = bar.addMenu('Edit')
        menuEdit.addAction('Options...',self.onEditOptions)
        menuView = bar.addMenu('View')
        self.actSliceWindow = menuView.addAction('Slice Window',self.onShowSliceWindow)
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
        self.menuRecentFile.clear()
        for node in self.settings['Paths/MostRecentlyUsed'].children:
            path = node.getValue()
            act = self.menuRecentFile.addAction(os.path.basename(path),self.onMRUClicked)
            act.setData(path)
            act.setStatusTip(path)

    def onMRUClicked(self):
        """Called when the user clicks a Most Recently Used file in the "File" menu.
        """
        path = self.sender().data()
        self.load(path)

    def onFileOpen(self):
        """Called when the user clicks "Open..." in the "File" menu.
        """
        filter = 'NetCDF files (*.nc);;All files (*.*)'
        paths,filter = QtWidgets.QFileDialog.getOpenFileNamesAndFilter(self,'',os.path.dirname(self.lastpath),filter)
        if not paths: return
        paths = tuple(map(u''.__class__, paths))
        if len(paths)==1:
            paths = paths[0]
        self.load(paths)

    def onLinkOpen(self):
        """Called when the user clicks "Open Link..." in the "File" menu.
        """
        path = 'http://data.nodc.noaa.gov/thredds/dodsC/woa/WOA09/NetCDFdata/temperature_annual_1deg.nc.info'
        path = 'http://data.nodc.noaa.gov/thredds/catalog/woa/WOA09/NetCDFdata/catalog.html?dataset=woa/WOA09/NetCDFdata/temperature_annual_1deg.nc'
        path = 'http://www.esrl.noaa.gov/psd/thredds/dodsC/Datasets/noaa.oisst.v2/sst.mnmean.nc'
        path = 'http://data.nodc.noaa.gov/thredds/dodsC/woa/WOA09/NetCDFdata/temperature_annual_1deg.nc'
        path = 'http://dtvirt5.deltares.nl:8080/thredds/dodsC/opendap/rijkswaterstaat/jarkus/profiles/transect.nc'
        path = 'http://megara.tamu.edu:8080/thredds/dodsC/mch_outputs/ngom_24h/mch_his_ngom_24h_2008.nc'
        path,ok = QtWidgets.QInputDialog.getText(self,'Open DAP resource','URL:',QtWidgets.QLineEdit.Normal,path)
        if not ok: return
        self.load(path)

    def onEditOptions(self):
        dlg = QtWidgets.QDialog(self,QtCore.Qt.Dialog|QtCore.Qt.CustomizeWindowHint|QtCore.Qt.WindowTitleHint|QtCore.Qt.WindowCloseButtonHint)
        dlg.setWindowTitle('Options')

        layout = QtWidgets.QVBoxLayout()
        cb = QtWidgets.QCheckBox('Treat values outside prescribed valid range as missing data.',dlg)
        cb.setChecked(self.settings['MaskValuesOutsideRange'].getValue(usedefault=True))
        layout.addWidget(cb)

        layoutButtons = QtWidgets.QHBoxLayout()
        bnOk = QtWidgets.QPushButton('OK',dlg)
        bnCancel = QtWidgets.QPushButton('Cancel',dlg)
        layoutButtons.addStretch()
        layoutButtons.addWidget(bnOk)
        layoutButtons.addWidget(bnCancel)
        layout.addLayout(layoutButtons)

        dlg.setLayout(layout)

        bnOk.clicked.connect(dlg.accept)
        bnCancel.clicked.connect(dlg.reject)

        if dlg.exec_()!=QtWidgets.QDialog.Accepted: return

        mask = cb.isChecked()
        self.settings['MaskValuesOutsideRange'].setValue(mask)

        for store in self.figurepanel.figure.getDataSources().values():
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
        if dialog.exec_()==QtWidgets.QDialog.Accepted:
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
            curpath = u''.__class__(curnode.data(0,QtCore.Qt.UserRole+1))
            if path==curpath:
                self.tree.clearSelection()
                curnode.setSelected(True)
                QtWidgets.QMessageBox.information(self,'Already open','"%s" has already been opened.' % path)
                return
            curstorenames.append(u''.__class__(curnode.data(0,QtCore.Qt.UserRole)))

        # Try to load the NetCDF file.
        try:
            store = xmlplot.data.open(paths)
        except xmlplot.data.NetCDFError as e:
            QtWidgets.QMessageBox.critical(self,'Error opening file',u'%s' % e)
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
        fileroot = QtWidgets.QTreeWidgetItem([storename],QtWidgets.QTreeWidgetItem.Type)
        fileroot.setData(0,QtCore.Qt.UserRole,storename)
        fileroot.setData(0,QtCore.Qt.UserRole+1,path)
        fileroot.setToolTip(0,path)

        # Add a node for each dimension set and add dependent variables.
        for dims in sorted(dim2var.keys(), key=lambda x: (len(x), ','.join(x))):
            vars = dim2var[dims]
            nodename = ','.join(dims)
            if nodename=='': nodename = '[none]'
            curdimroot = QtWidgets.QTreeWidgetItem([nodename],QtWidgets.QTreeWidgetItem.Type)
            items = []
            for variable in sorted(vars, key=lambda x: x.getLongName().lower()):
                varname, longname = variable.getName(),variable.getLongName()
                item = QtWidgets.QTreeWidgetItem([longname],QtWidgets.QTreeWidgetItem.Type)
                item.setData(0,QtCore.Qt.UserRole,'%s[\'%s\']' % (storename,varname))
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
        return selected[0].data(0,QtCore.Qt.UserRole)

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
        varname = index.data(QtCore.Qt.UserRole)

        # If there is not internal expression, it is not variable or file (but a container only).
        # Return without showing the context menu.
        if varname is None: return

        # Get the selected variable
        item = self.store[varname]

        # Build and show the context menu
        menu = QtWidgets.QMenu(self)
        actReassign,actClose,actProperties = None,None,None
        if isinstance(item,(xmlplot.common.VariableStore,xmlplot.common.Variable)):
            actProperties = menu.addAction('Properties...')
        if isinstance(item,xmlplot.common.VariableStore):
            actReassign = menu.addAction('Reassign coordinates...')
            actClose    = menu.addAction('Close')
        if menu.isEmpty(): return
        actChosen = menu.exec_(self.tree.mapToGlobal(point))
        if actChosen is None: return

        # Interpret and execute the action chosen in the menu.
        if actChosen is actProperties:
            dialog = NcPropertiesDialog(item,parent=self,flags=QtCore.Qt.CustomizeWindowHint|QtCore.Qt.Dialog|QtCore.Qt.WindowTitleHint|QtCore.Qt.WindowCloseButtonHint)
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
        # Make buttons regarding colorbar visible if and only if there is a colorbar
        self.slicetab.bnSymmetric.setVisible(ndim == 2)
        self.slicetab.bnColormap.setVisible(ndim == 2)
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
        QtWidgets.QApplication.setOverrideCursor(QtGui.QCursor(QtCore.Qt.WaitCursor))

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
            QtWidgets.QApplication.restoreOverrideCursor()

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
                    if numpy.ma.getmask(meanval): meanval = numpy.nan
                    return fmt % meanval
            except:
                raise

    def setAxesBounds(self,dim=None):
        varname = self.getSelectedVariable()
        if varname is None: return

        # Show wait cursor and progress dialog
        QtWidgets.QApplication.setOverrideCursor(QtGui.QCursor(QtCore.Qt.WaitCursor))

        progdialog = QtWidgets.QProgressDialog('Examining data range...',None,0,100,self,QtCore.Qt.Dialog|QtCore.Qt.WindowTitleHint)
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
                todoslices = list(slics.keys())
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
                        progdialog.setValue(int(round(100*cumprog)))
                    return vmin,vmax
                else:
                    # No iteration needed: just obtain the data using the current slice, and
                    # read minimum and maximum values.
                    curvarname = self.addSliceSpec(basevarname,basevar,slices=curslices)
                    curvar = self.store.getExpression(curvarname)
                    curvardata = curvar.getSlice([slice(None)]*len(slabdims))
                    while isinstance(curvardata,(list,tuple)): curvardata = curvardata[0]
                    vmin,vmax = [],[]
                    for idim in range(len(slabdims)):
                        vmin.append(curvardata.coords_stag[idim].min())
                        vmax.append(curvardata.coords_stag[idim].max())
                    datamin,datamax = None,None
                    if not numpy.all(numpy.ma.getmask(curvardata.data)):
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
                #print('%s (%s): %s - %s' % (axisnode.getSecondaryId(),axisdims,vamin,vamax))
                if axisnode['Minimum'].getValue(usedefault=True)>axisnode['Maximum'].getValue(usedefault=True): vamin,vamax = vamax,vamin
                axisnode['Minimum'].setValue(vamin)
                axisnode['Maximum'].setValue(vamax)
            self.figurepanel.figure.setUpdating(oldupdating)

        finally:
            progdialog.close()

            # Restore original cursor
            QtWidgets.QApplication.restoreOverrideCursor()

    def makeColorbarSymmetric(self):
        for axisnode in self.figurepanel.figure['Axes'].children:
            if axisnode.getSecondaryId() == 'colorbar':
                vamin = axisnode['Minimum'].getValue(usedefault=True)
                vamax = axisnode['Maximum'].getValue(usedefault=True)
                absmax = max(abs(vamax), abs(vamin))
                axisnode['Minimum'].setValue(-absmax)
                axisnode['Maximum'].setValue(absmax)

    def changeColormap(self, colormap):
        """Set colormap of figure to the given name and save previously used colormap."""
        figure = self.figurepanel.figure
        old_colormap = figure['ColorMap'].getValue(usedefault=True)
        figure['ColorMap'].setValue(colormap)
        if old_colormap not in figure.colormapQuickList:
            figure.colormapQuickList[old_colormap] = 'recently used'

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
            QtWidgets.QMessageBox.critical(self,'No slice dimension selected','Before creating an animation you must first select one or more dimensions you want to take slices from. The index of one of these will be varied to build the animation.')
            return
        elif nfree>2:
            QtWidgets.QMessageBox.critical(self,'Insufficient slice dimensions selected','Before creating an animation you must first select at least %i more dimensions you want to take slices from. For the animation, only 1 or 2 free (non-sliced) dimensions should remain.' % (nfree-2))
            return
        elif nfree<1:
            QtWidgets.QMessageBox.critical(self,'Too many slice dimensions selected','Before creating an animation you must first deselect at least %i slice dimensions. For the animation, 1 or 2 free (non-sliced) dimensions should remain.' % (1-nfree))
            return

        # Get the directory to export PNG images to.
        targetdir = u''.__class__(QtWidgets.QFileDialog.getExistingDirectory(self,'Select directory for still images'))
        if targetdir=='': return

        # Show wait cursor
        QtWidgets.QApplication.setOverrideCursor(QtGui.QCursor(QtCore.Qt.WaitCursor))

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
            dlgProgress = QtWidgets.QProgressDialog('Please wait while stills are generated.','Cancel',imin,imax,self,QtCore.Qt.Dialog|QtCore.Qt.WindowTitleHint)
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
            QtWidgets.QApplication.restoreOverrideCursor()

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
        self.slicetab.sliceChanged.connect(self.onSliceChanged)
        self.slicetab.makeSymmetric.connect(self.makeColorbarSymmetric)
        self.slicetab.changeColormap.connect(self.changeColormap)
        self.slicetab.setAxesBounds.connect(self.setAxesBounds)
        self.slicetab.onRecord.connect(self.onRecordAnimation)
        self.slicetab.startAnimation.connect(self.figurepanel.startAnimation)
        self.slicetab.stopAnimation.connect(self.figurepanel.stopAnimation)
        self.dockSlice.setWidget(self.slicetab)

        self.redraw(preserveproperties=False)

        self.figurepanel.figure.setUpdating(oldupdating)

    def onVarDoubleClicked(self,item,column):
        if item.parent() is not self.expressionroot: return
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
            expression = item.data(0,QtCore.Qt.UserRole)
            dlg.edit.setText(expression)

        valid = False
        while not valid:
            if dlg.exec_()!=QtWidgets.QDialog.Accepted: return
            expression = str(dlg.edit.text())
            try:
                var = self.store[expression]
                valid = True
            except Exception as e:
                QtWidgets.QMessageBox.critical(self,'Unable to parse expression',str(e))
                dlg.edit.selectAll()

        if item is None:
            if self.expressionroot is None:
                self.expressionroot = QtWidgets.QTreeWidgetItem(['expressions'],QtWidgets.QTreeWidgetItem.Type)
                self.tree.addTopLevelItem(self.expressionroot)
            item = QtWidgets.QTreeWidgetItem(QtWidgets.QTreeWidgetItem.Type)
            self.expressionroot.addChild(item)
        item.setData(0,QtCore.Qt.DisplayRole,expression)
        item.setData(0,QtCore.Qt.UserRole,expression)

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

def start(args):
    if args.nc is not None:
        if xmlplot.data.netcdf.selectednetcdfmodule is None: xmlplot.data.netcdf.chooseNetCDFModule()
        for xmlplot.data.netcdf.selectednetcdfmodule,(m,v) in enumerate(xmlplot.data.netcdf.netcdfmodules):
            if m==args.nc: break
        else:
            print('Forced NetCDF module "%s" is not available. Available modules: %s.' % (args.nc,', '.join([m[0] for m in xmlplot.data.netcdf.netcdfmodules])))
            sys.exit(2)

    # Start Qt
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([' '])
        app.lastWindowClosed.connect(app.quit)

    # Set icon for all windows.
    app.setWindowIcon(QtGui.QIcon(os.path.join(rootdir,'pyncview.png')))

    if "win32" in sys.platform:
        # Give the program a unique entry in the taskbasr with its own icon (Windows 7 and up only)
        import ctypes
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(u'BoldingBruggeman.PyNcView')
        except:
            pass

    # Create main dialog.
    dialog = VisualizeDialog()

    # Open files provided on the command line (if any).
    for path in args.path:
        try:
            dialog.load(path)
        except Exception as e:
            print('Error: %s' % e)

    # Show dialog
    dialog.show()

    # Redirect expections to Qt-based dialog.
    if not args.debug:
        xmlplot.errortrap.redirect_stderr('PyNcView','You may be able to continue working. However, we would appreciate it if you report this error. To do so, post a message to <a href="https://github.com/BoldingBruggeman/pyncview/issues">the PyNcView issue tracker</a> with the above error message, and the circumstances under which the error occurred.')

    # Start application message loop
    ret = app.exec_()

    # Save persistent program settings.    
    dialog.settings.save()

    return ret

def main():
    # Parse command line options
    parser = argparse.ArgumentParser(description="""This utility may be used to visualize the
contents of a NetCDF file.
""")
    parser.add_argument('-v', '--version', action='store_true', help='show program\'s version number and exit')
    parser.add_argument('--nc', help='NetCDF module to use')
    parser.add_argument('-p','--profile', help='activates profiling, saving to the supplied path.')
    parser.add_argument('-d','--debug',action='store_true',help='Send exceptions to stderr')
    parser.add_argument('path', nargs='*', help='Path or URL to open')
    args = parser.parse_args(get_argv()[1:])
    if args.version:
        printVersion()
    elif args.profile is not None:
        # We will do profiling
        import cProfile
        import pstats
        cProfile.run('start(args)', args.profile)
        p = pstats.Stats(args.profile)
        p.strip_dirs().sort_stats('cumulative').print_stats()
    else:
        # Just enter the main loop
        ret = start(args)

    # Exit
    sys.exit(ret)

if __name__ == '__main__':
    main()
