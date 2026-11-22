"""Local vocabulary MCQs: reject ambiguous options before ranking plausibility.

WordNet morphology, derivations and synsets + bilingual sense overlap +
part-of-speech/frequency matching. No network or personal-word-list sampling.
"""
from contextlib import closing
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
import math
import random
import re
import sqlite3
import threading
import unicodedata
from . import lexicon

def canonical_spelling(text):
    return text.replace('isation','ization').replace('ise','ize').replace('our','or').replace('-', '').replace(' ', '')


_LOCK = threading.RLock()  # WordNet's seek-based corpus reader is shared by request threads.


def spelling(text):
    return unicodedata.normalize('NFKC', text).casefold().replace('’', "'").strip()


@lru_cache(maxsize=1)
def wordnet():
    from nltk.corpus.reader import WordNetCorpusReader
    from nltk.data import ZipFilePathPointer
    archive = lexicon.PATH.parent / 'wordnet.zip'
    class EnglishWordNet(WordNetCorpusReader):
        # Only the pinned English corpus is needed; disable multilingual mappings
        # that would otherwise require an unrelated global NLTK installation.
        def map_wn(self, version='wordnet'):
            return None
    return EnglishWordNet(ZipFilePathPointer(str(archive), 'wordnet/'), None) if archive.exists() else None


@lru_cache(maxsize=8192)
def lexical_signature(text):
    """Return lemmas, derived forms, synsets and stems for all parts of speech."""
    from nltk.stem.snowball import EnglishStemmer
    stemmer = EnglishStemmer()
    text = spelling(text).replace(' ', '_')
    family = {text}
    synsets = set()
    with _LOCK:
        wn = wordnet()
        if wn:
            # All morphological analyses, including irregular verbs and plurals.
            for pos in ('n', 'v', 'a', 'r'):
                family.update(wn._morphy(text, pos))
            for base in tuple(family):
                for sense in wn.synsets(base):
                    synsets.add(sense.name())
                    for lemma in sense.lemmas():
                        if lemma.name().casefold() == base:
                            family.update(r.name().casefold() for r in lemma.derivationally_related_forms())
    stems = {stemmer.stem(canonical_spelling(x.replace('_', ' '))) for x in family}
    family = {canonical_spelling(x) for x in family}
    return frozenset(family), frozenset(synsets), frozenset(stems)


@lru_cache(maxsize=8192)
def ancestor_senses(word):
    # Direct general/specific terms can both fit a bare gloss (teacher/lecturer).
    with _LOCK:
        wn=wordnet()
        return frozenset(parent.name() for sense in wn.synsets(spelling(word).replace(' ','_'))
                         for parent in sense.hypernyms()) if wn else frozenset()


def english_conflict(left, right):
    a, b = spelling(left), spelling(right)
    if a == b:
        return True
    af, ass, ast = lexical_signature(a)
    bf, bss, bst = lexical_signature(b)
    aa, ba = ancestor_senses(a), ancestor_senses(b)
    # WordNet models teacher/lecturer as sibling educator roles; bare Chinese
    # glosses 教师/讲师 still overlap too much for this vocabulary exercise.
    overlapping_roles = aa & ba & {'educator.n.01'}
    if af & bf or ast & bst or ass & bss or ass & ba or bss & aa or overlapping_roles:
        return True
    # UK/US spelling and almost identical forms must not be the whole challenge.
    a, b = canonical_spelling(a), canonical_spelling(b)
    if a == b or (min(len(a),len(b)) >= 4 and SequenceMatcher(None,a,b).ratio() >= .8):
        return True
    return False


def chinese_senses(text):
    text = unicodedata.normalize('NFKC', text or '').lower()
    # Parenthetical labels, POS and enumeration do not make distinct meanings.
    text = re.sub(r'\([^)]*\)|（[^）]*）|\[[^]]*\]|【[^】]*】', '', text)
    parts = re.split(r'[,，;；\n/、。:：]', text)
    result = set()
    for part in parts:
        part = ''.join(re.findall(r'[\u4e00-\u9fff]', part))
        if part.endswith(('的','地')) and len(part)>2:
            part=part[:-1]
        if part:
            result.add(part)
    return frozenset(result)


def chinese_conflict(left, right):
    """Compare every sense, not just the displayed first definition."""
    for a in chinese_senses(left):
        for b in chinese_senses(right):
            if a == b or (min(len(a),len(b)) >= 2 and (a in b or b in a)):
                return True
            if min(len(a),len(b)) >= 2:
                ratio = SequenceMatcher(None,a,b).ratio()
                overlap = len(set(a)&set(b))/max(1,min(len(set(a)),len(set(b))))
                # Filter one-character polarity/direction variants, not useful pairs
                # like 教师/律师 that merely share a suffix.
                changes = [frozenset((x,y)) for x,y in zip(a,b) if x != y]
                modifiers = {frozenset(pair) for pair in ('有无','不有','上下','大小','高低','冷热','多少','内外','前后','左右','真假','正反','开关','进出')}
                tiny_variant = len(a) == len(b) == 2 and len(changes) == 1 and changes[0] in modifiers
                if tiny_variant or ratio >= .65 or (min(len(a),len(b)) >= 3 and overlap >= .75):
                    return True
    return False


