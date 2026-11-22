"""
AI 学习报告查看面板
"""

import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date
from typing import Optional
from services.database import Database
from services.report_service import ReportService, get_report_service
from models.daily_report import DailyReport


class ReportPanel(ttk.Frame):
    """报告查看面板"""

    def __init__(self, parent, db: Database):
        super().__init__(parent)
        self.db = db
        self.report_service = get_report_service(db)

        self._build_ui()
        self._load_report_list()

    def _build_ui(self):
        # 顶部工具栏
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, padx=10, pady=(10, 5))

        ttk.Label(
            toolbar, text="📊 学习报告", font=("Microsoft YaHei", 14, "bold"),
        ).pack(side=tk.LEFT)

        ttk.Button(
            toolbar, text="🤖 生成今日报告", command=self._generate_today_report,
        ).pack(side=tk.RIGHT, padx=5)

        ttk.Button(
            toolbar, text="🔄 刷新", command=self._load_report_list,
        ).pack(side=tk.RIGHT)

        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=10)

        # 主内容区：左侧列表 + 右侧详情
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # 左侧：报告列表
        list_frame = ttk.Frame(paned)
        paned.add(list_frame, weight=1)

        ttk.Label(list_frame, text="历史报告", font=("", 10, "bold")).pack(anchor=tk.W, pady=(0, 5))

        self.report_listbox = tk.Listbox(
            list_frame, font=("Microsoft YaHei", 10),
            selectmode=tk.SINGLE, exportselection=False,
        )
        list_scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.report_listbox.yview)
        self.report_listbox.configure(yscrollcommand=list_scroll.set)
        self.report_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        list_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.report_listbox.bind("<<ListboxSelect>>", self._on_select_report)

        # 右侧：报告详情
        detail_frame = ttk.Frame(paned)
        paned.add(detail_frame, weight=2)

        ttk.Label(detail_frame, text="报告详情", font=("", 10, "bold")).pack(anchor=tk.W, pady=(0, 5))

        self.report_text = tk.Text(
            detail_frame, font=("Microsoft YaHei", 10),
            wrap=tk.WORD, relief=tk.SUNKEN, borderwidth=1,
            state=tk.DISABLED,
        )
        detail_scroll = ttk.Scrollbar(detail_frame, orient=tk.VERTICAL, command=self.report_text.yview)
        self.report_text.configure(yscrollcommand=detail_scroll.set)
        self.report_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        detail_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    # ==================== 数据加载 ====================

    def _load_report_list(self):
        self.report_listbox.delete(0, tk.END)
        self.reports = self.report_service.get_all_reports(30)
        for i, r in enumerate(self.reports):
            summary = r.summary[:40] if r.summary else "(空)"
            self.report_listbox.insert(tk.END, f"{r.date}  {summary}")
        if not self.reports:
            self.report_listbox.insert(tk.END, "（暂无报告）")

    def _on_select_report(self, event):
        selection = self.report_listbox.curselection()
        if not selection or not self.reports:
            return
        idx = selection[0]
        if idx >= len(self.reports):
            return

        report = self.reports[idx]
        self._show_report_detail(report)

    def _show_report_detail(self, report: DailyReport):
        self.report_text.config(state=tk.NORMAL)
        self.report_text.delete("1.0", tk.END)

        if report.full_report:
            self.report_text.insert(tk.END, report.full_report)
        else:
            # 构建简易展示
            self.report_text.insert(tk.END, f"日期：{report.date}\n\n")
            if report.summary:
                self.report_text.insert(tk.END, f"📝 概况\n{report.summary}\n\n")
            if report.weak_words:
                self.report_text.insert(tk.END, f"⚠️ 薄弱词汇\n{report.weak_words}\n\n")
            if report.confused_words:
                self.report_text.insert(tk.END, f"🔄 易混淆提醒\n{report.confused_words}\n\n")
            if report.trend_analysis:
                self.report_text.insert(tk.END, f"📉 趋势\n{report.trend_analysis}\n\n")
            if report.suggestion:
                self.report_text.insert(tk.END, f"💡 建议\n{report.suggestion}")

        self.report_text.config(state=tk.DISABLED)

    # ==================== 报告生成 ====================

    def _generate_today_report(self):
        today = date.today().isoformat()

        # 检查今天是否有学习数据
        stats = self.db.get_daily_stats(today)
        if not stats or (stats.new_words_learned == 0 and stats.words_reviewed == 0):
            messagebox.showwarning("提示", "今日暂无学习记录，无法生成报告。\n请先完成今日的学习和复习。")
            return

        if stats.report_generated:
            if not messagebox.askyesno("确认", "今日报告已存在，是否重新生成？"):
                return

        self._set_buttons_state(tk.DISABLED)
        self.report_text.config(state=tk.NORMAL)
        self.report_text.delete("1.0", tk.END)
        self.report_text.insert(tk.END, "⏳ 正在调用 AI 生成报告，请稍候...")
        self.report_text.config(state=tk.DISABLED)
        self.update()

        try:
            report = self.report_service.generate_daily_report(today)
            self._load_report_list()
            if report:
                self._show_report_detail(report)
                messagebox.showinfo("成功", "今日学习报告已生成！")
            else:
                self.report_text.config(state=tk.NORMAL)
                self.report_text.delete("1.0", tk.END)
                self.report_text.insert(tk.END, "❌ 报告生成失败，请检查 AI API 配置。")
                self.report_text.config(state=tk.DISABLED)
        except Exception as e:
            self.report_text.config(state=tk.NORMAL)
            self.report_text.delete("1.0", tk.END)
            self.report_text.insert(tk.END, f"❌ 生成失败：{e}")
            self.report_text.config(state=tk.DISABLED)
        finally:
            self._set_buttons_state(tk.NORMAL)

    def _set_buttons_state(self, state):
        for child in self.winfo_children():
            if isinstance(child, ttk.Button):
                child.config(state=state)

    def refresh(self):
        self._load_report_list()
