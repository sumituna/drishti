from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import anthropic
import requests
import os
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

load_dotenv()

import json as json_module
from pathlib import Path

PROMPTS_FILE = Path(__file__).parent / 'prompts.json'

def load_prompts():
    try:
        with open(PROMPTS_FILE, 'r', encoding='utf-8') as f:
            return json_module.load(f)
    except Exception:
        return {}

def save_prompts(prompts):
    try:
        with open(PROMPTS_FILE, 'w', encoding='utf-8') as f:
            json_module.dump(prompts, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False

from chart_pack import build_free_pack, build_free_md

app = Flask(__name__)
CORS(app)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
NGROK_URL = os.getenv("NGROK_URL")
VEDIC_ENGINE_URL = os.environ.get(
    "VEDIC_ENGINE_URL",
    "https://mocha-editor-monogamy.ngrok-free.app",
).rstrip("/")
# Chart computation path on the engine (override to /chart-free when available)
VEDIC_ENGINE_CHART_PATH = os.environ.get("VEDIC_ENGINE_CHART_PATH", "/api/vedic-native")

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

def _birth_to_engine_payload(birth_data):
    date_str = birth_data.get("date", "")
    time_str = birth_data.get("time", "00:00")
    year, month, day = [int(x) for x in date_str.split("-")]
    hour, minute = [int(x) for x in time_str.split(":")]
    return {
        "year": year, "month": month, "day": day,
        "hour": hour, "minute": minute,
        "lat": float(birth_data.get("lat", 28.6139)),
        "lon": float(birth_data.get("lon", 77.209)),
        "utc_offset": float(birth_data.get("utc_offset", 5.5)),
    }

def fetch_chart_from_engine(birth_data):
    """POST birth data to the remote Vedic computation engine via HTTP."""
    try:
        if not VEDIC_ENGINE_URL:
            return {"error": "VEDIC_ENGINE_URL not configured"}
        payload = _birth_to_engine_payload(birth_data)
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

def get_vedic_context(birth_data):
    try:
        date_str = birth_data.get("date", "")
        time_str = birth_data.get("time", "00:00")
        year, month, day = [int(x) for x in date_str.split("-")]
        hour, minute = [int(x) for x in time_str.split(":")]
        payload = {
            "year": year, "month": month, "day": day,
            "hour": hour, "minute": minute,
            "lat": float(birth_data.get("lat", 28.6139)),
            "lon": float(birth_data.get("lon", 77.209)),
            "utc_offset": float(birth_data.get("utc_offset", 5.5))
        }
        response = requests.post(f"{NGROK_URL}/api/vedic-native", json=payload, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def get_today_transits():
    try:
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        payload = {"date": today, "lat": 28.6139, "lon": 77.209, "utc_offset": 5.5}
        response = requests.post(f"{NGROK_URL}/api/transit-day", json=payload, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def get_year_ahead(birth_data):
    try:
        date_str = birth_data.get("date", "")
        time_str = birth_data.get("time", "00:00")
        year, month, day = [int(x) for x in date_str.split("-")]
        hour, minute = [int(x) for x in time_str.split(":")]

        payload = {
            "year": year, "month": month, "day": day,
            "hour": hour, "minute": minute,
            "lat": float(birth_data.get("lat", 28.6139)),
            "lon": float(birth_data.get("lon", 77.209)),
            "utc_offset": float(birth_data.get("utc_offset", 5.5))
        }

        response = requests.post(
            f"{NGROK_URL}/api/year-ahead",
            json=payload,
            timeout=60
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def build_year_context(months):
    """Build a month-by-month score table for Claude's prompt"""
    if not months:
        return ""
    lines = ["YEAR AHEAD — MONTHLY DOMAIN SCORES:"]
    for m in months:
        scores = m.get('scores', {})
        career = scores.get('career', 0)
        wealth = scores.get('wealth', 0)
        rel = scores.get('relationship', 0)
        health = scores.get('health', 0)
        lines.append(
            f"{m['month_label']}: Career {career} · Wealth {wealth} · "
            f"Relationships {rel} · Health {health} · "
            f"Dasha: {m['dasha_path']} · Tone: {m['transit_tone']}"
        )
    return "\n".join(lines)

@app.route("/year-ahead", methods=["POST"])
def year_ahead():
    data = request.json
    birth_data = {
        "date": data.get("date"),
        "time": data.get("time"),
        "lat": data.get("lat"),
        "lon": data.get("lon"),
        "utc_offset": data.get("timezone")
    }

    result = get_year_ahead(birth_data)

    if "error" in result:
        return jsonify({"error": result["error"]}), 500

    months = result.get("months", [])

    # Also ask Claude to narrate the year
    year_context = build_year_context(months)
    name = data.get("name", "Seeker")

    try:
        message = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=600,
            messages=[{
                "role": "user",
                "content": f"""You are Drishti — a Vedic oracle. Based on these month-by-month domain scores, write a 3-sentence year narrative for {name}. Identify the peak window, the low period, and the single most important timing insight. Be specific about months. Do not mention raw numbers — translate them into plain language.

{year_context}

Respond in JSON:
{{
  "year_narrative": "3 sentences covering peak, low, and key insight",
  "peak_window": "e.g. July–September 2026",
  "peak_domain": "e.g. career",
  "low_window": "e.g. October–November 2026",
  "key_insight": "One sentence of Vedic timing wisdom"
}}"""
            }]
        )
        raw = message.content[0].text
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        import json
        narrative = json.loads(raw.strip())
    except Exception as e:
        narrative = {
            "year_narrative": "Your year ahead holds distinct phases of growth and consolidation.",
            "peak_window": "See chart below",
            "peak_domain": "career",
            "low_window": "See chart below",
            "key_insight": "Timing is everything in Vedic astrology."
        }

    return jsonify({
        "success": True,
        "months": months,
        "narrative": narrative,
        "year_context": year_context
    })

def format_transit_context(transit_result):
    if "error" in transit_result:
        return ""
    planets = transit_result.get("planets", {})
    lines = []
    for planet, data in planets.items():
        if isinstance(data, dict):
            sign = data.get("sign", "")
            house = data.get("house", "")
            retro = " (R)" if data.get("retrograde") else ""
            nakshatra = data.get("nakshatra", "")
            line = f"- {planet}: {sign} H{house}{retro} {nakshatra}".strip()
            lines.append(line)
    if lines:
        return "TODAY'S TRANSITS (current sky):\n" + "\n".join(lines)
    return ""

def build_agent_prompt(agent_type, name, situation, question, timeline, vedic_context, transit_context, preference='plain'):
    prompts = load_prompts()
    agent_key = f"{agent_type}_agent"
    custom_prompt = prompts.get(agent_key, "")

    agent_configs = {
        "career": {
            "title": "Career & Purpose Agent",
            "focus": "10th house, 6th house, Saturn, Sun, Jupiter, D10 chart, Artha houses (2nd/6th/10th)",
            "domain": "career, profession, purpose, work, ambition, recognition, business"
        },
        "relationships": {
            "title": "Relationships & Love Agent",
            "focus": "7th house, 5th house, Venus, Mars, Moon, Upapada Lagna, Navamsha D9",
            "domain": "love, marriage, partnerships, family, social connections, collaboration"
        },
        "wealth": {
            "title": "Wealth & Resources Agent",
            "focus": "2nd house, 11th house, Jupiter, Venus, Dhana yogas, Ashtakavarga bindus in wealth houses",
            "domain": "money, finances, investments, assets, income, material security"
        },
        "timing": {
            "title": "Timing & Energy Agent",
            "focus": "current Mahadasha, Antardasha, Pratyantar, transits, Moon nakshatra, upcoming dasha shifts",
            "domain": "timing of events, energy quality, windows of opportunity, periods to avoid"
        }
    }

    config = agent_configs[agent_type]
    transit_section = f"\n\n{transit_context}" if transit_context else ""

    if preference == 'plain':
        language_rule = """
LANGUAGE: Plain & Personal mode.
Never use Vedic jargon. Translate everything to plain English:
- "sub-period" not "Antardasha", "main period" not "Mahadasha"
- "minor cycle" not "Pratyantar", "career house" not "H10"
- "at full strength" not "exalted", "weakened by Sun" not "combust"
- "challenging house" not "dusthana", "soul planet" not "Atmakaraka"
Write warmly, like explaining to a smart friend."""
    else:
        language_rule = """
LANGUAGE: Vedic & Technical mode.
Use full Vedic terminology — dashas, nakshatras, house numbers, yogas, dignities."""

    return f"""You are the {config['title']} — a specialist Vedic astrologer who reads only through the lens of {config['domain']}.

You have been given a person's complete Vedic birth chart. Your job is to analyze ONLY your domain and give a probability-grounded assessment.

PERSON: {name}

THEIR CONTEXT:
- Situation: {situation}
- Question: {question}
- Timeline: {timeline}

VEDIC CHART:
{vedic_context}{transit_section}

YOUR SPECIALIST FOCUS: {config['focus']}

Respond in this exact JSON:
{{
  "domain": "{agent_type}",
  "score": <integer 0-100 representing favorability>,
  "verdict": "One sentence verdict with the score woven in naturally",
  "signals": [
    "Specific planet/house/dasha signal 1",
    "Specific planet/house/dasha signal 2",
    "Specific planet/house/dasha signal 3"
  ],
  "timing": "Specific timing insight for this domain",
  "advice": "One concrete action this person should take based on their chart"
}}

{language_rule}

SPECIALIST INSTRUCTIONS:
{custom_prompt if custom_prompt else f"Focus on {config['focus']} for this reading."}

Rules:
- Score must be justified by actual chart factors
- Every signal must name a specific planet, house, nakshatra, or dasha
- Timing must reference actual dasha periods or transit windows
- Speak only about your domain — do not comment on other life areas
- Do not mention Western astrology
- Do not break JSON structure"""

def build_synthesis_prompt(name, situation, question, timeline, agent_results, preference='plain'):
    agents_text = ""
    for agent in agent_results:
        agents_text += f"\n{agent['domain'].upper()} AGENT (score: {agent['score']}):\n"
        agents_text += f"Verdict: {agent['verdict']}\n"
        agents_text += f"Timing: {agent['timing']}\n"
        agents_text += f"Advice: {agent['advice']}\n"

    prompts = load_prompts()
    synthesis_voice = prompts.get('synthesis_voice', 'Speak as a warm brilliant Vedic astrologer.')
    plain_rules = prompts.get('plain_mode_rules', '')
    vedic_rules = prompts.get('vedic_mode_rules', '')

    if preference == 'plain':
        language_instruction = plain_rules
    else:
        language_instruction = vedic_rules

    return f"""{synthesis_voice}

You have received reports from 4 specialist agents who have each read {name}'s chart.
Your job is to synthesize them into one unified consultation — the way a master astrologer 
would speak directly to this person.

PERSON: {name}
SITUATION: {situation}
QUESTION: {question}  
TIMELINE: {timeline}

SPECIALIST REPORTS:
{agents_text}

{language_instruction}

Respond in this exact JSON:
{{
  "overall_score": <0-100>,
  "synthesis": "3-4 sentences in consultation voice — open with '{name}, let me tell you what I see here.' Then the core message. Then what matters most.",
  "convergence": "One sentence — the theme appearing across all domains, in plain language",
  "tension": "One sentence — the key tension or trade-off, in plain language",
  "oracle_note": "One poetic but grounded sentence of wisdom for this person",
  "top_action": "The single most important thing they should do — specific and actionable",
  "followup_questions": [
    "A natural next question about their primary concern",
    "An angle they haven't considered",
    "A timing or decision question"
  ]
}}

Rules:
- synthesis MUST open with addressing {name} directly by name
- Every sentence must feel like it was written for this specific person
- oracle_note should feel ancient but immediately relevant
- top_action must be concrete — a real thing they can do this week
- Do not break JSON structure"""

def detect_chart_type(question, situation=""):
    text = (question + " " + situation).lower()
    
    decision_words = ['should i', 'shall i', 'is it a good time', 'right time', 
                      'right decision', 'take this', 'accept', 'reject', 'worth it',
                      'good idea', 'bad idea', 'do it', 'move forward', 'go ahead']
    
    timing_words = ['when', 'timing', 'how long', 'which period', 'next few years',
                    'best time', 'peak', 'window', 'how soon', 'which year',
                    'which month', 'forecast', 'future', 'ahead', 'coming years']
    
    relationship_words = ['relationship', 'partner', 'love', 'marriage', 'compatible',
                          'romantic', 'spouse', 'boyfriend', 'girlfriend', 'husband',
                          'wife', 'dating', 'soulmate', 'find love', 'meet someone']
    
    for word in decision_words:
        if word in text:
            return 'decision_matrix'
    
    for word in relationship_words:
        if word in text:
            return 'compatibility_venn'
    
    for word in timing_words:
        if word in text:
            return 'dasha_river'
    
    return 'none'

def build_relationship_subscores_prompt(name, vedic_context):
    return f"""You are a Vedic astrology specialist. Based on this birth chart, 
compute 4 relationship readiness scores for {name}.

CHART:
{vedic_context}

Focus on:
- Attraction: Venus strength, 5th house, Mars position (raw magnetism and desire)
- Communication: Mercury, 3rd house, Moon (emotional expression in relationships)  
- Longevity: 7th house lord strength, Saturn influence, Navamsha D9 (commitment capacity)
- Karma: Rahu/Ketu axis, 8th house, past life indicators (karmic relationship patterns)

Respond in exact JSON:
{{
  "attraction": <0-100>,
  "communication": <0-100>,
  "longevity": <0-100>,
  "karma": <0-100>,
  "attraction_desc": "Max 8 words — one punchy phrase only",
  "communication_desc": "Max 8 words — one punchy phrase only",
  "longevity_desc": "Max 8 words — one punchy phrase only",
  "karma_desc": "Max 8 words — one punchy phrase only",
  "readiness_summary": "Two sentences — overall relationship readiness right now"
}}

Rules:
- Scores must reflect actual chart factors
- Plain language descriptions — no jargon
- Do not break JSON"""

def call_agent(agent_type, name, situation, question, timeline, vedic_context, transit_context, preference='plain'):
    try:
        prompt = build_agent_prompt(agent_type, name, situation, question, timeline, vedic_context, transit_context, preference)
        message = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = message.content[0].text
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception as e:
        return {
            "domain": agent_type,
            "score": 50,
            "verdict": f"Reading unavailable for this domain.",
            "signals": ["Chart data received", "Analysis incomplete", "Try again"],
            "timing": "Unable to determine timing",
            "advice": "Consult a Vedic astrologer directly"
        }

@app.route("/ask", methods=["POST"])
def ask():
    data = request.json
    name = data.get("name", "Seeker")
    question = data.get("question", "")
    birth_data = {
        "date": data.get("date"),
        "time": data.get("time"),
        "place": data.get("place"),
        "lat": data.get("lat"),
        "lon": data.get("lon"),
        "utc_offset": data.get("timezone")
    }

    vedic_result = get_vedic_context(birth_data)
    if "error" in vedic_result:
        return jsonify({"error": f"Chart calculation failed: {vedic_result['error']}"}), 500

    vedic_context = vedic_result.get("karmi_prompt_context") or str(vedic_result)
    transit_result = get_today_transits()
    transit_context = format_transit_context(transit_result)

    try:
        message = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1024,
            messages=[{"role": "user", "content": build_single_prompt(question, vedic_context, name, transit_context)}]
        )
        raw = message.content[0].text
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        reading = json.loads(raw.strip())
        return jsonify({"success": True, "reading": reading})
    except Exception as e:
        return jsonify({"error": f"Reading failed: {str(e)}"}), 500

def build_single_prompt(question, vedic_context, name, transit_context=""):
    transit_section = f"\n\n{transit_context}" if transit_context else ""
    return f"""You are Drishti — an ancient Vedic oracle with the precision of a master astrologer and the clarity of a trusted advisor.

PERSON: {name}
THEIR QUESTION: {question}

THEIR VEDIC CHART CONTEXT:
{vedic_context}{transit_section}

Respond in this exact JSON structure:
{{
  "verdict": "One powerful sentence with a probability",
  "signals": ["Signal 1", "Signal 2", "Signal 3"],
  "timing": "Specific timing insight",
  "oracle_note": "One poetic Vedic wisdom sentence",
  "followup_questions": ["Question 1", "Question 2", "Question 3"]
}}

Rules: probability must be chart-justified, every signal names a specific planet/house/dasha, no Western astrology, no broken JSON."""

@app.route("/ask-v2", methods=["POST"])
def ask_v2():
    data = request.json
    name = data.get("name", "Seeker")
    situation = data.get("situation", "")
    question = data.get("question", "")
    timeline = data.get("timeline", "")
    birth_data = {
        "date": data.get("date"),
        "time": data.get("time"),
        "place": data.get("place"),
        "lat": data.get("lat"),
        "lon": data.get("lon"),
        "utc_offset": data.get("timezone")
    }

    # Step 1: Get chart + transits
    vedic_result = get_vedic_context(birth_data)
    if "error" in vedic_result:
        return jsonify({"error": f"Chart calculation failed: {vedic_result['error']}"}), 500

    vedic_context = vedic_result.get("karmi_prompt_context") or str(vedic_result)
    transit_result = get_today_transits()
    transit_context = format_transit_context(transit_result)
    preference = data.get("preference", "plain")

    # Step 2: Run 4 agents in parallel
    agent_types = ["career", "relationships", "wealth", "timing"]
    agent_results = []

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(
                call_agent, agent_type, name, situation, question, timeline, vedic_context, transit_context, preference
            ): agent_type
            for agent_type in agent_types
        }
        for future in as_completed(futures):
            result = future.result()
            agent_results.append(result)

    # Sort results in consistent order
    order = ["career", "relationships", "wealth", "timing"]
    agent_results.sort(key=lambda x: order.index(x.get("domain", "career")))

    # Detect chart type
    chart_type = detect_chart_type(question, situation)
    
    # If relationship question, get sub-scores
    relationship_subscores = None
    if chart_type == 'compatibility_venn':
        try:
            rs_message = client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=400,
                messages=[{
                    "role": "user",
                    "content": build_relationship_subscores_prompt(name, vedic_context)
                }]
            )
            rs_raw = rs_message.content[0].text
            if rs_raw.startswith("```"):
                rs_raw = rs_raw.split("```")[1]
                if rs_raw.startswith("json"):
                    rs_raw = rs_raw[4:]
            relationship_subscores = json.loads(rs_raw.strip())
        except Exception as e:
            relationship_subscores = {
                "attraction": 50, "communication": 50,
                "longevity": 50, "karma": 50,
                "attraction_desc": "Venus indicates moderate attraction energy",
                "communication_desc": "Mercury suggests average communication patterns",
                "longevity_desc": "7th house shows mixed commitment indicators",
                "karma_desc": "Nodal axis reveals karmic relationship themes",
                "readiness_summary": "Your chart shows readiness with areas to develop."
            }

    # Step 3: Synthesis
    try:
        preference = data.get("preference", "plain")
        synthesis_prompt = build_synthesis_prompt(name, situation, question, timeline, agent_results, preference)
        message = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1024,
            messages=[{"role": "user", "content": synthesis_prompt}]
        )
        raw = message.content[0].text
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        synthesis = json.loads(raw.strip())
    except Exception as e:
        synthesis = {
            "overall_score": 50,
            "synthesis": "Your chart holds complex patterns across all life domains.",
            "convergence": "Multiple areas of your life are in transition simultaneously.",
            "tension": "The chart shows competing pulls between different life priorities.",
            "oracle_note": "The stars reveal what patience and clarity can illuminate.",
            "top_action": "Focus on one domain at a time for clearest results.",
            "followup_questions": ["What is my strongest domain right now?", "When does this period shift?", "What should I prioritize?"]
        }

    return jsonify({
        "success": True,
        "agents": agent_results,
        "synthesis": synthesis,
        "chart_type": chart_type,
        "relationship_subscores": relationship_subscores
    })

