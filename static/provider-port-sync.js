(()=>{
  if(window.__vpnBenchProviderPortSyncLoaded)return;
  window.__vpnBenchProviderPortSyncLoaded=true;

  const providerKey=provider=>`vpnbench-provider-port:${String(provider||'').trim().toLowerCase()}`;
  const configKey=rel=>`vpnbench-port:${rel}`;
  const validPort=value=>{
    const port=Number(value||0);
    return Number.isInteger(port)&&port>=1&&port<=65535?port:0;
  };

  function rowProvider(row){
    return row?.querySelector('.provider-pill')?.textContent?.trim()||'';
  }

  function rowRel(row){
    return row?.dataset?.rel||row?.querySelector('[data-port-rel]')?.dataset?.portRel||'';
  }

  function providerRows(provider){
    const wanted=String(provider||'').trim().toLowerCase();
    return [...document.querySelectorAll('#configs .config-item')].filter(
      row=>rowProvider(row).toLowerCase()===wanted
    );
  }

  function setRowPort(row,port){
    const input=row?.querySelector('[data-port-rel]');
    const rel=rowRel(row);
    if(!input||!rel||!port)return;
    input.value=String(port);
    localStorage.setItem(configKey(rel),String(port));
  }

  function bootstrapProviderPorts(){
    const rows=[...document.querySelectorAll('#configs .config-item')];
    if(!rows.length)return;

    const groups=new Map();
    for(const row of rows){
      const provider=rowProvider(row);
      const input=row.querySelector('[data-port-rel]');
      if(!provider||!input)continue; // Proton NAT-PMP has no manual input.
      const key=provider.toLowerCase();
      if(!groups.has(key))groups.set(key,{provider,rows:[]});
      groups.get(key).rows.push(row);
    }

    for(const {provider,rows:providerConfigRows} of groups.values()){
      let shared=validPort(localStorage.getItem(providerKey(provider)));
      if(!shared){
        const populated=providerConfigRows
          .map(row=>validPort(row.querySelector('[data-port-rel]')?.value))
          .find(Boolean);
        if(populated){
          shared=populated;
          localStorage.setItem(providerKey(provider),String(shared));
        }
      }
      if(!shared)continue;

      // Only fill empty rows. Existing per-config overrides remain untouched.
      for(const row of providerConfigRows){
        const input=row.querySelector('[data-port-rel]');
        if(input&&!validPort(input.value))setRowPort(row,shared);
      }
    }
  }

  function saveAndPropagate(input){
    const row=input.closest('.config-item');
    const provider=rowProvider(row);
    const rel=rowRel(row);
    const port=validPort(input.value);
    if(!row||!provider||!rel)return;

    if(!port){
      localStorage.removeItem(configKey(rel));
      return;
    }

    const key=providerKey(provider);
    const previous=validPort(localStorage.getItem(key));
    localStorage.setItem(key,String(port));
    localStorage.setItem(configKey(rel),String(port));

    // A forwarded port is normally account/provider-wide. Apply a changed
    // provider default to empty rows and rows that still used the old default,
    // while preserving deliberate per-config overrides.
    for(const otherRow of providerRows(provider)){
      if(otherRow===row)continue;
      const other=otherRow.querySelector('[data-port-rel]');
      if(!other)continue;
      const current=validPort(other.value);
      if(!current||(previous&&current===previous))setRowPort(otherRow,port);
    }
  }

  document.addEventListener('input',event=>{
    if(event.target.matches?.('#configs [data-port-rel]'))saveAndPropagate(event.target);
  },true);
  document.addEventListener('change',event=>{
    if(event.target.matches?.('#configs [data-port-rel]'))saveAndPropagate(event.target);
  },true);

  const configs=document.querySelector('#configs');
  if(configs){
    new MutationObserver(()=>queueMicrotask(bootstrapProviderPorts)).observe(configs,{childList:true,subtree:false});
  }

  let attempts=0;
  const timer=setInterval(()=>{
    attempts+=1;
    bootstrapProviderPorts();
    if(document.querySelector('#configs .config-item')||attempts>=50)clearInterval(timer);
  },100);
})();
