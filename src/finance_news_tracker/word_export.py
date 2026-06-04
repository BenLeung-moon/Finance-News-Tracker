"""Render the executive summary as a simple two-page Word document.

Layout (per request):
- Page 1: the executive summary content, kept compact to fit on one page.
- Page 2: the source citations (separated by a page break).
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

GREY = RGBColor(0x66, 0x66, 0x66)
HK_TZ = ZoneInfo("Asia/Hong_Kong")

_DIRECTION = {
    "usd_jpy_up": "USD/JPY up (yen weaker)",
    "usd_jpy_down": "USD/JPY down (yen stronger)",
    "mixed": "Mixed",
    "unclear": "Unclear",
    "usd_jpy_bullish": "Bullish USD/JPY",
    "usd_jpy_bearish": "Bearish USD/JPY",
}

_SOURCE_LABELS = {
    "boj_whatsnew": "Bank of Japan",
    "boj_statistics": "BOJ Statistics",
    "nikkei_asia": "Nikkei Asia",
    "nhk_world": "NHK WORLD-JAPAN",
    "fed_press_monetary": "Federal Reserve (Monetary Policy)",
    "fed_speeches": "Federal Reserve (Speeches)",
    "us_treasury_press": "US Treasury",
    "fxstreet_news": "FXStreet",
    "investing_forex": "Investing.com (Forex)",
}


def _direction(value: str) -> str:
    return _DIRECTION.get(value, value)


def _source_label(source_id: str) -> str:
    return _SOURCE_LABELS.get(source_id, source_id)


def _to_hk(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(HK_TZ)


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _format_generated_time(generated_at: datetime) -> str:
    return f"{_to_hk(generated_at).strftime('%Y-%m-%d %H:%M')} HK time"


def _relevance_label(score: Any) -> str:
    try:
        value = int(score)
    except (TypeError, ValueError):
        value = 0
    if value >= 80:
        return "High"
    if value >= 60:
        return "Medium"
    return "Low"


def _display_date(item: dict[str, Any]) -> str:
    pub = item.get("published_at")
    if pub:
        parsed = _parse_datetime(pub)
        if parsed:
            return _to_hk(parsed).strftime("%Y-%m-%d")
        return str(pub)[:10]
    collected = item.get("collected_at")
    if collected:
        parsed = _parse_datetime(collected)
        if parsed:
            return f"~{_to_hk(parsed).strftime('%Y-%m-%d')} (first seen)"
        return f"~{str(collected)[:10]} (first seen)"
    return "date unknown"


def _add_hyperlink(paragraph, url: str, text: str, size: int = 9) -> None:
    """Append a clickable external hyperlink run to ``paragraph``."""
    r_id = paragraph.part.relate_to(url, RT.HYPERLINK, is_external=True)
    link = OxmlElement("w:hyperlink")
    link.set(qn("r:id"), r_id)

    run = OxmlElement("w:r")
    rpr = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), "0563C1")
    rpr.append(color)
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    rpr.append(underline)
    sz = OxmlElement("w:sz")
    sz.set(qn("w:val"), str(size * 2))  # half-points
    rpr.append(sz)
    run.append(rpr)

    t = OxmlElement("w:t")
    t.text = text
    t.set(qn("xml:space"), "preserve")
    run.append(t)
    link.append(run)
    paragraph._p.append(link)


def _tight(paragraph, before: int = 0, after: int = 4) -> None:
    pf = paragraph.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.line_spacing = 1.0


def _heading(doc: Document, text: str) -> None:
    p = doc.add_paragraph()
    _tight(p, before=6, after=2)
    run = p.add_run(text)
    run.bold = True
    run.font.size = Pt(11)


def write_word_summary(
    llm_summary: dict[str, Any],
    items: list[dict[str, Any]],
    generated_at: datetime,
    out_path: Path,
    max_stories: int = 7,
    *,
    citation_items: list[dict[str, Any]] | None = None,
) -> Path:
    citations = citation_items if citation_items is not None else items
    doc = Document()

    # Compact margins give the content more room to stay on one page.
    for section in doc.sections:
        section.top_margin = section.bottom_margin = Pt(46)   # ~0.64"
        section.left_margin = section.right_margin = Pt(54)   # ~0.75"

    normal = doc.styles["Normal"].font
    normal.name = "Calibri"
    normal.size = Pt(9)

    # ---- Page 1: content -------------------------------------------------
    title = doc.add_paragraph()
    _tight(title, after=2)
    tr = title.add_run("USD/JPY Executive Summary")
    tr.bold = True
    tr.font.size = Pt(16)

    meta = doc.add_paragraph()
    _tight(meta, after=2)
    mr = meta.add_run(
        f"Generated {_format_generated_time(generated_at)}  |  "
        "Sources: BOJ, Nikkei Asia, NHK, Federal Reserve, US Treasury, "
        "FXStreet, Investing.com"
    )
    mr.font.size = Pt(8)
    mr.font.color.rgb = GREY

    _heading(doc, "Market Read")
    p = doc.add_paragraph(str(llm_summary.get("market_read", "")))
    _tight(p, after=6)

    _heading(doc, "Top Stories")
    for i, item in enumerate(items[:max_stories], 1):
        takeaway = item.get("why_it_matters") or item.get("summary", "")
        p = doc.add_paragraph()
        _tight(p, after=4)
        head = p.add_run(f"{i}. {item['title']}")
        head.bold = True
        tag = p.add_run(
            f"  ({_source_label(item['source'])} · "
            f"{_direction(item['likely_usdjpy_direction'])} · "
            f"Relevance {_relevance_label(item.get('relevance_score'))})"
        )
        tag.font.size = Pt(8)
        tag.font.color.rgb = GREY
        if takeaway:
            p.add_run().add_break()
            line = p.add_run(takeaway)
            line.font.size = Pt(9)
        p.add_run().add_break()
        date_run = p.add_run(f"Date: {_display_date(item)}  |  ")
        date_run.font.size = Pt(8)
        date_run.font.color.rgb = GREY
        _add_hyperlink(p, item["url"], "Read more", size=8)

    _heading(doc, "Watchlist")
    watchlist = llm_summary.get("watchlist") or [
        "Monitor BOJ release calendar and upcoming MPM dates",
        "Watch US data (CPI, payrolls) for rate-differential moves",
    ]
    for w in watchlist:
        p = doc.add_paragraph(str(w), style="List Bullet")
        _tight(p, after=2)
        for r in p.runs:
            r.font.size = Pt(9)

    # ---- Page 2: sources -------------------------------------------------
    doc.add_page_break()

    _heading(doc, "Source Citations")
    for item in citations[:15]:
        p = doc.add_paragraph(style="List Bullet")
        _tight(p, after=3)
        _add_hyperlink(p, item["url"], item["title"], size=9)
        tail = p.add_run(f"  — {_source_label(item['source'])}, {_display_date(item)}")
        tail.font.size = Pt(8)
        tail.font.color.rgb = GREY

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))
    return out_path