def _pack_birth_payload(data):
    return {
        "date": data.get("date"),
        "time": data.get("time", "00:00"),
        "lat": data.get("lat"),
        "lon": data.get("lon"),
        "utc_offset": data.get("timezone") or data.get("utc_offset", 5.5),
    }

@app.route("/generate-free-pack", methods=["POST"])
def generate_free_pack():
    try:
        data = request.json or {}
        name = (data.get("name") or "Seeker").strip()
        date = data.get("date")
        time = data.get("time", "00:00")
        place = (data.get("place") or "").strip()

        if not date or not time or not place:
            return jsonify({"error": "Missing birth date, time, or place"}), 400
        if not data.get("lat") or not data.get("lon"):
            return jsonify({"error": "Birth place must be selected from geocode dropdown"}), 400

        chart = fetch_chart_from_engine(_pack_birth_payload(data))
        if "error" in chart:
            return jsonify({"error": chart["error"]}), 500

        pack = build_free_pack(chart, name, date, time, place)
        return jsonify(pack)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/download-free-pack", methods=["GET"])
def download_free_pack():
    try:
        data = request.args
        name = (data.get("name") or "Seeker").strip()
        date = data.get("date")
        time = data.get("time", "00:00")
        place = (data.get("place") or "").strip()

        if not date or not time or not place:
            return jsonify({"error": "Missing birth parameters"}), 400
        if not data.get("lat") or not data.get("lon"):
            return jsonify({"error": "Missing lat/lon"}), 400

        chart = fetch_chart_from_engine({
            "date": date,
            "time": time,
            "lat": data.get("lat"),
            "lon": data.get("lon"),
            "utc_offset": data.get("timezone") or data.get("utc_offset", 5.5),
        })
        if "error" in chart:
            return jsonify({"error": chart["error"]}), 500

        pack = build_free_pack(chart, name, date, time, place)
        md_content = build_free_md(pack)

        safe_name = re.sub(r"[^\w\-]", "_", name)[:40] or "chart"
        filename = f"{safe_name}_karmi_free.md"

        return Response(
            md_content,
            mimetype="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "Drishti is awake"})

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "karmi2026")

