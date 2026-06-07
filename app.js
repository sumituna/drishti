const API = 'http://localhost:5051';

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
    statusEl.textContent = '';
    return;
  }

  statusEl.textContent = 'Searching...';
  statusEl.className = 'place-status';

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
      statusEl.textContent = '✗ No cities found';
      statusEl.className = 'place-status error';
      dropdown.classList.add('hidden');
      return;
    }

    statusEl.textContent = '';
    dropdown.innerHTML = data.map((item, i) =>
      `<div class="city-option" onclick="selectCity(${i})" data-lat="${item.lat}" data-lon="${item.lon}" data-name="${item.display_name}">
        ${item.display_name}
      </div>`
    ).join('');
    dropdown.classList.remove('hidden');

  } catch (err) {
    statusEl.textContent = '✗ Search failed — check connection';
    statusEl.className = 'place-status error';
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
  placeInput.value = shortName;
  dropdown.classList.add('hidden');

  statusEl.textContent = 'Getting timezone...';
  statusEl.className = 'place-status';

  try {
    const tzRes = await fetch(
      `https://timeapi.io/api/timezone/coordinate?latitude=${lat}&longitude=${lon}`
    );
    const tzData = await tzRes.json();
    const secs = tzData?.currentUtcOffset?.seconds;
    resolvedTimezone = Number.isFinite(secs) ? secs / 3600 : Math.round((lon / 15) * 2) / 2;
  } catch {
    resolvedTimezone = Math.round((lon / 15) * 2) / 2;
  }

  statusEl.textContent = `✓ ${shortName.split(',')[0].trim()} · UTC${resolvedTimezone >= 0 ? '+' : ''}${resolvedTimezone}`;
  statusEl.className = 'place-status success';
}

function clearCity() {
  resolvedLat = null;
  resolvedLon = null;
  resolvedTimezone = null;
  const statusEl = document.getElementById('place-status');
  if (statusEl) { statusEl.textContent = ''; statusEl.className = 'place-status'; }
}

// ── Landing page ──
function setQuestion(q) {
  const el = document.getElementById('question');
  if (el) { el.value = q; el.focus(); }
}

async function submitQuestion() {
  const name = document.getElementById('name')?.value?.trim();
  const dob = document.getElementById('dob')?.value;
  const tob = document.getElementById('tob')?.value;
  const place = document.getElementById('place')?.value?.trim();
  const question = document.getElementById('question')?.value?.trim();

  if (!name || !dob || !tob || !place || !question) {
    alert('Please fill in all fields and enter your question.');
    return;
  }

  if (!resolvedLat || !resolvedLon) {
    alert('Please wait — city coordinates are still being looked up, or try typing your city again and tabbing out.');
    return;
  }

  sessionStorage.setItem('drishti_data', JSON.stringify({
    name, dob, tob, place,
    lat: resolvedLat,
    lon: resolvedLon,
    timezone: resolvedTimezone,
    question
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

  await runPipeline(data);
}

async function runPipeline(data) {
  const steps = ['step-chart', 'step-planets', 'step-dashas', 'step-reading'];
  const statuses = [
    'Reading your chart...',
    'Mapping planetary positions...',
    'Calculating dasha periods...',
    'Consulting the oracle...'
  ];

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
    const t1 = setTimeout(() => advanceStep(), 1500);
    const t2 = setTimeout(() => advanceStep(), 3000);
    const t3 = setTimeout(() => advanceStep(), 4500);

    const response = await fetch(`${API}/ask`, {
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
        question: data.question
      })
    });

    clearTimeout(t1); clearTimeout(t2); clearTimeout(t3);

    steps.forEach(s => {
      document.getElementById(s)?.classList.remove('active');
      document.getElementById(s)?.classList.add('done');
    });

    const result = await response.json();

    if (!response.ok || result.error) {
      showError(result.error || 'Something went wrong.');
      return;
    }

    showReading(result.reading);

  } catch (err) {
    showError('Could not reach Drishti. Please check the server is running.');
  }
}

function showReading(r) {
  document.getElementById('loading-bubble')?.classList.add('hidden');

  document.getElementById('verdict').textContent = r.verdict || '';
  document.getElementById('timing').textContent = r.timing || '';
  document.getElementById('oracle-note').textContent = r.oracle_note || '';

  const signalsList = document.getElementById('signals');
  if (signalsList && r.signals) {
    signalsList.innerHTML = r.signals.map(s => `<li>${s}</li>`).join('');
  }

  const chipsEl = document.getElementById('followup-chips');
  if (chipsEl && r.followup_questions) {
    chipsEl.innerHTML = r.followup_questions.map(q =>
      `<button class="followup-chip" onclick="alert('One question per session. Explore more on Karmi!')">${q}</button>`
    ).join('');
  }

  document.getElementById('reading-card')?.classList.remove('hidden');

  setTimeout(() => {
    document.getElementById('limit-card')?.classList.remove('hidden');
  }, 1000);
}

function showError(msg) {
  document.getElementById('loading-bubble')?.classList.add('hidden');
  const errDiv = document.createElement('div');
  errDiv.className = 'chat-bubble';
  errDiv.innerHTML = `<div class="bubble-label">DRISHTI</div><p style="color:#ff6b6b;font-size:14px;">${msg}</p>`;
  document.querySelector('.chat-main')?.appendChild(errDiv);
}