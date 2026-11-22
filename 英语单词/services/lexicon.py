"""Read-only public lexicons. Missing labels are unknown, never negative evidence."""
import sqlite3
import json
from pathlib import Path

PATH=Path(__file__).resolve().parents[1]/'resources'/'lexicons'/'lexicons.sqlite3'
TAG_MAP={'zk':'初中','gk':'高中','cet4':'四级','cet6':'六级','ky':'考研','ielts':'雅思','toefl':'托福','tem4':'专四','tem8':'专八'}

def status():
    manifest=PATH.parent/'sources.json'
    return {'available':PATH.exists(),'counts':json.loads(manifest.read_text(encoding='utf-8')).get('counts',{}) if manifest.exists() else {}}

def query(word):
    if not PATH.exists():return None
    key=' '.join(word.lower().split())
    with sqlite3.connect(PATH.as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        row=db.execute('SELECT * FROM entries WHERE word=?',(key,)).fetchone()
        english=[dict(r) for r in db.execute('SELECT pos,gloss FROM wordnet WHERE word=? ORDER BY pos,gloss',(key,))]
        labels=[dict(r) for r in db.execute('SELECT label,source FROM labels WHERE word=?',(key,))]
    entry=dict(row) if row else {}
    tags=[TAG_MAP[t] for t in entry.get('tag','').split() if t in TAG_MAP]
    evidence=[{'label':t,'source':'ECDICT:tag'} for t in tags]+labels
    # Frequency is intentionally not converted into school/exam or domain labels.
    return {'entry':entry,'wordnet':english,'tags':list(dict.fromkeys(tags+[r['label'] for r in labels])),'classification_evidence':evidence} if entry or english or labels else None

def local_tags(word):
    data=query(word)
    return data['tags'] if data else []

def build_record(word,primary):
    """Prefer paired senses; auxiliary dictionaries stay explicitly unaligned."""
    supplemental=query(word) or {};ec=supplemental.get('entry',{})
    primary=primary or {}
    senses=primary.get('senses',[])
    primary_zh=primary.get('chinese_meaning','').strip()
    primary_en=primary.get('english_meaning','').strip()
    paired=bool(primary_zh and primary_en)
    ec_paired=bool(ec.get('translation') and ec.get('definition'))
    # Paired primary dictionary > bilingual ECDICT > primary monolingual > ECDICT.
    use_primary=bool(primary_zh or primary_en) and (paired or not ec_paired)
    zh=primary_zh if use_primary else ec.get('translation','')
    en=primary_en if use_primary else ec.get('definition','')
    sources=[];notes=[];references=[]
    if primary_zh or primary_en:
        references.append({'source':'已有本地双解词典','chinese':primary_zh,'english':primary_en,'senses':senses})
        if use_primary:sources.append('已有本地双解词典')
    if ec.get('translation') or ec.get('definition'):
        references.append({'source':'ECDICT','chinese':ec.get('translation',''),'english':ec.get('definition','')})
        if not use_primary:sources.append('ECDICT')
    if not zh:zh=ec.get('translation','') or primary_zh
    if not en:en=ec.get('definition','') or primary_en
    if not en and supplemental.get('wordnet'):
        en='\n'.join(f"[{r['pos']}] {r['gloss']}" for r in supplemental['wordnet'])
        sources.append('WordNet 3.0（英英补充，未与中文逐义对齐）')
    if supplemental.get('wordnet'):references.append({'source':'WordNet 3.0','definitions':supplemental['wordnet']})
    if not zh and not en:return None
    if use_primary and paired and senses:
        notes.append('双解原文（按词典义项）\n'+'\n\n'.join(f"{i+1}. {s['chinese']}\n{s['english']}" for i,s in enumerate(senses) if s['chinese'] or s['english']))
    elif en:notes.append('英文释义原文（与中文不保证逐条对应）\n'+en)
    for title,key in [('搭配','collocations'),('近义词','synonyms'),('词源','word_origin')]:
        if primary.get(key):notes.append(title+'：'+primary[key])
    related=primary.get('related_senses',[])
    if related:notes.append('相关短语（不作为该单词本义）\n'+'\n\n'.join(s['phrase']+'\n'+s['chinese']+'\n'+s['english'] for s in related))
    notes.append('词典来源：'+'；'.join(dict.fromkeys(sources or ['ECDICT'])))
    examples=primary.get('examples',[])[:8] if use_primary else []
    return {'word':word,'phonetic':(primary.get('phonetic','') or ec.get('phonetic','')) if use_primary else (ec.get('phonetic','') or primary.get('phonetic','')),'part_of_speech':(primary.get('part_of_speech','') or ec.get('pos','')) if use_primary else ec.get('pos',''),
            'chinese_meaning':zh,'english_meaning':en,'example_sentence':'\n'.join(x[0] for x in examples),'example_translation':'\n'.join(x[1] for x in examples),
            'notes':'\n\n'.join(notes),'source':'local','dictionary_sources':list(dict.fromkeys(sources)),
            'dictionary_references':references,'classification_evidence':supplemental.get('classification_evidence',[])}
