# Texts for people (CLI, hook context, notes, web view) in English and
# German. One JSON file per language in locale/ - the web view loads the same
# files. t("key", n=3) formats with str.format; a missing key falls back to
# English, then to the key itself, so a gap is visible but never a crash.
import json
import locale
import os

from . import config, system

LANGUAGES = ('en', 'de')
_texts = {}
_current = None


def detect():
    # Explicit setting, then the vault's language, then the system
    lang = str(config.get('language') or '').lower()[:2]
    if lang in LANGUAGES:
        return lang
    from . import vault
    if vault.LANG in LANGUAGES:
        return vault.LANG
    return system_language()


def system_language():
    for name in ('LC_ALL', 'LC_MESSAGES', 'LANG', 'LANGUAGE'):
        value = os.environ.get(name, '')
        if value:
            return 'de' if value.lower().startswith('de') else 'en'
    try:
        value = locale.getlocale()[0] or ''
    except ValueError:
        value = ''
    return 'de' if value.lower().startswith('de') else 'en'


def language():
    global _current
    if _current is None:
        _current = detect()
    return _current


def use(lang):
    global _current
    _current = lang if lang in LANGUAGES else 'en'


def texts(lang):
    if lang not in _texts:
        try:
            with open(os.path.join(system.PACKAGE, 'locale', lang + '.json'), encoding='utf-8') as f:
                _texts[lang] = json.load(f)
        except (OSError, ValueError):
            _texts[lang] = {}
    return _texts[lang]


def t(key, lang=None, **values):
    text = texts(lang or language()).get(key)
    if text is None:
        text = texts('en').get(key, key)
    return text.format(**values) if values else text
