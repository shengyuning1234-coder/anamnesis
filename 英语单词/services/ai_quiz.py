"""AI writes context; dictionary-backed options and answers remain locally checked."""
import random
import re
from . import distractors as d
from .ai_client import complete, AIError
from .quiz_prompt import SYSTEM, build_quiz_prompt


def generate(word, direction):
    if direction not in ('en2cn', 'cn2en'):
        raise AIError('AI 出题方向无效')
    if not word.chinese_meaning.strip():
        raise AIError('词条缺少可靠释义')
    candidates = d.choose(word.word, word.chinese_meaning, word.part_of_speech, 12)
    if len(candidates) < 3:
        raise AIError('本地合格候选不足')
    result = complete(build_quiz_prompt(word.word, word.chinese_meaning,
                      word.part_of_speech, direction, candidates, word.example_sentence),
                      system=SYSTEM, max_tokens=1400, timeout=25, attempts=2, scene='quiz')
    if not isinstance(result, dict) or result.get('unable'):
        raise AIError('AI 无法确认唯一答案')
    sentence, explanation, choices = (result.get(k) for k in ('sentence', 'explanation', 'distractors'))
    if not isinstance(sentence, str) or not 8 <= len(sentence.split()) <= 30 or len(sentence) > 500:
        raise AIError('AI 语境句格式不合格')
    if not re.fullmatch(r"[A-Za-z0-9\s.,!?;:'\"()’—–\-/]+", sentence) or '____' in sentence:
        raise AIError('AI 语境句包含非英文内容或预填空位')
    if not isinstance(explanation, str) or not explanation.strip() or len(explanation) > 1800:
        raise AIError('AI 未提供有效解析')
    if not isinstance(choices, list) or len(choices) != 3 or any(not isinstance(x, str) for x in choices) or len(set(choices)) != 3:
        raise AIError('AI 干扰项数量或格式不合格')
    allowed = {c['word']: c for c in candidates}
    if any(x not in allowed for x in choices):
        raise AIError('AI 选项超出已校验的本地候选')
    selected = [allowed[x] for x in choices]
    full_meaning = word.chinese_meaning + '\n' + d.reference(word.word).get('translation', '')
    for i, candidate in enumerate(selected):
        if d.english_conflict(word.word, candidate['word']) or d.chinese_conflict(full_meaning, candidate['meaning']):
            raise AIError('AI 选项与答案含义重叠')
        if any(d.english_conflict(candidate['word'], other['word']) or d.chinese_conflict(candidate['meaning'], other['meaning']) for other in selected[:i]):
            raise AIError('AI 干扰项存在近重复')
    target = re.compile(r'(?<![A-Za-z])' + re.escape(word.word) + r'(?![A-Za-z])', re.I)
    if len(target.findall(sentence)) != 1:
        raise AIError('AI 语境句必须恰好包含一次目标词原形')
    correct = word.word if direction == 'cn2en' else d.first_meaning(word.chinese_meaning)
    options = [c['word'] if direction == 'cn2en' else d.first_meaning(c['meaning']) for c in selected] + [correct]
    if len(set(options)) != 4:
        raise AIError('AI 选项显示内容重复')
    random.shuffle(options)
    context = target.sub('____', sentence) if direction == 'cn2en' else sentence
    task = f'选择符合语境和词义「{d.first_meaning(word.chinese_meaning)}」的英文单词' if direction == 'cn2en' else f'选择「{word.word}」在句中的意思'
    return {'type': 'choice', 'mode': 'choice_' + direction, 'word_id': word.id,
            'word': word.word, 'prompt': context + '\n\n' + task, 'options': options,
            'answer': correct, 'hint': '', 'explanation': explanation.strip(),
            'generation_source': 'ai'}
