(()=>{
  if(window.__vpnBenchPeerMapLoaded)return;
  window.__vpnBenchPeerMapLoaded=true;

  const REGION_ORDER=['NL','DE','CH','DK','SE','PL','RO'];
  const REGION_POS={NL:[315,230],DE:[370,260],CH:[365,315],DK:[390,170],SE:[500,100],PL:[500,260],RO:[570,365]};
  const EXIT_POS={NL:[300,220],DE:[365,245],CH:[350,325],DK:[375,155],SE:[490,82],PL:[485,245],RO:[555,350],FI:[565,72],NO:[415,68],FR:[280,315],GB:[210,240],BE:[305,260],AT:[410,315],CZ:[440,280],IT:[405,395],ES:[225,410],HU:[475,330]};
  const esc=v=>String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
  const n=(v,d=1)=>v==null||!Number.isFinite(Number(v))?'–':Number(v).toFixed(d);
  const short=name=>String(name||'').replace(/\.(conf|ovpn)$/i,'');
  const scoreOf=r=>Number(r?.peer_connectivity?.score||0);
  const regionsOf=r=>r?.peer_connectivity?.regions||{};
  const exitCode=r=>{
    const c=String(r?.exit?.country||'').toUpperCase();
    if(EXIT_POS[c])return c;
    const m=String(r?.name||'').toUpperCase().match(/(?:^|[-_. ])(NL|DE|CH|DK|SE|PL|RO|FI|NO|FR|GB|BE|AT|CZ|IT|ES|HU)(?:[-_. ]|$)/);
    return m?.[1]||'DE';
  };
  const labelOf=r=>`${r?.provider||'VPN'} · ${r?.exit?.city||short(r?.name)||'Exit'}`;
  const tone=s=>s>=85?'great':s>=70?'good':s>=55?'mid':'bad';
  const lineColor=s=>s>=85?'#45d483':s>=70?'#9fda55':s>=55?'#f2c94c':'#ff6b6b';

  function selectedIds(){return [...document.querySelectorAll('.compare-check:checked')].map(x=>Number(x.value)).filter(Number.isFinite)}

  function bestPerRegion(items){
    const best={};
    for(const code of REGION_ORDER){
      let winner=null,score=-1;
      for(const r of items){
        const s=Number(regionsOf(r)?.[code]?.score);
        if(Number.isFinite(s)&&s>score){winner=r;score=s}
      }
      best[code]=winner?{id:Number(winner.id),score}:null;
    }
    return best;
  }

  function mapSvg(run){
    const code=exitCode(run);
    let [ex,ey]=EXIT_POS[code]||[365,245];
    if(REGION_POS[code]){ex-=24;ey+=28}
    const regions=regionsOf(run);
    const lines=REGION_ORDER.map(c=>{
      const reg=regions[c]||{}; const s=Number(reg.score||0); const [tx,ty]=REGION_POS[c];
      return `<line class="peer-route" x1="${ex}" y1="${ey}" x2="${tx}" y2="${ty}" stroke="${lineColor(s)}" stroke-width="${2.2+s/28}" opacity="${0.48+s/190}"><title>${esc(c)} · ${n(s,0)}/100 · ↓ ${n(reg.download_mbps,1)} Mbps · ↑ ${n(reg.upload_mbps,1)} Mbps · ${n(reg.ping_ms,1)} ms · Loss ${n(reg.loss_pct,1)}%</title></line>`;
    }).join('');
    const nodes=REGION_ORDER.map(c=>{const reg=regions[c]||{},s=Number(reg.score||0),[x,y]=REGION_POS[c];return `<g class="peer-target"><circle cx="${x}" cy="${y}" r="18" fill="${lineColor(s)}"><title>${esc(c)} · ${n(s,0)}/100</title></circle><text x="${x}" y="${y+4}" text-anchor="middle">${c}</text><text class="score" x="${x}" y="${y+34}" text-anchor="middle">${n(s,0)}/100</text></g>`}).join('');
    return `<svg class="peer-europe-svg" viewBox="0 0 760 500" role="img" aria-label="Europa Peer Connectivity">
      <rect class="peer-water" x="0" y="0" width="760" height="500" rx="14"/>
      <path class="peer-land" d="M165 225 L205 190 L270 175 L315 188 L350 150 L395 165 L430 145 L470 160 L520 150 L575 185 L620 235 L610 295 L575 320 L605 370 L560 415 L500 405 L455 380 L420 430 L370 420 L330 375 L280 360 L235 325 L205 280 Z"/>
      <path class="peer-land" d="M390 175 L405 100 L438 55 L485 38 L535 65 L555 118 L515 165 L470 185 Z"/>
      <path class="peer-land" d="M175 205 L205 185 L230 215 L220 265 L190 275 L170 245 Z"/>
      ${lines}${nodes}
      <g class="peer-exit"><circle cx="${ex}" cy="${ey}" r="12"/><text x="${ex+17}" y="${ey+4}">${esc(code)} Exit</text></g>
    </svg>`;
  }

  function regionCards(run){
    const regions=regionsOf(run);
    return `<div class="peer-region-details">${REGION_ORDER.map(code=>{const r=regions[code]||{},net=(r.networks||[])[0]||{};return `<article class="peer-region-card"><div class="top"><b>${code} · ${esc(r.city||'')}</b><span class="peer-score-cell ${tone(Number(r.score||0))}">${n(r.score,0)}</span></div><div class="network" title="${esc(r.primary||net.label||'')}">${esc(r.primary||net.label||'Kein Messziel')}</div><div class="peer-region-metrics"><div><span>Down</span><b>${n(r.download_mbps,1)} Mbps</b></div><div><span>Up</span><b>${n(r.upload_mbps,1)} Mbps</b></div><div><span>Ping</span><b>${n(r.ping_ms,1)} ms</b></div><div><span>Loss</span><b>${n(r.loss_pct,1)} %</b></div></div></article>`}).join('')}</div>`;
  }

  function matrix(items){
    const best=bestPerRegion(items);
    return `<div class="peer-matrix-card"><h4>Europa-Matrix</h4><p>Je Land ist der beste Exit dieses Providers markiert.</p><div class="peer-matrix-scroll"><table class="peer-matrix"><thead><tr><th>Config</th><th>EU</th>${REGION_ORDER.map(c=>`<th>${c}</th>`).join('')}</tr></thead><tbody>${items.map(r=>`<tr><td><b>${esc(short(r.name))}</b></td><td><span class="peer-score-cell ${tone(scoreOf(r))}">${n(scoreOf(r),0)}</span></td>${REGION_ORDER.map(c=>{const s=Number(regionsOf(r)?.[c]?.score||0),isBest=best[c]?.id===Number(r.id);return `<td><span class="peer-score-cell ${tone(s)} ${isBest?'best':''}" title="${isBest?'Bester Exit dieses Providers für '+c:''}">${n(s,0)}${isBest?' ★':''}</span></td>`}).join('')}</tr>`).join('')}</tbody></table></div></div>`;
  }

  function providerView(provider,items,host){
    items=[...items].sort((a,b)=>scoreOf(b)-scoreOf(a));
    const best=items[0]; let active=best;
    host.innerHTML=`<div class="peer-summary"><div><span>Beste EU-Peer-Config</span><b>${esc(short(best.name))}</b></div><div><span>EU Peer Score</span><b>${n(scoreOf(best),0)}/100</b></div><div><span>Raw Speed</span><b>${n(best?.torrent_score?.components?.raw_speed,0)}/100</b></div><div><span>Torrent Score</span><b>${n(best?.torrent_score?.score,0)}/100</b></div></div><div class="peer-config-tabs">${items.map((r,i)=>`<button type="button" class="peer-config-tab ${i===0?'active best':''}" data-id="${Number(r.id)}">${esc(short(r.name))}</button>`).join('')}</div><div class="peer-map-wrap"><div class="peer-europe-card" id="peerMapCanvas"></div>${matrix(items)}</div><div id="peerRegionCards"></div><div class="peer-source-note">Peer Connectivity ist ein Proxy aus kurzen iPerf3- und ICMP-Messungen zu mehreren europäischen Rechenzentrumsnetzen. Es misst nicht direkt private Tracker-Peers.</div>`;
    const canvas=host.querySelector('#peerMapCanvas'),details=host.querySelector('#peerRegionCards');
    const draw=run=>{active=run;canvas.innerHTML=mapSvg(run)+`<div class="peer-map-legend"><span><i style="background:#45d483"></i>stark</span><span><i style="background:#f2c94c"></i>mittel</span><span><i style="background:#ff6b6b"></i>schwach</span></div>`;details.innerHTML=regionCards(run)};
    draw(active);
    host.querySelectorAll('.peer-config-tab').forEach(btn=>btn.addEventListener('click',()=>{host.querySelectorAll('.peer-config-tab').forEach(x=>x.classList.remove('active'));btn.classList.add('active');const run=items.find(r=>Number(r.id)===Number(btn.dataset.id));if(run)draw(run)}));
  }

  async function render(){
    const panel=document.querySelector('#comparisonPanel'); if(!panel||panel.hidden)return;
    const ids=new Set(selectedIds());
    const res=await fetch('/api/results'); const all=await res.json();
    const selected=all.filter(r=>ids.has(Number(r.id)));
    const withPeer=selected.filter(r=>r?.peer_connectivity?.regions&&Object.keys(r.peer_connectivity.regions).length);
    panel.querySelector('#peerConnectivityMaps')?.remove();
    const section=document.createElement('section'); section.id='peerConnectivityMaps'; section.className='peer-map-section';
    if(!withPeer.length){section.innerHTML='<div class="peer-map-empty"><b>EU Peer Connectivity noch nicht gemessen.</b><br>Diese ausgewählten Ergebnisse stammen aus einem älteren Benchmark. Starte die Configs nach dem Update neu.</div>';panel.querySelector('.compare-footnote')?.before(section);return}
    const groups={};withPeer.forEach(r=>(groups[r.provider||'VPN']??=[]).push(r));const providers=Object.keys(groups).sort();
    section.innerHTML=`<div class="peer-map-head"><div><div class="compare-kicker">Seedbox / Peer Connectivity</div><h3>Europa-Peering nach Provider und Config</h3><p>Welche VPN-Exit-Config erreicht typische europäische Rechenzentrums-/Seedbox-Regionen am besten?</p></div></div><div class="peer-provider-tabs">${providers.map((p,i)=>`<button type="button" class="peer-provider-tab ${i===0?'active':''}" data-provider="${esc(p)}">${esc(p)}</button>`).join('')}</div><div id="peerProviderView"></div>`;
    panel.querySelector('.compare-footnote')?.before(section);
    const host=section.querySelector('#peerProviderView');
    const show=p=>providerView(p,groups[p],host);show(providers[0]);
    section.querySelectorAll('.peer-provider-tab').forEach(btn=>btn.addEventListener('click',()=>{section.querySelectorAll('.peer-provider-tab').forEach(x=>x.classList.remove('active'));btn.classList.add('active');show(btn.dataset.provider)}));
  }

  let tries=0;const timer=setInterval(()=>{tries++;const btn=document.querySelector('#openCompare');if(btn&&!btn.dataset.peerMapBound){btn.dataset.peerMapBound='1';btn.addEventListener('click',()=>setTimeout(()=>render().catch(console.warn),80));clearInterval(timer)}else if(tries>100)clearInterval(timer)},100);
})();