_POS_SHORT = r'(?:adj|adv|prep|pron|conj|det|aux|interj|int|num|art|abbr|suff?|pref|comb\.form|comb|na|un|pl|vi|vt|v|n|a)'
_POS_LONG = (
    r'(?:noun|verb|adjective|adverb|preposition|pronoun|conjunction|determiner|'
    r'interjection|numeral|article|名词|动词|形容词|副词|介词|代词|连词|冠词|数词|助词|感叹词|叹词|短语)'
)
_POS_LABEL = rf'(?:{_POS_SHORT}[.．]?|{_POS_LONG})'
_POS_LIST = rf'{_POS_LABEL}(?:\s*(?:[/／&,，、+＋]|\band\b)\s*{_POS_LABEL})*'
_POS_WRAPPED = rf'(?:[(（]\s*{_POS_LIST}\s*[)）]|[\[［【]\s*{_POS_LIST}\s*[\]］】]|<\s*{_POS_LIST}\s*>)'
_POS_MARKER = (
    rf'{_POS_WRAPPED}|{_POS_LIST}\s*[:：]|'
    rf'{_POS_SHORT}[.．]|{_POS_LONG}(?:[.．]|(?=\s|$))|'
    rf'{_POS_SHORT}(?=\s+[\u3400-\u9fff]|$)'
)
_POS_IN_GLOSS = re.compile(
    rf'(^|[,，、/／]\s*)(?:\s*(?:[①-⑳]|\d+[.)、]|[·•])\s*)?'
    rf'(?:{_POS_MARKER})(?:\s*[/／&,，、+＋]\s*(?:{_POS_MARKER}))*\s*',
    re.I,
)
_WRAPPED_POS_IN_GLOSS = re.compile(_POS_WRAPPED, re.I)


def first_meaning(text):
    for gloss in re.split(r'[\r\n；;]+|\\n', text or ''):
        gloss = re.sub(r'^\s*(?:[①-⑳]|\d+[.)、]|[·•-])\s*', '', gloss.strip())
        gloss = _POS_IN_GLOSS.sub(r'\1', gloss).strip()
        gloss = _WRAPPED_POS_IN_GLOSS.sub('', gloss).strip()
        if gloss:
            return gloss[:60]
    return ''


def parts_of_speech(pos, meaning=''):
    # POS labels only: the English article "a" inside a definition is NOT adj.
    mapping={'n':'n','noun':'n','名词':'n','v':'v','vi':'v','vt':'v','verb':'v','动词':'v',
             'a':'a','s':'a','adj':'a','adjective':'a','形容词':'a','r':'r','adv':'r','adverb':'r','副词':'r','prep':'p','preposition':'p','pron':'p','pronoun':'p','det':'p','conj':'p','interj':'p','aux':'p'}
    explicit=[mapping[x] for x in re.findall(r'[a-z]+|[\u4e00-\u9fff]+',pos.lower()) if x in mapping]
    if explicit:return frozenset(explicit[:1])
    for line in meaning.splitlines():
        line=re.sub(r'^\s*(?:[①-⑳]|\d+[.)、])\s*','',line.lower().strip())
        match=re.match(r'^(noun|verb|adjective|adverb|preposition|pronoun|interj|prep|pron|conj|det|aux|adj|adv|vi|vt|n|v|a|s|名词|动词|形容词|副词)(?:[.\s:：]|$)',line)
        if match:return frozenset([mapping[match[1]]])
    return frozenset()


@lru_cache(maxsize=4096)
def lexical_topics(word, pos=None):
    with _LOCK:
        wn=wordnet()
        return frozenset(s.lexname() for s in wn.synsets(spelling(word).replace(' ','_'), pos=pos)[:1]) if wn else frozenset()


@lru_cache(maxsize=4096)
def sibling_words(word, pos=None):
    """WordNet co-hyponyms: related category, distinct sense (e.g. fruits)."""
    names=set()
    with _LOCK:
        wn=wordnet()
        if wn:
            for sense in wn.synsets(spelling(word).replace(' ','_'), pos=pos)[:1]:
                for parent in sense.hypernyms():
                    for sibling in parent.hyponyms():
                        if sibling != sense:
                            for lemma in sibling.lemmas():
                                # Reject obscure alternate senses: 'jack' is a fruit
                                # only in a minor sense; its displayed gloss is not.
                                primary = wn.synsets(lemma.name())[:1]
                                if sibling in primary:
                                    names.add(lemma.name().replace('_', ' '))
    return frozenset(names)


@dataclass(frozen=True)
class Candidate:
    word: str
    meaning: str
    pos: frozenset
    rank: int = 10000
    tags: frozenset = frozenset()


