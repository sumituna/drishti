const API = 'https://drishti-6n6f.onrender.com';

// ── City Lookup ──
let resolvedLat = null;
let resolvedLon = null;
let resolvedTimezone = null;
let citySearchTimer = null;

function onPlaceInput(value) {
  clearCity();
  const dropdown = document.getElementById('city-dropdown');
  const statusEl = document.getElementById('place-status');
  if (!value || value.length < 2) {
    dropdown.classList.add('hidden');
    if (statusEl) statusEl.textContent = '';
    return;
  }
  if (statusEl) { statusEl.textContent = 'Searching...'; statusEl.className = 'place-status'; }
  clearTimeout(citySearchTimer);
  citySearchTimer = setTimeout(() => searchCities(value), 400);
}

async function searchCities(query) {
  const statusEl = document.getElementById('place-status');
  const dropdown = document.getElementById('city-dropdown');
  try {
    const encoded = encodeURIComponent(query.trim());
    const res = await fetch(
      `https://nominatim.openstreetmap.org/search?q=${encoded}&format=json&limit=5`,
      { headers: { 'User-Agent': 'KarmiApp/1.0' } }
    );
    const data = await res.json();
    if (!data || data.length === 0) {
      if (statusEl) { statusEl.textContent = '✗ No cities found'; statusEl.className = 'place-status error'; }
      dropdown.classList.add('hidden');
      return;
    }
    if (statusEl) statusEl.textContent = '';
    dropdown.innerHTML = data.map((item, i) =>
      `<div class="city-option" onmousedown="selectCity(${i})" data-lat="${item.lat}" data-lon="${item.lon}" data-name="${item.display_name}">
        ${item.display_name}
      </div>`
    ).join('');
    dropdown.classList.remove('hidden');
  } catch (err) {
    if (statusEl) { statusEl.textContent = '✗ Search failed'; statusEl.className = 'place-status error'; }
  }
}

async function selectCity(index) {
  const dropdown = document.getElementById('city-dropdown');
  const statusEl = document.getElementById('place-status');
  const placeInput = document.getElementById('place');
  const option = dropdown.querySelectorAll('.city-option')[index];
  const lat = parseFloat(option.dataset.lat);
  const lon = parseFloat(option.dataset.lon);
  const fullName = option.dataset.name;
  const shortName = fullName.split(',').slice(0, 3).join(',');
  resolvedLat = lat;
  resolvedLon = lon;
  if (placeInput) placeInput.value = shortName;
  dropdown.classList.add('hidden');
  if (statusEl) { statusEl.textContent = 'Getting timezone...'; statusEl.className = 'place-status'; }
  try {
    const tzRes = await fetch(`https://timeapi.io/api/timezone/coordinate?latitude=${lat}&longitude=${lon}`);
    const tzData = await tzRes.json();
    const secs = tzData?.currentUtcOffset?.seconds;
    resolvedTimezone = Number.isFinite(secs) ? secs / 3600 : Math.round((lon / 15) * 2) / 2;
  } catch {
    resolvedTimezone = Math.round((lon / 15) * 2) / 2;
  }
  if (statusEl) {
    statusEl.textContent = `✓ ${shortName.split(',')[0].trim()} · UTC${resolvedTimezone >= 0 ? '+' : ''}${resolvedTimezone}`;
    statusEl.className = 'place-status success';
  }
}

function hideCityDropdown() {
  setTimeout(() => {
    const dropdown = document.getElementById('city-dropdown');
    if (dropdown) dropdown.classList.add('hidden');
  }, 150);
}

function clearCity() {
  resolvedLat = null; resolvedLon = null; resolvedTimezone = null;
  const statusEl = document.getElementById('place-status');
  if (statusEl) { statusEl.textContent = ''; statusEl.className = 'place-status'; }
}

function fillContext(situation, question, timeline) {
  const s = document.getElementById('situation');
  const q = document.getElementById('question');
  const t = document.getElementById('timeline');
  if (s) s.value = situation;
  if (q) q.value = question;
  if (t) t.value = timeline;
}

// ── Submit V2 ──
async function submitV2() {
  const name = document.getElementById('name')?.value?.trim();
  const dob = document.getElementById('dob')?.value;
  const tob = document.getElementById('tob')?.value;
  const place = document.getElementById('place')?.value?.trim();
  const situation = document.getElementById('situation')?.value?.trim();
  const question = document.getElementById('question')?.value?.trim();
  const timeline = document.getElementById('timeline')?.value?.trim();

  if (!name || !dob || !tob || !place || !question) {
    alert('Please fill in your birth details and question.');
    return;
  }
  if (!resolvedLat || !resolvedLon) {
    alert('Please select your birth city from the dropdown.');
    return;
  }

  sessionStorage.setItem('drishti_data', JSON.stringify({
    name, dob, tob, place,
    lat: resolvedLat, lon: resolvedLon, timezone: resolvedTimezone,
    situation: situation || '', question, timeline: timeline || '',
    mode: 'v2'
  }));

  window.location.href = 'chat.html';
}

