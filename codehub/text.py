# Search terms: fold case, umlauts and accents, split paths and camelCase,
# drop filler words, cut endings. Same rules for the index and the query,
# so "Farben" finds "farbe" and "DeskCava.qml" finds "desk cava".
import re
import unicodedata

_UMLAUTS = str.maketrans({'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ß': 'ss', 'Ä': 'ae', 'Ö': 'oe', 'Ü': 'ue'})
_WORD = re.compile(r'[0-9A-Za-zÀ-ÖØ-öø-ÿ]+')
_PARTS = re.compile(r'[A-ZÀ-Ö]?[a-zß-öø-ÿ]+|[A-ZÀ-Ö]+(?![a-zß-öø-ÿ])|\d+')

STOP = set('''
der die das den dem des ein eine einen einem einer eines und oder aber mit ohne fuer von vom zu
zum zur im in am an auf aus bei bis nach vor ueber unter durch gegen bitte mach mache machen
macht kannst kann koennen soll sollte muss mir mich mein meine meinen dein deine wir ihr sie
es ist sind war wird werden wurde noch auch nur nicht kein keine keinen mal so wie was wo wer
warum wieso weshalb dass da dann wenn als ob jetzt hier dort dies diese dieser dieses alles
alle immer gerade einfach mehr sehr viel gut ganz schon doch etwas irgendwie hast habe hat
haben geht gehen gibt wieder neue neuen neues bauen baue fixen fix aendern aenderung
the and for with this that you can please make into from are was were has have not but
what why how when where which there their then than also just like want need should could
would does done use using file files
'''.split())


def short(text, n):
    text = ' '.join(str(text or '').split())
    return text if len(text) <= n else text[:n - 1].rstrip() + '…'


def fold(text):
    # lower case, umlauts as ae/oe/ue (as in code comments), no accents
    text = str(text).translate(_UMLAUTS).lower()
    return ''.join(c for c in unicodedata.normalize('NFKD', text) if not unicodedata.combining(c))


def split(text):
    # "quickshell/desk/DeskCava.qml" -> quickshell desk DeskCava Desk Cava qml
    out = []
    for word in _WORD.findall(str(text)):
        out.append(word)
        parts = _PARTS.findall(word)
        if len(parts) > 1:
            out.extend(parts)
    return ' '.join(out)


def stem(word):
    # rough base form: farben -> farb, fenster -> fenst, hooks -> hook
    if len(word) >= 6:
        for ending in ('en', 'er', 'es', 'e', 'n', 's'):
            if word.endswith(ending) and len(word) - len(ending) >= 4:
                return word[:-len(ending)]
    return word


def terms(query):
    out = []
    for word in split(query).split():
        f = fold(word)
        if len(f) < 3 or f in STOP or f.isdigit():
            continue
        s = stem(f)
        if s not in out:
            out.append(s)
    return out[:12]


def file_name(title, fallback='Untitled'):
    # characters Obsidian dislikes in file names and [[links]]
    s = re.sub(r'[\\/:*?"<>|#^\[\]]+', ' ', str(title))
    s = ' '.join(s.split()).strip(' .')
    return s[:90].rstrip() or fallback


def excerpt(text, terms_, n=220):
    # the spot with the first term, cut at word boundaries
    f = fold(text)
    pos = min((f.find(b) for b in terms_ if f.find(b) >= 0), default=0)
    # folding shifts positions slightly (ae/oe/ue) - close enough for an excerpt
    start = max(0, pos - n // 3)
    piece = ' '.join(text[start:start + n].split())
    return ('…' if start else '') + piece + ('…' if start + n < len(text) else '')
