from aqt import mw
import anki
import logging
import os

from .constants import MODEL_FIELDS

logger = logging.getLogger(__name__)

def getDeckList():
    return [deck['name'] for deck in mw.col.decks.all()]


def getOrCreateDeck(deckName):
    deck_id = mw.col.decks.id(deckName)
    deck = mw.col.decks.get(deck_id)
    mw.col.decks.save(deck)
    mw.col.reset()
    mw.reset()
    return deck


def getOrCreateModel(modelName):
    model = mw.col.models.byName(modelName)
    if model:
        if set([f['name'] for f in model['flds']]) == set(MODEL_FIELDS):
            return model
        else:
            logger.warning('模版字段异常，自动删除重建')
            mw.col.models.rem(model)

    logger.info(f'创建新模版:{modelName}')
    newModel = mw.col.models.new(modelName)
    mw.col.models.add(newModel)
    for field in MODEL_FIELDS:
        mw.col.models.addField(newModel, mw.col.models.newField(field))
    mw.col.models.update(newModel)
    return newModel


def getOrCreateModelCardTemplate(modelObject, cardTemplateName):
    logger.info(f'添加卡片类型:{cardTemplateName}')
    existingCardTemplate = modelObject['tmpls']
    if cardTemplateName in [t.get('name') for t in existingCardTemplate]:
        return
    cardTemplate = mw.col.models.newTemplate(cardTemplateName)
    dirpath = os.path.dirname(__file__)
    logger.warning(dirpath)
    with open(os.path.join(dirpath,'front.html'), 'r') as f:
        cardTemplate['qfmt'] = f.read()
    with open(os.path.join(dirpath,'back.html'), 'r') as f:
        cardTemplate['afmt'] = f.read()
    with open(os.path.join(dirpath,'styling.css'), 'r') as f:
        modelObject['css'] = f.read()
    mw.col.models.addTemplate(modelObject, cardTemplate)


def addNotesToDeck(deckObject, modelObject, database):
    modelObject['did'] = deckObject['id']

    for row in database:
        newNote = anki.notes.Note(mw.col, modelObject)
        for i in range(len(row)):
            if row[i] is not None:
                newNote[database.description[i][0]] = row[i]
        mw.col.addNote(newNote)
        mw.col.reset()
    logger.info(f"添加笔记{newNote['word']}")
