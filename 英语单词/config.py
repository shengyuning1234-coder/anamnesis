"""
配置文件 —— 支持从 data/settings.json 动态加载 AI 配置
可通过图形界面「设置」按钮修改，无需手动编辑此文件
"""

import json
import os
import base64
import tempfile
import tenancy

# ========== 路径常量 ==========
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = os.path.abspath(os.environ.get("APP_DATA_DIR", os.path.join(_BASE_DIR, "data")))
def _settings_file(): return tenancy.path('settings.json')
def _apikey_file(): return tenancy.path('.apikey')

# ========== 数据库配置 ==========
DB_PATH = os.path.join(_DATA_DIR, "words.db")

# ========== 在线词典 API ==========
# 免费词典 API，无需 Key
DICT_API_URL = "https://api.dictionaryapi.dev/api/v2/entries/en/{word}"

# ========== 本地 MDX 词典配置 ==========
# 可通过环境变量 LOCAL_DICT_PATH 覆盖（Docker 部署时使用）
_LOCAL_DICT_PATH = os.environ.get(
    "LOCAL_DICT_PATH",
    os.path.join(_BASE_DIR, "..", "朗文英汉", "oaldpe.mdx")
)

def get_local_dict_path() -> str:
    return os.path.normpath(_LOCAL_DICT_PATH)

# ========== 默认 AI 配置 ==========
_DEFAULT_AI_CONFIG = {
    "api_base": "https://api.openai.com/v1",
    "model": "gpt-3.5-turbo",
}

# ========== 学习系统默认配置 ==========
_DEFAULT_LEARNING_CONFIG = {
    "daily_quota": 20,          # 每日新词配额 1-200
    "review_mode": "mixed",     # en2cn / cn2en / mixed
    "auto_decay": True,         # 是否自动衰减过期未复习的熟练度
}


def _ensure_data_dir():
    """确保 data 目录存在"""
    if not os.path.isdir(_DATA_DIR):
        os.makedirs(_DATA_DIR)


def _load_settings() -> dict:
    """从 settings.json 加载配置，不存在则返回默认值"""
    _ensure_data_dir()
    if os.path.isfile(_settings_file()):
        try:
            with open(_settings_file(), "r", encoding="utf-8") as f:
                data = json.load(f)
            # 合并默认值，确保所有键都存在
            merged = dict(_DEFAULT_AI_CONFIG)
            merged.update(_DEFAULT_LEARNING_CONFIG)
            merged.update(data)
            return merged
        except (json.JSONDecodeError, IOError):
            pass
    merged = dict(_DEFAULT_AI_CONFIG)
    merged.update(_DEFAULT_LEARNING_CONFIG)
    return merged


def _load_apikey() -> str:
    """从 .apikey 文件加载 API Key（base64 编码存储）"""
    _ensure_data_dir()
    if os.path.isfile(_apikey_file()):
        try:
            with open(_apikey_file(), "r", encoding="utf-8") as f:
                encoded = f.read().strip()
            if encoded:
                return base64.b64decode(encoded).decode("utf-8")
        except Exception:
            pass
    return ""


def save_settings(api_base: str, model: str) -> bool:
    """
    保存 AI 配置（不含 API Key）到 settings.json
    读取现有配置后合并写入，不覆盖学习设置
    返回是否成功
    """
    _ensure_data_dir()
    try:
        current = _load_settings()
        current["api_base"] = api_base.strip()
        current["model"] = model.strip()
        with open(_settings_file(), "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False, indent=2)
        global _cached_settings
        _cached_settings = current
        return True
    except IOError:
        return False


def save_apikey(api_key: str) -> bool:
    """
    保存 API Key 到 .apikey 文件（base64 编码）
    传入空字符串则删除文件
    返回是否成功
    """
    _ensure_data_dir()
    try:
        key = api_key.strip()
        if not key:
            # 删除 key 文件
            if os.path.isfile(_apikey_file()):
                os.remove(_apikey_file())
            global _cached_apikey
            _cached_apikey = ""
            return True
        encoded = base64.b64encode(key.encode("utf-8")).decode("ascii")
        fd,temporary=tempfile.mkstemp(prefix='.apikey-',dir=tenancy.directory())
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(encoded)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporary,_apikey_file())
        finally:
            if os.path.exists(temporary): os.unlink(temporary)
        _cached_apikey = key
        return True
    except IOError:
        return False


def get_apikey_masked() -> str:
    """
    获取掩码后的 API Key（用于界面展示）
    如 sk-abc...xyz12
    """
    key = _load_apikey()
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return key[:4] + "***" + key[-4:]


# ========== 模块级缓存（首次加载后使用） ==========
_cached_settings = None
_cached_apikey = None


def _get_settings() -> dict:
    return _load_settings()


def _get_apikey() -> str:
    key = _load_apikey()
    if not key and tenancy.profile.get() != 'admin':
        token = tenancy.profile.set('admin')
        try: key = _load_apikey()
        finally: tenancy.profile.reset(token)
    return key


# ========== 对外暴露的动态属性 ==========

def get_ai_api_key() -> str:
    """获取当前 API Key"""
    if 'resolve_ai' in globals(): return resolve_ai()['key']
    return _get_apikey()


def get_ai_api_base() -> str:
    """获取当前 API 地址"""
    return _get_settings().get("api_base", _DEFAULT_AI_CONFIG["api_base"])


def get_ai_model() -> str:
    """获取当前模型名称"""
    return _get_settings().get("model", _DEFAULT_AI_CONFIG["model"])


# 兼容旧代码的模块级访问（动态读取，非固定值）
# 推荐使用 get_ai_api_key() / get_ai_api_base() / get_ai_model() 函数


# ========== 学习系统配置 ==========

def get_daily_quota() -> int:
    """获取每日新词配额"""
    return _get_settings().get("daily_quota", _DEFAULT_LEARNING_CONFIG["daily_quota"])


def get_review_mode() -> str:
    """获取默认复习模式"""
    return _get_settings().get("review_mode", _DEFAULT_LEARNING_CONFIG["review_mode"])


def get_auto_decay() -> bool:
    """是否启用自动衰减"""
    return _get_settings().get("auto_decay", _DEFAULT_LEARNING_CONFIG["auto_decay"])


def save_learning_settings(daily_quota: int = None, review_mode: str = None, auto_decay: bool = None) -> bool:
    """保存学习系统配置"""
    _ensure_data_dir()
    try:
        current = _load_settings()
        if daily_quota is not None:
            current["daily_quota"] = daily_quota
        if review_mode is not None:
            current["review_mode"] = review_mode
        if auto_decay is not None:
            current["auto_decay"] = auto_decay
        with open(_settings_file(), "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False, indent=2)
        global _cached_settings
        _cached_settings = current
        return True
    except IOError:
        return False
