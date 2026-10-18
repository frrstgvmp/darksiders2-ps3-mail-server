"""Read-only community announcements in the observed THQ News version-1 format."""
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

NEWS_PATH = '/thqconnect/news/getNews'
MAX_FILE_BYTES = 128 * 1024
MAX_ITEMS = 32
TEXT_LIMITS = {'prefix': 64, 'title': 256, 'body': 4096}


class NewsQueryError(ValueError):
    pass


class NewsFeedError(ValueError):
    pass


def checked_text(value, name):
    if not isinstance(value, str):
        raise NewsFeedError('News text must be a string')
    try:
        size = len(value.encode('utf-8'))
    except UnicodeError as exc:
        raise NewsFeedError('News text must be valid UTF-8') from exc
    if size > TEXT_LIMITS[name]:
        raise NewsFeedError('News text exceeds its byte limit')
    if any(ord(c) < 32 and not (name == 'body' and c in '\n\t') for c in value):
        raise NewsFeedError('News text contains a control character')
    return value


class NewsFeed:
    """Load an operator-owned JSON file on each request; no player writes."""

    def __init__(self, path=None):
        self.path = Path(path) if path is not None else None

    def entries(self, language):
        if self.path is None:
            return []
        try:
            with self.path.open('rb') as file:
                raw = file.read(MAX_FILE_BYTES + 1)
            if len(raw) > MAX_FILE_BYTES:
                raise NewsFeedError('News file is too large')
            data = json.loads(raw)
        except (OSError, ValueError, UnicodeError) as exc:
            raise NewsFeedError('News file could not be loaded') from exc
        if not isinstance(data, dict) or set(data) != {'items'}:
            raise NewsFeedError('News file must contain an items array')
        items = data['items']
        if not isinstance(items, list) or len(items) > MAX_ITEMS:
            raise NewsFeedError('News file has too many items or no items array')
        result = []
        for item in items:
            if not isinstance(item, dict) or set(item) - {*TEXT_LIMITS, 'datePosted', 'translations'}:
                raise NewsFeedError('Invalid news item')
            posted = item.get('datePosted')
            # The original reader parses decimal text and sign-extends a 32-bit
            # result, even though the destination field occupies eight bytes.
            if type(posted) is not int or not 0 <= posted <= 0x7fffffff:
                raise NewsFeedError('datePosted must fit a signed 32-bit timestamp')
            text = {key: checked_text(item.get(key), key) for key in TEXT_LIMITS}
            translations = item.get('translations', {})
            if not isinstance(translations, dict) or len(translations) > 32:
                raise NewsFeedError('Invalid translations')
            seen = set()
            for locale, values in translations.items():
                if not isinstance(locale, str) or not 1 <= len(locale) <= 32:
                    raise NewsFeedError('Invalid translation language')
                normalized = locale.casefold()
                if normalized in seen:
                    raise NewsFeedError('Duplicate translation language')
                seen.add(normalized)
                if not isinstance(values, dict) or set(values) - set(TEXT_LIMITS):
                    raise NewsFeedError('Invalid translated fields')
                translated = {key: checked_text(value, key) for key, value in values.items()}
                if normalized == language.casefold():
                    text.update(translated)
            result.append([text['prefix'], text['title'], text['body'], posted])
        return sorted(result, key=lambda item: item[3], reverse=True)

    def reply(self, method, path):
        parts = urlsplit(path)
        if method != 'GET' or parts.path != NEWS_PATH:
            return None
        if len(path) > 8192:
            raise NewsQueryError('News query is too long')
        query = parse_qs(parts.query, keep_blank_values=True)
        required = {'version': '1', 'platform': 'PS3_PSN', 'title': 'Darksiders2'}
        if any(query.get(key) != [value] for key, value in required.items()):
            raise NewsQueryError('Unsupported news client parameters')
        limits, languages = query.get('limit', ['32']), query.get('language', ['English'])
        if (len(limits) != 1 or not limits[0].isascii() or not limits[0].isdecimal()
                or len(limits[0]) > 2 or not 0 <= int(limits[0]) <= MAX_ITEMS):
            raise NewsQueryError('News limit must be between 0 and 32')
        if len(languages) != 1 or not 1 <= len(languages[0]) <= 32:
            raise NewsQueryError('Invalid news language')
        entries = self.entries(languages[0])[:int(limits[0])]
        # Original readers: result 0x67dd8c, entry 0x67db24. These arrays are
        # positional: [result, [[prefix, title, body, datePosted], ...]].
        return json.dumps([0, entries], ensure_ascii=False, separators=(',', ':')).encode('utf-8') + b'\n'
