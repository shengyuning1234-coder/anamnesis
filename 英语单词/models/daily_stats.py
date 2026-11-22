"""
每日学习统计数据模型
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class DailyStats:
    """单日学习统计"""
    id: Optional[int] = None
    date: str = ""                      # 日期 YYYY-MM-DD
    new_words_learned: int = 0          # 今日新学单词数
    words_reviewed: int = 0             # 今日复习单词数
    total_reviews: int = 0              # 今日复习总次数（含多次轮）
    ratings_1: int = 0                  # 评分=1 次数
    ratings_2: int = 0
    ratings_3: int = 0
    ratings_4: int = 0
    ratings_5: int = 0
    avg_rating: float = 0.0            # 平均评分
    avg_proficiency_before: float = 0.0
    avg_proficiency_after: float = 0.0
    study_duration_min: int = 0         # 学习时长（分钟）
    words_from_book: int = 0            # 从词书导入的新词数
    report_generated: int = 0           # 是否已生成报告 0/1

    @classmethod
    def from_dict(cls, data: dict) -> "DailyStats":
        return cls(
            id=data.get("id"),
            date=data.get("date", ""),
            new_words_learned=data.get("new_words_learned", 0),
            words_reviewed=data.get("words_reviewed", 0),
            total_reviews=data.get("total_reviews", 0),
            ratings_1=data.get("ratings_1", 0),
            ratings_2=data.get("ratings_2", 0),
            ratings_3=data.get("ratings_3", 0),
            ratings_4=data.get("ratings_4", 0),
            ratings_5=data.get("ratings_5", 0),
            avg_rating=data.get("avg_rating", 0.0),
            avg_proficiency_before=data.get("avg_proficiency_before", 0.0),
            avg_proficiency_after=data.get("avg_proficiency_after", 0.0),
            study_duration_min=data.get("study_duration_min", 0),
            words_from_book=data.get("words_from_book", 0),
            report_generated=data.get("report_generated", 0),
        )
