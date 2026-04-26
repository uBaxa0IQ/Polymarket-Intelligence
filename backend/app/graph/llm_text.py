"""Parse and normalize LLM output text (JSON, debate footers, evidence lines)."""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from typing import Any


def parse_iso_datetime(raw: Any) -> datetime | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def strip_markdown_fences(text: str) -> str:
    s = text.strip()
    if s.startswith("```"):
        lines = s.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    return s


def parse_json_array(text: str) -> list[Any]:
    s = strip_markdown_fences(text)
    m = re.search(r"\[", s)
    if m and m.start() > 0:
        s = s[m.start() :]
    data = json.loads(s)
    if not isinstance(data, list):
        raise ValueError("Expected JSON array")
    return data


def parse_json_object(text: str) -> dict[str, Any]:
    s = strip_markdown_fences(text)
    m = re.search(r"\{", s)
    if m and m.start() > 0:
        s = s[m.start() :]
    data = json.loads(s)
    if not isinstance(data, dict):
        raise ValueError("Expected JSON object")
    return data


def parse_debate_control_footer(text: str) -> tuple[dict[str, Any] | None, str | None]:
    s = (text or "").strip()
    if not s:
        return None, "empty_response"
    lines = [ln.strip() for ln in s.splitlines() if ln.strip()]
    if lines:
        last = lines[-1]
        if last.startswith("{") and last.endswith("}"):
            try:
                data = json.loads(last)
                if isinstance(data, dict) and "p_yes_estimate" in data:
                    return data, None
            except json.JSONDecodeError:
                pass
    br = s.rfind("{")
    if br != -1:
        try:
            dec = json.JSONDecoder()
            obj, _end = dec.raw_decode(s[br:])
            if isinstance(obj, dict) and "p_yes_estimate" in obj:
                return obj, None
        except json.JSONDecodeError:
            pass
    return None, "parse_failed"


def normalize_debate_control(parsed: dict[str, Any] | None) -> dict[str, Any]:
    p_est: float | None = None
    if parsed:
        pr = parsed.get("p_yes_estimate")
        if pr is not None and isinstance(pr, (int, float)):
            p_est = float(pr)
            if not (0.0 <= p_est <= 1.0):
                p_est = None
    return {"p_yes_estimate": p_est}


def strip_debate_footer(text: str) -> str:
    lines = text.rstrip().splitlines()
    if lines:
        last = lines[-1].strip()
        if last.startswith("{") and last.endswith("}"):
            try:
                data = json.loads(last)
                if isinstance(data, dict) and "p_yes_estimate" in data:
                    return "\n".join(lines[:-1]).rstrip()
            except json.JSONDecodeError:
                pass
    return text


def parse_pub_date(raw: Any) -> date | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return datetime.strptime(s, "%Y-%m-%d").date()
    if re.match(r"^\d{4}-\d{2}$", s):
        return datetime.strptime(s + "-01", "%Y-%m-%d").date()
    if re.match(r"^\d{4}$", s):
        return date(int(s), 1, 1)
    return None


def format_news_lines(items: list[dict], cutoff: date | None) -> list[str]:
    out: list[str] = []
    for it in items:
        if it.get("relevance") not in ("HIGH", "MEDIUM"):
            continue
        fact = it.get("fact")
        if not fact:
            continue
        src = it.get("source", "?")
        dt_raw = it.get("date", "?")
        parsed = parse_pub_date(dt_raw)
        if cutoff and parsed and parsed < cutoff:
            continue
        sy = it.get("supports_yes")
        out.append(
            f"[NEWS {it['relevance']}] {fact} (source: {src}, date: {dt_raw}, supports_yes: {sy})"
        )
    return out


def format_base_rate_lines(items: list[dict]) -> list[str]:
    out: list[str] = []
    for it in items:
        finding = it.get("finding")
        if not finding:
            continue
        typ = it.get("type", "?")
        src = it.get("source", "?")
        dt = it.get("date", "?")
        ip = it.get("implied_probability")
        notes = it.get("notes")
        extra = f" implied_p={ip}" if ip is not None else ""
        n = f" notes={notes}" if notes else ""
        out.append(f"[BASE {typ}{extra}] {finding} (source: {src}, date: {dt}){n}")
    return out


def stage2_web_search_query(ma: dict) -> str | None:
    q = str(ma.get("question") or "").strip()
    return q[:800] if q else None