def check_admin(req):
    # Check password from header, query param, or JSON body
    auth = req.headers.get("X-Admin-Password", "")
    if auth == ADMIN_PASSWORD:
        return True
    pwd = req.args.get("pwd", "")
    if pwd == ADMIN_PASSWORD:
        return True
    try:
        body = req.get_json(silent=True) or {}
        if body.get("password") == ADMIN_PASSWORD:
            return True
    except:
        pass
    return False

@app.route("/admin", methods=["GET", "POST"])
def admin_page():
    # Simple password form
    if request.method == "POST":
        pwd = request.form.get("password", "")
        if pwd != ADMIN_PASSWORD:
            return admin_login("Incorrect password")
        # Password correct - show studio with prompts
        prompts = load_prompts()
        return admin_studio(prompts)
    return admin_login()

def admin_login(error=""):
    return f"""<!DOCTYPE html>
<html>
<head>
<title>Drishti Prompt Studio</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ background: #07071A; color: #F0EBE0; font-family: system-ui, sans-serif; display: flex; align-items: center; justify-content: center; min-height: 100vh; }}
.box {{ background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); border-radius: 20px; padding: 40px; width: 100%; max-width: 400px; }}
h2 {{ font-size: 20px; font-weight: 400; margin-bottom: 8px; }}
p {{ font-size: 13px; color: rgba(240,235,224,0.5); margin-bottom: 24px; }}
input {{ width: 100%; background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 10px; padding: 12px 14px; color: #F0EBE0; font-size: 14px; outline: none; margin-bottom: 12px; }}
button {{ width: 100%; background: #C9A84C; color: #07071A; border: none; border-radius: 10px; padding: 13px; font-size: 14px; font-weight: 500; cursor: pointer; }}
.error {{ color: #ff6b6b; font-size: 12px; margin-top: 10px; }}
</style>
</head>
<body>
<div class="box">
  <h2>Drishti Prompt Studio</h2>
  <p>Enter your admin password to configure Claude's reading instructions.</p>
  <form method="POST">
    <input type="password" name="password" placeholder="Password" autofocus />
    <button type="submit">Enter →</button>
    {"<div class='error'>" + error + "</div>" if error else ""}
  </form>
</div>
</body>
</html>"""

