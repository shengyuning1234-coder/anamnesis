"""词条迁移格式，保留新版已有的学习进度字段。"""
from datetime import datetime

def export_words(db):
    return {'format': 'anamnesis.words', 'version': 2, 'exported_at': datetime.now().isoformat(),
            'words': [w.to_dict() for w in db.get_all_words()]}

def import_words(db, document, mode='merge', dry_run=False):
    if not isinstance(document, dict) or not isinstance(document.get('words'), list): raise ValueError('无效的词条迁移文件')
    added = updated = skipped = 0
    for item in document['words']:
        text = str(item.get('word', '')).strip()
        if not text: continue
        existing = db.find_word_by_text(text)
        if existing and mode != 'overwrite': skipped += 1; continue
        if not dry_run:
            from models.word import Word
            value = Word.from_dict({**item, 'id': existing.id if existing else None})
            if existing: db.update_word(value); updated += 1
            else: db.add_word(value); added += 1
        elif existing: updated += 1
        else: added += 1
    return {'added': added, 'updated': updated, 'skipped': skipped, 'dry_run': dry_run}