def prominent_pos(word, pos):
    """Discard rare POS readings such as natural='白痴' instead of adjective."""
    counts={}
    with _LOCK:
        wn=wordnet()
        if not wn:return False
        for sense in wn.synsets(word):
            category='a' if sense.pos()=='s' else sense.pos()
            counts[category]=counts.get(category,0)+sum(lemma.count() for lemma in sense.lemmas() if lemma.name().casefold()==word)
    highest=max(counts.values(),default=0)
    return highest<5 or counts.get(pos,0)>=highest*.2


@lru_cache(maxsize=1)
def candidate_pool():
    if not lexicon.PATH.exists(): return ()
    with closing(sqlite3.connect(lexicon.PATH.as_uri()+'?mode=ro',uri=True)) as c:
        rows=c.execute("SELECT word,translation,pos,definition,bnc,frq,tag FROM entries WHERE translation<>'' AND ((bnc>0 AND bnc<=30000) OR (frq>0 AND frq<=30000) OR tag<>'')").fetchall()
    result=[]
    for word,zh,pos,en,bnc,frq,tag in rows:
        if not re.fullmatch(r'[a-z]+(?:[ -][a-z]+){0,2}',word) or len(word)>32:continue
        if re.search(r'过去式|过去分词|现在分词|复数|第三人称|的变形',zh):continue
        ranks=[v for v in [bnc,frq] if v>0]
        primary=parts_of_speech('',zh) or parts_of_speech(pos,en)
        if not primary or not prominent_pos(word,next(iter(primary))):continue
        result.append(Candidate(word,zh,primary,min(ranks) if ranks else 20000,frozenset(tag.split())))
    return tuple(result)


@lru_cache(maxsize=1)
def topic_pool():
    """Index prominent senses, so a teacher gets people rather than random nouns."""
    groups={}
    for candidate in candidate_pool():
        if not candidate.pos or 'p' in candidate.pos:continue
        pos=next(iter(candidate.pos))
        for topic in lexical_topics(candidate.word,pos):
            groups.setdefault(topic,[]).append(candidate)
    return {key:tuple(values) for key,values in groups.items()}


@lru_cache(maxsize=4096)
def reference(word):
    data=lexicon.query(word)
    return data.get('entry',{}) if data else {}


def choose(word, meaning, pos='', count=3):
    """Hard exclusion then bounded ranking, including pairwise option checks."""
    with _LOCK:
        if wordnet() is None:return []  # No unsafe fallback if lexical safeguards are missing.
    entry=reference(word)
    target_pos=parts_of_speech(pos,meaning) or parts_of_speech(entry.get('pos',''),entry.get('translation','')+'\n'+entry.get('definition',''))
    target_tags=set(entry.get('tag','').split())
    ranks=[entry.get(k,0) for k in ('bnc','frq') if entry.get(k,0)>0]
    rank=min(ranks) if ranks else 5000
    # Include the full dictionary entry so a hidden second sense cannot be another answer.
    full_meaning=meaning+'\n'+entry.get('translation','')
    pool=[c for c in candidate_pool() if c.word!=spelling(word) and (not target_pos or c.pos & target_pos)
          and (' ' in c.word)==(' ' in word)]
    # Never reward maximal spelling resemblance. Prefer familiar peers of similar POS/difficulty.
    def score(c):
        return (abs(math.log((c.rank+100)/(rank+100)))
                + .10*abs(len(c.word)-len(word))
                - .4*bool(target_tags & c.tags) + random.random()*.8)
    primary_pos=next(iter(target_pos), None)
    if primary_pos not in ('n','v','a','r'):return []
    siblings=sibling_words(word,primary_pos)
    topics=lexical_topics(word,primary_pos)
    eligible_words={c.word for c in pool}
    topic_words=[c for topic in topics for c in topic_pool().get(topic,()) if c.word in eligible_words]
    topical=random.sample(topic_words,min(1200,len(topic_words)))
    related=[c for c in pool if c.word in siblings and abs(math.log((c.rank+100)/(rank+100)))<4]
    candidates=sorted(list({c.word:c for c in random.sample(pool,min(1200,len(pool)))+related+topical}.values()),key=score)
    # WordNet's broad lexical domains add topic plausibility without treating
    # synonyms (which are rejected below) as good distractors.
    shortlist=list({c.word:c for c in candidates[:100]+related}.values())
    random_ties={c.word:random.random()*.3 for c in shortlist}
    shortlist.sort(key=lambda c: abs(math.log((c.rank+100)/(rank+100)))
                   + .1*abs(len(c.word)-len(word)) - 3.0*bool(topics & lexical_topics(c.word,primary_pos)) - 4.0*(c.word in siblings)
                   + random_ties[c.word])
    selected=[]
    for c in shortlist+candidates[100:400]:
        if not first_meaning(c.meaning) or len(first_meaning(c.meaning))>max(35,len(first_meaning(meaning))*3):continue
        if english_conflict(word,c.word) or chinese_conflict(full_meaning,c.meaning):continue
        if any(english_conflict(c.word,other.word) or chinese_conflict(c.meaning,other.meaning) for other in selected):continue
        selected.append(c)
        if len(selected)==count:break
    return [{'word':c.word,'meaning':c.meaning} for c in selected]
