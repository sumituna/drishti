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

const BAND_LABELS = {
  high: 'High',
  moderate: 'Moderate',
  'low-moderate': 'Low–Moderate',
  low: 'Low',
  very_low: 'Very Low',
};

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

  const originalText = btn.textContent;
  btn.disabled = true;
  btn.textContent = 'Generating…';

  try {
    const res = await fetch(`${PACK_API}/generate-free-pack`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(lastForm),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Generation failed');

    packData = data;
    showPackResults(data);
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

  const order = ['career', 'wealth', 'relationships', 'health', 'spirituality', 'travel'];
  el.innerHTML = order.map(key => {
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
