"""Exercise the historical NAS schema on a temporary copy only."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing


class NasUpgradeTests(unittest.TestCase):
    def test_old_database_upgrade_preserves_records_and_login(self):
        source_path = os.environ.get('ANAMNESIS_LEGACY_DB')
        if not source_path or not (source := Path(source_path).resolve()).is_file():
            self.skipTest('Set ANAMNESIS_LEGACY_DB to a legacy NAS database')
        with tempfile.TemporaryDirectory(prefix='nas-upgrade-') as directory:
            target = Path(directory) / 'words.db'
            with closing(sqlite3.connect('file:' + str(source) + '?mode=ro', uri=True)) as src, closing(sqlite3.connect(target)) as dst:
                src.backup(dst)
                original = {table: src.execute('SELECT * FROM ' + table + ' ORDER BY id').fetchall() for table in ('words', 'review_logs', 'word_books', 'word_meanings')}
            password = 'nas-upgrade-test-password'
            digest = hashlib.pbkdf2_hmac('sha256', password.encode(), b'0123456789abcdef', 100000).hex()
            (Path(directory) / '.password').write_text(b'0123456789abcdef'.hex() + ':100000:' + digest)
            program = '''
import application as a, json
client=a.app.test_client()
assert client.get('/api/words').status_code == 401
assert client.post('/api/auth/setup',json={'password':'replacement-password'}).status_code == 409
assert client.post('/api/auth/login',json={'password':'wrong-password'}).status_code == 401
assert client.post('/api/auth/login',json={'password':'nas-upgrade-test-password'}).status_code == 200
assert client.get('/api/words').status_code == 200
with a.conn() as c:
    assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert not c.execute('PRAGMA foreign_key_check').fetchall()
    wid=c.execute('SELECT id FROM words ORDER BY id').fetchone()[0]
mid=a.db.add_meaning(wid,'NAS compatibility test')
assert any(m['id']==mid for m in a.db.get_meanings_by_word_id(wid))
assert client.post('/api/review/'+str(wid),json={'rating':4}).status_code==200
'''
            result = subprocess.run([sys.executable, '-c', program], cwd=Path(__file__).parent, env={**os.environ, 'APP_DATA_DIR': directory}, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            with closing(sqlite3.connect(target)) as c:
                for table in ('words', 'review_logs', 'word_books', 'word_meanings'):
                    rows=c.execute('SELECT * FROM ' + table + ' ORDER BY id').fetchall()
                    self.assertGreaterEqual(len(rows),len(original[table]))
                self.assertEqual(len(c.execute('SELECT * FROM words').fetchall()),len(original['words']))
            backups=list((Path(directory)/'backups').glob('before-nas-v2-*.db'))
            self.assertEqual(len(backups),1)
            with closing(sqlite3.connect(backups[0])) as c:
                for table, rows in original.items():
                    self.assertEqual(c.execute('SELECT * FROM '+table+' ORDER BY id').fetchall(),rows)
            result=subprocess.run([sys.executable,'-c',"import application; print('restart ok')"],cwd=Path(__file__).parent,env={**os.environ,'APP_DATA_DIR':directory},capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(len(list((Path(directory)/'backups').glob('before-nas-v2-*.db'))),1)

if __name__=='__main__': unittest.main()
