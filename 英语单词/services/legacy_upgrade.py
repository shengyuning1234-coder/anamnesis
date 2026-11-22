"""Upgrade legacy NAS databases without dropping business records.

Runs before Database creates tables. The original SQLite snapshot is retained,
and incompatible operational tables are archived under legacy_* names.
"""
import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path


def upgrade(path):
    path = Path(path)
    if not path.exists():
        return
    with closing(sqlite3.connect(path)) as c:
        tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'words' not in tables or 'nas_upgrade_history' in tables:
            return
        cols = lambda table: {r[1] for r in c.execute('PRAGMA table_info("' + table + '")')}
        is_legacy = ('schema_migrations' in tables and 'checksum' in cols('schema_migrations'))
        if not is_legacy:
            return
        directory = path.parent / 'backups'
        directory.mkdir(exist_ok=True)
        backup = directory / ('before-nas-v2-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.db')
        with closing(sqlite3.connect(backup)) as target:
            c.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('旧数据库备份校验失败，已停止升级')
        c.execute('PRAGMA foreign_keys=OFF')
        c.execute('BEGIN IMMEDIATE')
        try:
            # Keep historical sessions and sync audit intact. New sessions use a
            # different protocol and must not overwrite historical records.
            for table, required in [('schema_migrations', 'checksum'), ('quiz_sessions', 'owner_key'), ('review_operations', 'operation_id')]:
                if table in tables and required in cols(table):
                    c.execute('ALTER TABLE "' + table + '" RENAME TO "legacy_' + table + '"')
            if 'word_meanings' in tables:
                fields = [('meaning', "TEXT NOT NULL DEFAULT ''"), ('meaning_order', 'INTEGER DEFAULT 0'),
                          ('unlocked', 'INTEGER DEFAULT 0'), ('example_sentence', "TEXT DEFAULT ''"),
                          ('example_translation', "TEXT DEFAULT ''"), ('part_of_speech', "TEXT DEFAULT ''"), ('updated_at', "TEXT DEFAULT ''")]
                existing = cols('word_meanings')
                for name, kind in fields:
                    if name not in existing:
                        c.execute('ALTER TABLE word_meanings ADD COLUMN ' + name + ' ' + kind)
                c.execute("UPDATE word_meanings SET meaning=chinese_meaning,meaning_order=meaning_index-1,unlocked=CASE WHEN unlocked_at<>'' THEN 1 ELSE 0 END")
            for table, field in [('word_confusions', 'confused_word'), ('word_embeddings', 'updated_at')]:
                if table in tables and field not in cols(table):
                    c.execute('ALTER TABLE ' + table + ' ADD COLUMN ' + field + " TEXT DEFAULT ''")
            if 'word_confusions' in tables:
                c.execute('UPDATE word_confusions SET confused_word=confused_with_word')
            c.execute('CREATE TABLE nas_upgrade_history(version TEXT PRIMARY KEY,applied_at TEXT NOT NULL,backup TEXT NOT NULL)')
            c.execute('INSERT INTO nas_upgrade_history VALUES (?,?,?)', ('nas-v2', datetime.now().isoformat(), str(backup)))
            c.commit()
        except Exception:
            c.rollback()
            raise


def legacy_password_exists(data):
    return (Path(data) / '.password').is_file()


def verify_legacy_password(data, password):
    import hashlib
    import hmac
    try:
        parts = (Path(data) / '.password').read_text().strip().split(':')
        if len(parts) == 3:
            salt, iterations, digest = parts
            computed = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(iterations)).hex()
        elif len(parts) == 2:
            salt, digest = parts
            computed = hashlib.sha256((salt + ':' + password).encode()).hexdigest()
        else:
            return False
        return hmac.compare_digest(computed, digest)
    except (OSError, ValueError):
        return False
