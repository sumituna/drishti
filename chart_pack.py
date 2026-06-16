"""Free chart pack — extract data from Karmi vedic engine response."""

import json
import os
import re
import requests
from datetime import datetime

VEDIC_ENGINE_URL = os.environ.get(
    "VEDIC_ENGINE_URL",
    "https://mocha-editor-monogamy.ngrok-free.dev",
).rstrip("/")
VEDIC_ENGINE_CHART_PATH = os.environ.get("VEDIC_ENGINE_CHART_PATH", "/api/vedic-native")

DOMAIN_KEYS = [
    "career", "relationships", "travel",
    "health", "spirituality", "wealth",
]

DOMAIN_API_MAP = {
    "career": "career",
    "wealth": "wealth",
    "relationship": "relationships",
    "health": "health",
    "spirituality": "spirituality",
    "travel": "travel",
}

BAND_MAP = {
    "HIGH": "high",
    "MODERATE": "moderate",
    "LOW": "low",
    "VERY_LOW": "very_low",
}

BAR_MAP = {
    "high": 8,
    "moderate": 5,
    "low": 3,
    "very_low": 1,
}

YOGA_RANK = {"high": 0, "medium": 1, "low": 2, "challenging": 3}

DOMAIN_LABELS = {
    "career": "Career",
    "wealth": "Wealth",
    "relationships": "Relationships",
    "health": "Health",
    "spirituality": "Spirituality",
    "travel": "Travel",
}


def get_chart(body):
    """Fetch raw chart JSON from the Vedic computation engine."""
    try:
        if not VEDIC_ENGINE_URL:
            return {"error": "VEDIC_ENGINE_URL not configured"}

        date_str = body.get("date", "")
        time_str = body.get("time", "00:00")
        year, month, day = [int(x) for x in date_str.split("-")]
        hour, minute = [int(x) for x in time_str.split(":")]

        payload = {
            "year": year,
            "month": month,
            "day": day,
            "hour": hour,
            "minute": minute,
            "lat": float(body.get("lat", 28.6139)),
            "lon": float(body.get("lon", 77.209)),
            "utc_offset": float(body.get("utc_offset") or body.get("timezone", 5.5)),
        }

        url = f"{VEDIC_ENGINE_URL}{VEDIC_ENGINE_CHART_PATH}"
        headers = {
            "Content-Type": "application/json",
            "ngrok-skip-browser-warning": "true",
        }
        response = requests.post(url, json=payload, headers=headers, timeout=45)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}


def _scalar(val) -> str:
    if val is None:
        return ""
    if isinstance(val, dict):
        return str(val.get("planet") or val.get("lord") or val.get("sign") or "")
    return str(val)


def _format_date(end) -> str:
    if not end:
        return "—"
    try:
        if isinstance(end, str):
            d = datetime.fromisoformat(end.replace("Z", "+00:00"))
        else:
            d = end
        return d.strftime("%d %b %Y")
    except Exception:
        return str(end)


def _clean_note(raw: str) -> str:
    if not raw:
        return ""
    note = raw.split(";")[0].strip()
    note = re.sub(r"\[.*?\]", "", note).strip()
    if note.lower() == "none":
        return ""
    return note


def parse_domains_from_context(context: str) -> dict:
    domains = {}
    if not context:
        return domains

    line_re = re.compile(
        r"^\s+(CAREER|RELATIONSHIP|TRAVEL|HEALTH|SPIRITUALITY|WEALTH)"
        r"\s+(\d+)/100\s+\[(\w+)\]",
        re.MULTILINE,
    )
    trigger_re = re.compile(r"^\s+Triggers:\s*(.+)$")

    lines = context.splitlines()
    for i, line in enumerate(lines):
        m = line_re.match(line)
        if not m:
            continue

        band_raw = m.group(3).upper()
        band = BAND_MAP.get(band_raw, band_raw.lower())
        key = DOMAIN_API_MAP[m.group(1).lower()]

        note = ""
        for j in range(i + 1, min(i + 4, len(lines))):
            tm = trigger_re.match(lines[j])
            if tm:
                note = _clean_note(tm.group(1).strip())
                break

        domains[key] = {"band": band, "note": note}

    return domains


