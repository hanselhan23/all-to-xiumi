"""
模板注册和查找。
"""

from .base import Template
from .generic import GenericTemplate
from .red import RedTemplate
from .wanyou import WanyouTemplate

_BUILTIN: dict[str, type[Template]] = {
    "generic": GenericTemplate,
    "wanyou": WanyouTemplate,
    "red": RedTemplate,
}


def get_template(name: str = "generic") -> Template:
    """根据名称获取模板实例。"""
    name = name.strip().lower()
    cls = _BUILTIN.get(name, GenericTemplate)
    return cls()


def list_templates() -> list[str]:
    """列出所有内置模板名称。"""
    return list(_BUILTIN.keys())


def register_template(name: str, template_cls: type[Template]) -> None:
    """注册自定义模板类。"""
    _BUILTIN[name.strip().lower()] = template_cls
