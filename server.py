from flask import Flask, request, jsonify
from flask_cors import CORS
import anthropic
import requests
import os
import json
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

app = Flask(__name__)
CORS(app)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
NGROK_URL = os.getenv("NGROK_URL")

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

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

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "Drishti is awake"})

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "karmi2026")

@app.route("/admin", methods=["GET"])
def admin_page():
    return """<!DOCTYPE html>
<html>
<head>
<title>Drishti Prompt Studio</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: #07071A; color: #F0EBE0; font-family: system-ui, sans-serif; font-size: 14px; }
.header { padding: 24px 40px; border-bottom: 1px solid rgba(255,255,255,0.08); display: flex; align-items: center; justify-content: space-between; }
.logo { font-size: 13px; letter-spacing: 0.2em; color: #F0EBE0; }
.subtitle { font-size: 11px; color: rgba(240,235,224,0.5); margin-top: 4px; }
.main { max-width: 900px; margin: 0 auto; padding: 40px; }
.section { margin-bottom: 40px; }
.section-title { font-size: 11px; letter-spacing: 0.2em; color: #3D9E8C; text-transform: uppercase; margin-bottom: 12px; }
.section-desc { font-size: 12px; color: rgba(240,235,224,0.5); margin-bottom: 10px; line-height: 1.5; }
textarea { width: 100%; background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; padding: 14px; color: #F0EBE0; font-family: system-ui, sans-serif; font-size: 13px; line-height: 1.6; resize: vertical; min-height: 140px; outline: none; transition: border-color 0.2s; }
textarea:focus { border-color: #C9A84C; }
.btn-row { display: flex; gap: 12px; margin-top: 16px; flex-wrap: wrap; }
.btn { padding: 10px 20px; border-radius: 8px; border: none; cursor: pointer; font-size: 13px; font-weight: 500; transition: all 0.2s; }
.btn-primary { background: #C9A84C; color: #07071A; }
.btn-primary:hover { background: #D4B05A; }
.btn-secondary { background: rgba(255,255,255,0.06); color: #F0EBE0; border: 1px solid rgba(255,255,255,0.1); }
.btn-secondary:hover { background: rgba(255,255,255,0.1); }
.btn-test { background: rgba(61,158,140,0.2); color: #3D9E8C; border: 1px solid rgba(61,158,140,0.3); }
.btn-test:hover { background: rgba(61,158,140,0.3); }
.status { padding: 10px 16px; border-radius: 8px; font-size: 12px; margin-top: 12px; display: none; }
.status.success { background: rgba(61,158,140,0.15); border: 1px solid rgba(61,158,140,0.3); color: #3D9E8C; display: block; }
.status.error { background: rgba(255,107,107,0.1); border: 1px solid rgba(255,107,107,0.2); color: #ff6b6b; display: block; }
.divider { height: 1px; background: rgba(255,255,255,0.06); margin: 40px 0; }
.test-result { background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; padding: 16px; margin-top: 16px; font-size: 12px; line-height: 1.7; color: rgba(240,235,224,0.7); display: none; white-space: pre-wrap; max-height: 300px; overflow-y: auto; }
.version-item { background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.06); border-radius: 8px; padding: 12px; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center; }
.version-date { font-size: 11px; color: rgba(240,235,224,0.4); }
.version-btn { padding: 4px 12px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.1); background: none; color: rgba(240,235,224,0.6); font-size: 11px; cursor: pointer; }
.version-btn:hover { border-color: #C9A84C; color: #C9A84C; }
input[type=password] { width: 100%; background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; padding: 12px 14px; color: #F0EBE0; font-size: 14px; outline: none; margin-bottom: 12px; }
input[type=password]:focus { border-color: #C9A84C; }
.login-box { max-width: 400px; margin: 100px auto; padding: 40px; background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); border-radius: 20px; }
.login-title { font-size: 20px; margin-bottom: 8px; }
.login-sub { font-size: 13px; color: rgba(240,235,224,0.5); margin-bottom: 24px; }
</style>
</head>
<body>
<div id="login-screen">
  <div class="login-box">
    <div class="login-title">Drishti Prompt Studio</div>
    <div class="login-sub">Enter your admin password to continue.</div>
    <input type="password" id="pwd-input" placeholder="Password" onkeydown="if(event.key==='Enter')login()" />
    <button class="btn btn-primary" style="width:100%" onclick="login()">Enter →</button>
    <div class="status" id="login-status"></div>
  </div>
</div>

<div id="studio-screen" style="display:none">
<div class="header">
  <div>
    <div class="logo">DRISHTI · PROMPT STUDIO</div>
    <div class="subtitle">Configure how Claude reads your chart data</div>
  </div>
  <button class="btn btn-secondary" onclick="testReading()">Test with Sumit's chart →</button>
</div>

<div class="main">

  <div class="section">
    <div class="section-title">Career Agent</div>
    <div class="section-desc">Instructions for how Claude reads career questions. Specify which houses, planets, and charts to prioritise and in what order.</div>
    <textarea id="career_agent" rows="8"></textarea>
  </div>

  <div class="section">
    <div class="section-title">Relationships Agent</div>
    <div class="section-desc">Instructions for relationship and love questions. Specify Venus, 7th house, D9 focus and weighting.</div>
    <textarea id="relationships_agent" rows="8"></textarea>
  </div>

  <div class="section">
    <div class="section-title">Wealth Agent</div>
    <div class="section-desc">Instructions for money and investment questions. Specify 2nd/11th house, Jupiter, Dhana yoga focus.</div>
    <textarea id="wealth_agent" rows="8"></textarea>
  </div>

  <div class="section">
    <div class="section-title">Timing Agent</div>
    <div class="section-desc">Instructions for timing questions. Specify dasha depth, transit focus, and window identification.</div>
    <textarea id="timing_agent" rows="8"></textarea>
  </div>

  <div class="divider"></div>

  <div class="section">
    <div class="section-title">Synthesis Voice</div>
    <div class="section-desc">How Drishti speaks when delivering the final unified reading. This sets the tone and style of the consultation voice.</div>
    <textarea id="synthesis_voice" rows="5"></textarea>
  </div>

  <div class="section">
    <div class="section-title">Plain Mode Rules</div>
    <div class="section-desc">Translation rules for Plain & Personal mode. Define which Vedic terms get replaced with plain English equivalents.</div>
    <textarea id="plain_mode_rules" rows="8"></textarea>
  </div>

  <div class="section">
    <div class="section-title">Vedic Mode Rules</div>
    <div class="section-desc">Instructions for Vedic & Technical mode. Define the level of technical depth and terminology expected.</div>
    <textarea id="vedic_mode_rules" rows="5"></textarea>
  </div>

  <div class="btn-row">
    <button class="btn btn-primary" onclick="savePrompts()">Save & Apply →</button>
    <button class="btn btn-secondary" onclick="resetToDefaults()">Reset to Defaults</button>
    <button class="btn btn-test" onclick="testReading()">Test Reading</button>
  </div>
  <div class="status" id="save-status"></div>

  <div class="divider"></div>

  <div class="section">
    <div class="section-title">Test Result</div>
    <div class="section-desc">Fire a test reading with Sumit's chart using current prompts.</div>
    <div class="test-result" id="test-result"></div>
  </div>

  <div class="divider"></div>

  <div class="section">
    <div class="section-title">Version History</div>
    <div class="section-desc">Last 5 saved versions. Click Restore to roll back.</div>
    <div id="version-list"></div>
  </div>

</div>
</div>

<script>
let token = sessionStorage.getItem('admin_token');
if (token) showStudio();

function login() {
  const pwd = document.getElementById('pwd-input').value;
  fetch('/admin/auth', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({password: pwd})
  }).then(r => r.json()).then(d => {
    if (d.success) {
      token = d.token;
      sessionStorage.setItem('admin_token', token);
      showStudio();
    } else {
      const s = document.getElementById('login-status');
      s.textContent = 'Incorrect password.';
      s.className = 'status error';
    }
  });
}

function showStudio() {
  document.getElementById('login-screen').style.display = 'none';
  document.getElementById('studio-screen').style.display = 'block';
  loadPrompts();
}

function loadPrompts() {
  fetch('/admin/prompts', {
    headers: {'Authorization': 'Bearer ' + token}
  }).then(r => r.json()).then(data => {
    const fields = ['career_agent','relationships_agent','wealth_agent',
                    'timing_agent','synthesis_voice','plain_mode_rules','vedic_mode_rules'];
    fields.forEach(f => {
      const el = document.getElementById(f);
      if (el) el.value = data[f] || '';
    });
    renderVersionHistory(data.version_history || []);
  });
}

function savePrompts() {
  const fields = ['career_agent','relationships_agent','wealth_agent',
                  'timing_agent','synthesis_voice','plain_mode_rules','vedic_mode_rules'];
  const prompts = {};
  fields.forEach(f => {
    prompts[f] = document.getElementById(f)?.value || '';
  });
  fetch('/admin/prompts', {
    method: 'POST',
    headers: {'Content-Type':'application/json','Authorization':'Bearer ' + token},
    body: JSON.stringify(prompts)
  }).then(r => r.json()).then(d => {
    const s = document.getElementById('save-status');
    if (d.success) {
      s.textContent = '✓ Prompts saved and applied. Next reading will use these instructions.';
      s.className = 'status success';
      loadPrompts();
    } else {
      s.textContent = '✗ Save failed: ' + (d.error || 'unknown error');
      s.className = 'status error';
    }
    setTimeout(() => s.style.display = 'none', 4000);
  });
}

function resetToDefaults() {
  if (!confirm('Reset all prompts to defaults? This cannot be undone.')) return;
  fetch('/admin/reset', {
    method: 'POST',
    headers: {'Authorization':'Bearer ' + token}
  }).then(r => r.json()).then(d => {
    if (d.success) { loadPrompts(); }
  });
}

function testReading() {
  const resultEl = document.getElementById('test-result');
  resultEl.style.display = 'block';
  resultEl.textContent = 'Running test reading with Sumit chart (Oct 6 1978, 20:40, New Delhi)...';
  fetch('/admin/test', {
    method: 'POST',
    headers: {'Authorization':'Bearer ' + token}
  }).then(r => r.json()).then(d => {
    if (d.success) {
      const s = d.synthesis;
      resultEl.textContent = 
        'OVERALL: ' + s.overall_score + '%\n\n' +
        'SYNTHESIS:\n' + s.synthesis + '\n\n' +
        'CONVERGENCE: ' + s.convergence + '\n\n' +
        'TENSION: ' + s.tension + '\n\n' +
        'TOP ACTION: ' + s.top_action + '\n\n' +
        'ORACLE: ' + s.oracle_note;
    } else {
      resultEl.textContent = 'Error: ' + (d.error || 'test failed');
    }
  });
}

function renderVersionHistory(versions) {
  const el = document.getElementById('version-list');
  if (!versions.length) {
    el.innerHTML = '<div style="font-size:12px;color:rgba(240,235,224,0.3)">No versions saved yet.</div>';
    return;
  }
  el.innerHTML = versions.slice().reverse().map((v, i) =>
    '<div class="version-item">' +
    '<div><div style="font-size:12px;color:rgba(240,235,224,0.7)">' + v.label + '</div>' +
    '<div class="version-date">' + v.saved_at + '</div></div>' +
    '<button class="version-btn" onclick="restoreVersion(' + (versions.length - 1 - i) + ')">Restore</button>' +
    '</div>'
  ).join('');
}

function restoreVersion(index) {
  if (!confirm('Restore this version?')) return;
  fetch('/admin/restore/' + index, {
    method: 'POST',
    headers: {'Authorization':'Bearer ' + token}
  }).then(r => r.json()).then(d => {
    if (d.success) loadPrompts();
  });
}
</script>
</body>
</html>"""

