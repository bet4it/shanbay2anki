import anki
from aqt import mw
from aqt.qt import *
from aqt.utils import showCritical, showInfo, tooltip

import json
import logging

from .UIForm import mainUI
from .workers import *
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
        self.exampleCheckBox.setChecked(config['example'])
        self.titleCNRadioButton.setChecked(config['titleCN'])
        self.titleENRadioButton.setChecked(config['titleEN'])
        self.webLinkRadioButton.setChecked(config['webLink'])
        self.appLinkRadioButton.setChecked(config['appLink'])
        self.noLinkRadioButton.setChecked(config['noLink'])
        self.BrEPhoneticCheckBox.setChecked(config['BrEPhonetic'])
        self.AmEPhoneticCheckBox.setChecked(config['AmEPhonetic'])
        self.BrEPronRadioButton.setChecked(config['BrEPron'])
        self.AmEPronRadioButton.setChecked(config['AmEPron'])
        self.noPronRadioButton.setChecked(config['noPron'])
        self.cookie = config['cookie']
        try:
            from .bays import convert
        except ModuleNotFoundError:
            return
        self.translateCheckBox.setEnabled(True)
        self.translateCheckBox.setChecked(config['translate'])

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
            example=self.exampleCheckBox.isChecked(),
            translate=self.translateCheckBox.isChecked(),
            titleCN=self.titleCNRadioButton.isChecked(),
            titleEN=self.titleENRadioButton.isChecked(),
            webLink=self.webLinkRadioButton.isChecked(),
            appLink=self.appLinkRadioButton.isChecked(),
            noLink=self.noLinkRadioButton.isChecked(),
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

        self.workerThread.start()
        self.loginWorker = LoginStateCheckWorker(self.api.checkCookie, json.loads(self.cookie))
        self.loginWorker.moveToThread(self.workerThread)
        self.loginWorker.start.connect(self.loginWorker.run)
        self.loginWorker.logSuccess.connect(self.onLoginSuccess)
        self.loginWorker.logSuccess.connect(self.workerThread.quit)
        self.loginWorker.logFailed.connect(self.onLoginFailed)
        self.loginWorker.logFailed.connect(self.workerThread.quit)
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
        self.downloadWord()

    def downloadWord(self):
        self.wordDownloadThread.start()
        self.wordDownloadWorker = WordDownloadWorker(self.api)
        self.wordDownloadWorker.moveToThread(self.wordDownloadThread)
        self.progressBar.setTextVisible(True)
        self.progressBar.setValue(0)
        self.progressBar.setMaximum(self.api.getWordNumber())
        self.wordDownloadWorker.tick.connect(lambda: self.progressBar.setValue(self.progressBar.value() + 1))
        self.wordDownloadWorker.start.connect(self.wordDownloadWorker.run)
        self.wordDownloadWorker.done.connect(lambda: tooltip(f'单词下载完成'))
        self.wordDownloadWorker.done.connect(self.initItem)
        self.wordDownloadWorker.done.connect(self.downloadWordExample)
        self.wordDownloadWorker.start.emit()

    def downloadWordExample(self):
        if not self.config['example']:
            self.downloadSentenceTranslate()
            return
        self.wordExampleDownloadWorker = WordExampleDownloadWorker(self.api)
        self.wordExampleDownloadWorker.moveToThread(self.wordDownloadThread)
        self.progressBar.setValue(0)
        self.progressBar.setMaximum(len(self.api.getWordsWithoutExample()))
        self.wordExampleDownloadWorker.tick.connect(lambda: self.progressBar.setValue(self.progressBar.value() + 1))
        self.wordExampleDownloadWorker.start.connect(self.wordExampleDownloadWorker.run)
        self.wordExampleDownloadWorker.done.connect(lambda: tooltip(f'例句下载完成'))
        self.wordExampleDownloadWorker.done.connect(self.downloadSentenceTranslate)
        self.wordExampleDownloadWorker.start.emit()

    def downloadSentenceTranslate(self):
        if not self.config['translate']:
            self.downloadFinish()
            return
        self.SentenceTranslateDownloadWorker = SentenceTranslateDownloadWorker(self.api)
        self.SentenceTranslateDownloadWorker.moveToThread(self.wordDownloadThread)
        self.progressBar.setValue(0)
        self.progressBar.setMaximum(len(self.api.getSentencesWithoutTranslate()))
        self.SentenceTranslateDownloadWorker.tick.connect(lambda: self.progressBar.setValue(self.progressBar.value() + 1))
        self.SentenceTranslateDownloadWorker.start.connect(self.SentenceTranslateDownloadWorker.run)
        self.SentenceTranslateDownloadWorker.done.connect(lambda: tooltip(f'翻译下载完成'))
        self.SentenceTranslateDownloadWorker.done.connect(self.downloadFinish)
        self.SentenceTranslateDownloadWorker.start.emit()

    def downloadFinish(self):
        self.progressBar.setMaximum(1)
        self.progressBar.setTextVisible(False)
        self.mainTab.setEnabled(True)
        self.wordDownloadThread.quit()

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

            self.audioDownloadThread.start()
            self.audioDownloadWorker = AudioDownloadWorker(audiosDownloadTasks)
            self.audioDownloadWorker.moveToThread(self.audioDownloadThread)
            self.audioDownloadWorker.tick.connect(lambda: self.progressBar.setValue(self.progressBar.value() + 1))
            self.audioDownloadWorker.start.connect(self.audioDownloadWorker.run)
            self.audioDownloadWorker.done.connect(lambda: tooltip(f'发音下载完成'))
            self.audioDownloadWorker.done.connect(self.audioDownloadThread.quit)
            self.audioDownloadWorker.start.emit()
