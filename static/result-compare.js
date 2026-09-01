(()=>{
  if (window.__vpnBenchCompareV2Loaded) return;
  window.__vpnBenchCompareV2Loaded = true;

  const state = {
    results: [],
    selected: new Set(),
    baseline: null,
    panel: null,
    toolbar: null
  };

  const palette = ['#0a7cff','#28b463','#f59e0b','#8b5cf6','#06b6d4','#ef6aa8','#14b8a6','#fb7185'];
  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[ch]));
  const n = (value, digits=1) => value == null || !Number.isFinite(Number(value)) ? null : Number(value).toFixed(digits);
  const raw = value => value == null || !Number.isFinite(Number(value)) ? null : Number(value);

  const scoreOf = r => raw(r?.torrent_score?.score) ?? 0;
  const ratingOf = r => r?.torrent_score?.rating || (r?.ok ? 'Noch nicht bewertet' : 'Fehlgeschlagen');
  const downOf = r => raw(r?.throughput?.download_mbps ?? r?.download?.mbps);
  const upOf = r => raw(r?.throughput?.upload_mbps ?? r?.upload?.mbps);
  const singleOf = r => raw(r?.throughput?.single_download_mbps);
  const pingOf = r => raw(r?.ping?.avg_ms);
  const jitterOf = r => raw(r?.ping?.jitter_ms);
  const lossOf = r => raw(r?.ping?.loss_pct);
  const portOf = r => r?.port_forwarding || {};
  const shortFile = name => String(name || '').replace(/\.(conf|ovpn)$/i, '');
  const dateLabel = r => r?.ts ? new Date(r.ts * 1000).toLocaleString() : '–';

  function exitLabel(r) {
    const x = r?.exit || {};
    const place = [x.city, x.country].filter(Boolean).join(' / ');
    return place || shortFile(r?.name) || 'Unbekannter Exit';
  }

  function resultLabel(r) {
    return `${r?.provider || 'VPN'} · ${exitLabel(r)}`;
  }

  function providerClass(provider) {
    const p = String(provider || '').toLowerCase();
    if (p.includes('proton')) return 'proton';
    if (p.includes('ovpn')) return 'ovpn';
    return 'other';
  }

  function scoreTone(score) {
    if (score >= 90) return 'great';
    if (score >= 75) return 'good';
    if (score >= 60) return 'use';
    if (score >= 45) return 'warn';
    return 'bad';
  }

  function portRank(r) {
    const s = portOf(r).status;
    return s === 'open' ? 3 : s === 'mapped_unverified' ? 2 : s === 'unknown' ? 1 : 0;
  }

  function portText(r) {
    const p = portOf(r);
    const number = p.public_port ? ` ${p.public_port}` : '';
    if (p.status === 'open') return {label:`Offen ·${number}`, tone:'ok', hint:'Extern bestätigt'};
    if (p.status === 'mapped_unverified') return {label:`Mapping ·${number}`, tone:'mapped', hint:'Mapping aktiv, extern nicht bestätigt'};
    if (p.status === 'closed') return {label:'Geschlossen', tone:'bad', hint:'Kein erreichbarer eingehender Port'};
    return {label:'Unbekannt', tone:'unknown', hint:'Port nicht bestätigt'};
  }

  function ensureToolbar() {
    const tbody = document.querySelector('#results');
    const card = tbody?.closest('.card');
    if (!card) return null;
    card.classList.add('results-card-scene');

    let toolbar = document.querySelector('#compareToolbar');
    if (!toolbar) {
      toolbar = document.createElement('div');
      toolbar.id = 'compareToolbar';
      toolbar.className = 'compare-toolbar';
      toolbar.innerHTML = `
        <div class="compare-toolbar-copy">
          <div class="compare-kicker">Vergleich</div>
          <strong>Benchmark-Runs auswählen</strong>
          <span class="muted small" id="compareSelectedCount">0 ausgewählt</span>
        </div>
        <div class="compare-toolbar-actions">
          <button class="secondary" id="selectLatestCompare">Letzten Run je Config</button>
          <button class="secondary" id="clearCompareSelection">Auswahl aufheben</button>
          <button id="openCompare" disabled>Auswahl vergleichen</button>
        </div>`;
      const tableWrap = card.querySelector('.result-table-wrap') ||
        [...card.children].find(el => el.tagName === 'DIV' && String(el.getAttribute('style') || '').includes('overflow'));
      if (tableWrap) {
        tableWrap.classList.add('result-table-wrap');
        card.insertBefore(toolbar, tableWrap);
      } else {
        card.appendChild(toolbar);
      }
      toolbar.querySelector('#selectLatestCompare').addEventListener('click', selectLatestPerConfig);
      toolbar.querySelector('#clearCompareSelection').addEventListener('click', () => {
        state.selected.clear();
        renderResults();
      });
      toolbar.querySelector('#openCompare').addEventListener('click', renderComparison);
    }
    state.toolbar = toolbar;
    updateSelectionUI();
    return toolbar;
  }

  function updateSelectionUI() {
    const count = state.selected.size;
    const countEl = document.querySelector('#compareSelectedCount');
    const open = document.querySelector('#openCompare');
    if (countEl) countEl.textContent = `${count} ausgewählt`;
    if (open) open.disabled = count < 2;
  }

  function selectLatestPerConfig() {
    const byKey = new Map();
    for (const r of state.results) {
      const key = `${r.provider || ''}\u0000${r.name || ''}`;
      if (byKey.has(key)) continue;
      if (r.ok) byKey.set(key, Number(r.id));
    }
    for (const r of state.results) {
      const key = `${r.provider || ''}\u0000${r.name || ''}`;
      if (!byKey.has(key)) byKey.set(key, Number(r.id));
    }
    state.selected = new Set([...byKey.values()]);
    renderResults();
  }

  function makeCheckbox(r) {
    const checked = state.selected.has(Number(r.id));
    return `<label class="compare-check-wrap" title="Für Vergleich auswählen">
      <input class="compare-check" type="checkbox" value="${Number(r.id)}" ${checked ? 'checked' : ''}>
      <span></span>
    </label>`;
  }

  function renderResults() {
    const tbody = document.querySelector('#results');
    const table = tbody?.closest('table');
    if (!tbody || !table) return;

    ensureToolbar();
    table.classList.add('results-table-scene');
    const thead = table.querySelector('thead');
    if (thead) {
      thead.innerHTML = `<tr>
        <th class="select-col">Vergleich</th>
        <th>VPN / Exit</th>
        <th>Bewertung</th>
        <th>Durchsatz</th>
        <th>Netzqualität</th>
        <th>Port</th>
        <th>Gemessen</th>
      </tr>`;
    }

    tbody.innerHTML = '';
    if (!state.results.length) {
      tbody.innerHTML = `<tr><td colspan="7"><div class="results-empty">
        <strong>Noch keine VPN-Benchmark-Ergebnisse</strong>
        <span>Starte einen Test, danach kannst du die Runs hier auswählen und direkt vergleichen.</span>
      </div></td></tr>`;
      updateSelectionUI();
      return;
    }

    for (const r of state.results) {
      const tr = document.createElement('tr');
      tr.dataset.resultId = String(r.id);
      const e = r.exit || {};
      const port = portText(r);
      const score = scoreOf(r);
      const rating = ratingOf(r);
      const error = r.error || r.warning || '';
      const place = [e.city, e.country].filter(Boolean).join(' / ') || 'Exit nicht ermittelt';
      const ip = e.ip || '–';
      const org = e.org || '';
      const file = r.name || '–';

      tr.innerHTML = `
        <td class="select-col">${makeCheckbox(r)}</td>
        <td class="endpoint-cell">
          <div class="endpoint-head">
            <span class="provider-chip ${providerClass(r.provider)}">${esc(r.provider || 'VPN')}</span>
            <strong>${esc(place)}</strong>
          </div>
          <div class="endpoint-file" title="${esc(file)}">${esc(file)}</div>
          <div class="endpoint-meta">${esc(ip)}${org ? ` · ${esc(org)}` : ''}</div>
          ${error ? `<details class="result-details"><summary>Fehler / Hinweis</summary><div class="result-error">${esc(error)}</div></details>` : ''}
        </td>
        <td class="rating-cell">
          <span class="rating-pill ${scoreTone(score)}">${esc(rating)}</span>
          <div class="score-line"><b>${r.ok ? n(score,0) : '–'}</b><span>/100</span></div>
        </td>
        <td>
          <div class="metric-stack">
            <div><span>↓ Download</span><b>${downOf(r) == null ? '–' : `${n(downOf(r),1)} Mbps`}</b></div>
            <div><span>↑ Upload</span><b>${upOf(r) == null ? '–' : `${n(upOf(r),1)} Mbps`}</b></div>
            ${singleOf(r) == null ? '' : `<div class="minor"><span>Single</span><b>${n(singleOf(r),1)} Mbps</b></div>`}
          </div>
        </td>
        <td>
          <div class="quality-grid">
            <div><span>Ping</span><b>${pingOf(r) == null ? '–' : `${n(pingOf(r),2)} ms`}</b></div>
            <div><span>Jitter</span><b>${jitterOf(r) == null ? '–' : `${n(jitterOf(r),2)} ms`}</b></div>
            <div><span>Loss</span><b>${lossOf(r) == null ? '–' : `${n(lossOf(r),2)} %`}</b></div>
          </div>
        </td>
        <td class="port-cell">
          <span class="port-pill ${port.tone}">${esc(port.label)}</span>
          <span class="port-hint">${esc(port.hint)}</span>
        </td>
        <td class="date-cell">${esc(dateLabel(r))}</td>`;
      tbody.appendChild(tr);
    }

    tbody.querySelectorAll('.compare-check').forEach(input => {
      input.addEventListener('change', event => {
        const id = Number(event.currentTarget.value);
        if (event.currentTarget.checked) state.selected.add(id);
        else state.selected.delete(id);
        updateSelectionUI();
      });
    });
    updateSelectionUI();
  }

  async function refreshData() {
    try {
      const [rr, br] = await Promise.all([fetch('/api/results'), fetch('/api/baseline')]);
      state.results = await rr.json();
      const bd = await br.json();
      state.baseline = bd?.reference || null;
      const ids = new Set(state.results.map(r => Number(r.id)));
      state.selected = new Set([...state.selected].filter(id => ids.has(id)));
      renderResults();
    } catch (error) {
      console.warn('VPN Exit Bench comparison refresh failed', error);
    }
  }

  function bestBy(items, getter, direction='max') {
    const values = items.map(r => [r, getter(r)]).filter(([,v]) => v != null && Number.isFinite(v));
    if (!values.length) return null;
    values.sort((a,b) => direction === 'min' ? a[1] - b[1] : b[1] - a[1]);
    return values[0][0];
  }

  function recommendation(items) {
    const valid = items.filter(r => r.ok);
    if (!valid.length) return {winner:null, html:`<div class="compare-rec-copy"><h3>Keine erfolgreiche Messung ausgewählt</h3><p>Wähle mindestens zwei erfolgreiche Runs.</p></div>`};

    const ranked = [...valid].sort((a,b) => scoreOf(b) - scoreOf(a));
    const winner = ranked[0];
    const second = ranked[1] || null;
    const delta = second ? scoreOf(winner) - scoreOf(second) : null;

    const flags = [];
    if (bestBy(valid, downOf)?.id === winner.id) flags.push('Schnellster Download');
    if (bestBy(valid, upOf)?.id === winner.id) flags.push('Schnellster Upload');
    if (bestBy(valid, pingOf, 'min')?.id === winner.id) flags.push('Beste Latenz');
    if (bestBy(valid, lossOf, 'min')?.id === winner.id) flags.push('Niedrigster Packet Loss');
    if ([...valid].sort((a,b) => portRank(b) - portRank(a))[0]?.id === winner.id && portRank(winner) >= 2) flags.push('Port Forwarding');
    if (!flags.length) flags.push('Bestes Gesamtpaket');

    let detail = `${n(scoreOf(winner),0)}/100 Torrent Score`;
    if (second && delta != null) {
      detail += delta < 2
        ? ` · praktisch Gleichstand mit ${resultLabel(second)}`
        : ` · ${n(delta,1)} Punkte vor ${resultLabel(second)}`;
    }

    const pf = portOf(winner);
    let warning = '';
    if (pf.status === 'closed') warning = 'Der eingehende Port ist geschlossen. Für qBittorrent und Seeding ist das ein klarer Nachteil.';
    else if (pf.status === 'unknown') warning = 'Der eingehende Port wurde nicht bestätigt. Für eine belastbare Torrent-Empfehlung solltest du den Port prüfen.';
    else if (pf.status === 'mapped_unverified') warning = 'Port-Mapping ist aktiv, die externe Erreichbarkeit konnte aber nicht vollständig bestätigt werden.';

    return {
      winner,
      html:`<div class="compare-rec-icon">★</div>
        <div class="compare-rec-copy">
          <div class="compare-kicker">Empfehlung</div>
          <h3>${esc(resultLabel(winner))}</h3>
          <p><b>${esc(detail)}</b><br>Aktuell das beste Gesamtpaket aus Durchsatz, Peer-Erreichbarkeit, Stabilität und Latenz.</p>
          <div class="compare-badges">${flags.map(x => `<span>${esc(x)}</span>`).join('')}</div>
          ${warning ? `<div class="compare-warning">${esc(warning)}</div>` : ''}
        </div>`
    };
  }

  function compareRunCards(items, winner) {
    return `<div class="compare-run-grid">${items.map((r,index) => {
      const p = portText(r);
      const isWinner = winner && Number(winner.id) === Number(r.id);
      return `<article class="compare-run-card ${isWinner ? 'winner' : ''}" style="--series:${palette[index % palette.length]}">
        <div class="run-card-top">
          <div>
            <span class="provider-chip ${providerClass(r.provider)}">${esc(r.provider || 'VPN')}</span>
            <h4>${esc(exitLabel(r))}</h4>
          </div>
          <div class="run-score ${scoreTone(scoreOf(r))}">${r.ok ? `${n(scoreOf(r),0)}<small>/100</small>` : 'Fehler'}</div>
        </div>
        <div class="run-file" title="${esc(r.name)}">${esc(r.name || '–')}</div>
        <div class="run-card-metrics">
          <div><span>Download</span><b>${downOf(r)==null?'–':`${n(downOf(r),1)} Mbps`}</b></div>
          <div><span>Upload</span><b>${upOf(r)==null?'–':`${n(upOf(r),1)} Mbps`}</b></div>
          <div><span>Ping</span><b>${pingOf(r)==null?'–':`${n(pingOf(r),1)} ms`}</b></div>
          <div><span>Port</span><b>${esc(p.label)}</b></div>
        </div>
        <div class="run-date">${esc(dateLabel(r))}</div>
      </article>`;
    }).join('')}</div>`;
  }

  function barRows(items, getter, max, format, baseline=null) {
    const marker = baseline != null && Number.isFinite(baseline) ? Math.min(100, (baseline / max) * 100) : null;
    return items.map((r,index) => {
      const value = getter(r);
      const width = value == null ? 0 : Math.max(0, Math.min(100, (value/max)*100));
      return `<div class="compare-bar-row">
        <div class="compare-bar-label"><span class="compare-dot" style="--series:${palette[index % palette.length]}"></span>${esc(resultLabel(r))}</div>
        <div class="compare-bar-track">
          ${marker == null ? '' : `<span class="compare-baseline-marker" style="left:${marker}%"></span>`}
          <span class="compare-bar-fill" style="width:${width}%;--series:${palette[index % palette.length]}"></span>
        </div>
        <div class="compare-bar-value">${value == null ? '–' : esc(format(value))}</div>
      </div>`;
    }).join('');
  }

  function metricChart(title, subtitle, items, getter, baseline, format, extraClass='') {
    const values = items.map(getter).filter(v => v != null && Number.isFinite(v));
    const pool = [...values];
    if (baseline != null && Number.isFinite(baseline)) pool.push(baseline);
    const max = Math.max(...pool, 1) * 1.06;
    return `<section class="compare-chart-card ${extraClass}">
      <div class="compare-chart-title">
        <div><strong>${esc(title)}</strong><span>${esc(subtitle)}</span></div>
        ${baseline == null ? '' : `<em>Baseline ${esc(format(baseline))}</em>`}
      </div>
      <div class="compare-bars">${barRows(items, getter, max, format, baseline)}</div>
    </section>`;
  }

  function scoreChart(items) {
    return `<section class="compare-chart-card compare-score-card">
      <div class="compare-chart-title">
        <div><strong>Torrent Score</strong><span>Gesamtbewertung für qBittorrent</span></div>
        <em>0–100 · höher ist besser</em>
      </div>
      <div class="compare-bars">${barRows(items, scoreOf, 100, v => `${n(v,0)}/100`)}</div>
    </section>`;
  }

  function qualityCards(items) {
    return `<section class="quality-section">
      <div class="section-title">
        <div><strong>Netzqualität & Peer-Erreichbarkeit</strong><span>Je niedriger Ping, Jitter und Loss, desto besser. Ein erreichbarer Port ist für Torrents besonders wichtig.</span></div>
      </div>
      <div class="quality-card-grid">${items.map((r,index) => {
        const p = portText(r);
        return `<article class="quality-card" style="--series:${palette[index % palette.length]}">
          <div class="quality-head"><span class="compare-dot" style="--series:${palette[index % palette.length]}"></span><b>${esc(resultLabel(r))}</b></div>
          <div class="quality-metrics">
            <div><span>Ping</span><b>${pingOf(r)==null?'–':`${n(pingOf(r),2)} ms`}</b></div>
            <div><span>Jitter</span><b>${jitterOf(r)==null?'–':`${n(jitterOf(r),2)} ms`}</b></div>
            <div><span>Packet Loss</span><b>${lossOf(r)==null?'–':`${n(lossOf(r),2)} %`}</b></div>
          </div>
          <div class="quality-port"><span class="port-pill ${p.tone}">${esc(p.label)}</span><small>${esc(p.hint)}</small></div>
        </article>`;
      }).join('')}</div>
    </section>`;
  }

  function ensurePanel() {
    let panel = document.querySelector('#comparisonPanel');
    if (!panel) {
      const resultsCard = document.querySelector('#results')?.closest('.card');
      if (!resultsCard) return null;
      panel = document.createElement('div');
      panel.id = 'comparisonPanel';
      panel.className = 'card compare-panel';
      panel.hidden = true;
      resultsCard.parentNode.insertBefore(panel, resultsCard);
    }
    state.panel = panel;
    return panel;
  }

  function renderComparison() {
    const selected = state.results.filter(r => state.selected.has(Number(r.id)));
    if (selected.length < 2) return;

    const panel = ensurePanel();
    if (!panel) return;
    const rec = recommendation(selected);
    const baseDown = raw(state.baseline?.down_mbps);
    const baseUp = raw(state.baseline?.up_mbps);

    panel.innerHTML = `
      <div class="compare-panel-head">
        <div>
          <div class="compare-kicker">Direktvergleich</div>
          <h2>${selected.length} Benchmark-Runs im Vergleich</h2>
          <p>Ausgewählte Messungen aus deiner Ergebnis-Historie${baseDown || baseUp ? ` · Baseline ${baseDown ? n(baseDown,1)+' Mbps Down' : ''}${baseDown && baseUp ? ' / ' : ''}${baseUp ? n(baseUp,1)+' Mbps Up' : ''}` : ''}.</p>
        </div>
        <button class="secondary" id="closeCompare">Vergleich schließen</button>
      </div>
      <div class="compare-recommendation">${rec.html}</div>
      ${compareRunCards(selected, rec.winner)}
      <div class="compare-chart-layout">
        ${scoreChart(selected)}
        <div class="compare-throughput-grid">
          ${metricChart('Download','Mehrere parallele Streams',selected,downOf,baseDown,v=>`${n(v,1)} Mbps`)}
          ${metricChart('Upload','Für Seeding besonders relevant',selected,upOf,baseUp,v=>`${n(v,1)} Mbps`)}
        </div>
      </div>
      ${qualityCards(selected)}
      <div class="compare-footnote">Die Empfehlung priorisiert nicht nur maximale Geschwindigkeit. Für qBittorrent wiegen ein funktionierender eingehender Port und stabile Verbindungen stärker als kleine Unterschiede bei wenigen Millisekunden Ping.</div>`;

    panel.hidden = false;
    panel.querySelector('#closeCompare').addEventListener('click', () => {
      panel.hidden = true;
      document.querySelector('#compareToolbar')?.scrollIntoView({behavior:'smooth', block:'center'});
    });
    panel.scrollIntoView({behavior:'smooth', block:'start'});
  }

  const originalLoadResults = window.loadResults;
  window.loadResults = async function vpnBenchLoadResultsV2() {
    if (typeof originalLoadResults === 'function' && originalLoadResults !== window.loadResults) {
      try { await originalLoadResults(); } catch (_) {}
    }
    await refreshData();
  };

  const observer = new MutationObserver(() => {
    if (!document.querySelector('#results')) return;
    if (!document.querySelector('.results-table-scene')) refreshData();
  });
  observer.observe(document.body, {childList:true, subtree:true});

  refreshData();
})();