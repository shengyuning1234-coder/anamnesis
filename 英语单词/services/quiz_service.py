"""
多级测验引擎 —— 根据熟练度自动分层
支持选择题/回忆/拼写/释义/综合等多种模式
"""

import json
import random
import urllib.request
import urllib.error
from typing import List, Optional, Tuple, Dict
from models.word import Word
from services.database import Database
from config import get_ai_api_key
from services.local_dict import local_dict
from services.distractors import first_meaning, chinese_conflict, english_conflict


class QuizService:
    """多级测验引擎"""

    # 模式定义: (名称, 描述, 熟练度区间, 基础评分加成)
    MODES = {
        "choice_en2cn":    ("🅰️ 英→中选择题",  "看英文选中文释义",        (0, 25),   3),
        "choice_cn2en":    ("🅰️ 中→英选择题",  "看中文选英文单词",        (0, 25),   3),
        "recall_en2cn":    ("🧠 英→中回忆",    "看英文回忆中文，自评",    (15, 45),  5),
        "recall_cn2en":    ("🧠 中→英回忆",    "看中文回忆英文，自评",    (15, 45),  5),
        "spell_en":        ("✍️ 拼写英文",     "看中文拼写出英文单词",    (35, 65),  8),
        "type_cn":         ("📝 写出中文释义",  "看英文写出中文意思",      (55, 85),  10),
        "type_multi_cn":   ("📝 多义项写出",   "写出单词的多个中文义项",   (65, 100), 12),
        "fill_blank":      ("🎯 句子填空",     "根据上下文填入单词",       (70, 100), 12),
        "synonym_antonym": ("🎯 近/反义词",    "写出近义词或反义词",       (75, 100), 12),
    }

    def __init__(self, db: Database):
        self.db = db

    # ==================== 模式选择 ====================

    def get_mode_for_word(self, word: Word) -> str:
        """根据单词熟练度自动选择测验模式"""
        prof = word.proficiency
        # 按优先级从高到低匹配
        candidates = []
        for mode, (name, desc, (lo, hi), bonus) in self.MODES.items():
            if lo <= prof <= hi:
                candidates.append(mode)
        if not candidates:
            # 超出范围时选最近的一档
            if prof < 15:
                candidates = ["choice_en2cn", "choice_cn2en"]
            else:
                candidates = ["synonym_antonym", "fill_blank", "type_multi_cn"]
        if not word.example_sentence:
            candidates = [m for m in candidates if m != 'fill_blank']
        if not any(self._extract_syn_ant(word.notes)):
            candidates = [m for m in candidates if m != 'synonym_antonym']
        return random.choice(candidates or ['spell_en'])

    def get_modes_for_proficiency(self, proficiency: int, count: int = 3) -> List[str]:
        """获取适合某熟练度的模式列表"""
        candidates = []
        for mode, (name, desc, (lo, hi), bonus) in self.MODES.items():
            if lo <= proficiency <= hi:
                candidates.append(mode)
        if not candidates:
            candidates = ["choice_en2cn", "choice_cn2en"] if proficiency < 15 else ["synonym_antonym", "fill_blank"]
        random.shuffle(candidates)
        return candidates[:count]

    # ==================== 题目生成 ====================

    def generate_question(self, word: Word, mode: str = None) -> dict:
        """为单词生成一道测验题，返回题目数据"""
        if mode is None:
            mode = self.get_mode_for_word(word)

        generators = {
            "choice_en2cn":    self._gen_choice_en2cn,
            "choice_cn2en":    self._gen_choice_cn2en,
            "recall_en2cn":    self._gen_recall_en2cn,
            "recall_cn2en":    self._gen_recall_cn2en,
            "spell_en":        self._gen_spell_en,
            "type_cn":         self._gen_type_cn,
            "type_multi_cn":   self._gen_type_multi_cn,
            "fill_blank":      self._gen_fill_blank,
            "synonym_antonym": self._gen_synonym_antonym,
        }

        gen = generators.get(mode, self._gen_recall_en2cn)
        question = gen(word)
        if question.get('type') == 'choice' and len(question.get('options', [])) < 4:
            mode = 'recall_en2cn' if mode == 'choice_en2cn' else 'recall_cn2en'
            question = generators[mode](word)
        question["mode"] = mode
        question["word_id"] = word.id
        question["word"] = word.word
        return question

    # ---- 选择题：英→中 ----

    def _gen_choice_en2cn(self, word: Word) -> dict:
        correct = self._first_meaning(word.chinese_meaning)
        distractors = self._get_distractors_cn(word.id, correct, 3, word)
        options = distractors + [correct] if correct else []
        random.shuffle(options)
        return {
            "type": "choice",
            "prompt": f"「{word.word}」的中文意思是？",
            "options": options,
            "answer": correct,
            "hint": f"音标：{word.phonetic}" if word.phonetic else "",
        }

    # ---- 选择题：中→英 ----

    def _gen_choice_cn2en(self, word: Word) -> dict:
        correct = word.word
        meaning = self._first_meaning(word.chinese_meaning)
        distractors = self._get_distractors_en(word.id, correct, 3, word)
        options = distractors + [correct]
        random.shuffle(options)
        return {
            "type": "choice",
            "prompt": f"「{meaning}」对应的英文单词是？",
            "options": options,
            "answer": correct,
            "hint": "",
        }

    # ---- 回忆模式：英→中 ----

    def _gen_recall_en2cn(self, word: Word) -> dict:
        return {
            "type": "recall",
            "prompt": f"请回忆「{word.word}」的中文意思",
            "answer": word.chinese_meaning,
            "hint": f"音标：{word.phonetic}  |  词性：{word.part_of_speech}" if word.phonetic else "",
            "extra": f"例句：{word.example_sentence}" if word.example_sentence else "",
        }

    # ---- 回忆模式：中→英 ----

    def _gen_recall_cn2en(self, word: Word) -> dict:
        return {
            "type": "recall",
            "prompt": f"请回忆对应「{self._first_meaning(word.chinese_meaning)}」的英文单词",
            "answer": word.word,
            "hint": "",
            "extra": f"音标：{word.phonetic}" if word.phonetic else "",
        }

    # ---- 拼写模式 ----

    def _gen_spell_en(self, word: Word) -> dict:
        return {
            "type": "spell",
            "prompt": f"请拼写出「{self._first_meaning(word.chinese_meaning)}」的英文单词",
            "answer": word.word.lower().strip(),
            "hint": f"词性：{word.part_of_speech}",
            "accept_variants": self._get_variants(word.word),
        }

    # ---- 释义写出 ----

    def _gen_type_cn(self, word: Word) -> dict:
        return {
            "type": "type_cn",
            "prompt": f"请写出「{word.word}」的中文意思",
            "answer": word.chinese_meaning,
            "hint": f"词性：{word.part_of_speech}" if word.part_of_speech else "",
            "reference": word.chinese_meaning,
        }

    # ---- 多义项写出 ----

    def _gen_type_multi_cn(self, word: Word) -> dict:
        meanings = [m.strip() for m in word.chinese_meaning.replace("①", "").replace("②", "").replace("③", "").split("\n") if m.strip()]
        return {
            "type": "type_multi_cn",
            "prompt": f"请尽可能多地写出「{word.word}」的中文义项",
            "answer": word.chinese_meaning,
            "hint": f"词性：{word.part_of_speech}  |  共 {len(meanings)} 个义项" if word.part_of_speech else f"共 {len(meanings)} 个义项",
            "expected_count": len(meanings),
            "reference": word.chinese_meaning,
        }

    # ---- 句子填空 ----

    def _gen_fill_blank(self, word: Word) -> dict:
        sentence = self._pick_sentence(word)
        blanked = sentence.replace(word.word, "____", 1) if word.word in sentence else f"____ ({word.chinese_meaning[:20]})"
        return {
            "type": "fill_blank",
            "prompt": f"根据上下文填入合适的单词：\n「{blanked}」",
            "answer": word.word.lower().strip(),
            "hint": "",
        }

    # ---- 近/反义词 ----

    def _gen_synonym_antonym(self, word: Word) -> dict:
        is_synonym = random.choice([True, False])
        # 从 notes 中提取近义词/反义词信息
        syns, ants = self._extract_syn_ant(word.notes)
        if is_synonym and syns:
            answer = syns
            prompt = f"请写出「{word.word}」的近义词（至少1个）"
        elif ants:
            answer = ants
            prompt = f"请写出「{word.word}」的反义词（至少1个）"
        else:
            answer = syns or ants or ""
            prompt = f"请写出「{word.word}」的近义词或反义词"
        return {
            "type": "synonym_antonym",
            "prompt": prompt,
            "answer": answer,
            "hint": f"词义：{self._first_meaning(word.chinese_meaning)}",
            "reference": answer,
        }

    # ==================== AI 评判 ====================

    def judge_answer(self, question: dict, user_answer: str) -> Tuple[bool, int, str]:
        """
        评判用户答案
        返回 (是否正确, 评分1-5, 反馈文本)
        """
        qtype = question.get("type", "")
        correct_answer = question.get("answer", "").strip()
        user = user_answer.strip()

        if not user:
            return False, 1, "未作答"

        # 选择题：精确匹配
        if qtype == "choice":
            ok = (user == correct_answer)
            return ok, (5 if ok else 1), ("✅ 正确！" if ok else f"❌ 正确答案是：{correct_answer}")

        # 回忆模式：用户自评 → 根据自评结果打分
        if qtype == "recall":
            remembered = user.lower().strip() in ("remember", "记得", "yes", "true", "1")
            rating = 5 if remembered else 2
            feedback = "✅ 已记住" if remembered else "📖 继续加油"
            return remembered, rating, feedback

        # 拼写模式：不区分大小写比对
        if qtype == "spell":
            ok = user.lower().strip() == correct_answer.lower().strip()
            if not ok:
                variants = question.get("accept_variants", [])
                ok = user.lower().strip() in [v.lower() for v in variants]
            return ok, (5 if ok else 2), ("✅ 拼写正确！" if ok else f"❌ 正确拼写：{correct_answer}")

        # 写出释义 / 多义项 / 填空 / 近反义词：AI 判断
        if qtype == 'fill_blank':
            ok = user.casefold() in [x.casefold() for x in self._get_variants(correct_answer)]
            return ok, 5 if ok else 2, '✅ 正确' if ok else f'参考答案：{correct_answer}'
        if qtype in ("type_cn", "type_multi_cn", "synonym_antonym"):
            return self._ai_judge(question, user)

        return False, 2, "未知题型"

    def _ai_judge(self, question: dict, user_answer: str) -> Tuple[bool, int, str]:
        """使用 AI 评判开放性答案"""
        from services.ai_client import complete, AIError
        if get_ai_api_key():
            try:
                result = complete('评判英语学习答案，意思合理即可。返回 JSON {"correct":true/false,"rating":1到5,"feedback":"简短中文说明"}。' + json.dumps({'question': question, 'user_answer': user_answer}, ensure_ascii=False), max_tokens=500)
                if type(result.get('correct')) is not bool:
                    raise AIError('评分响应格式无效')
                return result['correct'], max(1,min(5,int(result.get('rating',3)))), str(result.get('feedback',''))
            except (AIError, ValueError, TypeError):
                pass
        ref = question.get('reference', question.get('answer', '')).strip()
        user = user_answer.strip().casefold()
        ok = bool(ref and user) and (user in ref.casefold() or ref.casefold() in user)
        return ok, 4 if ok else 2, ('✅ 参考释义匹配' if ok else f'参考答案：{ref[:150]}（本地匹配）')

    # ==================== 辅助方法 ====================

    def _first_meaning(self, text: str) -> str:
        return first_meaning(text)

    def _choice_candidates(self, target, count):
        if not target:return []
        return local_dict.distractors(target.word, count * 4, target.chinese_meaning, target.part_of_speech)

    def _get_distractors_cn(self, exclude_word_id: int, correct: str, count: int, target=None) -> List[str]:
        target=target or self.db.get_word_by_id(exclude_word_id)
        selected=[]
        displayed = {correct}
        for entry in self._choice_candidates(target,count):
            meaning=first_meaning(entry['meaning'])
            if not meaning or meaning in displayed or chinese_conflict(target.chinese_meaning,entry['meaning']):continue
            if english_conflict(target.word,entry['word']):continue
            if any(chinese_conflict(entry['meaning'],old['meaning']) or english_conflict(entry['word'],old['word']) for old in selected):continue
            selected.append(entry)
            displayed.add(meaning)
            if len(selected)==count:break
        return [first_meaning(e['meaning']) for e in selected]

    def _get_distractors_en(self, exclude_word_id: int, correct: str, count: int, target=None) -> List[str]:
        target=target or self.db.get_word_by_id(exclude_word_id)
        if not target:return []
        selected=[]
        for entry in self._choice_candidates(target,count):
            if not entry.get('word') or english_conflict(correct,entry['word']) or chinese_conflict(target.chinese_meaning,entry['meaning']):continue
            if any(english_conflict(entry['word'],old['word']) or chinese_conflict(entry['meaning'],old['meaning']) for old in selected):continue
            selected.append(entry)
            if len(selected)==count:break
        return [e['word'] for e in selected]

    def _get_variants(self, word: str) -> List[str]:
        """获取单词的常见变体"""
        w = word.lower().strip()
        variants = [w]
        # 常见英美拼写差异
        if w.endswith("our"):
            variants.append(w[:-3] + "or")
        elif w.endswith("or") and len(w) > 3:
            variants.append(w[:-2] + "our")
        if w.endswith("ize"):
            variants.append(w[:-3] + "ise")
        elif w.endswith("ise") and len(w) > 3:
            variants.append(w[:-3] + "ize")
        return variants

    def _pick_sentence(self, word: Word) -> str:
        """选一个包含目标词的例句"""
        sentences = [s.strip() for s in word.example_sentence.split("\n") if s.strip() and word.word in s]
        if sentences:
            return random.choice(sentences)
        return f"The word '{word.word}' is important."

    def _extract_syn_ant(self, notes: str) -> Tuple[str, str]:
        """从笔记中提取近义词/反义词"""
        syns = ""
        ants = ""
        if not notes:
            return syns, ants
        for line in notes.split("\n"):
            line = line.strip()
            if "近义" in line or "synonym" in line.lower():
                syns = line.split("：", 1)[-1].split(":", 1)[-1].strip()
            if "反义" in line or "antonym" in line.lower():
                ants = line.split("：", 1)[-1].split(":", 1)[-1].strip()
        return syns, ants
