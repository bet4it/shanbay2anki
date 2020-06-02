import anki
from aqt.qt import *
from aqt.utils import showInfo, tooltip

import os
import logging
import sqlite3

from .UIForm import mainUI
from .workers import AudioDownloadWorker
from .noteManager import getDeckList, getOrCreateDeck, getOrCreateModel, getOrCreateModelCardTemplate, addWordToDeck
from .constants import MODEL_FIELDS
from .logger import Handler

logger = logging.getLogger(__name__)

class Windows(QDialog, mainUI.Ui_Dialog):
    def __init__(self, parent=None):
        super(Windows, self).__init__(parent)
        self.conn = None
        self.db = None
        self.config = {}
        self.audioDownloadThread = QThread(self)

        self.setupUi(self)
        self.setupLogger()
        self.initDB()
        self.initItem()

    def closeEvent(self, event):
        if self.audioDownloadThread.isRunning():
            self.audioDownloadThread.requestInterruption()
            self.workerThread.quit()
            self.workerThread.wait()

        event.accept()

    def setupLogger(self):

        def onDestroyed():
            logger.removeHandler(QtHandler)

        logging.basicConfig(handlers=[logging.FileHandler('shanbay2anki.log', 'w', 'utf-8')], level=logging.DEBUG)

        logTextBox = QPlainTextEdit(self)
        layout = QVBoxLayout()
        layout.addWidget(logTextBox)
        self.logTab.setLayout(layout)
        QtHandler = Handler(self)
        logger.addHandler(QtHandler)
        QtHandler.newRecord.connect(logTextBox.appendPlainText)
        logTextBox.destroyed.connect(onDestroyed)

    def initDB(self):
        self.conn = sqlite3.connect('data.db')
        self.conn.set_trace_callback(logger.debug)
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
        columns.remove('ipa_audio')
        if not self.config['BrEPhonetic']:
            columns.remove('ipa_uk')
        if not self.config['AmEPhonetic']:
            columns.remove('ipa_us')
        if self.config['BrEPron']:
            columns.append('ipa_uk_url')
        if self.config['AmEPron']:
            columns.append('ipa_us_url')

        audiosDownloadTasks = []
        self.db.execute(sqlStr.format(','.join(columns), ','.join('"{0}"'.format(b) for b in selectedBooks)))
        for row in self.db:
            word = dict(zip(map(lambda x: x[0], self.db.description), row))
            if self.config['BrEPron'] and word['ipa_uk_url']:
                url = word.pop('ipa_uk_url')
                fileName = os.path.basename(url)
                word['ipa_audio'] = "[sound:{}]".format(fileName)
                audiosDownloadTasks.append((fileName, url))
            if self.config['AmEPron'] and word['ipa_us_url']:
                url = word.pop('ipa_us_url')
                fileName = os.path.basename(url)
                word['ipa_audio'] = "[sound:{}]".format(fileName)
                audiosDownloadTasks.append((fileName, url))
            addWordToDeck(deck, model, word)
        showInfo("创建单词书成功！")

        if audiosDownloadTasks:
            self.createBtn.setEnabled(False)
            self.progressBar.setValue(0)
            self.progressBar.setMaximum(len(audiosDownloadTasks))
            if self.audioDownloadThread is not None:
                self.audioDownloadThread.requestInterruption()
                self.audioDownloadThread.quit()
                self.audioDownloadThread.wait()

            self.audioDownloadThread = QThread(self)
            self.audioDownloadThread.start()
            self.audioDownloadWorker = AudioDownloadWorker(audiosDownloadTasks)
            self.audioDownloadWorker.moveToThread(self.audioDownloadThread)
            self.audioDownloadWorker.tick.connect(lambda: self.progressBar.setValue(self.progressBar.value() + 1))
            self.audioDownloadWorker.start.connect(self.audioDownloadWorker.run)
            self.audioDownloadWorker.done.connect(lambda: tooltip(f'发音下载完成'))
            self.audioDownloadWorker.done.connect(self.audioDownloadThread.quit)
            self.audioDownloadWorker.start.emit()
            self.createBtn.setEnabled(True)