@app.route("/admin/auth", methods=["POST"])
def admin_auth():
    data = request.json
    if data.get("password") == ADMIN_PASSWORD:
        import secrets
        token = secrets.token_hex(16)
        return jsonify({"success": True, "token": token})
    return jsonify({"success": False})

def verify_admin(req):
    auth = req.headers.get("Authorization", "")
    return auth.startswith("Bearer ") and len(auth) > 10

@app.route("/admin/prompts", methods=["GET"])
def get_prompts():
    if not verify_admin(request):
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(load_prompts())

@app.route("/admin/prompts", methods=["POST"])
def update_prompts():
    if not verify_admin(request):
        return jsonify({"error": "unauthorized"}), 401
    try:
        new_prompts = request.json
        current = load_prompts()

        # Save version history
        from datetime import datetime
        history = current.get("version_history", [])
        history.append({
            "label": f"Version {len(history) + 1}",
            "saved_at": datetime.now().strftime("%d %b %Y %H:%M"),
            "prompts": {k: current[k] for k in current if k != "version_history"}
        })
        # Keep last 5 only
        history = history[-5:]

        new_prompts["version_history"] = history
        save_prompts(new_prompts)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/admin/reset", methods=["POST"])
def reset_prompts():
    if not verify_admin(request):
        return jsonify({"error": "unauthorized"}), 401
    default_path = Path(__file__).parent / 'prompts.json'
    prompts = load_prompts()
    prompts["version_history"] = prompts.get("version_history", [])
    save_prompts(prompts)
    return jsonify({"success": True})

