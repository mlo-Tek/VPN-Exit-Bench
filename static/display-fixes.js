(()=>{
  if(window.__vpnBenchDisplayFixesLoaded)return;
  window.__vpnBenchDisplayFixesLoaded=true;

  const REGION_ORDER=['NL','DE','CH','DK','SE','PL','RO'];
  const short=name=>String(name||'').replace(/\.(conf|ovpn)$/i,'');
  let cachedResults=[];
  let cacheAt=0;
  let inFlight=null;
  let scheduled=false;

  function exitLabel(r){
    const x=r?.exit||{};
    const place=[x.city,x.country].filter(Boolean).join(' / ');
    return place||short(r?.name)||'Unbekannter Exit';
  }

  function resultLabel(r){
    return `${r?.provider||'VPN'} · ${exitLabel(r)}`;
  }

  function finiteScore(value){
    if(value==null||value==='')return null;
    const n=Number(value);
    return Number.isFinite(n)?n:null;
  }

  async function results(force=false){
    const now=Date.now();
    if(!force&&cachedResults.length&&now-cacheAt<750)return cachedResults;
    if(inFlight)return inFlight;
    inFlight=fetch('/api/results',{cache:'no-store'})
      .then(r=>r.ok?r.json():[])
      .then(data=>{
        cachedResults=Array.isArray(data)?data:[];
        cacheAt=Date.now();
        return cachedResults;
      })
      .catch(()=>cachedResults)
      .finally(()=>{inFlight=null});
    return inFlight;
  }

  function patchProviderChips(root=document){
    root.querySelectorAll('.provider-chip').forEach(chip=>{
      if(chip.textContent.trim().toLowerCase()==='cryptostorm'){
        chip.classList.add('cryptostorm');
      }
    });
  }

  function patchFailedScoreRows(root,items){
    const failedLabels=new Set(items.filter(r=>r?.ok===false).map(resultLabel));
    root.querySelectorAll('.compare-score-card .compare-bar-row').forEach(row=>{
      const label=row.querySelector('.compare-bar-label')?.textContent?.trim();
      if(!failedLabels.has(label))return;

      const fill=row.querySelector('.compare-bar-fill');
      if(fill)fill.remove();
      const value=row.querySelector('.compare-bar-value');
      if(value&&value.textContent!=='Fehler')value.textContent='Fehler';
      row.classList.add('compare-bar-row-failed');
    });
  }

  function providerForMatrix(section){
    const active=section.querySelector('.peer-provider-tab.active');
    return active?.dataset?.provider||active?.textContent?.trim()||'';
  }

  function runForMatrixRow(items,provider,configName){
    return items.find(r=>String(r?.provider||'')===provider&&short(r?.name)===configName)||null;
  }

  function markMissingScore(cell){
    const score=cell?.querySelector('.peer-score-cell');
    if(!score)return;
    if(score.textContent!=='–')score.textContent='–';
    score.classList.remove('great','good','mid','bad','best');
    score.classList.add('unknown');
    score.title='Keine gültige Messung';
  }

  function patchPeerMatrix(root,items){
    root.querySelectorAll('.peer-map-section').forEach(section=>{
      const table=section.querySelector('.peer-matrix');
      if(!table)return;
      const provider=providerForMatrix(section);
      const headers=[...table.querySelectorAll('thead th')].map(th=>th.textContent.trim());

      table.querySelectorAll('tbody tr').forEach(row=>{
        const cells=[...row.querySelectorAll('td')];
        const configName=cells[0]?.textContent?.trim();
        const run=runForMatrixRow(items,provider,configName);
        if(!run)return;

        for(let i=1;i<cells.length;i++){
          const code=headers[i];
          const value=code==='EU'
            ? run?.peer_connectivity?.score
            : REGION_ORDER.includes(code)
              ? run?.peer_connectivity?.regions?.[code]?.score
              : null;
          if(finiteScore(value)===null)markMissingScore(cells[i]);
        }
      });
    });
  }

  async function patch(force=false){
    const items=await results(force);
    patchProviderChips(document);
    patchFailedScoreRows(document,items);
    patchPeerMatrix(document,items);
  }

  function schedule(force=false){
    if(force)cacheAt=0;
    if(scheduled)return;
    scheduled=true;
    requestAnimationFrame(()=>{
      scheduled=false;
      patch(force).catch(()=>{});
    });
  }

  document.addEventListener('click',event=>{
    const target=event.target.closest?.('#openCompare,#refreshResultsBtn,.peer-provider-tab,.peer-config-tab');
    if(target)setTimeout(()=>schedule(true),120);
  });

  const observer=new MutationObserver(()=>schedule(false));
  observer.observe(document.body,{childList:true,subtree:true});
  schedule(true);
})();
