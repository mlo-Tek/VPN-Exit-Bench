(()=>{
  if(window.__vpnBenchConfigManagerLoaded)return;
  window.__vpnBenchConfigManagerLoaded=true;

  const selectedConfigs=new Set();
  const portKey=rel=>'vpnbench-port:'+rel;
  const h=v=>String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
  const savedPort=rel=>Number(localStorage.getItem(portKey(rel))||0);
  const isProton=c=>String(c?.provider||'').toLowerCase()==='proton';
  const typeLabel=type=>String(type||'').toLowerCase()==='openvpn'?'OpenVPN':'WireGuard';

  function getConfigShell(){
    const list=document.querySelector('#configs');
    const card=list?.closest('.card');
    if(!list||!card)return null;

    const head=[...card.children].find(el=>el.classList?.contains('row'));
    if(head){
      head.classList.add('config-section-head');
      [...head.querySelectorAll('.muted.small')].forEach(el=>el.remove());
    }

    let toolbar=card.querySelector('#configToolbar');
    if(!toolbar){
      toolbar=document.createElement('div');
      toolbar.id='configToolbar';
      toolbar.className='config-toolbar';
      toolbar.innerHTML=`
        <div class="config-toolbar-summary">
          <strong id="configCount">0 Configs</strong>
          <span class="muted small" id="configSelectedCount">0 ausgewählt</span>
        </div>
        <div class="config-toolbar-actions">
          <button type="button" class="secondary" id="selectAllConfigs">Alle auswählen</button>
          <button type="button" class="secondary" id="clearConfigSelection">Alle abwählen</button>
          <button type="button" class="danger" id="deleteSelectedConfigs" disabled>Ausgewählte löschen</button>
        </div>`;
      card.insertBefore(toolbar,list);

      toolbar.querySelector('#selectAllConfigs').addEventListener('click',()=>{
        list.querySelectorAll('.config-select-input').forEach(input=>{
          selectedConfigs.add(input.value);
          input.checked=true;
          input.closest('.config-item')?.classList.add('selected');
        });
        updateConfigSelectionUi();
      });
      toolbar.querySelector('#clearConfigSelection').addEventListener('click',()=>{
        selectedConfigs.clear();
        list.querySelectorAll('.config-select-input').forEach(input=>{
          input.checked=false;
          input.closest('.config-item')?.classList.remove('selected');
        });
        updateConfigSelectionUi();
      });
      toolbar.querySelector('#deleteSelectedConfigs').addEventListener('click',deleteSelectedConfigs);
    }
    return {list,card,toolbar};
  }

  function updateConfigSelectionUi(){
    const shell=getConfigShell();
    if(!shell)return;
    const all=[...shell.list.querySelectorAll('.config-select-input')];
    const selected=all.filter(input=>selectedConfigs.has(input.value)).length;
    const count=document.querySelector('#configSelectedCount');
    const del=document.querySelector('#deleteSelectedConfigs');
    const allBtn=document.querySelector('#selectAllConfigs');
    const clearBtn=document.querySelector('#clearConfigSelection');
    if(count)count.textContent=`${selected} ausgewählt`;
    if(del)del.disabled=selected===0;
    if(allBtn)allBtn.disabled=!all.length||selected===all.length;
    if(clearBtn)clearBtn.disabled=selected===0;
  }

  async function startManagedConfig(c,portInput,button){
    if(typeof window.startOne==='function'){
      return window.startOne(c,portInput||{value:0},button);
    }

    const old=button.textContent;
    button.disabled=true;
    button.textContent='Läuft…';
    try{
      const response=await fetch('/api/test',{
        method:'POST',
        headers:{'content-type':'application/json'},
        body:JSON.stringify({rel:c.rel,port:Number(portInput?.value||0)})
      });
      const data=await response.json();
      if(!response.ok)throw new Error(data.error||'Start fehlgeschlagen');
      if(typeof window.followJob==='function')await window.followJob(data.job_id);
    }catch(error){
      alert(error.message||String(error));
    }finally{
      button.disabled=false;
      button.textContent=old;
    }
  }

  function renderConfig(c){
    const row=document.createElement('div');
    row.className='config-item';
    row.dataset.rel=c.rel;
    const selected=selectedConfigs.has(c.rel);
    if(selected)row.classList.add('selected');
    const proton=isProton(c);
    const port=savedPort(c.rel);

    row.innerHTML=`
      <label class="config-select" title="Für Aktionen auswählen">
        <input class="config-select-input" type="checkbox" value="${h(c.rel)}" ${selected?'checked':''}>
        <span></span>
      </label>
      <div class="config-identity">
        <div class="config-name-row">
          <span class="provider-pill">${h(c.provider)}</span>
          <strong class="config-name" title="${h(c.name)}">${h(c.name)}</strong>
        </div>
        <div class="config-subline"><span>${h(typeLabel(c.type))}</span><span class="config-rel">${h(c.rel)}</span></div>
      </div>
      <div class="config-port-slot">
        ${proton
          ? '<div class="config-auto-port"><span class="config-auto-dot"></span><div><strong>Auto</strong><small>NAT-PMP</small></div></div>'
          : `<label class="config-port-field"><span>qBit-Port</span><input type="number" min="1" max="65535" data-port-rel="${h(c.rel)}" value="${port||''}" placeholder="optional"></label>`}
      </div>
      <button type="button" class="benchAction config-test-btn">Testen</button>`;

    const select=row.querySelector('.config-select-input');
    select.addEventListener('change',()=>{
      if(select.checked){
        selectedConfigs.add(c.rel);
        row.classList.add('selected');
      }else{
        selectedConfigs.delete(c.rel);
        row.classList.remove('selected');
      }
      updateConfigSelectionUi();
    });

    const input=row.querySelector('[data-port-rel]');
    if(input){
      input.addEventListener('change',()=>{
        const value=Number(input.value||0);
        if(value>0)localStorage.setItem(portKey(c.rel),String(value));
        else localStorage.removeItem(portKey(c.rel));
      });
    }

    const test=row.querySelector('.config-test-btn');
    test.addEventListener('click',()=>startManagedConfig(c,input||{value:0},test));
    return row;
  }

  async function loadConfigsManaged(){
    const shell=getConfigShell();
    if(!shell)return;
    const response=await fetch('/api/configs');
    const configs=await response.json();
    const validRels=new Set(configs.map(c=>c.rel));
    [...selectedConfigs].forEach(rel=>{if(!validRels.has(rel))selectedConfigs.delete(rel)});

    const count=document.querySelector('#configCount');
    if(count)count.textContent=`${configs.length} Config${configs.length===1?'':'s'}`;
    shell.list.className='config-list';
    shell.list.removeAttribute('style');
    shell.list.innerHTML='';

    if(!configs.length){
      shell.list.innerHTML='<div class="config-empty">Noch keine Configs vorhanden.</div>';
      updateConfigSelectionUi();
      return;
    }

    configs.forEach(c=>shell.list.appendChild(renderConfig(c)));
    updateConfigSelectionUi();
  }

  async function deleteSelectedConfigs(){
    const rels=[...selectedConfigs];
    if(!rels.length)return;
    if(!confirm(`${rels.length} ausgewählte Config${rels.length===1?'':'s'} wirklich löschen?`))return;

    const button=document.querySelector('#deleteSelectedConfigs');
    const old=button.textContent;
    button.disabled=true;
    button.textContent='Lösche…';
    try{
      const response=await fetch('/api/configs',{
        method:'DELETE',
        headers:{'content-type':'application/json'},
        body:JSON.stringify({rels})
      });
      const result=await response.json();
      if(!response.ok&&!result.deleted?.length)throw new Error(result.error||'Löschen fehlgeschlagen');
      (result.deleted||[]).forEach(item=>{
        selectedConfigs.delete(item.rel);
        localStorage.removeItem(portKey(item.rel));
      });
      await loadConfigsManaged();
      if(result.skipped?.length){
        alert(result.skipped.map(x=>`${x.rel}: ${x.error}`).join('\n'));
      }
    }catch(error){
      alert(error.message||String(error));
    }finally{
      button.textContent=old;
      updateConfigSelectionUi();
    }
  }

  function enhanceResultSelection(){
    const toolbar=document.querySelector('#compareToolbar');
    if(!toolbar)return;
    const actions=toolbar.querySelector('.compare-toolbar-actions');
    if(!actions)return;

    const clear=toolbar.querySelector('#clearCompareSelection');
    if(clear)clear.textContent='Alle abwählen';
    const latest=toolbar.querySelector('#selectLatestCompare');
    if(latest)latest.textContent='Letzten Run je Config';

    if(!toolbar.querySelector('#selectAllCompare')){
      const button=document.createElement('button');
      button.type='button';
      button.className='secondary';
      button.id='selectAllCompare';
      button.textContent='Alle auswählen';
      if(latest)actions.insertBefore(button,latest);
      else actions.insertBefore(button,actions.firstChild);
      button.addEventListener('click',()=>{
        document.querySelectorAll('.compare-check').forEach(input=>{
          if(!input.checked&&!input.disabled){
            input.checked=true;
            input.dispatchEvent(new Event('change',{bubbles:true}));
          }
        });
      });
    }
  }

  const observer=new MutationObserver(()=>enhanceResultSelection());
  observer.observe(document.body,{childList:true,subtree:true});

  window.loadConfigs=loadConfigsManaged;
  loadConfigsManaged().catch(error=>console.warn('Config manager load failed',error));
  enhanceResultSelection();
})();
