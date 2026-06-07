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
  let stepIndex = 0;

  const advanceStep = () => {
    if (stepIndex > 0) {
      document.getElementById(steps[stepIndex - 1])?.classList.remove('active');
      document.getElementById(steps[stepIndex - 1])?.classList.add('done');
    }
    if (stepIndex < steps.length) {
      document.getElementById(steps[stepIndex])?.classList.add('active');
      stepIndex++;
    }
  };

  // Animate thinking agents sequentially
  const agentSequence = [
    { id: 'think-chart',         status: 'Computing planetary positions...',  delay: 0    },
    { id: 'think-career',        status: 'Analysing 10th house & Saturn...',  delay: 800  },
    { id: 'think-relationships', status: 'Reading Venus & 7th house...',      delay: 1400 },
    { id: 'think-wealth',        status: 'Checking Jupiter & 2nd house...',   delay: 2000 },
    { id: 'think-timing',        status: 'Mapping dasha windows...',          delay: 2600 },
    { id: 'think-synthesis',     status: 'Synthesising all readings...',      delay: 3400 },
  ];

  advanceStep(); // CHART

  // Fire agent animations
  agentSequence.forEach(({ id, status, delay }) => {
    setTimeout(() => {
      const el = document.getElementById(id);
      if (el) {
        el.classList.add('active');
        const statusEl = el.querySelector('.thinking-status');
        if (statusEl) statusEl.textContent = status;
      }
    }, delay);
  });

  const agentTimers = [
    setTimeout(() => advanceStep(), 2000),
    setTimeout(() => advanceStep(), 5000),
    setTimeout(() => advanceStep(), 7000),
  ];

  try {
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

    agentTimers.forEach(t => clearTimeout(t));
    steps.forEach(s => {
      document.getElementById(s)?.classList.remove('active');
      document.getElementById(s)?.classList.add('done');
    });

    // Mark all agents done
    agentSequence.forEach(({ id }) => {
      const el = document.getElementById(id);
      if (el) {
        el.classList.remove('active');
        el.classList.add('done');
      }
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
        <div class="agent-result-header" onclick="toggleAgentCard(this)" style="cursor:pointer;">
          <span class="agent-result-icon">${agentIcons[agent.domain] || '✦'}</span>
          <span class="agent-result-title">${agentTitles[agent.domain] || agent.domain}</span>
          <span class="agent-score ${agent.score >= 70 ? 'score-high' : agent.score >= 50 ? 'score-mid' : 'score-low'}">${agent.score}%</span>
          <span class="agent-expand-icon">+</span>
        </div>
        <p class="agent-verdict">${agent.verdict}</p>
        <div class="agent-detail hidden">
          <ul class="agent-signals">
            ${agent.signals.map(s => `<li>${s}</li>`).join('')}
          </ul>
          <div class="agent-timing">⏱ ${agent.timing}</div>
          <div class="agent-advice">→ ${agent.advice}</div>
        </div>
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

  loadYearAhead(JSON.parse(sessionStorage.getItem('drishti_data')));
}

function showError(msg) {
  document.getElementById('loading-bubble')?.classList.add('hidden');
  const errDiv = document.createElement('div');
  errDiv.className = 'chat-bubble';
  errDiv.innerHTML = `<div class="bubble-label">DRISHTI</div><p style="color:#ff6b6b;font-size:14px;">${msg}</p>`;
  document.querySelector('.chat-main')?.appendChild(errDiv);
}

// ── Charts ──
let timelineChartInstance = null;
let radarChartInstance = null;
let currentDomain = 'career';
let monthlyData = null;
let vedicDetailData = null;

const DOMAIN_COLORS = {
  career:       { line: '#C9A84C', fill: 'rgba(201,168,76,0.15)' },
  wealth:       { line: '#3D9E8C', fill: 'rgba(61,158,140,0.15)' },
  relationship: { line: '#E87C6B', fill: 'rgba(232,124,107,0.15)' },
  health:       { line: '#7B9E87', fill: 'rgba(123,158,135,0.15)' }
};

async function loadYearAhead(data) {
  try {
    const response = await fetch(`${API}/year-ahead`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: data.name,
        date: data.dob,
        time: data.tob,
        lat: data.lat,
        lon: data.lon,
        timezone: data.timezone
      })
    });

    const result = await response.json();
    if (!result.success) return;

    monthlyData = result.months;
    vedicDetailData = result.year_context;

    // Show narrative
    const narEl = document.getElementById('chart-narrative');
    if (narEl && result.narrative) {
      narEl.textContent = result.narrative.year_narrative;
    }

    // Show peak/low badges
    const peakEl = document.getElementById('chart-peak-info');
    if (peakEl && result.narrative) {
      peakEl.innerHTML = `
        <span class="peak-badge">⬆ Peak: ${result.narrative.peak_window}</span>
        <span class="low-badge">⬇ Watch: ${result.narrative.low_window}</span>
      `;
    }

    // Show vedic detail
    const vedicEl = document.getElementById('vedic-detail');
    if (vedicEl) vedicEl.textContent = result.year_context;

    renderTimelineChart(monthlyData, currentDomain);
    renderRadarChart(monthlyData);

    document.getElementById('chart-loading')?.classList.add('hidden');
    document.getElementById('charts-section')?.classList.remove('hidden');

  } catch (err) {
    console.error('Year ahead failed:', err);
  }
}