def admin_studio(prompts):
    fields = [
        ("career_agent", "Career Agent", "How Claude reads career questions — houses, planets, weightings."),
        ("relationships_agent", "Relationships Agent", "How Claude reads love and relationship questions."),
        ("wealth_agent", "Wealth Agent", "How Claude reads money and investment questions."),
        ("timing_agent", "Timing Agent", "How Claude reads timing and period questions."),
        ("synthesis_voice", "Synthesis Voice", "How Drishti speaks when delivering the final reading."),
        ("plain_mode_rules", "Plain Mode Rules", "Translation rules — Vedic terms to plain English."),
        ("vedic_mode_rules", "Vedic Mode Rules", "Instructions for full technical Vedic terminology mode."),
    ]
    
    fields_html = ""
    for key, title, desc in fields:
        value = prompts.get(key, "").replace('"', '&quot;').replace('<', '&lt;')
        fields_html += f"""
        <div class="section">
          <div class="section-title">{title}</div>
          <div class="section-desc">{desc}</div>
          <textarea name="{key}" rows="7">{value}</textarea>
        </div>"""
    
    # Version history
    history = prompts.get("version_history", [])
    history_html = ""
    if history:
        for i, v in enumerate(reversed(history)):
            history_html += f"""
            <div class="version-item">
              <div>
                <div class="v-label">{v.get('label','Version')}</div>
                <div class="v-date">{v.get('saved_at','')}</div>
              </div>
              <button type="submit" form="restore-form" name="restore_index" value="{len(history)-1-i}">Restore</button>
            </div>"""
    else:
        history_html = "<div class='no-versions'>No versions saved yet.</div>"
    
    return f"""<!DOCTYPE html>
<html>
<head>
<title>Drishti Prompt Studio</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ background: #07071A; color: #F0EBE0; font-family: system-ui, sans-serif; font-size: 14px; }}
.header {{ padding: 20px 40px; border-bottom: 1px solid rgba(255,255,255,0.08); display: flex; align-items: center; justify-content: space-between; }}
.logo {{ font-size: 13px; letter-spacing: 0.2em; }}
.sub {{ font-size: 11px; color: rgba(240,235,224,0.4); margin-top: 3px; }}
.main {{ max-width: 860px; margin: 0 auto; padding: 40px; }}
.section {{ margin-bottom: 32px; }}
.section-title {{ font-size: 11px; letter-spacing: 0.18em; color: #3D9E8C; text-transform: uppercase; margin-bottom: 8px; }}
.section-desc {{ font-size: 12px; color: rgba(240,235,224,0.45); margin-bottom: 10px; line-height: 1.5; }}
textarea {{ width: 100%; background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; padding: 12px 14px; color: #F0EBE0; font-family: system-ui, sans-serif; font-size: 13px; line-height: 1.6; resize: vertical; outline: none; }}
textarea:focus {{ border-color: #C9A84C; }}
.btn-row {{ display: flex; gap: 12px; margin-top: 8px; flex-wrap: wrap; }}
.btn {{ padding: 10px 22px; border-radius: 8px; border: none; cursor: pointer; font-size: 13px; font-weight: 500; }}
.btn-save {{ background: #C9A84C; color: #07071A; }}
.btn-test {{ background: rgba(61,158,140,0.2); color: #3D9E8C; border: 1px solid rgba(61,158,140,0.3); }}
.divider {{ height: 1px; background: rgba(255,255,255,0.06); margin: 36px 0; }}
.version-item {{ background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.06); border-radius: 8px; padding: 12px 16px; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center; }}
.v-label {{ font-size: 12px; color: rgba(240,235,224,0.7); }}
.v-date {{ font-size: 11px; color: rgba(240,235,224,0.35); margin-top: 2px; }}
.version-item button {{ padding: 4px 12px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.1); background: none; color: rgba(240,235,224,0.5); font-size: 11px; cursor: pointer; }}
.no-versions {{ font-size: 12px; color: rgba(240,235,224,0.3); }}
.saved-msg {{ background: rgba(61,158,140,0.15); border: 1px solid rgba(61,158,140,0.3); color: #3D9E8C; border-radius: 8px; padding: 10px 14px; font-size: 12px; margin-bottom: 20px; display: none; }}
</style>
</head>
<body>
<div class="header">
  <div>
    <div class="logo">DRISHTI · PROMPT STUDIO</div>
    <div class="sub">Configure how Claude reads your chart data</div>
  </div>
  <a href="/admin/test-reading" target="_blank" style="background:rgba(61,158,140,0.2);color:#3D9E8C;border:1px solid rgba(61,158,140,0.3);padding:8px 16px;border-radius:8px;font-size:12px;text-decoration:none;">Test with Sumit's chart →</a>
</div>

<div class="main">

<form method="POST" action="/admin/save">
  <input type="hidden" name="password" value="{ADMIN_PASSWORD}">
  {fields_html}
  <div class="btn-row">
    <button type="submit" class="btn btn-save">Save & Apply →</button>
  </div>
</form>

<div class="divider"></div>

<div class="section">
  <div class="section-title">Version History</div>
  <div class="section-desc">Last 5 saved versions. Restore any previous configuration.</div>
  {history_html}
  <form method="POST" action="/admin/restore" id="restore-form">
    <input type="hidden" name="password" value="{ADMIN_PASSWORD}">
  </form>
</div>

</div>
</body>
</html>"""