def _ensure_domain_scores(domain_scores: dict) -> dict:
    """Always return all 6 domains with band and note."""
    normalized = {}
    for key in DOMAIN_KEYS:
        entry = domain_scores.get(key) if domain_scores else None
        if not isinstance(entry, dict):
            entry = {}
        normalized[key] = {
            "band": entry.get("band") or "moderate",
            "note": entry.get("note") or "",
        }
    return normalized


def _yoga_rank(yoga: dict) -> int:
    eff = (yoga.get("effective_strength") or yoga.get("strength") or "medium").lower()
    return YOGA_RANK.get(eff, 1)


def extract_top_yogas(chart: dict, limit: int = 3):
    yogas = chart.get("yogas") or []
    ranked = sorted(yogas, key=_yoga_rank)
    top = []
    for y in ranked[:limit]:
        top.append({
            "name": y.get("name", ""),
            "planets": y.get("planets_involved") or [],
            "desc": y.get("desc", ""),
        })
    return top, len(yogas)


def extract_free_pack(chart: dict, body: dict) -> dict:
    if chart.get("error"):
        raise ValueError(chart["error"])

    asc = chart.get("ascendant") or {}
    planets = chart.get("planets") or {}
    dasha = chart.get("dasha") or {}
    karakas = chart.get("karakas") or {}
    current_maha = dasha.get("current_maha") or {}
    current_antar = dasha.get("current_antar") or {}

    rising = asc.get("sign", "")
    moon = (planets.get("Moon") or {}).get("sign", "")
    sun = (planets.get("Sun") or {}).get("sign", "")
    atmakaraka = _scalar(karakas.get("Atmakaraka"))
    maha_lord = _scalar(dasha.get("mahas"))
    maha_end = _format_date(current_maha.get("end"))
    antar_lord = _scalar(dasha.get("antar"))
    antar_end = _format_date(current_antar.get("end"))

    context = chart.get("karmi_context") or chart.get("karmi_prompt_context") or ""
    domain_scores = _ensure_domain_scores(parse_domains_from_context(context))

    top_yogas, total_yoga_count = extract_top_yogas(chart)

    return {
        "rising": rising,
        "moon": moon,
        "sun": sun,
        "atmakaraka": atmakaraka,
        "maha_lord": maha_lord,
        "maha_end": maha_end,
        "antar_lord": antar_lord,
        "antar_end": antar_end,
        "top_yogas": top_yogas,
        "total_yoga_count": total_yoga_count,
        "domain_scores": domain_scores,
        "_meta": {
            "name": body.get("name", "Seeker"),
            "date": body.get("date", ""),
            "time": body.get("time", ""),
            "place": body.get("place", ""),
        },
    }


def _bar_line(band: str) -> str:
    filled = BAR_MAP.get(band, 5)
    return "█" * filled + "░" * (10 - filled)


def _yoga_md_line(yoga: dict) -> str:
    planets = yoga.get("planets") or []
    planet_str = " + ".join(planets) if planets else ""
    prefix = f"({planet_str})" if planet_str else ""
    desc = yoga.get("desc", "")
    if prefix:
        return f"◈ {yoga.get('name', '')} {prefix} — {desc}"
    return f"◈ {yoga.get('name', '')} — {desc}"


