"""Rule 2 enforcement: every number in model prose must trace to a tool output."""
import re
from typing import Any

_DATE = re.compile(r"\b\d{4}-\d{2}(-\d{2})?\b|\b\d{1,2}:\d{2}\b")
_EVID = re.compile(r"\bE\d+\b")
_NUM = re.compile(r"(?<![\w.])(?P<cur>[£$€])?\s?(?P<num>\d[\d,]*(?:\.\d+)?)\s?(?P<suf>%|bn|m|k)?(?![\w])", re.I)
_SCALE = {"k": 1e3, "m": 1e6, "bn": 1e9, "%": 1.0, None: 1.0}
SMALL_INT_OK = 12  # bare counts like "3 tools" / "top 5" are allowed; anything with %, currency or a suffix is not


def collect_numbers(obj: Any, out: list[float] | None = None) -> list[float]:
    out = [] if out is None else out
    if isinstance(obj, bool):
        return out
    if isinstance(obj, (int, float)):
        out.append(abs(float(obj)))
    elif isinstance(obj, dict):
        for v in obj.values():
            collect_numbers(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            collect_numbers(v, out)
    elif isinstance(obj, str):
        for m in re.finditer(r"\d[\d,]*(?:\.\d+)?", _DATE.sub(" ", obj)):  # numbers inside strings e.g. peak month labels
            try:
                out.append(float(m.group().replace(",", "")))
            except ValueError:
                pass
    return out


def find_unsupported(text: str, evidence_numbers: list[float]) -> list[str]:
    cleaned = _EVID.sub(" ", _DATE.sub(" ", text))
    bad = []
    for m in _NUM.finditer(cleaned):
        raw = m.group("num").replace(",", "")
        v = float(raw)
        suf = (m.group("suf") or "").lower() or None
        if re.fullmatch(r"(19|20)\d{2}", raw) and not suf and not m.group("cur"):
            continue  # a year
        if "." not in raw and v <= SMALL_INT_OK and not suf and not m.group("cur"):
            continue
        dec = len(raw.split(".")[1]) if "." in raw else 0
        scale = _SCALE[suf]
        half = 0.5 * 10 ** (-dec) * scale + 1e-9
        if not any(abs(n - v * scale) <= half for n in evidence_numbers):
            bad.append(m.group(0).strip())
    return bad
