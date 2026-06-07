from flask import Flask, request, jsonify
from flask_cors import CORS
import anthropic
import requests
import os
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

load_dotenv()

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

def build_agent_prompt(agent_type, name, situation, question, timeline, vedic_context, transit_context):
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

Rules:
- Score must be justified by actual chart factors
- Every signal must name a specific planet, house, nakshatra, or dasha
- Timing must reference actual dasha periods or transit windows
- Speak only about your domain — do not comment on other life areas
- Do not mention Western astrology
- Do not break JSON structure"""

def build_synthesis_prompt(name, situation, question, timeline, agent_results):
    agents_text = ""
    for agent in agent_results:
        agents_text += f"\n{agent['domain'].upper()} AGENT (score: {agent['score']}):\n"
        agents_text += f"Verdict: {agent['verdict']}\n"
        agents_text += f"Timing: {agent['timing']}\n"
        agents_text += f"Advice: {agent['advice']}\n"

    return f"""You are the Drishti Synthesis Oracle — you read the outputs of 4 specialist Vedic astrology agents and synthesize them into a unified life reading.

PERSON: {name}

THEIR CONTEXT:
- Situation: {situation}
- Question: {question}
- Timeline: {timeline}

SPECIALIST AGENT REPORTS:
{agents_text}

Your job: synthesize these 4 domain readings into one coherent life picture. Find the convergences, tensions, and the single most important message this person needs to hear right now.

Respond in this exact JSON:
{{
  "overall_score": <integer 0-100, weighted average reflecting the whole life picture>,
  "synthesis": "2-3 sentences — the unified verdict that weaves all domains together",
  "convergence": "The one theme that appears across multiple domains",
  "tension": "The key tension or trade-off the chart reveals",
  "oracle_note": "One poetic but grounded sentence of Vedic wisdom for this person right now",
  "top_action": "The single most important thing this person should do in their timeline",
  "followup_questions": [
    "A natural next question about career or purpose",
    "A natural next question about relationships or timing",
    "A natural next question about a specific decision"
  ]
}}

Rules:
- Synthesize — do not just repeat what agents said
- Find meaning in the combination of scores and signals
- oracle_note should feel like ancient wisdom applied to their modern situation
- Do not mention Western astrology
- Do not break JSON structure"""

def call_agent(agent_type, name, situation, question, timeline, vedic_context, transit_context):
    try:
        prompt = build_agent_prompt(agent_type, name, situation, question, timeline, vedic_context, transit_context)
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

    # Step 2: Run 4 agents in parallel
    agent_types = ["career", "relationships", "wealth", "timing"]
    agent_results = []

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(
                call_agent, agent_type, name, situation, question, timeline, vedic_context, transit_context
            ): agent_type
            for agent_type in agent_types
        }
        for future in as_completed(futures):
            result = future.result()
            agent_results.append(result)

    # Sort results in consistent order
    order = ["career", "relationships", "wealth", "timing"]
    agent_results.sort(key=lambda x: order.index(x.get("domain", "career")))

    # Step 3: Synthesis
    try:
        synthesis_prompt = build_synthesis_prompt(name, situation, question, timeline, agent_results)
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
        "synthesis": synthesis
    })

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "Drishti is awake"})

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5051))
    app.run(debug=False, host="0.0.0.0", port=port)