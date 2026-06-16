"""Free chart pack — extract identity, domains, yogas from Karmi chart API."""

import re
from datetime import datetime

from theme_table import get_theme, get_md_theme

DOMAIN_KEYS = [
    "career", "wealth", "relationships",
    "health", "spirituality", "travel",
]

DOMAIN_API_MAP = {
    "career": "career",
    "wealth": "wealth",
    "relationship": "relationships",
    "relationships": "relationships",
    "health": "health",
    "spirituality": "spirituality",
    "travel": "travel",
}

STRENGTH_TO_FLOAT = {
    "high": 0.91,
    "medium": 0.82,
    "low": 0.70,
    "challenging": 0.65,
}


def score_to_band_bar(score: int):
    if score >= 70:
        return "high", 8
    if score >= 45:
        return "moderate", 5
    if score >= 35:
        return "low-moderate", 4
    if score >= 25:
        return "low", 3
    return "very_low", 1


def parse_domains_from_context(context: str) -> dict:
    """Parse domain lines from EventScorer karmi_context string."""
    domains: dict = {}
    if not context:
        return domains

    line_re = re.compile(
        r"^\s+(CAREER|WEALTH|RELATIONSHIP|HEALTH|SPIRITUALITY|TRAVEL)"
        r"\s+(\d+)/100\s+\[(\w+)\]",
        re.MULTILINE,
    )
    trigger_re = re.compile(
        r"^\s+Triggers:\s*(.+)$",
        re.MULTILINE,
    )

    lines = context.splitlines()
    for i, line in enumerate(lines):
        m = line_re.match(line)
        if not m:
            continue
        raw_name, score_str, band_raw = m.group(1), m.group(2), m.group(3)
        score = int(score_str)
        band, bar = score_to_band_bar(score)
        key = DOMAIN_API_MAP[raw_name.lower()]

        note = ""
        for j in range(i + 1, min(i + 4, len(lines))):
            tm = trigger_re.match(lines[j])
            if tm:
                note = tm.group(1).strip()
                if note.lower() == "none":
                    note = ""
                break

        domains[key] = {
            "band": band,
            "bar": bar,
            "note": note,
            "score": score,
        }

    return domains


def _yoga_strength(yoga: dict) -> float:
    eff = yoga.get("effective_strength") or yoga.get("strength") or "medium"
    return STRENGTH_TO_FLOAT.get(eff, 0.75)


def extract_top_yogas(chart: dict, limit: int = 3) -> tuple[list, int]:
    yogas = chart.get("yogas") or []
    ranked = sorted(yogas, key=_yoga_strength, reverse=True)
    top = []
    for y in ranked[:limit]:
        top.append({
            "name": y.get("name", "Yoga"),
            "effect": y.get("desc", ""),
            "strength": round(_yoga_strength(y), 2),
        })
    return top, len(yogas)


def _format_birth_details(name: str, date: str, time: str, place: str) -> str:
    try:
        dt = datetime.strptime(date, "%Y-%m-%d")
        date_fmt = dt.strftime("%d %b %Y")
    except ValueError:
        date_fmt = date
    return f"{name} · {date_fmt} · {time} · {place}"


def build_free_pack(chart: dict, name: str, date: str, time: str, place: str) -> dict:
    if "error" in chart:
        raise ValueError(chart["error"])

    asc = chart.get("ascendant") or {}
    planets = chart.get("planets") or {}
    dasha = chart.get("dasha") or {}
    rising = asc.get("sign", "—")
    moon = (planets.get("Moon") or {}).get("sign", "—")
    sun = (planets.get("Sun") or {}).get("sign", "—")

    maha_lord = dasha.get("mahas") or (dasha.get("current_maha") or {}).get("lord", "—")

    context = chart.get("karmi_context") or chart.get("karmi_prompt_context") or ""
    domain_scores = parse_domains_from_context(context)
    for key in DOMAIN_KEYS:
        if key not in domain_scores:
            domain_scores[key] = {
                "band": "moderate",
                "bar": 5,
                "note": "Awaiting full domain analysis",
            }

    top_yogas, total_yoga_count = extract_top_yogas(chart)
    theme = get_theme(rising, maha_lord)
    md_theme_line = get_md_theme(maha_lord)

    return {
        "identity": {
            "name": name,
            "birth_details": _format_birth_details(name, date, time, place),
            "rising": rising,
            "moon": moon,
            "sun": sun,
        },
        "theme": theme,
        "mahadasha": {
            "lord": maha_lord,
            "theme_line": md_theme_line,
        },
        "domain_scores": domain_scores,
        "top_yogas": top_yogas,
        "total_yoga_count": total_yoga_count,
    }


def build_free_md(pack: dict) -> str:
    ident = pack["identity"]
    md = pack["mahadasha"]
    domains = pack["domain_scores"]
    yogas = pack["top_yogas"]

    lines = [
        f"# {ident['name']} — Karmi Free Chart Pack",
        "",
        f"**Birth:** {ident['birth_details']}",
        "",
        "## Chart Identity",
        f"- **Rising:** {ident['rising']}",
        f"- **Moon:** {ident['moon']}",
        f"- **Sun:** {ident['sun']}",
        "",
        f"**Chart Theme:** *{pack['theme']}*",
        "",
        "## Life Right Now",
        f"**{md['lord']} Mahadasha** — {md['theme_line']}",
        "",
        "### Domain Scores",
    ]

    labels = {
        "career": "Career",
        "wealth": "Wealth",
        "relationships": "Relationships",
        "health": "Health",
        "spirituality": "Spirituality",
        "travel": "Travel",
    }
    for key in DOMAIN_KEYS:
        d = domains.get(key, {})
        bar = d.get("bar", 5)
        band = d.get("band", "moderate")
        note = d.get("note", "")
        bar_vis = "█" * bar + "░" * (10 - bar)
        lines.append(
            f"- **{labels[key]}** [{band}] {bar_vis} {note}"
        )

    lines += ["", "## Top Active Yogas"]
    for y in yogas:
        lines.append(f"- **{y['name']}** — {y['effect']}")

    extra = pack.get("total_yoga_count", 0) - len(yogas)
    if extra > 0:
        lines.append(f"\n*+ {extra} more yogas in your full chart*")

    lines += [
        "",
        "---",
        "",
        "Generated by [Karmi.ai](https://karmi.ai) · Upload this file to ChatGPT, Claude, or Gemini.",
        "",
        "Unlock your full chart pack at https://karmi.ai/pack",
    ]
    return "\n".join(lines)
