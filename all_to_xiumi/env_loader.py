import os
import re
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"

_LOADED_PATHS: list[str] = []


def _env_override_enabled(value: str | None = None) -> bool:
    if value is None:
        value = os.environ.get("WANYOU_DOTENV_OVERRIDE", "1")
    value = str(value or "1").strip().lower()
    return value not in {"0", "false", "no", "off"}


def _candidate_paths() -> list[Path]:
    paths = [DEFAULT_ENV_PATH]
    explicit = os.environ.get("WANYOU_ENV_FILE", "").strip()
    if explicit:
        explicit_path = Path(explicit).expanduser()
        if not explicit_path.is_absolute():
            explicit_path = PROJECT_ROOT / explicit_path
        paths.append(explicit_path)
    return paths


def _strip_inline_comment(value: str) -> str:
    quote = ""
    escaped = False
    for index, char in enumerate(value):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = ""
            continue
        if char in {"'", '"'}:
            quote = char
            continue
        if char == "#" and (index == 0 or value[index - 1].isspace()):
            return value[:index].rstrip()
    return value.strip()


def _unquote(value: str) -> str:
    value = _strip_inline_comment(value).strip()
    if len(value) < 2:
        return value
    quote = value[0]
    if quote not in {"'", '"'} or value[-1] != quote:
        return value
    inner = value[1:-1]
    if quote == "'":
        return inner
    return (
        inner.replace(r"\\", "\\")
        .replace(r"\"", '"')
        .replace(r"\n", "\n")
        .replace(r"\r", "\r")
        .replace(r"\t", "\t")
    )


def _parse_env_lines(lines: Iterable[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    pattern = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")
    for raw_line in lines:
        line = raw_line.lstrip("\ufeff").strip()
        if not line or line.startswith("#"):
            continue
        match = pattern.match(line)
        if not match:
            continue
        key = match.group(1)
        value = _unquote(match.group(2))
        parsed[key] = value
    return parsed


def load_env_file(path: Path, *, override: bool = True) -> dict[str, str]:
    if not path.exists() or not path.is_file():
        return {}
    values = _parse_env_lines(path.read_text(encoding="utf-8").splitlines())
    for key, value in values.items():
        if override or key not in os.environ:
            os.environ[key] = value
    return values


def load_project_env(*, force: bool = False) -> list[str]:
    global _LOADED_PATHS
    if _LOADED_PATHS and not force:
        return list(_LOADED_PATHS)

    loaded: list[str] = []
    paths = _candidate_paths()
    override_value = os.environ.get("WANYOU_DOTENV_OVERRIDE", "1")
    for path in paths:
        try:
            values = _parse_env_lines(path.resolve().read_text(encoding="utf-8").splitlines())
        except Exception:
            continue
        if "WANYOU_DOTENV_OVERRIDE" in values:
            override_value = values["WANYOU_DOTENV_OVERRIDE"]
    override = _env_override_enabled(override_value)
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        values = load_env_file(resolved, override=override)
        if values:
            loaded.append(str(resolved))
    _LOADED_PATHS = loaded
    return list(_LOADED_PATHS)
