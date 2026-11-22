"""
AI 每日学习报告生成服务
每天学习结束后调用 AI 生成当日分析报告
使用压缩历史避免上下文膨胀
"""

import json
import urllib.request
import urllib.error
from datetime import date, datetime, timedelta
from typing import Optional, List
from models.daily_report import DailyReport
from models.word import Word
from services.database import Database
from services.summary_compressor import SummaryCompressor
from config import get_ai_api_key, get_ai_api_base, get_ai_model


class ReportService:
    """AI 学习报告生成器"""

    def __init__(self, db: Database):
        self.db = db
        self.compressor = SummaryCompressor(db)

    def _call_ai(self, system_prompt: str, user_prompt: str) -> Optional[str]:
        """调用 AI，返回文本内容"""
        api_key = get_ai_api_key()
        api_base = get_ai_api_base()
        model = get_ai_model()

        if not api_key:
            print("[ReportService] 未配置 API Key，无法生成报告")
            return None

        payload = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.5,
            "max_tokens": 1200,
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
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode())
            return result["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"[ReportService] AI 调用失败: {e}")
            return None

    # ==================== 报告生成 ====================

    def generate_daily_report(self, target_date: str = None) -> Optional[DailyReport]:
        """
        生成指定日期的学习报告
        返回 DailyReport 或 None（无 AI Key 或调用失败时返回基础报告）
        """
        if target_date is None:
            target_date = date.today().isoformat()

        # 收集数据
        stats = self.db.get_daily_stats(target_date)
        weak_words = self.db.get_low_proficiency_words(30, 10)

        # 获取压缩历史（最多800字）
        compact_history = self.compressor.build_compact_context(800)

        # 评分分布
        rating_dist = ""
        if stats:
            rating_dist = (
                f"★★★★★:{stats.ratings_5}次  ★★★★:{stats.ratings_4}次  "
                f"★★★:{stats.ratings_3}次  ★★:{stats.ratings_2}次  ★:{stats.ratings_1}次"
            )

        # 弱词信息
        weak_info = "\n".join(
            f"- {w.word} (熟练度:{w.proficiency}, 复习{w.review_count}次)"
            for w in weak_words[:10]
        ) if weak_words else "无薄弱词汇"

        user_prompt = f"""请根据以下学习数据生成简洁报告（200字以内，中文）：

【今日】{target_date}
新学{stats.new_words_learned if stats else 0}词 | 复习{stats.words_reviewed if stats else 0}词 | 共{stats.total_reviews if stats else 0}次
评分分布：{rating_dist} | 均分{stats.avg_rating if stats else 0:.1f}/5
熟度变化：{stats.avg_proficiency_before if stats else 0:.0f}→{stats.avg_proficiency_after if stats else 0:.0f}
学习时长：{stats.study_duration_min if stats else 0}分钟

【历史】
{compact_history}

【薄弱词】
{weak_info}

返回 JSON（只返回 JSON）：
{{"summary":"今日概况","weak_words_analysis":"薄弱词分析","confused_words":"易混淆提醒(无则空)","suggestion":"明日建议","trend_analysis":"趋势简析"}}
注意：所有字段必填，简洁有洞察，confused_words 没有就填空字符串。"""

        ai_response = self._call_ai(
            "你是英语学习分析助手。返回严格JSON，简洁有洞察力。",
            user_prompt
        )

        # 解析 AI 响应
        if ai_response:
            try:
                # 提取 JSON
                content = ai_response.strip()
                if content.startswith("```"):
                    lines = content.split("\n")
                    content = "\n".join(lines[1:-1])
                parsed = json.loads(content)
            except json.JSONDecodeError:
                parsed = {
                    "summary": ai_response[:200],
                    "weak_words_analysis": "",
                    "confused_words": "",
                    "suggestion": "",
                    "trend_analysis": "",
                }
        else:
            # 无 AI 时生成基础报告
            parsed = self._generate_basic_report(stats, weak_words, target_date)

        # 构建完整报告 Markdown
        full = self._build_full_report(target_date, stats, parsed)

        report = DailyReport(
            date=target_date,
            summary=parsed.get("summary", ""),
            weak_words=json.dumps(
                [{"word": w.word, "proficiency": w.proficiency, "review_count": w.review_count}
                 for w in weak_words[:10]],
                ensure_ascii=False
            ),
            confused_words=parsed.get("confused_words", ""),
            suggestion=parsed.get("suggestion", ""),
            trend_analysis=parsed.get("trend_analysis", ""),
            full_report=full,
        )
        self.db.save_daily_report(report)

        # 存储每日精简快照 & 触发滚动压缩
        if stats:
            stats.report_generated = 1
            self.db.upsert_daily_stats(stats)
            self.compressor.save_daily_snapshot(
                target_date,
                {
                    "new_words_learned": stats.new_words_learned,
                    "words_reviewed": stats.words_reviewed,
                    "total_reviews": stats.total_reviews,
                    "avg_rating": stats.avg_rating,
                    "avg_proficiency_before": stats.avg_proficiency_before,
                    "avg_proficiency_after": stats.avg_proficiency_after,
                    "study_duration_min": stats.study_duration_min,
                },
                parsed.get("summary", ""),
            )
            # 超过阈值时压缩旧数据
            self.compressor.compress_old_summaries()

        return report

    def _generate_basic_report(self, stats, weak_words, target_date) -> dict:
        """无 AI 时生成基础报告"""
        summary = f"{target_date} 学习完成。"
        if stats:
            summary = (
                f"今日新学{stats.new_words_learned or 0}个单词，复习{stats.words_reviewed or 0}个单词，"
                f"共复习{stats.total_reviews or 0}次，平均评分{(stats.avg_rating or 0):.1f}/5。"
                f"学习时长{stats.study_duration_min or 0}分钟。"
            )
        weak_analysis = ""
        if weak_words:
            weak_list = "、".join(w.word for w in weak_words[:5])
            weak_analysis = f"建议加强以下词汇的复习：{weak_list}"
        return {
            "summary": summary,
            "weak_words_analysis": weak_analysis,
            "confused_words": "",
            "suggestion": "保持每日复习节奏，重点攻克薄弱词汇。",
            "trend_analysis": "",
        }

    def _build_full_report(self, target_date: str, stats, parsed: dict) -> str:
        """构建完整 Markdown 报告"""
        lines = [
            f"# 📊 英语学习日报",
            f"**日期**：{target_date}",
            "",
            "## 📝 今日概况",
            parsed.get("summary", ""),
            "",
        ]
        if stats:
            lines += [
                "## 📈 数据统计",
                f"- 新学单词：{stats.new_words_learned} 个",
                f"- 复习单词：{stats.words_reviewed} 个",
                f"- 复习次数：{stats.total_reviews} 次",
                f"- 平均评分：{stats.avg_rating:.1f} / 5",
                f"- 复习前平均熟练度：{stats.avg_proficiency_before:.0f}",
                f"- 复习后平均熟练度：{stats.avg_proficiency_after:.0f}",
                f"- 学习时长：{stats.study_duration_min} 分钟",
                "",
            ]
        if parsed.get("weak_words_analysis"):
            lines += [
                "## ⚠️ 薄弱词汇",
                parsed["weak_words_analysis"],
                "",
            ]
        if parsed.get("confused_words"):
            lines += [
                "## 🔄 易混淆提醒",
                parsed["confused_words"],
                "",
            ]
        if parsed.get("trend_analysis"):
            lines += [
                "## 📉 趋势分析",
                parsed["trend_analysis"],
                "",
            ]
        if parsed.get("suggestion"):
            lines += [
                "## 💡 明日建议",
                parsed["suggestion"],
                "",
            ]
        return "\n".join(lines)

    # ==================== 查询 ====================

    def get_report(self, target_date: str = None) -> Optional[DailyReport]:
        if target_date is None:
            target_date = date.today().isoformat()
        return self.db.get_daily_report(target_date)

    def get_all_reports(self, limit: int = 30) -> list:
        return self.db.get_all_reports(limit)


# 模块级单例
_report_service: Optional[ReportService] = None


def get_report_service(db: Database = None) -> ReportService:
    global _report_service
    if _report_service is None and db is not None:
        _report_service = ReportService(db)
    return _report_service
