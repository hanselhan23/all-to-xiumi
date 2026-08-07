"""
html-to-xiumi 最小配置。

只保留秀米发布功能实际引用的配置项。原项目(Wanyou)的爬虫 / LLM / OCR
等无关配置不在本仓库范围内。
"""

import os
import platform

from .env_loader import load_project_env

load_project_env()


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name, "").strip().lower()
    if not value:
        return default
    return value not in {"0", "false", "no", "off"}


def _env_int(name: str, default: int = 0) -> int:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


# Selenium 选项
HEADLESS = True
PAGE_LOAD_TIMEOUT = 30
PAGE_LOAD_STRATEGY = "eager"
WAIT_TIMEOUT = 15
SELENIUM_BROWSER = os.environ.get(
    "WANYOU_SELENIUM_BROWSER",
    "chrome" if platform.system().lower() == "darwin" else "edge",
).lower()
SELENIUM_CACHE_DIR = "./output/selenium_cache"

# 输出相关(供 h5_generator 回退标题)
OUTPUT_DIR = "./output"
H5_TITLE = "HTML 推送"

# 秀米对接
XIUMI_HOME_URL = os.environ.get("XIUMI_HOME_URL", "https://xiumi.us/studio/v5?lang=zh_CN#/")
XIUMI_EDITOR_URL = os.environ.get("XIUMI_EDITOR_URL", "https://xiumi.us/studio/v5?lang=zh_CN#/paper/for/new")
XIUMI_PROFILE_DIR = "./output/selenium_cache/xiumi-profile"
XIUMI_LOGIN_WAIT_SECONDS = 600
XIUMI_SAVE_WAIT_SECONDS = 30

# 秀米图片处理
XIUMI_IMAGE_MODE = os.environ.get("XIUMI_IMAGE_MODE", "upload").strip().lower()
XIUMI_MAX_INLINE_IMAGE_HTML_CHARS = _env_int("XIUMI_MAX_INLINE_IMAGE_HTML_CHARS", 900000)
XIUMI_IMAGE_UPLOAD_MAX_FAILURES = _env_int("XIUMI_IMAGE_UPLOAD_MAX_FAILURES", 3)
XIUMI_IMAGE_UPLOAD_RETRIES = _env_int("XIUMI_IMAGE_UPLOAD_RETRIES", 2)
XIUMI_IMAGE_UPLOAD_BATCH_SIZE = _env_int("XIUMI_IMAGE_UPLOAD_BATCH_SIZE", 6)
XIUMI_IMAGE_UPLOAD_STALL_SECONDS = _env_int("XIUMI_IMAGE_UPLOAD_STALL_SECONDS", 180)
