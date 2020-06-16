import os
import sqlite3
import logging
import requests
from requests.compat import urljoin
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .constants import MODEL_FIELDS, DB_FIELDS, WEB_LINK, APP_LINK
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
        self.chapterNames = {}
        self.bookNames = {}

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

    def getWordExamples(self, word):
        url = urljoin(API_URL, f'abc/words/vocabularies/{word}/examples')
        r = self.session.get(url, timeout=self.timeout)
        for example in r.json():
            yield (example['content_en'].replace('vocab>', 'b>'), example['content_cn'], word)
        yield ("", "", word)
        yield ("", "", word)

    def getSentenceTranslate(self, sentence):
        from .bays import convert
        url = urljoin(API_URL, f'reading/bilingual?sentence_id={sentence}')
        r = self.session.get(url, timeout=self.timeout)
        return convert(r.json()['text'])

    def getArticle(self, chapter):
        url = urljoin(API_URL, f'reading/articles/{chapter}')
        r = self.session.get(url, timeout=self.timeout)
        return r.json()

    def getBookCatalogs(self, book):
        url = urljoin(API_URL, f'reading/books/{book}/static_catalogs')
        r = self.session.get(url, timeout=self.timeout)
        if r.status_code == 200:
            return r.json()
        return None

    def getChapterName(self, book, chapter):
        if chapter not in self.chapterNames:
            catalogs = self.getBookCatalogs(book)
            if catalogs is not None:
                self.bookNames[book] = {'cn': catalogs['book']['name_cn'], 'en': catalogs['book']['name_en']}
                for c in catalogs['catalogs']:
                    self.chapterNames[c['id']] = {'cn': c['title_cn'], 'en': c['title_en'], 'id': c['id']}
            else:
                article = self.getArticle(chapter)
                self.chapterNames[chapter] =  {'cn': article['title_cn'], 'en': article['title_en'], 'id': article['id']}
                if book not in self.bookNames:
                    catalogs = self.getBookCatalogs(article['book_id'])
                    self.bookNames[book] =  {'cn': catalogs['book']['name_cn'], 'en': catalogs['book']['name_en']}
        bookNameCN = self.bookNames[book]['cn']
        bookNameEN = self.bookNames[book]['en']
        chapterID = self.chapterNames[chapter]['id']
        chapterNameCN = self.chapterNames[chapter]['cn']
        chapterNameEN = self.chapterNames[chapter]['en']
        return bookNameCN, bookNameEN, chapterID, chapterNameCN, chapterNameEN

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
                sources = [obj['objective']['article_code'], obj['objective']['paragraph_code'], obj['objective']['sentence_code'], obj['source_content'], word]
                if 'book_code' in obj['objective']:
                    bookNameCN, bookNameEN, articleCode, chapterNameCN, chapterNameEN = self.getChapterName(obj['objective']['book_code'], obj['objective']['article_code'])
                    sources[0] = articleCode
                    self.db.execute(f"UPDATE words set source_type{idx} = ?, source_name_cn{idx} = ?, source_name_en{idx} = ?, source_title_cn{idx} = ?, source_title_en{idx} = ? where id = ?", ('book', bookNameCN, bookNameEN, chapterNameCN, chapterNameEN, word))
                elif 'article_code' in obj['objective']:
                    self.db.execute(f"UPDATE words set source_type{idx} = ?, source_name_en{idx} = ? where id = ?", ('news', obj['source_name'], word))
                self.db.execute(f"UPDATE words set source_article{idx} = ?, source_paragraph{idx} = ?, source_sentence{idx} = ?, source_content{idx} = ? where id = ?", sources)
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
        self.db.execute('''SELECT source_name_cn1 from words where source_type1 = 'book'
                     UNION SELECT source_name_cn2 from words where source_type2 = 'book'
                     UNION SELECT '扇贝新闻' from words where source_type1 = 'news' or source_type2 = 'news'
                     ''')
        return map(lambda i: i[0], reversed(self.db.fetchall()))

    def createWordBook(self, deckName, selectedBooks, currentConfig, audiosDownloadTasks):
        model = getOrCreateModel("Shanbay")
        getOrCreateModelCardTemplate(model, 'default')
        deck = getOrCreateDeck(deckName)
        sqlStr = "SELECT * from words where source_name_cn1 in ({0}) or source_name_cn2 in ({0})"

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
                if currentConfig['titleCN'] and row[f'source_name_cn{i}']:
                    word[f'source_name{i}'] = row[f'source_name_cn{i}']
                    if  row[f'source_title_cn{i}']:
                        word[f'source_name{i}'] += '<br>' + row[f'source_title_cn{i}']
                else:
                    word[f'source_name{i}'] = row[f'source_name_en{i}']
                    if  row[f'source_title_en{i}']:
                        word[f'source_name{i}'] += ' -- ' + row[f'source_title_en{i}']
                if currentConfig['webLink'] and row[f'source_type{i}'] in WEB_LINK:
                    word[f'source_name{i}'] = WEB_LINK[row[f'source_type{i}']].format(
                        row[f'source_article{i}'], word[f'source_name{i}'])
                if currentConfig['appLink'] and row[f'source_type{i}'] in APP_LINK:
                    word[f'source_name{i}'] = APP_LINK[row[f'source_type{i}']].format(
                        row[f'source_article{i}'], row[f'source_paragraph{i}'], word[f'source_name{i}'])
            addWordToDeck(deck, model, word)

    def getWordsWithoutExample(self):
        self.db.execute('SELECT id from words where examples1_en is NULL')
        return self.db.fetchall()

    def insertWordExamples(self, word):
        idx = 1
        for example in self.getWordExamples(word):
            self.db.execute(f"UPDATE words set examples{idx}_en = ?, examples{idx}_cn = ? where id = ?", example)
            idx += 1
            if idx == 3:
                break
        self.conn.commit()

    def getSentencesWithoutTranslate(self):
        self.db.execute("SELECT id, source_type1, source_sentence1, source_translate1, source_type2, source_sentence2, source_translate2 from words where (source_type1 = 'book' and source_translate1 is null) or (source_type2 = 'book' and source_translate2 is null)")
        return self.db.fetchall()

    def insertSentenceTranslates(self, row):
        if row['source_type1'] == 'book' and row['source_translate1'] is None:
            self.db.execute(f"UPDATE words set source_translate1 = ? where id = ?", (self.getSentenceTranslate(row['source_sentence1']), row['id']))
        if row['source_type2'] == 'book' and row['source_translate2'] is None:
            self.db.execute(f"UPDATE words set source_translate2 = ? where id = ?", (self.getSentenceTranslate(row['source_sentence2']), row['id']))
        self.conn.commit()
