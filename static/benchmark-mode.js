(()=>{
  if(window.__vpnBenchBenchmarkModeLoaded)return;
  window.__vpnBenchBenchmarkModeLoaded=true;

  const STORAGE_KEY='vpnbench-benchmark-mode';
  const VALID=new Set(['smart','deep']);
  const saved=String(localStorage.getItem(STORAGE_KEY)||'smart').toLowerCase();
  let mode=VALID.has(saved)?saved:'smart';

  function modeLabel(value){
    return value==='deep'?'Deep':'Smart';
  }

  function installControl(){
    const actions=document.querySelector('.top .actions');
    if(!actions||document.querySelector('#benchmarkMode'))return false;

    const wrap=document.createElement('label');
    wrap.className='benchmark-mode-control';
    wrap.innerHTML=`
      <span class="benchmark-mode-title">Testmodus</span>
      <select id="benchmarkMode" aria-label="Benchmark-Testmodus">
        <option value="smart">Smart · empfohlen</option>
        <option value="deep">Deep · maximale Messdauer</option>
      </select>
      <span class="benchmark-mode-hint" id="benchmarkModeHint"></span>`;
    actions.insertBefore(wrap,actions.firstChild);

    const select=wrap.querySelector('#benchmarkMode');
    select.value=mode;
    select.addEventListener('change',()=>{
      mode=VALID.has(select.value)?select.value:'smart';
      localStorage.setItem(STORAGE_KEY,mode);
      updateLabels();
    });
    updateLabels();
    return true;
  }

  function updateLabels(){
    const hint=document.querySelector('#benchmarkModeHint');
    if(hint){
      hint.textContent=mode==='smart'
        ? '≈ 45–60 s je Config · alle 7 EU-Regionen'
        : '≈ 2 min je Config · FRA + AMS vollständig';
    }
    const all=document.querySelector('#all');
    if(all&&!all.disabled)all.textContent=`Alle nacheinander testen · ${modeLabel(mode)}`;
    const baseline=document.querySelector('#baselineBtn');
    if(baseline&&!baseline.disabled)baseline.textContent=`Direktleitung als Baseline · ${modeLabel(mode)}`;
  }

  const securedFetch=window.fetch.bind(window);
  window.fetch=function(input,init={}){
    try{
      const url=new URL(input instanceof Request?input.url:String(input),window.location.href);
      const method=String(init.method||(input instanceof Request?input.method:'GET')||'GET').toUpperCase();
      const isBenchmarkPost=method==='POST'&&url.origin===window.location.origin&&[
        '/api/test','/api/test-all','/api/baseline'
      ].includes(url.pathname);

      if(!isBenchmarkPost)return securedFetch(input,init);

      let payload={};
      if(init.body){
        try{payload=JSON.parse(String(init.body))||{};}catch(_){return securedFetch(input,init);}
      }
      payload.mode=mode;
      const headers=new Headers(init.headers||{});
      headers.set('content-type','application/json');
      return securedFetch(input,{...init,headers,body:JSON.stringify(payload)});
    }catch(_){
      return securedFetch(input,init);
    }
  };

  window.vpnBenchBenchmarkMode=()=>mode;

  let attempts=0;
  const timer=setInterval(()=>{
    attempts+=1;
    if(installControl()||attempts>=40)clearInterval(timer);
  },100);
})();
