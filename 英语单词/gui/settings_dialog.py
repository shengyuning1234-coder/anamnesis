"""
AI 设置对话框 —— 配置 API 地址、模型名称、API Key
"""

import tkinter as tk
from tkinter import ttk, messagebox
from config import (
    get_ai_api_base,
    get_ai_model,
    get_apikey_masked,
    save_settings,
    save_apikey,
)


class SettingsDialog(tk.Toplevel):
    """AI 配置对话框"""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("⚙️ AI 模型设置")
        self.geometry("500x310")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._build_ui()
        self._load_current_settings()
        self._center_on_parent(parent)

    def _build_ui(self):
        pad = {"padx": 20, "pady": 6}

        # ===== 标题 =====
        header = ttk.Frame(self)
        header.pack(fill=tk.X, **pad)
        ttk.Label(
            header, text="🤖 AI 模型 API 配置",
            font=("Microsoft YaHei", 13, "bold"),
        ).pack(anchor=tk.W)
        ttk.Label(
            header,
            text="支持 OpenAI 兼容接口（如 DeepSeek、Moonshot、通义千问等）",
            foreground="gray", font=("", 9),
        ).pack(anchor=tk.W, pady=(2, 0))

        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=20, pady=(8, 4))

        # ===== 表单 =====
        form = ttk.Frame(self)
        form.pack(fill=tk.BOTH, expand=True, padx=20, pady=4)

        # API 地址
        ttk.Label(form, text="API 地址：", font=("", 10)).grid(
            row=0, column=0, sticky=tk.W, pady=5
        )
        self.api_base_var = tk.StringVar()
        self.api_base_entry = ttk.Entry(
            form, textvariable=self.api_base_var, width=45, font=("Consolas", 10),
        )
        self.api_base_entry.grid(row=0, column=1, sticky=tk.EW, pady=5, padx=(10, 0))

        # 模型名称
        ttk.Label(form, text="模型名称：", font=("", 10)).grid(
            row=1, column=0, sticky=tk.W, pady=5
        )
        self.model_var = tk.StringVar()
        self.model_entry = ttk.Entry(
            form, textvariable=self.model_var, width=45, font=("Consolas", 10),
        )
        self.model_entry.grid(row=1, column=1, sticky=tk.EW, pady=5, padx=(10, 0))

        # API Key
        ttk.Label(form, text="API Key：", font=("", 10)).grid(
            row=2, column=0, sticky=tk.W, pady=5
        )
        key_frame = ttk.Frame(form)
        key_frame.grid(row=2, column=1, sticky=tk.EW, pady=5, padx=(10, 0))

        self.api_key_var = tk.StringVar()
        self.api_key_entry = ttk.Entry(
            key_frame, textvariable=self.api_key_var, width=35, show="•",
            font=("Consolas", 10),
        )
        self.api_key_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.show_key_var = tk.BooleanVar(value=False)
        self.show_key_cb = ttk.Checkbutton(
            key_frame, text="👁", variable=self.show_key_var,
            command=self._toggle_key_visibility, width=3,
        )
        self.show_key_cb.pack(side=tk.LEFT, padx=(4, 0))

        # 提示
        self.key_hint_var = tk.StringVar()
        ttk.Label(
            form, textvariable=self.key_hint_var,
            foreground="gray", font=("", 8),
        ).grid(row=3, column=1, sticky=tk.W, pady=(0, 5), padx=(10, 0))

        form.columnconfigure(1, weight=1)

        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=20, pady=4)

        # ===== 底部提示 =====
        tip = ttk.Label(
            self,
            text="💡 提示：API Key 将安全存储在本地 data/.apikey 文件中，不会上传到任何地方。",
            foreground="#666", font=("", 8), wraplength=450,
        )
        tip.pack(fill=tk.X, padx=20, pady=(2, 4))

        # ===== 按钮 =====
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=20, pady=(0, 15))

        ttk.Button(
            btn_frame, text="🧪 测试连接", command=self._test_connection,
        ).pack(side=tk.LEFT)

        ttk.Button(
            btn_frame, text="💾 保存", command=self._save,
        ).pack(side=tk.RIGHT, padx=(10, 0))

        ttk.Button(
            btn_frame, text="❌ 取消", command=self.destroy,
        ).pack(side=tk.RIGHT)

    def _center_on_parent(self, parent):
        """居中于父窗口"""
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        w = self.winfo_width()
        h = self.winfo_height()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"+{x}+{y}")

    def _load_current_settings(self):
        """加载当前设置到界面"""
        self.api_base_var.set(get_ai_api_base())
        self.model_var.set(get_ai_model())

        masked = get_apikey_masked()
        if masked:
            self.api_key_var.set(masked)
            self.key_hint_var.set("已有 Key（掩码显示），如需更换请直接输入新 Key")
        else:
            self.api_key_var.set("")
            self.key_hint_var.set("尚未配置 API Key，AI 查词功能将不可用")

    def _toggle_key_visibility(self):
        """切换 Key 明文/掩码显示"""
        if self.show_key_var.get():
            self.api_key_entry.config(show="")
        else:
            self.api_key_entry.config(show="•")

    def _test_connection(self):
        """测试 API 连接"""
        import json
        import urllib.request
        import urllib.error
        import threading

        api_base = self.api_base_var.get().strip()
        api_key = self.api_key_var.get().strip()
        model = self.model_var.get().strip()

        if not api_base:
            messagebox.showwarning("提示", "请输入 API 地址")
            return
        if not api_key:
            messagebox.showwarning("提示", "请输入 API Key")
            return

        # 如果用户没有修改掩码值，使用已保存的真实 Key
        if get_apikey_masked() and api_key == get_apikey_masked():
            from config import _load_apikey
            api_key = _load_apikey()

        self._set_buttons_state(tk.DISABLED)

        def do_test():
            payload = json.dumps({
                "model": model or "gpt-3.5-turbo",
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 5,
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
                with urllib.request.urlopen(req, timeout=15) as resp:
                    result = json.loads(resp.read().decode())
                self.after(0, lambda: self._on_test_success(result))
            except urllib.error.HTTPError as e:
                body = e.read().decode() if e.fp else ""
                self.after(0, lambda: self._on_test_fail(f"HTTP {e.code}: {body[:300]}"))
            except Exception as e:
                self.after(0, lambda: self._on_test_fail(str(e)))

        threading.Thread(target=do_test, daemon=True).start()

    def _on_test_success(self, result):
        self._set_buttons_state(tk.NORMAL)
        messagebox.showinfo(
            "✅ 连接成功",
            f"API 连接正常！\n模型返回: {result['choices'][0]['message']['content'][:50]}...",
        )

    def _on_test_fail(self, error_msg):
        self._set_buttons_state(tk.NORMAL)
        messagebox.showerror("❌ 连接失败", f"无法连接到 API：\n{error_msg}")

    def _set_buttons_state(self, state):
        for child in self.winfo_children():
            if isinstance(child, ttk.Frame):
                for btn in child.winfo_children():
                    if isinstance(btn, ttk.Button):
                        btn.config(state=state)

    def _save(self):
        """保存设置"""
        api_base = self.api_base_var.get().strip()
        model = self.model_var.get().strip()
        api_key_input = self.api_key_var.get().strip()

        if not api_base:
            messagebox.showwarning("提示", "请输入 API 地址")
            return

        # 判断用户是否输入了新 Key（掩码值不等于真实值）
        import config as cfg_module
        # 刷新缓存
        cfg_module._cached_apikey = None
        real_key = cfg_module._load_apikey()
        masked = get_apikey_masked()

        key_to_save = None  # None = 不修改
        if not api_key_input:
            # 用户清空了 → 删除 Key
            key_to_save = ""
        elif masked and api_key_input == masked:
            # 用户没改掩码 → 保留原 Key
            key_to_save = None
        else:
            # 用户输入了新 Key
            key_to_save = api_key_input

        ok1 = save_settings(api_base, model)

        ok2 = True
        if key_to_save is not None:
            ok2 = save_apikey(key_to_save)

        if ok1 and ok2:
            messagebox.showinfo("✅ 保存成功", "AI 配置已保存，下次查词时生效。")
            self.destroy()
        else:
            messagebox.showerror("❌ 保存失败", "写入配置文件失败，请检查磁盘权限。")
