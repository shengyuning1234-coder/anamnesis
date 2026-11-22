"""
单词数据模型
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Word:
    """单词实体"""
    id: Optional[int] = None
    word: str = ""                          # 英文单词
    phonetic: str = ""                      # 音标
    part_of_speech: str = ""                # 词性 (noun/verb/adj/adv/...)
    chinese_meaning: str = ""               # 中文释义（可多行）
    example_sentence: str = ""              # 例句（可多个，换行分隔）
    example_translation: str = ""           # 例句翻译（可多个，换行分隔）
    notes: str = ""                         # 额外笔记：搭配/近义词/反义词/用法
    source: str = "manual"                  # 来源: online / ai / manual
    # ===== 学习系统字段 =====
    proficiency: int = 0                    # 熟练度 0-100
    review_count: int = 0                   # 累计复习次数
    review_stage: int = 0                   # 艾宾浩斯阶段 0-7（0=未开始复习）
    last_reviewed_at: str = ""              # 上次复习时间
    next_review_at: str = ""                # 下次复习时间
    # ===== 原有时间字段 =====
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    updated_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "word": self.word,
            "phonetic": self.phonetic,
            "part_of_speech": self.part_of_speech,
            "chinese_meaning": self.chinese_meaning,
            "example_sentence": self.example_sentence,
            "example_translation": self.example_translation,
            "notes": self.notes,
            "source": self.source,
            "proficiency": self.proficiency,
            "review_count": self.review_count,
            "review_stage": self.review_stage,
            "last_reviewed_at": self.last_reviewed_at,
            "next_review_at": self.next_review_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Word":
        return cls(
            id=data.get("id"),
            word=data.get("word", ""),
            phonetic=data.get("phonetic", ""),
            part_of_speech=data.get("part_of_speech", ""),
            chinese_meaning=data.get("chinese_meaning", ""),
            example_sentence=data.get("example_sentence", ""),
            example_translation=data.get("example_translation", ""),
            notes=data.get("notes", ""),
            source=data.get("source", "manual"),
            proficiency=data.get("proficiency", 0),
            review_count=data.get("review_count", 0),
            review_stage=data.get("review_stage", 0),
            last_reviewed_at=data.get("last_reviewed_at", ""),
            next_review_at=data.get("next_review_at", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )
