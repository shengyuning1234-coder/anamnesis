"""
AI 回退填充服务 —— 当在线词典查不到时，调用 AI 生成释义
"""

import json
import urllib.request
import urllib.error
from typing import Optional
from models.word import Word
from config import get_ai_api_key, get_ai_api_base, get_ai_model


class AIFiller:
    """使用 AI 填充单词的释义、例句、翻译"""

    @staticmethod
    def _call_ai(word: str) -> Optional[dict]:
        """调用 OpenAI 兼容 API"""
        api_key = get_ai_api_key()
        api_base = get_ai_api_base()
        model = get_ai_model()

        if not api_key:
            print("[AIFiller] 未配置 API Key，跳过 AI 调用")
            return None

        prompt = f"""你是一个专业中英双语词典助手。请为单词 "{word}" 提供详尽信息，以严格 JSON 格式返回（只返回 JSON，不要其他文字）：

{{
    "phonetic": "国际音标，如 /ˈeksəmpəl/",
    "part_of_speech": "词性（如 noun / verb / adj / adv，多个用 / 分隔）",
    "chinese_meaning": "中文释义，尽量列出所有常用义项，每项一行，格式：① 释义一\\n② 释义二\\n③ 释义三",
    "example_sentence": "2~3个地道英文例句，每个一行，编号显示",
    "example_translation": "对应例句的中文翻译，每个一行，编号对应",
    "collocations": "常用搭配/短语，如 make a decision，每项一行",
    "synonyms": "近义词，用逗号分隔",
    "antonyms": "反义词，用逗号分隔",
    "usage_note": "用法说明或记忆技巧（中文，30字以内），没有则填空字符串"
}}

注意：
- chinese_meaning 要详细列出多个常用中文义项，不能只写一个
- example_sentence 和 example_translation 绝不能为空，至少2个例句
- 如果单词有多个词性，请分别说明"""

        payload = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": "你是一个专业英语词典助手，返回严格 JSON 格式。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 800,
        }).encode()

        try:
            req = urllib.request.Request(
                f"{api_base}/chat/completions",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                result = json.loads(resp.read().decode())

            content = result["choices"][0]["message"]["content"].strip()
            # 尝试提取 JSON（有些模型可能包裹在 ```json ``` 中）
            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:-1])
            return json.loads(content)

        except urllib.error.HTTPError as e:
            body = e.read().decode() if e.fp else ""
            print(f"[AIFiller] HTTP {e.code}: {body[:200]}")
            return None
        except Exception as e:
            print(f"[AIFiller] 调用异常: {e}")
            return None

    @staticmethod
    def fill(word: str) -> Optional[Word]:
        """
        用 AI 填充单词信息（无词典参考，完全由 AI 生成）
        成功返回 Word 对象，失败返回 None
        """
        data = AIFiller._call_ai(word)
        if not data:
            return None

        return AIFiller._build_word(word, data, source="ai")

    @staticmethod
    def enhance_local_result(word: str, local_data: dict) -> Optional[Word]:
        """
        用 AI 优化本地词典查到的结构化内容：
        - 保留已有的音标、词性、释义
        - 补充缺失的音标、词性
        - 如例句不足则生成更多例句+翻译
        - 补充搭配、近反义词、用法说明
        返回完整 Word 对象
        """
        api_key = get_ai_api_key()
        api_base = get_ai_api_base()
        model = get_ai_model()

        if not api_key or not local_data:
            return None

        # 从本地数据提取已有内容
        phonetic = local_data.get("phonetic", "")
        pos = local_data.get("part_of_speech", "")
        zh_meaning = local_data.get("chinese_meaning", "")
        en_meaning = local_data.get("english_meaning", "")
        examples = local_data.get("examples", [])
        collocations = local_data.get("collocations", "")
        synonyms = local_data.get("synonyms", "")
        word_origin = local_data.get("word_origin", "")

        # 整理例句
        example_text = "\n".join(
            f"{i+1}. {en}" + (f"\n   {zh}" if zh else "")
            for i, (en, zh) in enumerate(examples[:5])
        ) if examples else "（无）"

        prompt = f"""你是一个专业中英词典编辑助手。以下是牛津词典中查到的关于单词 "{word}" 的内容，请基于此整理并补全，返回严格的 JSON。

【已有音标】{phonetic or "（缺失）"}
【已有词性】{pos or "（缺失）"}
【已有英文释义】{en_meaning or "（缺失）"}
【已有中文释义】{zh_meaning or "（缺失）"}
【已有例句】
{example_text}
【已有搭配】{collocations or "（缺失）"}
【已有近义词】{synonyms or "（缺失）"}
【词源】{word_origin or "（缺失）"}

请以严格 JSON 格式返回（只返回 JSON）：
{{
    "phonetic": "音标（保留已有的，没有则补充）",
    "part_of_speech": "词性（保留已有的，没有则补充）",
    "chinese_meaning": "整理后的中文释义，简洁直接，每项一行，格式：① 释义一\\n② 释义二\\n...",
    "example_sentence": "英文例句，每行一个（如词典已有则优先使用，不足则补充，至少2个）",
    "example_translation": "对应例句的中文翻译，每行一个",
    "collocations": "常用搭配，每项一行（词典已有则保留，不足则补充）",
    "synonyms": "近义词，逗号分隔（词典已有则保留）",
    "antonyms": "反义词，逗号分隔，没有则填空字符串",
    "usage_note": "用法说明或记忆技巧（中文，30字以内）"
}}

注意：
- chinese_meaning 要简洁（如"众多的"而非解释性长句），去除非释义文字
- example_sentence 和 example_translation 绝不能为空，至少2条
- 词典已有的优质内容优先保留，只补充缺失部分"""

        payload = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": "你是一个专业中英词典编辑助手，返回严格 JSON 格式。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 800,
        }).encode()

        try:
            req = urllib.request.Request(
                f"{api_base}/chat/completions",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
            )
            with urllib.request.urlopen(req, timeout=25) as resp:
                result = json.loads(resp.read().decode())

            content = result["choices"][0]["message"]["content"].strip()
            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:-1])
            data = json.loads(content)

            return AIFiller._build_word(word, data, source="ai")

        except Exception as e:
            print(f"[AIFiller] 增强异常: {e}")
            return None

    @staticmethod
    def translate_online_result(word: str, english_meaning: str, examples: str = "") -> Optional[dict]:
        """
        将在线词典的英文释义翻译为中文，并补充搭配/近反义词等
        返回 dict 含 chinese_meaning, example_translation, notes 等，失败返回 None
        """
        api_key = get_ai_api_key()
        api_base = get_ai_api_base()
        model = get_ai_model()

        if not api_key or not english_meaning:
            return None

        prompt = f"""你是一个专业中英词典翻译助手。以下是一个英语单词的英文释义，请将其翻译成地道的中文，并补充相关信息。

单词：{word}

英文释义：
{english_meaning}

英文例句：
{examples if examples else "（无）"}

请以严格 JSON 格式返回（只返回 JSON）：
{{
    "chinese_meaning": "所有义项的中文翻译，每项一行，格式：① 释义\\n② 释义\\n...",
    "example_translation": "英文例句的中文翻译，每个一行，对应编号",
    "collocations": "常用搭配/短语（中文说明），每项一行，没有则填空字符串",
    "synonyms": "近义词及其中文含义，用逗号分隔，没有则填空字符串",
    "antonyms": "反义词及其中文含义，用逗号分隔，没有则填空字符串",
    "usage_note": "用法说明或记忆技巧（中文，30字以内）"
}}"""

        payload = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": "你是一个专业中英词典翻译助手，返回严格 JSON 格式。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 600,
        }).encode()

        try:
            req = urllib.request.Request(
                f"{api_base}/chat/completions",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                result = json.loads(resp.read().decode())

            content = result["choices"][0]["message"]["content"].strip()
            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:-1])
            return json.loads(content)

        except Exception as e:
            print(f"[AIFiller] 翻译异常: {e}")
            return None

    @staticmethod
    def _build_word(word: str, data: dict, source: str = "ai") -> Word:
        """从 AI 返回的 dict 构建 Word 对象"""
        notes_parts = []
        collocations = data.get("collocations", "")
        if collocations:
            notes_parts.append(f"📎 常用搭配：\n{collocations}")
        synonyms = data.get("synonyms", "")
        if synonyms:
            notes_parts.append(f"🔗 近义词：{synonyms}")
        antonyms = data.get("antonyms", "")
        if antonyms:
            notes_parts.append(f"🔴 反义词：{antonyms}")
        usage_note = data.get("usage_note", "")
        if usage_note:
            notes_parts.append(f"💡 用法：{usage_note}")
        notes = "\n\n".join(notes_parts)

        return Word(
            word=word.strip(),
            phonetic=data.get("phonetic", ""),
            part_of_speech=data.get("part_of_speech", ""),
            chinese_meaning=data.get("chinese_meaning", ""),
            example_sentence=data.get("example_sentence", ""),
            example_translation=data.get("example_translation", ""),
            notes=notes,
            source=source,
        )
