const VEDIC_ENGINE_URL = 'https://mocha-editor-monogamy.ngrok-free.dev/api/vedic-native';
const PACK_API = typeof API !== 'undefined' ? API : 'https://drishti-6n6f.onrender.com';

let packData = null;
let lastForm = null;

const DOMAIN_LABELS = {
  career: 'Career',
  wealth: 'Wealth',
  relationships: 'Relationships',
  health: 'Health',
  spirituality: 'Spirituality',
  travel: 'Travel',
};

const DOMAIN_ORDER = ['career', 'wealth', 'relationships', 'health', 'spirituality', 'travel'];

const DOMAIN_API_MAP = {
  career: 'career',
  wealth: 'wealth',
  relationship: 'relationships',
  relationships: 'relationships',
  health: 'health',
  spirituality: 'spirituality',
  travel: 'travel',
};

const BAND_LABELS = {
  high: 'High',
  moderate: 'Moderate',
  'low-moderate': 'Low–Moderate',
  low: 'Low',
  very_low: 'Very Low',
};

const YOGA_STRENGTH_RANK = { high: 0, medium: 1, low: 2, challenging: 3 };

const MD_THEMES = {
  Sun: 'The soul steps into its authority',
  Moon: 'The heart learns what it truly needs',
  Mars: 'Energy seeks its right direction',
  Mercury: 'The mind sharpens its true purpose',
  Jupiter: 'Wisdom expands into new territory',
  Venus: 'Beauty and harmony take centre stage',
  Saturn: 'The great teacher demands accountability',
  Rahu: 'Ambition meets the unknown',
  Ketu: 'The past releases what no longer serves',
};

function scoreToBandBar(score) {
  if (score >= 70) return { band: 'high', bar: 8 };
  if (score >= 45) return { band: 'moderate', bar: 5 };
  if (score >= 35) return { band: 'low-moderate', bar: 4 };
  if (score >= 25) return { band: 'low', bar: 3 };
  return { band: 'very_low', bar: 1 };
}

function parseDomainsFromContext(context) {
  const domains = {};
  if (!context) return domains;

  const lines = context.split('\n');
  const lineRe = /^\s+(CAREER|WEALTH|RELATIONSHIP|HEALTH|SPIRITUALITY|TRAVEL)\s+(\d+)\/100\s+\[(\w+)\]/;
  const triggerRe = /^\s+Triggers:\s*(.+)$/;

  lines.forEach((line, i) => {
    const m = line.match(lineRe);
    if (!m) return;

    const score = parseInt(m[2], 10);
    const { band, bar } = scoreToBandBar(score);
    const key = DOMAIN_API_MAP[m[1].toLowerCase()];

    let note = '';
    for (let j = i + 1; j < Math.min(i + 4, lines.length); j++) {
      const tm = lines[j].match(triggerRe);
      if (tm) {
        note = tm[1].trim();
        if (note.toLowerCase() === 'none') note = '';
        break;
      }
    }

    domains[key] = { band, bar, note, score };
  });

  return domains;
}

function yogaStrengthRank(yoga) {
  const eff = yoga.effective_strength || yoga.strength || 'medium';
  return YOGA_STRENGTH_RANK[eff] ?? 1;
}

function extractTopYogas(chart, limit = 3) {
  const yogas = chart.yogas || [];
  const ranked = [...yogas].sort((a, b) => yogaStrengthRank(a) - yogaStrengthRank(b));
  const top = ranked.slice(0, limit).map(y => ({
    name: y.name || 'Yoga',
    effect: y.desc || '',
    strength: y.effective_strength || y.strength || 'medium',
  }));
  return { top, total: yogas.length };
}

function formatBirthDetails(name, date, time, place) {
  try {
    const [y, m, d] = date.split('-').map(Number);
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const dateFmt = `${String(d).padStart(2, '0')} ${months[m - 1]} ${y}`;
    return `${name} · ${dateFmt} · ${time} · ${place}`;
  } catch {
    return `${name} · ${date} · ${time} · ${place}`;
  }
}

function parseChartResponse(chart, form) {
  if (chart.error) throw new Error(chart.error);

  const asc = chart.ascendant || {};
  const planets = chart.planets || {};
  const dasha = chart.dasha || {};
  const rising = asc.sign || '—';
  const moon = (planets.Moon || {}).sign || '—';
  const sun = (planets.Sun || {}).sign || '—';
  const mahaLord = dasha.mahas || (dasha.current_maha || {}).lord || '—';

  const context = chart.karmi_context || chart.karmi_prompt_context || '';
  const domainScores = parseDomainsFromContext(context);
  DOMAIN_ORDER.forEach(key => {
    if (!domainScores[key]) {
      domainScores[key] = { band: 'moderate', bar: 5, note: 'Awaiting full domain analysis' };
    }
  });

  const { top: topYogas, total: totalYogaCount } = extractTopYogas(chart);

  return {
    identity: {
      name: form.name,
      birth_details: formatBirthDetails(form.name, form.date, form.time, form.place),
      rising,
      moon,
      sun,
    },
    theme: 'Theme coming soon',
    mahadasha: {
      lord: mahaLord,
      theme_line: MD_THEMES[mahaLord] || 'Your current planetary chapter unfolds.',
    },
    domain_scores: domainScores,
    top_yogas: topYogas,
    total_yoga_count: totalYogaCount,
  };
}

function prefillFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const name = params.get('name');
  const date = params.get('date');
  const time = params.get('time');
  const place = params.get('place');

  if (name) document.getElementById('name').value = name;
  if (date) document.getElementById('dob').value = date;
  if (time) document.getElementById('tob').value = time;
  if (place) document.getElementById('place').value = place;
}

