from __future__ import annotations

import re


_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
_BAD_CHAR_RE = re.compile(r"[\ufffd]")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
_COMMON_MOJIBAKE_TOKENS = (
    "Ã",
    "Â",
    "â",
    "å",
    "æ",
    "ç",
    "é",
    "è",
    "ä",
    "ï",
    "¤",
    "€",
    "鍏",
    "鏈",
    "璇",
    "闂",
    "绔",
    "鐢",
    "缃",
    "鎵",
)


def _cjk_score(text: str) -> int:
    return len(_CJK_RE.findall(text))


def _penalty_score(text: str) -> int:
    penalty = len(_BAD_CHAR_RE.findall(text)) * 4
    penalty += len(_CONTROL_RE.findall(text)) * 2
    penalty += sum(text.count(token) for token in _COMMON_MOJIBAKE_TOKENS)
    return penalty


def _quality_score(text: str) -> tuple[int, int, int]:
    return (_cjk_score(text), -_penalty_score(text), -len(text))


def _try_repair_once(text: str) -> list[str]:
    candidates: list[str] = []
    for source_encoding in ("latin1", "cp1252"):
        try:
            raw = text.encode(source_encoding)
        except Exception:
            continue

        for target_encoding in ("utf-8", "gbk", "gb18030"):
            try:
                candidates.append(raw.decode(target_encoding))
            except Exception:
                continue
    return candidates


def normalize_text(value: str | None) -> str:
    if value is None:
        return ""

    original = str(value).strip()
    if not original:
        return ""

    seen = {original}
    candidates = [original]
    queue = [original]

    # Some strings are encoded more than once, so iterate a few rounds.
    for _ in range(3):
        next_queue: list[str] = []
        for item in queue:
            for candidate in _try_repair_once(item):
                candidate = candidate.strip()
                if not candidate or candidate in seen:
                    continue
                seen.add(candidate)
                candidates.append(candidate)
                next_queue.append(candidate)
        if not next_queue:
            break
        queue = next_queue

    return max(candidates, key=_quality_score).strip()
