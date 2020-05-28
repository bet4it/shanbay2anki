from aqt import mw
from aqt.qt import *

from .addonWindow import Windows

def showWindow():
    w = Windows()
    w.exec()

action = QAction("shanbay2anki", mw)
action.triggered.connect(showWindow)
mw.form.menuTools.addAction(action)
