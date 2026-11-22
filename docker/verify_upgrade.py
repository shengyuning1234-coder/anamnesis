"""Record/compare nonvolatile WebUI state hashes without revealing credentials.

Run before stopping the old image, then check after starting the new one.
Only the two integration credentials intentionally rotated at startup are ignored.
"""
import argparse
import hashlib
import json
import os
import sqlite3
from pathlib import Path


def snapshot(root):
    state = {}
    state['session_keys'] = [hashlib.sha256(path.read_bytes()).hexdigest() for path in (
        root/'.webui_secret_key',
        Path(os.environ.get('APP_DATA_DIR', '/data/words'))/'.session-secret')]
    with sqlite3.connect(root/'webui.db') as db:
        for table in ('user', 'auth', 'chat', 'memory', 'model', 'file', 'knowledge'):
            columns = [row[1] for row in db.execute('PRAGMA table_info("'+table+'")')
                       if row[1] not in ('last_active_at', 'updated_at', 'last_read_at')]
            rows = list(db.execute('SELECT '+','.join('"'+c+'"' for c in columns)+' FROM "'+table+'"'))
            encoded = sorted(json.dumps(row, ensure_ascii=False, default=str) for row in rows)
            state[table] = {'count':len(rows), 'sha256':hashlib.sha256('\n'.join(encoded).encode()).hexdigest()}
        config = {}
        for key, raw in db.execute('SELECT key,value FROM config'):
            if key in ('web.search.external_web_search_api_key', 'rag.openai.api_key'):
                continue
            value = json.loads(raw) if isinstance(raw, str) else raw
            if key == 'rag.embedding.openai' and isinstance(value, dict):
                value.pop('key', None)
            # This value uses separate keys in some WebUI schemas.
            if key == 'rag.embedding.openai.key':
                continue
            config[key] = value
        state['config'] = {key:hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
                           for key, value in config.items()}
    return state


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('record', 'check'))
    parser.add_argument('path', type=Path)
    args = parser.parse_args()
    state = snapshot(Path(os.environ.get('DATA_DIR', '/data/openwebui')))
    if args.mode == 'record':
        args.path.write_text(json.dumps(state, sort_keys=True), encoding='utf-8')
        print('Recorded existing account, settings, provider, chat, memory and knowledge fingerprints')
    else:
        previous = json.loads(args.path.read_text(encoding='utf-8'))
        changed = [key for key in set(previous)|set(state) if previous.get(key) != state.get(key)]
        if changed:
            if 'config' in changed:
                print('Changed config names:', ', '.join(key for key in set(previous['config'])|set(state['config'])
                    if previous['config'].get(key) != state['config'].get(key)))
            raise SystemExit('Upgrade state differs: '+', '.join(changed))
        print('PASS existing accounts, settings, model connections, chats, memories and knowledge preserved')


if __name__ == '__main__':
    main()