@app.route("/admin/test", methods=["POST"])
def test_reading():
    if not verify_admin(request):
        return jsonify({"error": "unauthorized"}), 401
    try:
        birth_data = {
            "date": "1978-10-06",
            "time": "20:40",
            "lat": 28.6139,
            "lon": 77.209,
            "utc_offset": 5.5
        }
        vedic_result = get_vedic_context(birth_data)
        if "error" in vedic_result:
            return jsonify({"error": vedic_result["error"]}), 500

        vedic_context = vedic_result.get("karmi_prompt_context") or str(vedic_result)
        transit_result = get_today_transits()
        transit_context = format_transit_context(transit_result)

        agent_types = ["career", "relationships", "wealth", "timing"]
        agent_results = []
        preference = "plain"

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(
                    call_agent, agent_type, "Sumit",
                    "Testing the prompt studio",
                    "How is my overall chart looking right now?",
                    "Next 3 months",
                    vedic_context, transit_context, preference
                ): agent_type
                for agent_type in agent_types
            }
            for future in as_completed(futures):
                agent_results.append(future.result())

        order = ["career", "relationships", "wealth", "timing"]
        agent_results.sort(key=lambda x: order.index(x.get("domain", "career")))

        synthesis_prompt = build_synthesis_prompt(
            "Sumit", "Testing prompt studio",
            "How is my overall chart looking right now?",
            "Next 3 months", agent_results, preference
        )
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
        return jsonify({"success": True, "synthesis": synthesis, "agents": agent_results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/admin/restore/<int:index>", methods=["POST"])
def restore_version(index):
    if not verify_admin(request):
        return jsonify({"error": "unauthorized"}), 401
    try:
        prompts = load_prompts()
        history = prompts.get("version_history", [])
        if index < len(history):
            restored = history[index]["prompts"]
            restored["version_history"] = history
            save_prompts(restored)
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "Version not found"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5051))
    app.run(debug=False, host="0.0.0.0", port=port)