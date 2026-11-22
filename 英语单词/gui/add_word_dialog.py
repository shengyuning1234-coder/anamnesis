"""
录入/编辑单词对话框 —— 支持在线查询 + AI 回退
"""

import threading
import tkinter as tk
from tkinter import ttk, messagebox
from models.word import Word
from services.database import Database
from services.dictionary import DictionaryService
from services.ai_filler import AIFiller
from services.local_dict import local_dict
from config import get_ai_api_key


class AddWordDialog(tk.Toplevel):
    """录入/编辑单词弹窗"""

    def __init__(self, parent, db: Database, edit_word: Word = None):
        super().__init__(parent)
        self.db = db
        self.edit_word = edit_word
        self.query_result: Word = None

        self.title("✏️ 编辑单词" if edit_word else "➕ 录入单词")
        self.geometry("660x640")
        self.minsize(550, 500)
        self.transient(parent)
        self.grab_set()

        self._build_ui()

        if edit_word:
            self._load_word(edit_word)

    def _build_ui(self):
        pad = {"padx": 15, "pady": 4}

        # ===== 输入单词行 =====
        input_frame = ttk.Frame(self)
        input_frame.pack(fill=tk.X, **pad)

        ttk.Label(input_frame, text="英文单词：", font=("", 11, "bold")).pack(side=tk.LEFT)

        self.word_var = tk.StringVar()
        self.word_entry = ttk.Entry(input_frame, textvariable=self.word_var, font=("", 12), width=22)
        self.word_entry.pack(side=tk.LEFT, padx=10)
        self.word_entry.focus_set()

        self.query_btn = ttk.Button(input_frame, text="🔍 在线查词", command=self._do_query)
        self.query_btn.pack(side=tk.LEFT)

        self.status_var = tk.StringVar(value="💡 输入单词后点击「在线查词」自动填充")
        ttk.Label(self, textvariable=self.status_var, foreground="gray").pack(fill=tk.X, **pad)

        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=15, pady=3)

        # ===== 可滚动的表单区域 =====
        canvas_frame = ttk.Frame(self)
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=2)

        self._text_widgets = {}
        row = 0

        # 音标 (单行)
        ttk.Label(canvas_frame, text="音标：", font=("", 10)).grid(row=row, column=0, sticky=tk.NW, pady=3)
        self.phonetic_var = tk.StringVar()
        ttk.Entry(canvas_frame, textvariable=self.phonetic_var, font=("", 10), width=40).grid(
            row=row, column=1, sticky=tk.EW, padx=(10, 0), pady=3)
        row += 1

        # 词性 (单行)
        ttk.Label(canvas_frame, text="词性：", font=("", 10)).grid(row=row, column=0, sticky=tk.NW, pady=3)
        self.pos_var = tk.StringVar()
        ttk.Entry(canvas_frame, textvariable=self.pos_var, font=("", 10), width=40).grid(
            row=row, column=1, sticky=tk.EW, padx=(10, 0), pady=3)
        row += 1

        # 中文释义 (多行)
        self._add_text_field(canvas_frame, row, "中文释义：", "meaning", height=4)
        row += 1

        # 英文例句 (多行)
        self._add_text_field(canvas_frame, row, "英文例句：", "example", height=3)
        row += 1

        # 例句翻译 (多行)
        self._add_text_field(canvas_frame, row, "例句翻译：", "trans", height=3)
        row += 1

        # 额外笔记 (搭配/近反义词等)
        self._add_text_field(canvas_frame, row, "📝 笔记：", "notes", height=3)
        row += 1

        canvas_frame.columnconfigure(1, weight=1)

        # ===== 来源标签 =====
        self.source_var = tk.StringVar(value="来源：—")
        ttk.Label(self, textvariable=self.source_var, foreground="blue").pack(fill=tk.X, padx=15, pady=(0, 2))

        # ===== 按钮 =====
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=15, pady=(2, 10))

        ttk.Button(btn_frame, text="💾 保存", command=self._save).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(btn_frame, text="❌ 取消", command=self.destroy).pack(side=tk.LEFT)

    def _add_text_field(self, parent, row: int, label: str, key: str, height: int = 3):
        """添加带标签的多行文本框"""
        ttk.Label(parent, text=label, font=("", 10)).grid(row=row, column=0, sticky=tk.NW, pady=3)
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=1, sticky=tk.NSEW, padx=(10, 0), pady=3)

        text_widget = tk.Text(frame, height=height, width=50, font=("Microsoft YaHei", 10),
                              wrap=tk.WORD, relief=tk.SOLID, borderwidth=1)
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)

        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._text_widgets[key] = text_widget

    def _get_text(self, key: str) -> str:
        """获取多行文本框内容"""
        w = self._text_widgets.get(key)
        return w.get("1.0", "end-1c").strip() if w else ""

    def _set_text(self, key: str, value: str):
        """设置多行文本框内容"""
        w = self._text_widgets.get(key)
        if w:
            w.delete("1.0", tk.END)
            w.insert("1.0", value)

    def _load_word(self, w: Word):
        """加载编辑的单词数据"""
        self.word_var.set(w.word)
        self.phonetic_var.set(w.phonetic)
        self.pos_var.set(w.part_of_speech)
        self._set_text("meaning", w.chinese_meaning)
        self._set_text("example", w.example_sentence)
        self._set_text("trans", w.example_translation)
        self._set_text("notes", w.notes)
        source_map = {
            "local+ai": "📖 本地词典 + 🤖 AI 优化",
            "local": "📖 本地词典",
            "ai": "🤖 AI 生成",
            "online": "🌐 在线词典（英文释义）",
            "manual": "✍ 手动录入",
        }
        self.source_var.set(f"来源：{source_map.get(w.source, w.source)}")

    def _set_status(self, text: str, color: str = "gray"):
        """更新状态文字"""
        self.status_var.set(text)
        for child in self.winfo_children():
            if isinstance(child, ttk.Label) and child.cget("textvariable") == str(self.status_var):
                child.configure(foreground=color)

    def _fill_form(self, w: Word):
        """将查询结果填充到表单"""
        self.phonetic_var.set(w.phonetic)
        self.pos_var.set(w.part_of_speech)
        self._set_text("meaning", w.chinese_meaning)
        self._set_text("example", w.example_sentence)
        self._set_text("trans", w.example_translation)
        self._set_text("notes", w.notes)
        source_map = {
            "local+ai": "📖 本地词典 + 🤖 AI 优化",
            "local": "📖 本地词典",
            "ai": "🤖 AI 生成",
            "online": "🌐 在线词典（英文释义）",
            "manual": "✍ 手动录入",
        }
        self.source_var.set(f"来源：{source_map.get(w.source, w.source)}")

    def _do_query(self):
        """本地查词（结构化）→ AI 补全 → 拼写检查"""
        word = self.word_var.get().strip()
        if not word:
            messagebox.showwarning("提示", "请输入英文单词")
            return

        self.query_btn.config(state=tk.DISABLED, text="⏳ 查询中...")
        has_ai = bool(get_ai_api_key())

        def query_thread():
            # 1. 本地词典优先（返回结构化 dict）
            if local_dict.ready:
                self.after(0, lambda: self._set_status(
                    "📖 本地词典查询中...", "orange"))
                data = local_dict.query(word)
            else:
                data = None

            if data:
                # 2a. 有 AI → 增强补全
                if has_ai:
                    self.after(0, lambda: self._set_status(
                        "📖 已查到，AI 补全中...", "orange"))
                    enhanced = AIFiller.enhance_local_result(word, data)
                    if enhanced:
                        enhanced.source = "local+ai"
                        self.after(0, lambda: self._on_query_done(enhanced, "local+ai"))
                        return
                # 2b. 无 AI → 直接从结构化数据构建 Word
                w = self._word_from_local_data(word, data)
                self.after(0, lambda: self._on_query_done(w, "local"))
                return

            # 3. 本地未查到 → 拼写检查 + AI
            if local_dict.ready:
                similar = local_dict.suggest_similar(word)
            else:
                similar = []
            if similar:
                self.after(0, lambda: self._on_spell_suggest(word, similar))
                self.query_btn.config(state=tk.NORMAL, text="🔍 在线查词")
                return

            # 4. AI 生成
            if has_ai:
                self.after(0, lambda: self._set_status(
                    "🤖 AI 生成中...", "orange"))
                ai_result = AIFiller.fill(word)
                if ai_result:
                    self.after(0, lambda: self._on_query_done(ai_result, "ai"))
                    return

            # 5. 在线词典
            self.after(0, lambda: self._set_status(
                "⏳ 尝试在线词典...", "orange"))
            online_result = DictionaryService.query(word)
            if online_result and online_result.chinese_meaning:
                self.after(0, lambda: self._on_query_done(online_result, "online"))
            else:
                self.after(0, lambda: self._on_query_failed(word))

        threading.Thread(target=query_thread, daemon=True).start()

    def _word_from_local_data(self, word: str, data: dict) -> Word:
        """从本地词典结构化数据构建 Word（无 AI）"""
        examples = data.get("examples", [])
        example_en = "\n".join(en for en, _ in examples[:5])
        example_zh = "\n".join(zh for _, zh in examples[:5])
        notes_parts = []
        if data.get("synonyms"):
            notes_parts.append(f"🔗 近义词：{data['synonyms']}")
        if data.get("collocations"):
            notes_parts.append(f"📎 搭配：{data['collocations']}")
        if data.get("word_origin"):
            notes_parts.append(f"📖 词源：{data['word_origin']}")
        return Word(
            word=word,
            phonetic=data.get("phonetic", ""),
            part_of_speech=data.get("part_of_speech", ""),
            chinese_meaning=data.get("chinese_meaning", ""),
            example_sentence=example_en,
            example_translation=example_zh,
            notes="\n\n".join(notes_parts),
            source="local",
        )

    def _on_spell_suggest(self, word: str, similar: list):
        """拼写检查：弹窗提示相似词"""
        tips = "\n".join(f"  • {s}" for s in similar[:5])
        msg = f"未查到「{word}」，可能是拼写错误。\n\n相似词：\n{tips}\n\n是否仍要手动录入？"
        self._set_status(f"⚠ 未查到「{word}」，可能是拼写错误", "red")
        if messagebox.askyesno("拼写检查", msg):
            return  # 用户选择手动录入
        else:
            self.word_entry.focus_set()
            self.word_entry.select_range(0, tk.END)

    def _on_query_done(self, result: Word, source: str):
        """查询成功"""
        self._fill_form(result)
        source_map = {
            "local+ai": "📖 本地词典 + 🤖 AI 优化",
            "local": "📖 本地词典",
            "ai": "🤖 AI 生成",
            "online": "🌐 在线词典（英文释义）",
        }
        self.source_var.set(f"来源：{source_map.get(source, source)}")
        self._set_status(f"✅ 已从 {source_map.get(source, source)} 获取，请核对后保存", "green")
        self.query_btn.config(state=tk.NORMAL, text="🔍 在线查词")

    def _on_query_failed(self, word: str):
        """查询失败"""
        hint = "请点击主窗口「⚙️ 设置」配置 AI 后重试" if not get_ai_api_key() else "请手动填写释义"
        self._set_status(f"❌ 未查到「{word}」，{hint}", "red")
        self.query_btn.config(state=tk.NORMAL, text="🔍 在线查词")

    def _save(self):
        """保存单词"""
        word_text = self.word_var.get().strip()
        if not word_text:
            messagebox.showwarning("提示", "请输入英文单词")
            return

        meaning = self._get_text("meaning")
        if not meaning:
            if not messagebox.askyesno("提示", "中文释义为空，确定保存吗？"):
                return

        source = "manual"
        if self.edit_word:
            source = self.edit_word.source
        elif "AI 优化" in self.source_var.get():
            source = "local+ai"
        elif "本地词典" in self.source_var.get():
            source = "local"
        elif "AI" in self.source_var.get():
            source = "ai"
        elif "在线词典" in self.source_var.get():
            source = "online"

        word = Word(
            id=self.edit_word.id if self.edit_word else None,
            word=word_text,
            phonetic=self.phonetic_var.get().strip(),
            part_of_speech=self.pos_var.get().strip(),
            chinese_meaning=meaning,
            example_sentence=self._get_text("example"),
            example_translation=self._get_text("trans"),
            notes=self._get_text("notes"),
            source=source,
            # 编辑时保留学习进度
            proficiency=self.edit_word.proficiency if self.edit_word else 0,
            review_count=self.edit_word.review_count if self.edit_word else 0,
            review_stage=self.edit_word.review_stage if self.edit_word else 0,
            last_reviewed_at=self.edit_word.last_reviewed_at if self.edit_word else "",
            next_review_at=self.edit_word.next_review_at if self.edit_word else "",
        )

        if self.edit_word:
            self.db.update_word(word)
        else:
            if self.db.word_exists(word_text):
                if not messagebox.askyesno("重复提示", f"单词「{word_text}」已存在，是否仍然添加？"):
                    return
            self.db.add_word(word)

        self.destroy()
