import anki
from aqt.qt import *
from aqt.utils import showInfo

import os
import logging
import sqlite3

from .UIForm import mainUI
from .noteManager import getDeckList, getOrCreateDeck, getOrCreateModel, getOrCreateModelCardTemplate, addNotesToDeck
from .constants import MODEL_FIELDS

logger = logging.getLogger(__name__)

class Windows(QDialog, mainUI.Ui_Dialog):
    def __init__(self, parent=None):
        super(Windows, self).__init__(parent)
        self.conn = None
        self.db = None

        logging.basicConfig(handlers=[logging.FileHandler('shanbay2anki.log', 'w', 'utf-8')], level=logging.DEBUG)

        self.setupUi(self)
        self.initDB()
        self.initItem()

    def initDB(self):
        self.conn = sqlite3.connect('data.db')
        self.db = self.conn.cursor()

    def initItem(self):
        self.deckComboBox.addItems(getDeckList())

        self.db.execute('''SELECT source_name1 from words where source_type1 = 'book'
                     UNION SELECT source_name2 from words where source_type2 = 'book'
                     UNION SELECT '扇贝新闻' from words where source_type1 = 'news' or source_type2 = 'news'
                     ''')

        for bookname in reversed(self.db.fetchall()):
            item = QListWidgetItem()
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            item.setText(bookname[0])
            item.setCheckState(Qt.Unchecked)
            self.bookListWidget.addItem(item)

    @pyqtSlot()
    def on_createBtn_clicked(self):
        model = getOrCreateModel("Shanbay")
        getOrCreateModelCardTemplate(model, 'default')
        deck = getOrCreateDeck(self.deckComboBox.currentText())
        selectedBooks = [self.bookListWidget.item(index).text() for index in range(self.bookListWidget.count()) if
                         self.bookListWidget.item(index).checkState() == Qt.Checked]
        sqlStr = "SELECT {0} from words where source_name1 in ({1}) or source_name2 in ({1})"

        if '扇贝新闻' in selectedBooks:
            selectedBooks.remove('扇贝新闻')
            sqlStr += " or source_type1 = 'news' or source_type2 = 'news'"

        self.db.execute(sqlStr.format(','.join(MODEL_FIELDS), ','.join('"{0}"'.format(b) for b in selectedBooks)))
        addNotesToDeck(deck, model, self.db)
        showInfo("创建单词书成功！")
