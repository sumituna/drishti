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

def build_agent_prompt(agent_type, name, situation, question, timeline, vedic_context, transit_context, preference='plain'):
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

    if preference == 'plain':
        language_instruction = """LANGUAGE RULES (Plain & Personal mode):
- Open with "{name}, let me tell you what I see here."
- Write as a warm, direct astrologer speaking to a friend
- NEVER use Vedic terms — translate everything:
  * "sub-period" not "Antardasha"
  * "main period" not "Mahadasha"  
  * "minor cycle" not "Pratyantar"
  * "your career house" not "H10"
  * "at full strength" not "exalted"
  * "weakened by the Sun" not "combust"
  * "Saturn's 7-year test" not "Sade Sati"
  * "challenging house" not "dusthana"
  * "soul planet" not "Atmakaraka"
  * "relationship planet" not "Darakaraka"
  * "wealth combination" not "Dhana Yoga"
  * "success combination" not "Raja Yoga"
  * "lunar mansion" not "nakshatra"
- Use months and plain time references not dasha codes
- Make the person feel heard and understood
- Sound like you genuinely care about their situation""".replace("{name}", name)
    else:
        language_instruction = """LANGUAGE RULES (Vedic & Technical mode):
- Use full Vedic terminology throughout
- Reference specific houses (H1-H12), dashas, nakshatras
- Name specific yogas, dignities, combustion states
- Include dasha path codes and exact period dates
- Be precise and technically accurate"""

    return f"""You are Drishti — a warm, brilliant Vedic astrologer who speaks like a trusted advisor, not a textbook.

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

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5051))
    app.run(debug=False, host="0.0.0.0", port=port)