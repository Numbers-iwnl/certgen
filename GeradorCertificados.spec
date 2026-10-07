# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('assets', 'assets')]
binaries = []
hiddenimports = ['qrcode.image.pil', 'qrcode.image.base']

for pkg in ('pymupdf', 'openpyxl'):
    tmp_ret = collect_all(pkg)
    datas += tmp_ret[0]
    binaries += tmp_ret[1]
    hiddenimports += tmp_ret[2]

# PySide6 modules this app doesn't use. Left unexcluded, PyInstaller's
# default PySide6 hook pulls in the whole framework (WebEngine, QML,
# 3D, Multimedia, Charts...) -- excluding them is most of the difference
# between a ~250MB and a ~70MB onefile exe.
pyside6_excludes = [
    'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineQuick',
    'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtQuick3D', 'PySide6.QtQuickWidgets',
    'PySide6.QtQuickControls2', 'PySide6.QtQmlModels',
    'PySide6.Qt3DCore', 'PySide6.Qt3DRender', 'PySide6.Qt3DInput', 'PySide6.Qt3DLogic',
    'PySide6.Qt3DAnimation', 'PySide6.Qt3DExtras',
    'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets',
    'PySide6.QtCharts', 'PySide6.QtDataVisualization',
    'PySide6.QtPdf', 'PySide6.QtPdfWidgets',
    'PySide6.QtBluetooth', 'PySide6.QtNfc', 'PySide6.QtSensors', 'PySide6.QtSerialPort',
    'PySide6.QtSql', 'PySide6.QtTest', 'PySide6.QtHelp', 'PySide6.QtDesigner',
    'PySide6.QtRemoteObjects', 'PySide6.QtOpenGL', 'PySide6.QtOpenGLWidgets',
    'PySide6.QtPositioning', 'PySide6.QtLocation', 'PySide6.QtWebChannel', 'PySide6.QtWebSockets',
    'PySide6.QtStateMachine', 'PySide6.QtSpatialAudio', 'PySide6.QtTextToSpeech',
    'PySide6.QtSvg', 'PySide6.QtSvgWidgets',
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=pyside6_excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

# PyInstaller's native splash: rendered by the bootloader itself, so it
# appears the instant the exe is double-clicked -- during the onefile
# temp-extraction that otherwise leaves a double-click looking like
# nothing happened for a few seconds.
splash = Splash(
    'assets/splash.png',
    binaries=a.binaries,
    datas=a.datas,
    text_pos=(20, 290),
    text_size=11,
    text_color='#3a3530',
)

exe = EXE(
    pyz,
    a.scripts,
    splash,
    a.binaries,
    splash.binaries,
    a.datas,
    [],
    name='GeradorCertificados',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX-packed exes are a common antivirus false-positive
                # trigger; not worth it for a tool emailed around unsigned.
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets\\logo.ico',
    version='version_info.txt',
)
