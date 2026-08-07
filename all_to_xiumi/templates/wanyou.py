"""
万有预报模板 — 保留 Wanyou 项目的原有配色和品牌风格。
"""

from .base import Template


class WanyouTemplate(Template):
    """万有预报风格模板，用于生成清华物理系风格的推送。"""

    name = "wanyou"
    hero_mark_text = "清物语 · 物理系风格"
