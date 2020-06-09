import anki
from aqt import mw
from aqt.qt import *
from aqt.utils import showCritical, showInfo, tooltip

import json
import logging

from .UIForm import mainUI
from .workers import LoginStateCheckWorker, WordDownloadWorker, AudioDownloadWorker
from .noteManager import getDeckList
from .loginDialog import LoginDialog
from .shanbayAPI import ShanbayAPI
from .logger import Handler

logger = logging.getLogger(__name__)

class Windows(QDialog, mainUI.Ui_Dialog):
    def __init__(self, parent=None):
        super(Windows, self).__init__(parent)
        self.conn = None
        self.db = None
        self.config = {}
        self.cookie = "{}"
        self.workerThread = QThread(self)
        self.workerThread.start()
        self.wordDownloadThread = QThread(self)
        self.audioDownloadThread = QThread(self)
        self.api = ShanbayAPI()

        self.setupUi(self)
        self.setupLogger()
        self.setupGUIByConfig()
        self.initItem()

    def closeEvent(self, event):
        if self.workerThread.isRunning():
            self.workerThread.requestInterruption()
            self.workerThread.quit()
            self.workerThread.wait()

        if self.wordDownloadThread.isRunning():
            self.wordDownloadThread.requestInterruption()
            self.wordDownloadThread.quit()
            self.wordDownloadThread.wait()

        if self.audioDownloadThread.isRunning():
            self.audioDownloadThread.requestInterruption()
            self.audioDownloadThread.quit()
            self.audioDownloadThread.wait()

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

    def setupGUIByConfig(self):
        config = mw.addonManager.getConfig(__name__)
        self.deckComboBox.setCurrentText(config['deck'])
        self.sentenceCheckBox.setChecked(config['sentence'])
        self.BrEPhoneticCheckBox.setChecked(config['BrEPhonetic'])
        self.AmEPhoneticCheckBox.setChecked(config['AmEPhonetic'])
        self.BrEPronRadioButton.setChecked(config['BrEPron'])
        self.AmEPronRadioButton.setChecked(config['AmEPron'])
        self.noPronRadioButton.setChecked(config['noPron'])
        self.cookie = config['cookie']

    def initItem(self):
        self.deckComboBox.addItems(getDeckList())

        self.bookListWidget.clear()
        for bookName in self.api.getAllBooks():
            item = QListWidgetItem()
            item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            item.setText(bookName)
            item.setCheckState(Qt.Unchecked)
            self.bookListWidget.addItem(item)

        if self.bookListWidget.count() > 0:
            self.createBtn.setEnabled(True)
        else:
            self.createBtn.setEnabled(False)

    def saveCurrentConfig(self) -> dict:
        currentConfig = dict(
            deck=self.deckComboBox.currentText(),
            sentence=self.sentenceCheckBox.isChecked(),
            BrEPhonetic=self.BrEPhoneticCheckBox.isChecked(),
            AmEPhonetic=self.AmEPhoneticCheckBox.isChecked(),
            BrEPron=self.BrEPronRadioButton.isChecked(),
            AmEPron=self.AmEPronRadioButton.isChecked(),
            noPron=self.noPronRadioButton.isChecked(),
            cookie=self.cookie,
        )
        self.config = currentConfig
        logger.info(f'保存配置项:{currentConfig}')
        mw.addonManager.writeConfig(__name__, currentConfig)

    @pyqtSlot()
    def on_pullRemoteWordsBtn_clicked(self):
        self.mainTab.setEnabled(False)
        self.progressBar.setValue(0)
        self.progressBar.setMaximum(0)

        self.loginWorker = LoginStateCheckWorker(self.api.checkCookie, json.loads(self.cookie))
        self.loginWorker.moveToThread(self.workerThread)
        self.loginWorker.start.connect(self.loginWorker.run)
        self.loginWorker.logSuccess.connect(self.onLoginSuccess)
        self.loginWorker.logFailed.connect(self.onLoginFailed)
        self.loginWorker.start.emit()

    @pyqtSlot()
    def onLoginFailed(self):
        showCritical('第一次登录或cookie失效!请重新登录')
        self.progressBar.setValue(0)
        self.progressBar.setMaximum(1)
        self.mainTab.setEnabled(True)
        self.loginDialog = LoginDialog(
            loginUrl=self.api.loginUrl,
            loginCheckCallbackFn=self.api.loginCheckCallbackFn,
            parent=self
        )
        self.loginDialog.loginSucceed.connect(self.onLoginSuccess)
        self.loginDialog.show()

    @pyqtSlot(str)
    def onLoginSuccess(self, cookie):
        self.api.checkCookie(json.loads(cookie))
        self.cookie = cookie
        self.saveCurrentConfig()
        self.progressBar.setValue(0)
        self.progressBar.setMaximum(self.api.getWordNumber())
        self.wordDownloadThread = QThread(self)
        self.wordDownloadThread.start()
        self.wordDownloadWorker = WordDownloadWorker(self.api)
        self.wordDownloadWorker.moveToThread(self.wordDownloadThread)
        self.wordDownloadWorker.tick.connect(lambda: self.progressBar.setValue(self.progressBar.value() + 1))
        self.wordDownloadWorker.start.connect(self.wordDownloadWorker.run)
        self.wordDownloadWorker.done.connect(lambda: tooltip(f'单词下载完成'))
        self.wordDownloadWorker.done.connect(self.wordDownloadThread.quit)
        self.wordDownloadWorker.done.connect(lambda: self.mainTab.setEnabled(True))
        self.wordDownloadWorker.done.connect(self.initItem)
        self.wordDownloadWorker.start.emit()

    @pyqtSlot()
    def on_createBtn_clicked(self):
        self.saveCurrentConfig()

        selectedBooks = [self.bookListWidget.item(index).text() for index in range(self.bookListWidget.count()) if
                         self.bookListWidget.item(index).checkState() == Qt.Checked]
        deckName = self.deckComboBox.currentText()
        audiosDownloadTasks = []
        self.api.createWordBook(deckName, selectedBooks, self.config, audiosDownloadTasks)
        showInfo("创建单词书成功！")

        if audiosDownloadTasks:
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
