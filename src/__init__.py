from aqt import mw
from aqt.qt import *
import anki

import os
import logging
import sqlite3

from .noteManager import getOrCreateDeck, getOrCreateModel, getOrCreateModelCardTemplate, addNotesToDeck

logging.basicConfig(handlers=[logging.FileHandler('shanbay2anki.log', 'w', 'utf-8')], level=logging.DEBUG, format='[%(asctime)s][%(levelname)8s] -- %(message)s - (%(name)s)')

logger = logging.getLogger(__name__)

def mainFunction():
    model = getOrCreateModel("Shanbay")
    getOrCreateModelCardTemplate(model, 'default')
    deck = getOrCreateDeck("生词本")
    conn = sqlite3.connect('data.db')
    db = conn.cursor()
    addNotesToDeck(deck, model, db)

action = QAction("shanbay2anki", mw)
action.triggered.connect(mainFunction)
mw.form.menuTools.addAction(action)
