"""
词书数据模型
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class WordBook:
    """词书（如 CET-4、IELTS 等）"""
    id: Optional[int] = None
    name: str = ""                      # 词书名称
    description: str = ""               # 描述
    total_words: int = 0                # 词书总词数
    imported_count: int = 0             # 已导入学习的词数
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    @classmethod
    def from_dict(cls, data: dict) -> "WordBook":
        return cls(
            id=data.get("id"),
            name=data.get("name", ""),
            description=data.get("description", ""),
            total_words=data.get("total_words", 0),
            imported_count=data.get("imported_count", 0),
            created_at=data.get("created_at", ""),
        )


@dataclass
class WordBookEntry:
    """词书中的单词条目"""
    id: Optional[int] = None
    book_id: int = 0                    # 关联 word_books.id
    word: str = ""
    phonetic: str = ""
    part_of_speech: str = ""
    chinese_meaning: str = ""
    example_sentence: str = ""
    example_translation: str = ""
    imported: int = 0                   # 是否已导入到 words 表 0/1

    @classmethod
    def from_dict(cls, data: dict) -> "WordBookEntry":
        return cls(
            id=data.get("id"),
            book_id=data.get("book_id", 0),
            word=data.get("word", ""),
            phonetic=data.get("phonetic", ""),
            part_of_speech=data.get("part_of_speech", ""),
            chinese_meaning=data.get("chinese_meaning", ""),
            example_sentence=data.get("example_sentence", ""),
            example_translation=data.get("example_translation", ""),
            imported=data.get("imported", 0),
        )
