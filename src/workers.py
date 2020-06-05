import logging
import requests
from os import path
from urllib3 import Retry
from .misc import ThreadPool
from requests.adapters import HTTPAdapter
from aqt.qt import QObject, pyqtSignal, QThread

class LoginStateCheckWorker(QObject):
    start = pyqtSignal()
    logSuccess = pyqtSignal(str)
    logFailed = pyqtSignal()

    def __init__(self, checkFn, cookie):
        super().__init__()
        self.checkFn = checkFn
        self.cookie = cookie

    def run(self):
        loginState = self.checkFn(self.cookie)
        if loginState:
            self.logSuccess.emit(json.dumps(self.cookie))
        else:
            self.logFailed.emit()

class AudioDownloadWorker(QObject):
    start = pyqtSignal()
    tick = pyqtSignal()
    done = pyqtSignal()
    logger = logging.getLogger(__name__ + '.AudioDownloadWorker')
    retries = Retry(total=5, backoff_factor=3, status_forcelist=[500, 502, 503, 504])
    session = requests.Session()
    session.mount('http://', HTTPAdapter(max_retries=retries))
    session.mount('https://', HTTPAdapter(max_retries=retries))

    def __init__(self, audios: [tuple]):
        super().__init__()
        self.audios = audios

    def run(self):
        currentThread = QThread.currentThread()

        def __download(fileName, url):
            try:
                if currentThread.isInterruptionRequested():
                    return
                r = self.session.get(url, stream=True)

                if not path.exists(fileName) or path.getsize(fileName) != int(r.headers['Content-Length']):
                    with open(fileName, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=1024):
                            if chunk:
                                f.write(chunk)
                    self.logger.info(f'{fileName} 下载完成')
                else:
                    self.logger.info(f'{fileName} 跳过下载')
            except Exception as e:
                self.logger.warning(f'下载{fileName}:{url}异常: {e}')
            finally:
                self.tick.emit()

        with ThreadPool(max_workers=3) as executor:
            for fileName, url in self.audios:
                executor.submit(__download, fileName, url)
        self.done.emit()