def build_free_md(pack: dict) -> str:
    meta = pack.get("_meta", {})
    name = meta.get("name", "Seeker")
    date = meta.get("date", "")
    time = meta.get("time", "")
    place = meta.get("place", "")
    today = datetime.now().strftime("%d %b %Y")

    domains = pack.get("domain_scores", {})
    domain_rows = []
    for key in DOMAIN_KEYS:
        d = domains.get(key, {"band": "moderate", "note": ""})
        band = d.get("band", "moderate")
        note = d.get("note", "")
        bar = _bar_line(band)
        band_label = band.replace("_", " ").title()
        row = f"**{DOMAIN_LABELS[key]}**  {bar}  *{band_label}*"
        if note:
            row += f"  — {note}"
        domain_rows.append(row)

    yoga_lines = [_yoga_md_line(y) for y in pack.get("top_yogas", [])]
    remaining = pack.get("total_yoga_count", 0) - len(pack.get("top_yogas", []))

    chart_json = {
        "meta": {
            "name": name,
            "birth": date,
            "place": place,
            "ayanamsa": "Lahiri",
        },
        "identity": {
            "ascendant": pack.get("rising", ""),
            "moon_sign": pack.get("moon", ""),
            "sun_sign": pack.get("sun", ""),
            "atmakaraka": pack.get("atmakaraka", ""),
        },
        "current_dasha": {
            "mahadasha": {
                "lord": pack.get("maha_lord", ""),
                "ends": pack.get("maha_end", ""),
            },
            "antardasha": {
                "lord": pack.get("antar_lord", ""),
                "ends": pack.get("antar_end", ""),
            },
        },
        "top_yogas": pack.get("top_yogas", []),
        "domain_scores": domains,
    }

    return f"""# ✦ Your Karmi Vedic Chart — Free Edition
**{name}** · {date} · {time} · {place}
*Generated by Karmi.ai · {today}*

---

## HOW TO USE THIS FILE
1. Upload this file to ChatGPT, Claude, or Gemini — any free tier works
2. Copy any prompt below and paste it as your first message
3. The AI reads your chart and answers as your personal Vedic astrologer

*This is your permanent chart file. Save it. Use it anytime, forever.*

---

## ✦ YOUR CHART IDENTITY
| | |
|---|---|
| **Rising Sign** | {pack.get('rising', '')} |
| **Moon Sign** | {pack.get('moon', '')} |
| **Sun Sign** | {pack.get('sun', '')} |
| **Atmakaraka** | {pack.get('atmakaraka', '')} |
| **Current Period** | {pack.get('maha_lord', '')} Mahadasha · {pack.get('antar_lord', '')} Antardasha |
| **Mahadasha Ends** | {pack.get('maha_end', '')} |

---

## ✦ YOUR LIFE RIGHT NOW
**{pack.get('maha_lord', '')} Mahadasha**

{chr(10).join(domain_rows)}

---

## ✦ YOUR ACTIVE YOGAS
{chr(10).join(yoga_lines)}

+ {remaining} more yogas in your full chart

---

## ✦ PROMPT LIBRARY

### 🔹 START HERE
> You are a Vedic astrologer trained in classical Parashari tradition.
> Read the chart data at the bottom of this file. Confirm you can see it,
> then tell me my Rising sign, Moon sign, and Mahadasha lord.

### 🔹 PROMPT 1 — Who Am I
> Based on my {pack.get('rising', '')} Rising, {pack.get('moon', '')} Moon, {pack.get('sun', '')} Sun, and Atmakaraka
> {pack.get('atmakaraka', '')} — describe my core personality and what my soul is here
> to learn. Be specific to my chart, not generic.

### 🔹 PROMPT 2 — My Current Period
> I am in {pack.get('maha_lord', '')} Mahadasha and {pack.get('antar_lord', '')} Antardasha ending
> {pack.get('antar_end', '')}. What does this period mean for me specifically?
> What is being tested and what should I focus on?

### 🔹 PROMPT 3 — My Biggest Strength
> From my yogas and planetary strengths, what is my single greatest
> natural advantage? How can I use it more deliberately right now?

### 🔹 PROMPT 4 — This Year
> Based on my current dasha and domain scores — what is my single
> biggest focus for the next 12 months? What would be a waste of energy?

### 🔹 PROMPT 5 — One Honest Warning
> What is the one blind spot or pattern I most need to be aware of?
> Don't soften it.

---

## ✦ WANT TO GO DEEPER?
Full Chart Intelligence Pack — ₹199 once. Yours forever.
Includes full dasha sequences, 10-year transit map,
20 divisional charts, 30 precision prompts, Ankush's master prompt.
→ karmi.ai/pack

---

# ✦ CHART DATA
*The AI reads everything below. You do not need to.*

```json
{json.dumps(chart_json, indent=2)}
```
"""
