"""
AI 每日报告数据模型
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class DailyReport:
    """AI 生成的每日学习报告"""
    id: Optional[int] = None
    date: str = ""                      # 报告日期 YYYY-MM-DD
    summary: str = ""                   # 今日概况
    weak_words: str = ""                # 薄弱词汇分析（JSON 数组字符串）
    confused_words: str = ""            # 易混淆词汇提醒（JSON 数组字符串）
    suggestion: str = ""                # 明日学习建议
    trend_analysis: str = ""            # 趋势分析
    full_report: str = ""               # 完整报告 Markdown 文本
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    @classmethod
    def from_dict(cls, data: dict) -> "DailyReport":
        return cls(
            id=data.get("id"),
            date=data.get("date", ""),
            summary=data.get("summary", ""),
            weak_words=data.get("weak_words", ""),
            confused_words=data.get("confused_words", ""),
            suggestion=data.get("suggestion", ""),
            trend_analysis=data.get("trend_analysis", ""),
            full_report=data.get("full_report", ""),
            created_at=data.get("created_at", ""),
        )
