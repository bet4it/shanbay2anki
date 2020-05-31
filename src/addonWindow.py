import anki
from aqt.qt import *
from aqt.utils import showInfo

import os
import logging
import sqlite3

from .UIForm import mainUI
from .noteManager import getDeckList, getOrCreateDeck, getOrCreateModel, getOrCreateModelCardTemplate, addWordToDeck
from .constants import MODEL_FIELDS

logger = logging.getLogger(__name__)

class Windows(QDialog, mainUI.Ui_Dialog):
    def __init__(self, parent=None):
        super(Windows, self).__init__(parent)
        self.conn = None
        self.db = None
        self.config = {}

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

    def getCurrentConfig(self) -> dict:
        currentConfig = dict(
            sentence=self.sentenceCheckBox.isChecked(),
            AmEPhonetic=self.AmEPhoneticCheckBox.isChecked(),
            BrEPhonetic=self.BrEPhoneticCheckBox.isChecked(),
            BrEPron=self.BrEPronRadioButton.isChecked(),
            AmEPron=self.AmEPronRadioButton.isChecked(),
            noPron=self.noPronRadioButton.isChecked(),
        )
        self.config = currentConfig
        logger.info(f'当前设置:{currentConfig}')
        return currentConfig
        
    def downloadVideo(self, v):
        pass

    @pyqtSlot()
    def on_createBtn_clicked(self):
        self.getCurrentConfig()

        model = getOrCreateModel("Shanbay")
        getOrCreateModelCardTemplate(model, 'default')
        deck = getOrCreateDeck(self.deckComboBox.currentText())
        selectedBooks = [self.bookListWidget.item(index).text() for index in range(self.bookListWidget.count()) if
                         self.bookListWidget.item(index).checkState() == Qt.Checked]
        sqlStr = "SELECT {0} from words where source_name1 in ({1}) or source_name2 in ({1})"

        if '扇贝新闻' in selectedBooks:
            selectedBooks.remove('扇贝新闻')
            sqlStr += " or source_type1 = 'news' or source_type2 = 'news'"

        columns = list(MODEL_FIELDS)
        logger.debug(f'{columns=}')
        columns.remove('ipa_audio')
        if not self.config['BrEPhonetic']:
            columns.remove('ipa_uk')
        if not self.config['AmEPhonetic']:
            columns.remove('ipa_us')
        if self.config['BrEPron']:
            columns.append('ipa_uk_name')
            columns.append('ipa_uk_url')
        if self.config['AmEPron']:
            columns.append('ipa_us_name')
            columns.append('ipa_us_url')

        self.db.execute(sqlStr.format(','.join(columns), ','.join('"{0}"'.format(b) for b in selectedBooks)))
        for row in self.db:
            word = dict(zip(map(lambda x: x[0], self.db.description), row))
            if self.config['BrEPron'] and word['ipa_uk_url']:
                word['ipa_audio'] = "[sound:{}]".format(word.pop('ipa_uk_name'))
                self.downloadVideo(word.pop('ipa_uk_url'))
            if self.config['AmEPron'] and word['ipa_us_url']:
                word['ipa_us_name'] = "[sound:{}]".format(word.pop('ipa_us_name'))
                self.downloadVideo(word.pop('ipa_us_url'))
            addWordToDeck(deck, model, word)
        showInfo("创建单词书成功！")
