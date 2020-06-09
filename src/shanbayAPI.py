import os
import sqlite3
import logging
import requests
from requests.compat import urljoin
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .constants import MODEL_FIELDS, DB_FIELDS, INTENT_TEMPLATE
from .noteManager import getOrCreateDeck, getOrCreateModel, getOrCreateModelCardTemplate, addWordToDeck

logger = logging.getLogger(__name__)

API_URL = 'https://apiv3.shanbay.com/'

class ShanbayAPI():
    loginUrl = 'https://web.shanbay.com/web/account/login/'
    timeout = 10
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36',
    }
    retries = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    session = requests.Session()
    session.mount('http://', HTTPAdapter(max_retries=retries))
    session.mount('https://', HTTPAdapter(max_retries=retries))

    def __init__(self):
        self.conn = sqlite3.connect('shanbay2anki.db', check_same_thread=False)
        self.conn.set_trace_callback(logger.debug)
        self.conn.row_factory = sqlite3.Row
        self.db = self.conn.cursor()
        #self.db.execute('DROP TABLE IF EXISTS words')
        self.db.execute('CREATE TABLE IF NOT EXISTS words ({})'.format(','.join(map(lambda c:c+' TEXT', DB_FIELDS))))

    def checkCookie(self, cookie):
        rsp = requests.get(urljoin(API_URL, 'bayuser/user_detail'), cookies=cookie, headers=self.headers)
        if rsp.status_code == 200:
            logger.info('Cookie有效')
            cookiesJar = requests.utils.cookiejar_from_dict(cookie, cookiejar=None, overwrite=True)
            self.session.cookies = cookiesJar
            return True
        logger.info('Cookie失效')
        return False

    @staticmethod
    def loginCheckCallbackFn(cookie, content):
        if 'auth_token' in cookie:
            return True
        return False

    def getWord(self, word):
        url = urljoin(API_URL, 'wordscollection/words/' + word)
        r = self.session.get(url, timeout=self.timeout)
        return r.json()

    def getWordNumber(self):
        url = urljoin(API_URL, 'wordscollection/words')
        r = self.session.get(url, timeout=self.timeout)
        return r.json()['total']

    def getWordsByPage(self, idx):
        url = urljoin(API_URL, f'wordscollection/words?ipp=50&page={idx}')
        r = self.session.get(url, timeout=self.timeout)
        return r.json()

    def insertWord(self, word):
        self.db.execute('SELECT 1 FROM words WHERE id=? LIMIT 1', (word,))
        if self.db.fetchone() is not None:
            logger.info(f"Skip word {word}")
            return
        wordData = self.getWord(word)
        vocab = wordData['vocabulary']
        definition_cn = ''
        for sense in vocab['senses']:
            definition_cn += sense['pos'] + ' ' + sense['definition_cn'] + '<br>'
        ipa_uk = vocab['sound']['ipa_uk']
        ipa_uk = "/{}/".format(ipa_uk) if ipa_uk else None
        ipa_us = vocab['sound']['ipa_us']
        ipa_us = "/{}/".format(ipa_us) if ipa_us else None
        ipa_uk_url = (vocab['sound']['audio_uk_urls'] + [None])[0]
        ipa_us_url = (vocab['sound']['audio_us_urls'] + [None])[0]
        values = (word, vocab['word'], ipa_uk, ipa_uk_url, ipa_us, ipa_us_url, definition_cn)
        self.db.execute("INSERT INTO words (id, word, ipa_uk, ipa_uk_url, ipa_us, ipa_us_url, definition_cn) VALUES (?, ?, ?, ?, ?, ?, ?)", values)

        self.db.execute("UPDATE words set updated_at = ? where id = ?", (wordData['objects'][0]['updated_at'], word))
        idx = 1
        for obj in reversed(wordData['objects']):
            if obj['app_name'] == '扇贝阅读' and obj['objective'] :
                sources = (obj['source_name'], obj['objective']['article_code'], obj['objective']['paragraph_code'], obj['objective']['sentence_code'], obj['source_content'], word)
                self.db.execute(f"UPDATE words set source_name{idx} = ?, source_article{idx} = ?, source_paragraph{idx} = ?, source_sentence{idx} = ?, source_content{idx} = ? where id = ?", sources)
                if 'book_code' in obj['objective']:
                    self.db.execute(f"UPDATE words set source_type{idx} = ? where id = ?", ('book', word))
                elif 'article_code' in obj['objective']:
                    self.db.execute(f"UPDATE words set source_type{idx} = ? where id = ?", ('news', word))
                idx += 1
                if idx == 3:
                    break
        self.conn.commit()

    def getAllWords(self):
        idx = 1
        while True:
            words = self.getWordsByPage(idx)
            wordList = [i['vocabulary']['id'] for i in words['objects']]
            for word in wordList:
                yield word
            if len(wordList) != 50:
                break
            idx += 1

    def getAllBooks(self):
        self.db.execute('''SELECT source_name1 from words where source_type1 = 'book'
                     UNION SELECT source_name2 from words where source_type2 = 'book'
                     UNION SELECT '扇贝新闻' from words where source_type1 = 'news' or source_type2 = 'news'
                     ''')
        return map(lambda i: i[0], reversed(self.db.fetchall()))

    def createWordBook(self, deckName, selectedBooks, currentConfig, audiosDownloadTasks):
        model = getOrCreateModel("Shanbay")
        getOrCreateModelCardTemplate(model, 'default')
        deck = getOrCreateDeck(deckName)
        sqlStr = "SELECT * from words where source_name1 in ({0}) or source_name2 in ({0})"

        if '扇贝新闻' in selectedBooks:
            selectedBooks.remove('扇贝新闻')
            sqlStr += " or source_type1 = 'news' or source_type2 = 'news'"

        columns = list(MODEL_FIELDS)
        if not currentConfig['BrEPhonetic']:
            columns.remove('ipa_uk')
        if not currentConfig['AmEPhonetic']:
            columns.remove('ipa_us')

        self.db.execute(sqlStr.format(','.join('"{0}"'.format(b) for b in selectedBooks)))
        for row in self.db:
            word = {k:row[k] for k in row.keys() if k in columns}
            if currentConfig['BrEPron'] and row['ipa_uk_url']:
                url = row['ipa_uk_url']
                fileName = os.path.basename(url)
                word['ipa_audio'] = "[sound:{}]".format(fileName)
                audiosDownloadTasks.append((fileName, url))
            if currentConfig['AmEPron'] and row['ipa_us_url']:
                url = row['ipa_us_url']
                fileName = os.path.basename(url)
                word['ipa_audio'] = "[sound:{}]".format(fileName)
                audiosDownloadTasks.append((fileName, url))
            for i in (1,2):
                if row[f'source_type{i}'] in INTENT_TEMPLATE:
                    word[f'source_name{i}'] = INTENT_TEMPLATE[row[f'source_type{i}']].format(
                        row[f'source_article{i}'], row[f'source_paragraph{i}'], row[f'source_name{i}'])
            addWordToDeck(deck, model, word)