@app.route("/admin/save", methods=["POST"])
def admin_save():
    if request.form.get("password") != ADMIN_PASSWORD:
        return admin_login("Unauthorized")
    try:
        fields = ["career_agent","relationships_agent","wealth_agent",
                  "timing_agent","synthesis_voice","plain_mode_rules","vedic_mode_rules"]
        current = load_prompts()
        
        from datetime import datetime
        history = current.get("version_history", [])
        history.append({
            "label": f"Version {len(history) + 1}",
            "saved_at": datetime.now().strftime("%d %b %Y %H:%M"),
            "prompts": {k: current.get(k,"") for k in fields}
        })
        history = history[-5:]
        
        new_prompts = {"version_history": history}
        for f in fields:
            new_prompts[f] = request.form.get(f, "")
        
        save_prompts(new_prompts)
        prompts = load_prompts()
        return admin_studio(prompts)
    except Exception as e:
        return admin_login(f"Save failed: {str(e)}")

@app.route("/admin/restore", methods=["POST"])
def admin_restore():
    if request.form.get("password") != ADMIN_PASSWORD:
        return admin_login("Unauthorized")
    try:
        index = int(request.form.get("restore_index", 0))
        prompts = load_prompts()
        history = prompts.get("version_history", [])
        if index < len(history):
            restored = history[index]["prompts"]
            restored["version_history"] = history
            save_prompts(restored)
        return admin_studio(load_prompts())
    except Exception as e:
        return admin_login(f"Restore failed: {str(e)}")

