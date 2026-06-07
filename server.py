from flask import Flask, request, jsonify
from flask_cors import CORS
import anthropic
import requests
import os
import json
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
NGROK_URL = os.getenv("NGROK_URL")

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

def get_vedic_context(birth_data):
    try:
        # Parse date and time into individual components
        date_str = birth_data.get("date", "")
        time_str = birth_data.get("time", "00:00")
        
        year, month, day = [int(x) for x in date_str.split("-")]
        hour, minute = [int(x) for x in time_str.split(":")]
        
        payload = {
            "year": year,
            "month": month,
            "day": day,
            "hour": hour,
            "minute": minute,
            "lat": float(birth_data.get("lat", 28.6139)),
            "lon": float(birth_data.get("lon", 77.209)),
            "utc_offset": float(birth_data.get("utc_offset", 5.5))
        }
        
        response = requests.post(
            f"{NGROK_URL}/api/vedic-native",
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def get_today_transits():
    try:
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        payload = {
            "date": today,
            "lat": 28.6139,
            "lon": 77.209,
            "utc_offset": 5.5
        }
        response = requests.post(
            f"{NGROK_URL}/api/transit-day",
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def build_prompt(question, vedic_context, name, transit_context=""):
    transit_section = f"\n\n{transit_context}" if transit_context else ""
    return f"""You are Drishti — an ancient Vedic oracle with the precision of a master astrologer and the clarity of a trusted advisor. You have been given a person's complete Vedic birth chart and they have asked you one question.

Your task is to answer their question using ONLY what their chart reveals. You must give a probability assessment grounded in actual planetary positions, dashas, and transits — not generic advice.

PERSON: {name}
THEIR QUESTION: {question}

THEIR VEDIC CHART CONTEXT:
{vedic_context}{transit_section}

Respond in this exact JSON structure:
{{
  "verdict": "One powerful sentence — the core answer with a probability (e.g. 73% favorable)",
  "signals": [
    "Signal 1 — specific planet/dasha/house causing this",
    "Signal 2 — specific planet/dasha/house causing this",
    "Signal 3 — specific planet/dasha/house causing this"
  ],
  "timing": "When this energy peaks, shifts, or resolves — be specific with months if possible",
  "oracle_note": "One final sentence of deeper Vedic wisdom — poetic but grounded",
  "followup_questions": [
    "A natural next question they should ask",
    "Another angle worth exploring",
    "A timing or decision question"
  ]
}}

Rules:
- The probability must feel earned, not random — justify it through the chart
- Never be vague. Every signal must name a specific planet, house, or dasha period
- Where today's transits are provided, reference how current planetary positions activate or challenge the natal chart
- Do not mention Western astrology
- Do not break the JSON structure
- Speak as Drishti, not as an AI assistant"""

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

    # Step 1: Get vedic context
    vedic_result = get_vedic_context(birth_data)

    if "error" in vedic_result:
        return jsonify({"error": f"Chart calculation failed: {vedic_result['error']}"}), 500

    # Step 2: Extract karmi_prompt_context if available
    vedic_context = vedic_result.get("karmi_prompt_context") or str(vedic_result)

    # Step 2b: Get today's transits
    transit_result = get_today_transits()
    transit_context = ""
    if "error" not in transit_result:
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
            transit_context = "TODAY'S TRANSITS (current sky):\n" + "\n".join(lines)

    # Step 3: Call Claude
    try:
        message = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": build_prompt(question, vedic_context, name, transit_context)
                }
            ]
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

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "Drishti is awake"})

if __name__ == "__main__":
    app.run(debug=True, port=5051)