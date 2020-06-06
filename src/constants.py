MODEL_FIELDS = ('word', 'ipa_uk', 'ipa_us', 'ipa_audio', 'definition_cn', 'source_name1', 'source_content1', 'source_translate1', 'source_name2', 'source_content2', 'source_translate2')
INTENT_BOOK = '<a href="android-app://com.shanbay.news/#Intent;component=com.shanbay.news/.article.dictionaries.article.DictArticleActivity;S.extra_article_id={};S.extra_paragraph_id={};end">{}</a>'
INTENT_NEWS = '<a href="android-app://com.shanbay.news/#Intent;component=com.shanbay.news/.article.news.NewsArticleWebActivity;S.article_web_id={};S.article_web_paragraph_id={};end">{}</a>'
INTENT_TEMPLATE = {'book': INTENT_BOOK, 'news': INTENT_NEWS}