function renderTimelineChart(months, domain) {
  const ctx = document.getElementById('timelineChart');
  if (!ctx) return;

  const labels = months.map(m => m.month_label);
  const scores = months.map(m => m.scores[domain] || 0);
  const colors = DOMAIN_COLORS[domain] || DOMAIN_COLORS.career;

  if (timelineChartInstance) timelineChartInstance.destroy();

  timelineChartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: domain.charAt(0).toUpperCase() + domain.slice(1),
        data: scores,
        borderColor: colors.line,
        backgroundColor: colors.fill,
        borderWidth: 2,
        pointBackgroundColor: scores.map(s =>
          s >= 70 ? '#3D9E8C' : s >= 50 ? '#C9A84C' : '#ff8c69'
        ),
        pointRadius: 5,
        pointHoverRadius: 7,
        fill: true,
        tension: 0.4
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#0D0D2B',
          borderColor: 'rgba(255,255,255,0.1)',
          borderWidth: 1,
          titleColor: '#F0EBE0',
          bodyColor: 'rgba(240,235,224,0.7)',
          callbacks: {
            label: (ctx) => {
              const score = ctx.parsed.y;
              const band = score >= 70 ? 'Favorable' : score >= 50 ? 'Mixed' : 'Challenging';
              return `${score}/100 — ${band}`;
            },
            afterLabel: (ctx) => {
              const month = months[ctx.dataIndex];
              return `Dasha: ${month.dasha_path}`;
            }
          }
        }
      },
      scales: {
        y: {
          min: 0, max: 100,
          grid: { color: 'rgba(255,255,255,0.05)' },
          ticks: {
            color: 'rgba(240,235,224,0.4)',
            font: { size: 10 },
            callback: v => v >= 70 ? '▲ ' + v : v >= 50 ? '~ ' + v : '▼ ' + v
          }
        },
        x: {
          grid: { color: 'rgba(255,255,255,0.05)' },
          ticks: { color: 'rgba(240,235,224,0.5)', font: { size: 10 } }
        }
      }
    }
  });
}

function renderRadarChart(months) {
  const ctx = document.getElementById('radarChart');
  if (!ctx || !months.length) return;

  // Use average of first 3 months as "current" snapshot
  const domains = ['career', 'wealth', 'relationship', 'health', 'spirituality', 'travel'];
  const labels = ['Career', 'Wealth', 'Relationships', 'Health', 'Spirituality', 'Travel'];

  const scores = domains.map(d => {
    const avg = months.slice(0, 3).reduce((sum, m) => sum + (m.scores[d] || 0), 0) / 3;
    return Math.round(avg);
  });

  if (radarChartInstance) radarChartInstance.destroy();

  radarChartInstance = new Chart(ctx, {
    type: 'radar',
    data: {
      labels,
      datasets: [{
        label: 'Your Chart Now',
        data: scores,
        borderColor: '#C9A84C',
        backgroundColor: 'rgba(201,168,76,0.12)',
        borderWidth: 2,
        pointBackgroundColor: '#C9A84C',
        pointRadius: 4
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#0D0D2B',
          titleColor: '#F0EBE0',
          bodyColor: 'rgba(240,235,224,0.7)'
        }
      },
      scales: {
        r: {
          min: 0, max: 100,
          grid: { color: 'rgba(255,255,255,0.08)' },
          angleLines: { color: 'rgba(255,255,255,0.08)' },
          pointLabels: {
            color: 'rgba(240,235,224,0.6)',
            font: { size: 11, family: 'Inter' }
          },
          ticks: { display: false }
        }
      }
    }
  });
}

function toggleDomain(domain, btn) {
  currentDomain = domain;
  document.querySelectorAll('.dtoggle').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  if (monthlyData) renderTimelineChart(monthlyData, domain);
}

function toggleVedicMode(checkbox) {
  const vedicEl = document.getElementById('vedic-detail');
  if (vedicEl) {
    if (checkbox.checked) {
      vedicEl.classList.remove('hidden');
    } else {
      vedicEl.classList.add('hidden');
    }
  }
}

function toggleAgentCard(header) {
  const detail = header.parentElement.querySelector('.agent-detail');
  const icon = header.querySelector('.agent-expand-icon');
  if (detail) {
    detail.classList.toggle('hidden');
    if (icon) icon.textContent = detail.classList.contains('hidden') ? '+' : '−';
  }
}