"""
复习日志数据模型
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ReviewLog:
    """单次复习记录"""
    id: Optional[int] = None
    word_id: int = 0               # 关联 words.id
    reviewed_at: str = ""          # 复习时间
    rating: int = 0                # 评分 1-5（1=完全忘记,5=完全掌握）
    review_mode: str = "en2cn"     # 复习模式: en2cn / cn2en / mixed
    proficiency_before: int = 0    # 复习前熟练度
    proficiency_after: int = 0     # 复习后熟练度
    stage_before: int = 0          # 复习前阶段
    stage_after: int = 0           # 复习后阶段

    @classmethod
    def from_dict(cls, data: dict) -> "ReviewLog":
        return cls(
            id=data.get("id"),
            word_id=data.get("word_id", 0),
            reviewed_at=data.get("reviewed_at", ""),
            rating=data.get("rating", 0),
            review_mode=data.get("review_mode", "en2cn"),
            proficiency_before=data.get("proficiency_before", 0),
            proficiency_after=data.get("proficiency_after", 0),
            stage_before=data.get("stage_before", 0),
            stage_after=data.get("stage_after", 0),
        )
