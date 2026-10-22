# State and search index in .hub/hub.db (SQLite, WAL). files, notes and
# search are only a cache of the Markdown files ("codehub index --rebuild");
# sessions, traces, prompts, commits, subagents and counters are the record
# of what happened. Without sqlite3 the hub still answers from the maps.
import os
from contextlib import contextmanager

from . import vault

VERSION = 2
SCHEMA = '''
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS files(project TEXT, path TEXT, topic TEXT, description TEXT,
    also TEXT, PRIMARY KEY(project, path));
CREATE TABLE IF NOT EXISTS notes(path TEXT PRIMARY KEY, project TEXT, kind TEXT, title TEXT,
    tags TEXT, links TEXT, files TEXT, mtime REAL);
CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, project TEXT, title TEXT, start REAL,
    last REAL, end REAL, cwd TEXT, transcript TEXT, offset INTEGER DEFAULT 0, last_message TEXT,
    t_in INTEGER DEFAULT 0, t_out INTEGER DEFAULT 0, t_cache_read INTEGER DEFAULT 0,
    t_cache_write INTEGER DEFAULT 0, compact TEXT, answer TEXT, note TEXT, state TEXT);
CREATE TABLE IF NOT EXISTS traces(session TEXT, project TEXT, path TEXT, kind TEXT, n INTEGER,
    time REAL, PRIMARY KEY(session, path, kind));
CREATE TABLE IF NOT EXISTS prompts(session TEXT, time REAL, text TEXT);
CREATE TABLE IF NOT EXISTS commits(session TEXT, time REAL, hash TEXT, text TEXT,
    PRIMARY KEY(session, hash));
CREATE TABLE IF NOT EXISTS subagents(session TEXT, id TEXT, type TEXT, task TEXT,
    result TEXT, start REAL, end REAL, PRIMARY KEY(session, id));
CREATE TABLE IF NOT EXISTS suggestions(session TEXT, path TEXT, time REAL, PRIMARY KEY(session, path));
CREATE TABLE IF NOT EXISTS counters(day TEXT, kind TEXT, n INTEGER, PRIMARY KEY(day, kind));
CREATE INDEX IF NOT EXISTS prompts_s ON prompts(session);
'''
# Folded columns: title, path/topic words, text. Only searched; what is shown
# comes from the tables or the note files.
SEARCH_FTS = ("CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(kind UNINDEXED, project UNINDEXED, "
              "ref UNINDEXED, ft, fw, fx, tokenize='unicode61 remove_diacritics 2')")
SEARCH_PLAIN = 'CREATE TABLE IF NOT EXISTS search(kind TEXT, project TEXT, ref TEXT, ft TEXT, fw TEXT, fx TEXT)'

# Counter kinds: lookup, auto (prompt hook), search, free (grep/glob/find),
# read, hit (read a file the hub named), tok_in/out/cache_read/cache_write
TOKEN_COUNTERS = ('tok_in', 'tok_out', 'tok_cache_read', 'tok_cache_write')


class NoIndex(Exception):
    pass


_db = None
FTS = False


def db():
    global _db, FTS
    if _db is not None:
        return _db
    try:
        import sqlite3
    except ImportError as e:
        raise NoIndex('sqlite3 missing') from e
    os.makedirs(vault.INTERNAL, exist_ok=True)
    try:
        c = sqlite3.connect(os.path.join(vault.INTERNAL, 'hub.db'), timeout=5, isolation_level=None)
        c.execute('PRAGMA journal_mode=WAL')
        c.execute('PRAGMA synchronous=NORMAL')
        version = c.execute('PRAGMA user_version').fetchone()[0]
        if version < VERSION:
            c.execute('BEGIN IMMEDIATE')
            try:
                # another process may have finished it while we waited
                if c.execute('PRAGMA user_version').fetchone()[0] < VERSION:
                    from . import migrate
                    old = migrate.set_aside(c)
                    # one by one: executescript() would commit the open transaction
                    for statement in SCHEMA.split(';'):
                        if statement.strip():
                            c.execute(statement)
                    if old:
                        migrate.copy(c, old)
                    c.execute(f'PRAGMA user_version={VERSION}')
                c.execute('COMMIT')
            except BaseException:
                c.execute('ROLLBACK')
                raise
        try:
            c.execute(SEARCH_FTS)
        except sqlite3.OperationalError:
            c.execute(SEARCH_PLAIN)     # no FTS5: plain table, searched in Python
        sql = c.execute("SELECT sql FROM sqlite_master WHERE name='search'").fetchone()[0] or ''
        FTS = 'fts5' in sql.lower()
    except sqlite3.Error as e:
        raise NoIndex(str(e)) from e
    _db = c
    return c


def close():
    global _db
    if _db is not None:
        try:
            _db.close()
        except Exception:
            pass        # opened by another thread (the web view's worker)
        _db = None


@contextmanager
def transaction():
    c = db()
    c.execute('BEGIN IMMEDIATE')
    try:
        yield c
    except BaseException:
        c.execute('ROLLBACK')
        raise
    c.execute('COMMIT')


def meta(k, v=None):
    c = db()
    if v is None:
        r = c.execute('SELECT v FROM meta WHERE k=?', (k,)).fetchone()
        return r[0] if r else None
    c.execute('INSERT OR REPLACE INTO meta VALUES(?,?)', (k, str(v)))


def count(kind, n=1, day=None):
    try:
        db().execute('INSERT INTO counters VALUES(?,?,?) ON CONFLICT(day, kind) DO UPDATE SET n=n+excluded.n',
                     (day or vault.today(), kind, n))
    except Exception:
        pass        # a counter is never worth an error
