import logging
import requests
from requests.compat import urljoin
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

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
        self.groups = []

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
