(()=>{
  const filesInput=document.querySelector('#configFiles');
  const dropzone=document.querySelector('#dropzone');
  const uploadBtn=document.querySelector('#uploadBtn');
  const selectedEl=document.querySelector('#selectedFiles');
  const statusEl=document.querySelector('#uploadStatus');
  const providerEl=document.querySelector('#providerOverride');
  const providerList=document.querySelector('#providerList');
  const overwriteEl=document.querySelector('#overwriteConfigs');
  if(!filesInput||!dropzone||!uploadBtn)return;

  let selected=[];
  const h=v=>String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
  const valid=name=>/\.(conf|ovpn)$/i.test(String(name||''));

  function setFiles(files){
    const all=[...(files||[])];
    selected=all.filter(f=>valid(f.name));
    const ignored=all.length-selected.length;
    if(!selected.length)selectedEl.textContent=ignored?'Keine gültigen .conf/.ovpn-Dateien ausgewählt.':'Noch keine Dateien ausgewählt.';
    else selectedEl.textContent=`${selected.length} Datei${selected.length===1?'':'en'}: ${selected.map(f=>f.name).join(' · ')}${ignored?` · ${ignored} andere Datei(en) ignoriert`:''}`;
    uploadBtn.disabled=!selected.length;
  }

  function status(message,error=false){
    statusEl.className='uploadstatus on'+(error?' error':'');
    statusEl.innerHTML=message;
  }

  async function loadProviders(){
    try{
      const configs=await(await fetch('/api/configs')).json();
      const names=new Set(['Proton','OVPN','Mullvad','AirVPN','IVPN','Windscribe','Surfshark','NordVPN','PIA']);
      configs.forEach(c=>{if(c.provider)names.add(c.provider)});
      providerList.innerHTML=[...names].sort((a,b)=>a.localeCompare(b)).map(v=>`<option value="${h(v)}"></option>`).join('');
    }catch(_e){}
  }

  async function upload(){
    if(!selected.length)return;
    uploadBtn.disabled=true;uploadBtn.textContent='Lade hoch…';
    const data=new FormData();
    const provider=providerEl.value.trim();
    if(provider)data.append('provider',provider);
    if(overwriteEl.checked)data.append('overwrite','1');
    selected.forEach(file=>data.append('files',file,file.name));
    try{
      const response=await fetch('/api/configs/upload',{method:'POST',body:data});
      const result=await response.json();
      const uploaded=result.uploaded||[],skipped=result.skipped||[];
      const lines=[];
      if(uploaded.length)lines.push(`<b>${uploaded.length} hochgeladen:</b> ${uploaded.map(x=>`${h(x.provider)}/${h(x.name)}${x.overwritten?' (ersetzt)':''}`).join(' · ')}`);
      if(skipped.length)lines.push(`<b>${skipped.length} übersprungen:</b> ${skipped.map(x=>`${h(x.name)} – ${h(x.error)}`).join(' · ')}`);
      status(lines.join('<br>')||h(result.error||'Upload fehlgeschlagen'),!response.ok&&!uploaded.length);
      if(uploaded.length){
        selected=[];filesInput.value='';selectedEl.textContent='Noch keine Dateien ausgewählt.';
        if(typeof loadConfigs==='function')await loadConfigs();
        await loadProviders();
      }
    }catch(error){status(h(error.message||String(error)),true)}
    finally{uploadBtn.textContent='Ausgewählte Configs hochladen';uploadBtn.disabled=!selected.length}
  }

  filesInput.addEventListener('change',()=>setFiles(filesInput.files));
  ['dragenter','dragover'].forEach(type=>dropzone.addEventListener(type,event=>{event.preventDefault();dropzone.classList.add('drag')}));
  ['dragleave','drop'].forEach(type=>dropzone.addEventListener(type,event=>{event.preventDefault();dropzone.classList.remove('drag')}));
  dropzone.addEventListener('drop',event=>setFiles(event.dataTransfer.files));
  uploadBtn.addEventListener('click',upload);
  loadProviders();
})();