// ── Chat page ──
async function loadReading() {
  const raw = sessionStorage.getItem('drishti_data');
  if (!raw) { window.location.href = 'index.html'; return; }
  const data = JSON.parse(raw);

  const qEl = document.getElementById('user-question-text');
  if (qEl) qEl.textContent = data.question;

  const pillsEl = document.getElementById('context-pills');
  if (pillsEl) {
    let pills = '';
    if (data.situation) pills += `<span class="context-pill">${data.situation}</span>`;
    if (data.timeline) pills += `<span class="context-pill">${data.timeline}</span>`;
    pillsEl.innerHTML = pills;
  }

  await runV2Pipeline(data);
}

async function runV2Pipeline(data) {
  const steps = ['step-chart', 'step-agents', 'step-synthesis', 'step-reading'];
  const statuses = ['Reading your chart...', 'Running specialist agents...', 'Synthesizing readings...', 'Preparing your oracle...'];
  let stepIndex = 0;

  const advanceStep = () => {
    if (stepIndex > 0) {
      document.getElementById(steps[stepIndex - 1])?.classList.remove('active');
      document.getElementById(steps[stepIndex - 1])?.classList.add('done');
    }
    if (stepIndex < steps.length) {
      document.getElementById(steps[stepIndex])?.classList.add('active');
      const statusEl = document.getElementById('loading-status');
      if (statusEl) statusEl.textContent = statuses[stepIndex];
      stepIndex++;
    }
  };

  advanceStep();

  try {
    const t1 = setTimeout(() => advanceStep(), 2000);
    const t2 = setTimeout(() => advanceStep(), 5000);
    const t3 = setTimeout(() => advanceStep(), 7000);

    const response = await fetch(`${API}/ask-v2`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: data.name,
        date: data.dob,
        time: data.tob,
        place: data.place,
        lat: data.lat,
        lon: data.lon,
        timezone: data.timezone,
        situation: data.situation,
        question: data.question,
        timeline: data.timeline
      })
    });

    clearTimeout(t1); clearTimeout(t2); clearTimeout(t3);
    steps.forEach(s => {
      document.getElementById(s)?.classList.remove('active');
      document.getElementById(s)?.classList.add('done');
    });

    const result = await response.json();
    if (!response.ok || result.error) { showError(result.error || 'Something went wrong.'); return; }
    showV2Reading(result);

  } catch (err) {
    showError('Could not reach Drishti. Please check the server is running.');
  }
}

function showV2Reading(result) {
  document.getElementById('loading-bubble')?.classList.add('hidden');
  const { agents, synthesis } = result;

  // Synthesis card
  const synthCard = document.getElementById('synthesis-card');
  if (synthCard) {
    document.getElementById('overall-score').textContent = `${synthesis.overall_score}% aligned`;
    document.getElementById('synthesis-text').textContent = synthesis.synthesis;
    document.getElementById('convergence').textContent = synthesis.convergence;
    document.getElementById('tension').textContent = synthesis.tension;
    document.getElementById('oracle-note').textContent = synthesis.oracle_note;
    document.getElementById('top-action').textContent = synthesis.top_action;
    synthCard.classList.remove('hidden');
  }

  // Agent grid
  const agentGrid = document.getElementById('agent-grid');
  const agents2x2 = document.getElementById('agents-2x2');
  if (agentGrid && agents2x2) {
    const agentIcons = { career: '♄', relationships: '♀', wealth: '♃', timing: '☽' };
    const agentTitles = { career: 'Career & Purpose', relationships: 'Relationships', wealth: 'Wealth & Resources', timing: 'Timing & Energy' };
    agents2x2.innerHTML = agents.map(agent => `
      <div class="agent-result-card">
        <div class="agent-result-header">
          <span class="agent-result-icon">${agentIcons[agent.domain] || '✦'}</span>
          <span class="agent-result-title">${agentTitles[agent.domain] || agent.domain}</span>
          <span class="agent-score ${agent.score >= 70 ? 'score-high' : agent.score >= 50 ? 'score-mid' : 'score-low'}">${agent.score}%</span>
        </div>
        <p class="agent-verdict">${agent.verdict}</p>
        <ul class="agent-signals">
          ${agent.signals.map(s => `<li>${s}</li>`).join('')}
        </ul>
        <div class="agent-timing">⏱ ${agent.timing}</div>
        <div class="agent-advice">→ ${agent.advice}</div>
      </div>
    `).join('');
    agentGrid.classList.remove('hidden');
  }

  // Follow-up
  const chipsEl = document.getElementById('followup-chips');
  const followupCard = document.getElementById('followup-card');
  if (chipsEl && synthesis.followup_questions) {
    chipsEl.innerHTML = synthesis.followup_questions.map(q =>
      `<button class="followup-chip" onclick="alert('One session per reading. Return to ask more.')">${q}</button>`
    ).join('');
    followupCard?.classList.remove('hidden');
  }

  setTimeout(() => document.getElementById('limit-card')?.classList.remove('hidden'), 1000);
}

function showError(msg) {
  document.getElementById('loading-bubble')?.classList.add('hidden');
  const errDiv = document.createElement('div');
  errDiv.className = 'chat-bubble';
  errDiv.innerHTML = `<div class="bubble-label">DRISHTI</div><p style="color:#ff6b6b;font-size:14px;">${msg}</p>`;
  document.querySelector('.chat-main')?.appendChild(errDiv);
}