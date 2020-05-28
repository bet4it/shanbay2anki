import anki
from aqt.qt import *
from aqt.utils import showInfo

import os
import logging
import sqlite3

from .UIForm import mainUI
from .noteManager import getOrCreateDeck, getOrCreateModel, getOrCreateModelCardTemplate, addNotesToDeck

logger = logging.getLogger(__name__)

class Windows(QDialog, mainUI.Ui_Dialog):
    def __init__(self, parent=None):
        super(Windows, self).__init__(parent)
        self.setupUi(self)

        logging.basicConfig(handlers=[logging.FileHandler('shanbay2anki.log', 'w', 'utf-8')], level=logging.DEBUG)

    @pyqtSlot()
    def on_createBtn_clicked(self):
        model = getOrCreateModel("Shanbay")
        getOrCreateModelCardTemplate(model, 'default')
        deck = getOrCreateDeck("生词本")
        conn = sqlite3.connect('data.db')
        db = conn.cursor()
        addNotesToDeck(deck, model, db)
        showInfo("创建单词书成功！")
