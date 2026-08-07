import html
import os
import re
from pathlib import Path
from typing import Iterable


def is_remote_or_data_image(src: str) -> bool:
    value = (src or "").strip()
    if re.match(r"^[a-zA-Z]:[\\/]", value):
        return False
    return bool(
        re.match(r"^(https?:)?//", value)
        or re.match(r"^data:image/", value, flags=re.I)
        or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", value)
    )


def clean_markdown_image_target(src: str) -> str:
    cleaned = html.unescape(src or "").strip().strip("<>").strip('"').strip("'")
    if '"' in cleaned:
        cleaned = cleaned.split('"', 1)[0].strip()
    cleaned = cleaned.split("?", 1)[0].strip()
    if is_remote_or_data_image(cleaned):
        return cleaned

    # html2text may emit Windows paths as doubled backslashes and may escape
    # underscores in Markdown URLs. Normalize both before path probing.
    cleaned = cleaned.replace("\\/", "/")
    cleaned = re.sub(r"\\([_])", r"\1", cleaned)
    cleaned = re.sub(r"[\\/]+", lambda _match: os.sep, cleaned)
    return cleaned


def _with_fixed_inline_basename(path_text: str) -> str:
    dirname, basename = os.path.split(path_text)
    fixed_basename = re.sub(r"^([A-Za-z]+)(\d{4})(\.[^.]+)$", r"\1_\2\3", basename)
    if fixed_basename == basename:
        return path_text
    return os.path.join(dirname, fixed_basename)


def _with_fixed_run_dir(path_text: str) -> str:
    sep = re.escape(os.sep)
    return re.sub(
        rf"(^|{sep})output{sep}(\d{{8}})(\d{{4}})(?={sep})",
        lambda match: f"{match.group(1)}output{os.sep}{match.group(2)}_{match.group(3)}",
        path_text,
    )


def _with_fixed_wanyou_dir(path_text: str) -> str:
    path_text = re.sub(
        rf"images{re.escape(os.sep)}wanyou(?=\d)",
        f"images{os.sep}_wanyou_",
        path_text,
    )
    return re.sub(
        rf"images{re.escape(os.sep)}wanyou_(\d{{8}}_\d{{4}})",
        rf"images{os.sep}_wanyou_\1",
        path_text,
    )


def _candidate_roots(base_dir: str | os.PathLike[str] | None) -> list[Path]:
    roots: list[Path] = []
    if base_dir:
        roots.append(Path(base_dir))
    roots.append(Path.cwd())
    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        try:
            key = str(root.resolve())
        except Exception:
            key = str(root)
        if key not in seen:
            unique.append(root)
            seen.add(key)
    return unique


def iter_image_path_candidates(
    src: str,
    base_dir: str | os.PathLike[str] | None = None,
    extra_roots: Iterable[str | os.PathLike[str]] = (),
) -> list[Path]:
    cleaned = clean_markdown_image_target(src)
    if not cleaned or is_remote_or_data_image(cleaned):
        return []

    normalized = cleaned
    variants = [
        normalized,
        _with_fixed_inline_basename(normalized),
        _with_fixed_run_dir(normalized),
        _with_fixed_inline_basename(_with_fixed_run_dir(normalized)),
        _with_fixed_wanyou_dir(normalized),
        _with_fixed_wanyou_dir(_with_fixed_run_dir(normalized)),
    ]
    basename = os.path.basename(_with_fixed_inline_basename(normalized))

    roots = _candidate_roots(base_dir)
    roots.extend(Path(root) for root in extra_roots)

    candidates: list[Path] = []
    for variant in variants:
        path = Path(variant)
        if path.is_absolute():
            candidates.append(path)
            continue
        for root in roots:
            candidates.append(root / path)

    if f"images{os.sep}inline" in normalized:
        for root in roots:
            candidates.append(root / "images" / "inline" / basename)

        match = re.search(
            rf"output{re.escape(os.sep)}(\d{{8}})_?(\d{{4}}){re.escape(os.sep)}"
            rf"images{re.escape(os.sep)}inline{re.escape(os.sep)}([^{re.escape(os.sep)}]+)$",
            normalized,
        )
        if match:
            fixed_run_dir = f"{match.group(1)}_{match.group(2)}"
            fixed_basename = os.path.basename(_with_fixed_inline_basename(match.group(3)))
            for root in roots:
                candidates.append(root / "output" / fixed_run_dir / "images" / "inline" / fixed_basename)

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        try:
            key = str(candidate.resolve())
        except Exception:
            key = str(candidate)
        if key not in seen:
            unique.append(candidate)
            seen.add(key)
    return unique


def resolve_existing_image_path(
    src: str,
    base_dir: str | os.PathLike[str] | None = None,
    extra_roots: Iterable[str | os.PathLike[str]] = (),
) -> Path | None:
    for candidate in iter_image_path_candidates(src, base_dir=base_dir, extra_roots=extra_roots):
        if candidate.exists():
            return candidate.resolve()
    return None
