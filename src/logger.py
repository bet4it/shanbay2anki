import logging
from aqt.qt import pyqtSignal, QObject


class Handler(QObject, logging.Handler):
    newRecord = pyqtSignal(object)

    def __init__(self, parent):
        super().__init__(parent)
        super(logging.Handler).__init__()

        formatter = logging.Formatter('[%(asctime)s][%(name)s][%(levelname)s]\n%(message)s\n', '%d/%m/%Y %H:%M:%S')
        self.setFormatter(formatter)
        self.setLevel(logging.DEBUG)

    def emit(self, record):
        msg = self.format(record)
        self.newRecord.emit(msg)