(()=>{
  if (window.__vpnBenchCompareLoaded) return;
  window.__vpnBenchCompareLoaded = true;

  const state = {
    results: [],
    selected: new Set(),
    baseline: null,
    panel: null,
    toolbar: null
  };

  const palette = ['#2f7df6','#36c98f','#f2b84b','#a675ff','#ff7c66','#4cc9f0','#ef6aa8','#9acb52'];
  const escHtml = value => String(value ?? '').replace(/[&<>"']/g, ch => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[ch]));
  const num = (value, digits=1) => value == null || !Number.isFinite(Number(value)) ? null : Number(value).toFixed(digits);
  const rawNum = value => value == null || !Number.isFinite(Number(value)) ? null : Number(value);
  const scoreOf = r => rawNum(r?.torrent_score?.score) ?? 0;
  const downOf = r => rawNum(r?.throughput?.download_mbps ?? r?.download?.mbps);
  const upOf = r => rawNum(r?.throughput?.upload_mbps ?? r?.upload?.mbps);
  const pingOf = r => rawNum(r?.ping?.avg_ms);
  const jitterOf = r => rawNum(r?.ping?.jitter_ms);
  const lossOf = r => rawNum(r?.ping?.loss_pct);
  const portOf = r => r?.port_forwarding || {};
  const dateLabel = r => r?.ts ? new Date(r.ts * 1000).toLocaleString() : '–';
  const shortFile = name => String(name || '').replace(/\.(conf|ovpn)$/i,'');
  const resultLabel = r => {
    const exit = r?.exit || {};
    const place = [exit.city, exit.country].filter(Boolean).join(' / ');
    return `${r.provider || 'VPN'} · ${place || shortFile(r.name)}`;
  };
  const runLabel = r => `${resultLabel(r)} · ${dateLabel(r)}`;

  function ensureToolbar() {
    const tbody = document.querySelector('#results');
    const card = tbody?.closest('.card');
    if (!card) return null;

    let toolbar = document.querySelector('#compareToolbar');
    if (!toolbar) {
      toolbar = document.createElement('div');
      toolbar.id = 'compareToolbar';
      toolbar.className = 'compare-toolbar';
      toolbar.innerHTML = `
        <div class="compare-toolbar-left">
          <strong>Ergebnisse vergleichen</strong>
          <span class="muted small" id="compareSelectedCount">0 ausgewählt</span>
        </div>
        <div class="compare-toolbar-actions">
          <button class="secondary" id="selectLatestCompare">Letzten erfolgreichen Run je Config wählen</button>
          <button class="secondary" id="clearCompareSelection">Auswahl aufheben</button>
          <button id="openCompare" disabled>Auswahl vergleichen</button>
        </div>`;
      const tableWrap = [...card.children].find(el => el.tagName === 'DIV' && String(el.getAttribute('style')||'').includes('overflow'));
      if (tableWrap) card.insertBefore(toolbar, tableWrap);
      else card.appendChild(toolbar);

      toolbar.querySelector('#selectLatestCompare').addEventListener('click', selectLatestPerConfig);
      toolbar.querySelector('#clearCompareSelection').addEventListener('click', () => {
        state.selected.clear();
        syncCheckboxes();
        updateSelectionUI();
      });
      toolbar.querySelector('#openCompare').addEventListener('click', renderComparison);
    }
    state.toolbar = toolbar;
    return toolbar;
  }

  function ensureHeader() {
    const table = document.querySelector('#results')?.closest('table');
    const headRow = table?.querySelector('thead tr');
    if (!headRow) return;
    if (!headRow.querySelector('.compare-select-head')) {
      const th = document.createElement('th');
      th.className = 'compare-select-head';
      th.textContent = 'Vergleich';
      headRow.insertBefore(th, headRow.firstChild);
    }
  }

  function decorateRows() {
    const tbody = document.querySelector('#results');
    if (!tbody) return;
    ensureHeader();
    ensureToolbar();

    const rows = [...tbody.querySelectorAll('tr')];
    if (!state.results.length) {
      rows.forEach(tr => {
        const td = tr.querySelector('td[colspan]');
        if (td) td.colSpan = 13;
      });
      updateSelectionUI();
      return;
    }

    rows.forEach((tr, index) => {
      const result = state.results[index];
      if (!result) return;
      tr.dataset.resultId = String(result.id);
      let cell = tr.querySelector('.compare-select-cell');
      if (!cell) {
        cell = document.createElement('td');
        cell.className = 'compare-select-cell';
        tr.insertBefore(cell, tr.firstChild);
      }
      const checked = state.selected.has(Number(result.id));
      cell.innerHTML = `<label class="compare-check-wrap" title="${escHtml(runLabel(result))}">
        <input class="compare-check" type="checkbox" value="${Number(result.id)}" ${checked ? 'checked' : ''}>
        <span></span>
      </label>`;
      cell.querySelector('input').addEventListener('change', event => {
        const id = Number(event.currentTarget.value);
        if (event.currentTarget.checked) state.selected.add(id);
        else state.selected.delete(id);
        updateSelectionUI();
      });
    });
    updateSelectionUI();
  }

  function syncCheckboxes() {
    document.querySelectorAll('.compare-check').forEach(input => {
      input.checked = state.selected.has(Number(input.value));
    });
  }

  function updateSelectionUI() {
    const count = state.selected.size;
    const label = document.querySelector('#compareSelectedCount');
    const button = document.querySelector('#openCompare');
    if (label) label.textContent = `${count} ausgewählt`;
    if (button) button.disabled = count < 2;
  }

  function selectLatestPerConfig() {
    const byKey = new Map();
    for (const r of state.results) {
      if (!r?.ok) continue;
      const key = `${r.provider || ''}\u0000${r.name || ''}`;
      if (!byKey.has(key)) byKey.set(key, Number(r.id));
    }
    for (const r of state.results) {
      const key = `${r.provider || ''}\u0000${r.name || ''}`;
      if (!byKey.has(key)) byKey.set(key, Number(r.id));
    }
    state.selected = new Set([...byKey.values()]);
    syncCheckboxes();
    updateSelectionUI();
  }

  async function refreshData() {
    try {
      const [resultsResponse, baselineResponse] = await Promise.all([
        fetch('/api/results'),
        fetch('/api/baseline')
      ]);
      state.results = await resultsResponse.json();
      const baselineData = await baselineResponse.json();
      state.baseline = baselineData?.reference || null;

      const ids = new Set(state.results.map(r => Number(r.id)));
      state.selected = new Set([...state.selected].filter(id => ids.has(id)));
      decorateRows();
    } catch (error) {
      console.warn('VPN Exit Bench comparison refresh failed', error);
    }
  }

  function ensurePanel() {
    let panel = document.querySelector('#comparisonPanel');
    if (panel) {
      state.panel = panel;
      return panel;
    }
    const resultsCard = document.querySelector('#results')?.closest('.card');
    if (!resultsCard) return null;
    panel = document.createElement('div');
    panel.id = 'comparisonPanel';
    panel.className = 'card compare-panel';
    panel.hidden = true;
    resultsCard.parentNode.insertBefore(panel, resultsCard);
    state.panel = panel;
    return panel;
  }

  function barRows(items, valueGetter, maxValue, formatter, baselineValue=null) {
    const safeMax = maxValue > 0 ? maxValue : 1;
    const marker = baselineValue != null && baselineValue >= 0
      ? Math.min(100, (baselineValue / safeMax) * 100)
      : null;
    return items.map((r, index) => {
      const value = valueGetter(r);
      const width = value == null ? 0 : Math.max(0, Math.min(100, (value / safeMax) * 100));
      return `<div class="compare-bar-row">
        <div class="compare-bar-label" title="${escHtml(runLabel(r))}">${escHtml(resultLabel(r))}</div>
        <div class="compare-bar-track">
          ${marker == null ? '' : `<span class="compare-baseline-marker" style="left:${marker}%;" title="Baseline ${escHtml(formatter(baselineValue))}"></span>`}
          <span class="compare-bar-fill" style="width:${width}%;--series:${palette[index % palette.length]};"></span>
        </div>
        <div class="compare-bar-value">${value == null ? '–' : escHtml(formatter(value))}</div>
      </div>`;
    }).join('');
  }

  function metricChart(title, subtitle, items, getter, baselineValue, formatter) {
    const vals = items.map(getter).filter(v => v != null && Number.isFinite(v));
    const candidates = [...vals];
    if (baselineValue != null && Number.isFinite(baselineValue)) candidates.push(baselineValue);
    const max = Math.max(...candidates, 1) * 1.08;
    return `<section class="compare-chart-card">
      <div class="compare-chart-title"><strong>${escHtml(title)}</strong><span>${escHtml(subtitle)}</span></div>
      <div class="compare-bars">${barRows(items, getter, max, formatter, baselineValue)}</div>
    </section>`;
  }

  function portRank(r) {
    const status = portOf(r).status;
    return status === 'open' ? 3 : status === 'mapped_unverified' ? 2 : status === 'unknown' ? 1 : 0;
  }

  function portLabel(r) {
    const p = portOf(r);
    const port = p.public_port ? ` · ${p.public_port}` : '';
    if (p.status === 'open') return `Offen${port}`;
    if (p.status === 'mapped_unverified') return `Mapping aktiv${port}`;
    if (p.status === 'closed') return `Geschlossen${port}`;
    return `Unbekannt${port}`;
  }

  function bestBy(items, getter, direction='max') {
    const candidates = items.map(r => [r, getter(r)]).filter(([,v]) => v != null && Number.isFinite(v));
    if (!candidates.length) return null;
    candidates.sort((a,b) => direction === 'min' ? a[1]-b[1] : b[1]-a[1]);
    return candidates[0][0];
  }

  function buildRecommendation(items) {
    const valid = items.filter(r => r?.ok);
    if (!valid.length) {
      return {
        winner: null,
        html: `<div class="compare-rec-copy"><h3>Keine erfolgreiche Messung ausgewählt</h3><p>Für eine Empfehlung müssen mindestens zwei erfolgreiche Benchmark-Runs ausgewählt sein.</p></div>`
      };
    }

    const ranked = [...valid].sort((a,b) => scoreOf(b)-scoreOf(a));
    const winner = ranked[0];
    const second = ranked[1] || null;
    const delta = second ? scoreOf(winner) - scoreOf(second) : null;
    const fastestDown = bestBy(valid, downOf, 'max');
    const fastestUp = bestBy(valid, upOf, 'max');
    const bestPing = bestBy(valid, pingOf, 'min');
    const bestLoss = bestBy(valid, lossOf, 'min');
    const bestPort = [...valid].sort((a,b) => portRank(b)-portRank(a))[0] || null;
    const badges = [];
    if (fastestDown?.id === winner.id) badges.push('Schnellster Download');
    if (fastestUp?.id === winner.id) badges.push('Schnellster Upload');
    if (bestPing?.id === winner.id) badges.push('Beste Latenz');
    if (bestLoss?.id === winner.id) badges.push('Niedrigster Packet Loss');
    if (bestPort?.id === winner.id && portRank(winner) >= 2) badges.push('Port Forwarding');
    if (!badges.length) badges.push('Bestes Gesamtpaket');

    let headline = `${resultLabel(winner)} ist die beste qBittorrent-Wahl`;
    let detail = `Torrent Score ${num(scoreOf(winner),0)}/100`;
    if (second && delta != null) {
      if (delta < 2) detail += ` · praktisch Gleichstand mit ${resultLabel(second)}`;
      else if (delta < 5) detail += ` · knapper Vorsprung von ${num(delta,1)} Punkten`;
      else detail += ` · ${num(delta,1)} Punkte vor Platz 2`;
    }
    const pf = portOf(winner);
    let warning = '';
    if (pf.status === 'closed') warning = 'Der eingehende Port ist geschlossen; für Seeding/Peer-Erreichbarkeit ist das ein deutlicher Nachteil.';
    else if (pf.status === 'unknown') warning = 'Der eingehende Port konnte nicht bestätigt werden. Die Empfehlung ist deshalb weniger belastbar.';
    else if (pf.status === 'mapped_unverified') warning = 'Ein Port-Mapping wurde angelegt, die externe Erreichbarkeit aber nicht vollständig bestätigt.';

    return {
      winner,
      html: `<div class="compare-rec-icon">★</div>
        <div class="compare-rec-copy">
          <div class="compare-kicker">Empfehlung</div>
          <h3>${escHtml(headline)}</h3>
          <p>${escHtml(detail)}. Die Empfehlung berücksichtigt Durchsatz, eingehenden Port, Stabilität und Latenz.</p>
          <div class="compare-badges">${badges.map(b => `<span>${escHtml(b)}</span>`).join('')}</div>
          ${warning ? `<div class="compare-warning">${escHtml(warning)}</div>` : ''}
        </div>`
    };
  }

  function qualityTable(items) {
    return `<div class="compare-quality-wrap"><table class="compare-quality">
      <thead><tr><th>Run</th><th>Score</th><th>Download</th><th>Upload</th><th>Ping</th><th>Jitter</th><th>Loss</th><th>Port</th></tr></thead>
      <tbody>${items.map((r,index) => `<tr>
        <td><span class="compare-dot" style="--series:${palette[index % palette.length]}"></span><b>${escHtml(resultLabel(r))}</b><br><span class="muted small">${escHtml(dateLabel(r))}</span></td>
        <td><b>${r.ok ? `${num(scoreOf(r),0)}/100` : 'Fehler'}</b></td>
        <td>${downOf(r)==null?'–':`${num(downOf(r),1)} Mbps`}</td>
        <td>${upOf(r)==null?'–':`${num(upOf(r),1)} Mbps`}</td>
        <td>${pingOf(r)==null?'–':`${num(pingOf(r),2)} ms`}</td>
        <td>${jitterOf(r)==null?'–':`${num(jitterOf(r),2)} ms`}</td>
        <td>${lossOf(r)==null?'–':`${num(lossOf(r),2)} %`}</td>
        <td>${escHtml(portLabel(r))}</td>
      </tr>`).join('')}</tbody>
    </table></div>`;
  }

  function scoreChart(items) {
    return `<section class="compare-chart-card compare-score-card">
      <div class="compare-chart-title"><strong>Torrent Score</strong><span>Gesamtbewertung für qBittorrent · 0 bis 100</span></div>
      <div class="compare-bars">${items.map((r,index) => {
        const score = r.ok ? scoreOf(r) : 0;
        return `<div class="compare-bar-row">
          <div class="compare-bar-label" title="${escHtml(runLabel(r))}">${escHtml(resultLabel(r))}</div>
          <div class="compare-bar-track"><span class="compare-bar-fill" style="width:${Math.max(0,Math.min(100,score))}%;--series:${palette[index % palette.length]};"></span></div>
          <div class="compare-bar-value">${r.ok ? `${num(score,0)}/100` : 'Fehler'}</div>
        </div>`;
      }).join('')}</div>
    </section>`;
  }

  async function renderComparison() {
    const panel = ensurePanel();
    if (!panel) return;
    await refreshData();

    const selected = state.results.filter(r => state.selected.has(Number(r.id)));
    if (selected.length < 2) return;
    const recommendation = buildRecommendation(selected);
    const successful = selected.filter(r => r.ok);
    const baseDown = rawNum(state.baseline?.down_mbps);
    const baseUp = rawNum(state.baseline?.up_mbps);
    const failedCount = selected.length - successful.length;

    panel.innerHTML = `
      <div class="compare-panel-head">
        <div>
          <div class="compare-kicker">Direktvergleich</div>
          <h2>${selected.length} Benchmark-Runs im Vergleich</h2>
          <div class="muted small">Auswahl aus der Ergebnis-Historie. Baseline: ${baseDown==null?'–':`${num(baseDown,1)} Mbps Down`} / ${baseUp==null?'–':`${num(baseUp,1)} Mbps Up`}.</div>
        </div>
        <button class="secondary" id="closeCompare">Vergleich schließen</button>
      </div>
      <div class="compare-recommendation">${recommendation.html}</div>
      ${failedCount ? `<div class="compare-warning">${failedCount} ausgewählte${failedCount===1?'r Run wurde':' Runs wurden'} wegen eines fehlgeschlagenen Benchmarks nicht für die Empfehlung gewertet, bleibt aber in der Tabelle sichtbar.</div>` : ''}
      <div class="compare-chart-grid">
        ${scoreChart(selected)}
        ${metricChart('Download','Baseline-Markierung zeigt deine Direktleitung',successful,downOf,baseDown,v=>`${num(v,1)} Mbps`)}
        ${metricChart('Upload','Für Seeding besonders relevant',successful,upOf,baseUp,v=>`${num(v,1)} Mbps`)}
      </div>
      <section class="compare-chart-card">
        <div class="compare-chart-title"><strong>Qualität & Peer-Erreichbarkeit</strong><span>Rohwerte der ausgewählten Runs</span></div>
        ${qualityTable(selected)}
      </section>
      <div class="compare-footnote">Je höher der Torrent Score, desto besser das Gesamtpaket. Beim Durchsatz ist die gemessene Direktleitung die Referenz. Für Torrents wiegt ein funktionierender eingehender Port deutlich stärker als wenige Millisekunden Ping-Unterschied.</div>`;

    panel.hidden = false;
    panel.querySelector('#closeCompare').addEventListener('click', () => {
      panel.hidden = true;
    });
    panel.scrollIntoView({behavior:'smooth',block:'start'});
  }

  const originalLoadResults = window.loadResults;
  if (typeof originalLoadResults === 'function') {
    window.loadResults = async function(...args) {
      const value = await originalLoadResults.apply(this,args);
      await refreshData();
      return value;
    };
  }

  ensurePanel();
  refreshData();
})();