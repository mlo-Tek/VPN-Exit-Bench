(()=>{
  if(window.__vpnBenchSelectionBatchLoaded)return;
  window.__vpnBenchSelectionBatchLoaded=true;

  const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  let running=false;
  let scrollSnapshot=null;

  function selectedInputs(){
    return [...document.querySelectorAll('#configs .config-select-input:checked')];
  }

  function selectedCount(){
    return selectedInputs().length;
  }

  function toolbarActions(){
    return document.querySelector('#configToolbar .config-toolbar-actions');
  }

  function ensureBatchButton(){
    const actions=toolbarActions();
    if(!actions)return false;
    let button=actions.querySelector('#testSelectedConfigs');
    if(!button){
      button=document.createElement('button');
      button.type='button';
      button.id='testSelectedConfigs';
      button.className='benchAction config-batch-test';
      button.textContent='Ausgewählte testen';
      const clear=actions.querySelector('#clearConfigSelection');
      actions.insertBefore(button,clear||actions.firstChild);
      button.addEventListener('click',runSelectedConfigs);
    }
    updateBatchButton();
    return true;
  }

  function updateBatchButton(label){
    const button=document.querySelector('#testSelectedConfigs');
    if(!button)return;
    const count=selectedCount();
    button.disabled=running||count===0;
    if(label){
      button.textContent=label;
    }else if(count>0){
      button.textContent=`${count} ausgewählte testen`;
    }else{
      button.textContent='Ausgewählte testen';
    }
  }

  async function waitForJob(jobId){
    while(true){
      const response=await fetch(`/api/jobs/${encodeURIComponent(jobId)}`);
      const job=await response.json();
      if(!response.ok)throw new Error(job.error||'Benchmark-Status konnte nicht geladen werden');
      if(['done','error','cancelled'].includes(job.status))return job;
      await sleep(750);
    }
  }

  async function runOne(rel,port){
    const response=await fetch('/api/test',{
      method:'POST',
      headers:{'content-type':'application/json'},
      body:JSON.stringify({rel,port})
    });
    const data=await response.json();
    if(!response.ok)throw new Error(data.error||`Start fehlgeschlagen: ${rel}`);
    if(typeof window.followJob==='function'){
      await window.followJob(data.job_id);
    }else{
      await waitForJob(data.job_id);
    }
  }

  async function runSelectedConfigs(){
    if(running)return;
    const inputs=selectedInputs();
    if(!inputs.length)return;

    const items=inputs.map(input=>{
      const row=input.closest('.config-item');
      const portInput=row?.querySelector('[data-port-rel]');
      return {rel:input.value,port:Number(portInput?.value||0)};
    });

    running=true;
    updateBatchButton(`Starte 1/${items.length}…`);
    document.querySelectorAll('#configs .config-test-btn').forEach(btn=>btn.disabled=true);

    const failures=[];
    try{
      for(let index=0;index<items.length;index+=1){
        const item=items[index];
        updateBatchButton(`Teste ${index+1}/${items.length}…`);
        try{
          await runOne(item.rel,item.port);
        }catch(error){
          failures.push(`${item.rel}: ${error.message||String(error)}`);
        }
      }
    }finally{
      running=false;
      document.querySelectorAll('#configs .config-test-btn').forEach(btn=>btn.disabled=false);
      updateBatchButton();
    }

    if(failures.length){
      alert(`Einige ausgewählte Tests konnten nicht abgeschlossen werden:\n\n${failures.join('\n')}`);
    }
  }

  function rememberSelectionScroll(event){
    const control=event.target.closest?.('.config-select,.compare-check-wrap');
    if(!control)return;
    const configs=document.querySelector('#configs');
    const resultWrap=document.querySelector('.result-table-wrap');
    scrollSnapshot={
      x:window.scrollX,
      y:window.scrollY,
      configsTop:configs?.scrollTop??null,
      resultsTop:resultWrap?.scrollTop??null,
      resultsLeft:resultWrap?.scrollLeft??null
    };
  }

  function restoreSelectionScroll(event){
    if(!event.target.matches?.('.config-select-input,.compare-check'))return;
    const snapshot=scrollSnapshot;
    scrollSnapshot=null;
    if(!snapshot)return;
    requestAnimationFrame(()=>{
      const configs=document.querySelector('#configs');
      const resultWrap=document.querySelector('.result-table-wrap');
      if(configs&&snapshot.configsTop!=null)configs.scrollTop=snapshot.configsTop;
      if(resultWrap&&snapshot.resultsTop!=null){
        resultWrap.scrollTop=snapshot.resultsTop;
        resultWrap.scrollLeft=snapshot.resultsLeft||0;
      }
      window.scrollTo(snapshot.x,snapshot.y);
    });
  }

  document.addEventListener('pointerdown',rememberSelectionScroll,true);
  document.addEventListener('change',event=>{
    if(event.target.matches?.('.config-select-input'))updateBatchButton();
    restoreSelectionScroll(event);
  },true);
  document.addEventListener('click',event=>{
    if(event.target.closest?.('#selectAllConfigs,#clearConfigSelection')){
      setTimeout(updateBatchButton,0);
    }
  },true);

  const timer=setInterval(()=>{
    if(ensureBatchButton())clearInterval(timer);
  },100);

  const configs=document.querySelector('#configs');
  if(configs){
    new MutationObserver(()=>{
      ensureBatchButton();
      updateBatchButton();
    }).observe(configs,{childList:true});
  }
})();