async function generateChartPack() {
  const name = document.getElementById('name')?.value?.trim();
  const dob = document.getElementById('dob')?.value;
  const tob = document.getElementById('tob')?.value;
  const place = document.getElementById('place')?.value?.trim();
  const btn = document.getElementById('generate-btn');

  if (!name || !dob || !tob || !place) {
    alert('Please fill in all birth details.');
    return;
  }
  if (!resolvedLat || !resolvedLon) {
    alert('Please select your birth city from the dropdown.');
    return;
  }

  lastForm = {
    name, date: dob, time: tob, place,
    lat: resolvedLat, lon: resolvedLon,
    timezone: resolvedTimezone,
  };

  const [year, month, day] = dob.split('-').map(Number);
  const [hour, minute] = tob.split(':').map(Number);
  const enginePayload = {
    year, month, day, hour, minute,
    lat: resolvedLat,
    lon: resolvedLon,
    utc_offset: resolvedTimezone,
  };

  const originalText = btn.textContent;
  btn.disabled = true;
  btn.textContent = 'Generating…';

  try {
    const res = await fetch(VEDIC_ENGINE_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'ngrok-skip-browser-warning': 'true',
      },
      body: JSON.stringify(enginePayload),
    });
    const chart = await res.json();
    if (!res.ok) throw new Error(chart.error || 'Chart computation failed');

    packData = parseChartResponse(chart, lastForm);
    showPackResults(packData);
  } catch (err) {
    alert(err.message || 'Could not generate chart pack. Please try again.');
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
  }
}

function showPackResults(data) {
  document.getElementById('pack-pre-result')?.classList.add('hidden');
  document.getElementById('pack-results')?.classList.remove('hidden');

  const ident = data.identity || {};
  document.getElementById('result-name').textContent = ident.name || '';
  document.getElementById('result-birth').textContent = ident.birth_details || '';
  document.getElementById('result-rising').textContent = ident.rising || '—';
  document.getElementById('result-moon').textContent = ident.moon || '—';
  document.getElementById('result-sun').textContent = ident.sun || '—';
  document.getElementById('result-theme').textContent = data.theme || '';

  const md = data.mahadasha || {};
  document.getElementById('result-md-line').textContent =
    `${md.lord || '—'} Mahadasha · ${md.theme_line || ''}`;

  renderDomainBars(data.domain_scores || {});
  renderYogas(data.top_yogas || [], data.total_yoga_count || 0);
  renderShareCard(data);
}

function renderDomainBars(scores) {
  const el = document.getElementById('domain-bars');
  if (!el) return;

  el.innerHTML = DOMAIN_ORDER.map(key => {
    const d = scores[key] || { bar: 5, band: 'moderate', note: '' };
    const bar = Math.min(10, Math.max(0, d.bar || 5));
    const cells = Array.from({ length: 10 }, (_, i) =>
      `<span class="pack-bar-cell${i < bar ? ' filled' : ''}"></span>`
    ).join('');
    const bandLabel = BAND_LABELS[d.band] || d.band;
    const note = d.note ? `<span class="pack-domain-note">${d.note}</span>` : '';
    return `
      <div class="pack-domain-row">
        <span class="pack-domain-label">${DOMAIN_LABELS[key]}</span>
        <div class="pack-bar-track">${cells}</div>
        <span class="pack-domain-band">${bandLabel}</span>
        ${note}
      </div>`;
  }).join('');
}

function renderYogas(yogas, total) {
  const list = document.getElementById('yoga-list');
  const more = document.getElementById('yoga-more');
  if (!list) return;

  list.innerHTML = yogas.map(y => `
    <div class="pack-yoga-item">
      <div class="pack-yoga-name">${y.name}</div>
      <div class="pack-yoga-effect">${y.effect}</div>
    </div>
  `).join('');

  const extra = (total || 0) - yogas.length;
  if (more) {
    more.textContent = extra > 0
      ? `+ ${extra} more yogas in your full chart`
      : '';
  }
}

function renderShareCard(data) {
  const ident = data.identity || {};
  const md = data.mahadasha || {};
  const line = `${ident.rising} Rising · ${ident.moon} Moon · ${md.lord} Mahadasha`;
  document.getElementById('share-line').textContent = line;
  document.getElementById('share-theme').textContent = data.theme || '';

  const shareText = `${line}\n${data.theme || ''}\n\nGet your chart pack: https://karmi.ai/pack`;
  const wa = document.getElementById('whatsapp-link');
  if (wa) {
    wa.href = `https://wa.me/?text=${encodeURIComponent(shareText)}`;
  }
  window._packShareText = shareText;
}

function copyShareText() {
  const text = window._packShareText || '';
  if (!text) return;
  navigator.clipboard.writeText(text).then(() => {
    alert('Copied to clipboard.');
  }).catch(() => {
    prompt('Copy this text:', text);
  });
}

function downloadFreePack() {
  if (!lastForm) {
    alert('Generate your chart pack first.');
    return;
  }
  const q = new URLSearchParams({
    name: lastForm.name,
    date: lastForm.date,
    time: lastForm.time,
    place: lastForm.place,
    lat: lastForm.lat,
    lon: lastForm.lon,
    timezone: lastForm.timezone,
  });
  window.location.href = `${PACK_API}/download-free-pack?${q.toString()}`;
}

document.addEventListener('DOMContentLoaded', prefillFromUrl);
