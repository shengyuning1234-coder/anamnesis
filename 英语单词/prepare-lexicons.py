"""Fetch pinned public lexical resources and atomically build an offline SQLite index."""
import csv, hashlib, io, json, re, sqlite3, urllib.request, urllib.parse, zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent/'resources'/'lexicons'
ROOT.mkdir(parents=True,exist_ok=True)
SOURCES=[]
def fetch(repo,rev,name,target=None):
    url=f'https://raw.githubusercontent.com/{repo}/{rev}/'+urllib.parse.quote(name)
    path=ROOT/(target or Path(name).name)
    if not path.exists():
        temp=path.with_suffix(path.suffix+'.download')
        with urllib.request.urlopen(url,timeout=180) as response, temp.open('wb') as out:
            while chunk:=response.read(1024*1024):out.write(chunk)
        temp.replace(path)
    SOURCES.append({'repository':repo,'revision':rev,'url':url,'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size})
    return path

ec='bc015ed2e24a7abef49fc6dbbb7fe32c1dadaf8b'
csv_path=fetch('skywind3000/ECDICT',ec,'ecdict.csv')
fetch('skywind3000/ECDICT',ec,'LICENSE','ECDICT-LICENSE.txt')
fetch('skywind3000/ECDICT',ec,'README.md','ECDICT-README.md')
wl='395cebd583d97be61b065d281d16dc49c7e4a8b0'
primary=fetch('mahavivo/english-wordlists',wl,'小学英语大纲词汇.txt','primary.txt')
tem8=fetch('mahavivo/english-wordlists',wl,'英语专业星标八级词汇.txt','tem8.txt')
fetch('mahavivo/english-wordlists',wl,'README.md','wordlists-README.md')
wn_rev='550b6625bcef1f2abff2ff770a5a0d272c9c6b2a'
wn=fetch('nltk/nltk_data',wn_rev,'packages/corpora/wordnet.zip','wordnet.zip')
temp=ROOT/'lexicons.build.sqlite3'
if temp.exists():temp.unlink()
db=sqlite3.connect(temp)
db.executescript('CREATE TABLE entries(word TEXT PRIMARY KEY,phonetic TEXT,definition TEXT,translation TEXT,pos TEXT,tag TEXT,bnc INTEGER,frq INTEGER); CREATE TABLE labels(word TEXT,label TEXT,source TEXT,PRIMARY KEY(word,label)); CREATE TABLE wordnet(word TEXT,pos TEXT,gloss TEXT,PRIMARY KEY(word,pos,gloss));')
def number(value):
    try:return int(value)
    except (ValueError,TypeError):return 0
with csv_path.open(encoding='utf-8-sig',newline='') as stream:
    for row in csv.DictReader(stream):
        db.execute('INSERT OR IGNORE INTO entries VALUES (?,?,?,?,?,?,?,?)',(' '.join(row['word'].lower().split()),row['phonetic'],row['definition'].replace('\\n','\n'),row['translation'].replace('\\n','\n'),row['pos'],row['tag'],number(row['bnc']),number(row['frq'])))
for path,label in [(primary,'小学'),(tem8,'专八')]:
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        word=line.strip() if label=='小学' else line.split('[')[0].strip()
        if re.fullmatch(r"[A-Za-z]+(?:[ '-][A-Za-z]+)*",word):db.execute('INSERT OR IGNORE INTO labels VALUES (?,?,?)',(word.lower(),label,'mahavivo/english-wordlists:'+path.name))
with zipfile.ZipFile(wn) as archive:
    (ROOT/'WordNet-LICENSE.txt').write_bytes(archive.read('wordnet/LICENSE'))
    for pos in ['noun','verb','adj','adv']:
        for line in archive.read('wordnet/data.'+pos).decode('utf-8').splitlines():
            if not line or not line[0].isdigit() or '|' not in line:continue
            fields,gloss=line.split('|',1);parts=fields.split();count=int(parts[3],16)
            for i in range(count):
                word=parts[4+i*2].split('(')[0].replace('_',' ').lower()
                db.execute('INSERT OR IGNORE INTO wordnet VALUES (?,?,?)',(word,pos,gloss.strip()))
db.commit()
counts={table:db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in ['entries','labels','wordnet']}
db.close();temp.replace(ROOT/'lexicons.sqlite3')
(ROOT/'sources.json').write_text(json.dumps({'sources':SOURCES,'counts':counts,'wordlist_license':'No explicit license in upstream wordlists; retained locally with provenance; review before redistribution.'},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(counts))
