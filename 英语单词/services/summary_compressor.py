"""
摘要压缩服务 —— 防止历史总结无限增长
使用滚动窗口 + AI 渐进压缩
"""

import json
from datetime import date, timedelta
from typing import List, Optional, Dict
from services.database import Database


class SummaryCompressor:
    """学习摘要压缩器"""

    WINDOW_DAYS = 7           # 保留最近 N 天的逐日摘要
    COMPRESS_THRESHOLD = 14   # 超过此天数触发压缩

    def __init__(self, db: Database):
        self.db = db

    # ==================== 存储压缩摘要 ====================

    def save_daily_snapshot(self, target_date: str, stats: dict, report_summary: str):
        """
        存储每日精简快照（单行 JSON）
        只保留关键指标，不存储完整报告
        """
        snapshot = {
            "date": target_date,
            "new_words": stats.get("new_words_learned", 0),
            "reviewed": stats.get("words_reviewed", 0),
            "total_reviews": stats.get("total_reviews", 0),
            "avg_rating": stats.get("avg_rating", 0),
            "avg_prof_before": stats.get("avg_proficiency_before", 0),
            "avg_prof_after": stats.get("avg_proficiency_after", 0),
            "duration_min": stats.get("study_duration_min", 0),
            "summary": (report_summary or "")[:120],  # 截断到120字
        }
        self.db.save_compressed_snapshot(target_date, json.dumps(snapshot, ensure_ascii=False))

    def get_recent_snapshots(self, days: int = 7) -> List[dict]:
        """获取最近 N 天的精简快照"""
        rows = self.db.get_compressed_snapshots(days)
        snapshots = []
        for r in rows:
            try:
                snapshots.append(json.loads(r["snapshot"]))
            except (json.JSONDecodeError, KeyError):
                pass
        return snapshots

    # ==================== 滚动压缩 ====================

    def compress_old_summaries(self) -> Optional[str]:
        """
        将超过 WINDOW_DAYS 的旧摘要压缩为一段文本
        返回压缩后的文本，无数据则返回 None
        """
        all_snapshots = self.get_recent_snapshots(60)  # 最多取60天
        if len(all_snapshots) <= self.WINDOW_DAYS:
            return None

        # 前 N 天的逐日保留，更早的压缩
        recent = all_snapshots[-self.WINDOW_DAYS:]  # 最近7天保留
        old = all_snapshots[:-self.WINDOW_DAYS]      # 更早的压缩

        if not old:
            return None

        # 聚合旧数据
        total_days = len(old)
        total_new = sum(s.get("new_words", 0) for s in old)
        total_review = sum(s.get("total_reviews", 0) for s in old)
        avg_rating = round(
            sum(s.get("avg_rating", 0) for s in old) / total_days, 1
        ) if total_days else 0
        avg_prof_start = old[0].get("avg_prof_before", 0) if old else 0
        avg_prof_end = old[-1].get("avg_prof_after", 0) if old else 0
        total_min = sum(s.get("duration_min", 0) for s in old)

        compressed = (
            f"【历史概览·{old[0]['date']}至{old[-1]['date']}·共{total_days}天】"
            f"累计新学{total_new}词，复习{total_review}次，"
            f"平均评分{avg_rating}/5，"
            f"熟练度从{avg_prof_start}提升至{avg_prof_end}，"
            f"总学习时长{total_min}分钟。"
        )

        # 存储压缩结果
        self.db.save_compressed_summary(compressed)
        # 标记已压缩的快照
        for s in old:
            self.db.mark_snapshot_compressed(s["date"])

        return compressed

    def get_compressed_history(self) -> str:
        """获取压缩后的历史摘要文本（用于 AI 报告）"""
        parts = []

        # 1. 最近压缩摘要
        compressed_list = self.db.get_compressed_summaries(5)
        for c in compressed_list:
            parts.append(c)

        # 2. 最近7天逐日快照
        recent = self.get_recent_snapshots(7)
        if recent:
            lines = []
            for s in recent:
                lines.append(
                    f"{s['date']}: 新学{s.get('new_words',0)}词 "
                    f"复习{s.get('total_reviews',0)}次 "
                    f"均分{s.get('avg_rating',0)} "
                    f"熟{s.get('avg_prof_before',0)}→{s.get('avg_prof_after',0)}"
                )
            parts.append("【近7日】\n" + "\n".join(lines))

        return "\n\n".join(parts) if parts else "暂无历史数据"

    def build_compact_context(self, max_chars: int = 800) -> str:
        """
        构建给 AI 的压缩上下文（严格限制字数）
        """
        history = self.get_compressed_history()
        if len(history) <= max_chars:
            return history
        # 截断：保留压缩摘要 + 最近3天
        parts = history.split("\n\n")
        result_parts = []
        chars = 0
        for p in parts:
            if chars + len(p) > max_chars:
                break
            result_parts.append(p)
            chars += len(p) + 2
        return "\n\n".join(result_parts)