@app.route("/admin/test-reading", methods=["GET"])
def admin_test_reading():
    try:
        birth_data = {
            "date": "1978-10-06", "time": "20:40",
            "lat": 28.6139, "lon": 77.209, "utc_offset": 5.5
        }
        vedic_result = get_vedic_context(birth_data)
        if "error" in vedic_result:
            return f"<pre>Chart error: {vedic_result['error']}</pre>"

        vedic_context = vedic_result.get("karmi_prompt_context") or str(vedic_result)
        transit_result = get_today_transits()
        transit_context = format_transit_context(transit_result)

        agent_types = ["career", "relationships", "wealth", "timing"]
        agent_results = []

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(
                    call_agent, agent_type, "Sumit",
                    "Testing prompt studio",
                    "How is my overall chart right now?",
                    "Next 3 months",
                    vedic_context, transit_context, "plain"
                ): agent_type
                for agent_type in agent_types
            }
            for future in as_completed(futures):
                agent_results.append(future.result())

        order = ["career","relationships","wealth","timing"]
        agent_results.sort(key=lambda x: order.index(x.get("domain","career")))

        synthesis_prompt = build_synthesis_prompt(
            "Sumit", "Testing prompt studio",
            "How is my overall chart right now?",
            "Next 3 months", agent_results, "plain"
        )
        message = client.messages.create(
            model="claude-haiku-4-5", max_tokens=1024,
            messages=[{"role":"user","content":synthesis_prompt}]
        )
        raw = message.content[0].text
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"): raw = raw[4:]
        synthesis = json.loads(raw.strip())

        result_html = f"""<!DOCTYPE html>
<html>
<head><title>Test Result</title>
<style>
body {{ background:#07071A; color:#F0EBE0; font-family:system-ui,sans-serif; padding:40px; max-width:800px; margin:0 auto; }}
h2 {{ color:#C9A84C; margin-bottom:20px; font-weight:400; }}
.card {{ background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.08); border-radius:12px; padding:20px; margin-bottom:16px; }}
.label {{ font-size:10px; letter-spacing:0.2em; color:#3D9E8C; text-transform:uppercase; margin-bottom:8px; }}
p {{ font-size:14px; line-height:1.7; color:rgba(240,235,224,0.8); }}
.score {{ font-size:32px; color:#C9A84C; font-family:Georgia,serif; }}
.agent {{ border-left:2px solid rgba(201,168,76,0.3); padding-left:16px; margin-bottom:12px; }}
.agent-title {{ font-size:12px; font-weight:500; color:#C9A84C; margin-bottom:4px; }}
</style>
</head>
<body>
<h2>Test Reading — Sumit's Chart</h2>
<div class="card">
  <div class="label">Overall Score</div>
  <div class="score">{synthesis.get('overall_score',0)}%</div>
</div>
<div class="card">
  <div class="label">Synthesis</div>
  <p>{synthesis.get('synthesis','')}</p>
</div>
<div class="card">
  <div class="label">Top Action</div>
  <p>{synthesis.get('top_action','')}</p>
</div>
<div class="card">
  <div class="label">Oracle Note</div>
  <p><em>{synthesis.get('oracle_note','')}</em></p>
</div>
<div class="card">
  <div class="label">Agent Scores</div>
  {''.join(f'<div class="agent"><div class="agent-title">{a.get("domain","").upper()} — {a.get("score",0)}%</div><p>{a.get("verdict","")}</p></div>' for a in agent_results)}
</div>
<p style="margin-top:20px;font-size:12px;color:rgba(240,235,224,0.3)"><a href="/admin" style="color:#3D9E8C">← Back to Prompt Studio</a></p>
</body>
</html>"""
        return result_html

    except Exception as e:
        import traceback
        return f"<pre style='color:#ff6b6b'>Error: {str(e)}\n{traceback.format_exc()}</pre>"

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5051))
    app.run(debug=False, host="0.0.0.0", port=port)