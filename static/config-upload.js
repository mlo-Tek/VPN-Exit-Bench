(()=>{
  if(!document.querySelector('link[data-vpnbench-compare]')){
    const link=document.createElement('link');
    link.rel='stylesheet';
    link.href='/static/result-compare.css';
    link.dataset.vpnbenchCompare='1';
    document.head.appendChild(link);
  }
  if(!document.querySelector('script[data-vpnbench-compare]')){
    const script=document.createElement('script');
    script.src='/static/result-compare.js';
    script.dataset.vpnbenchCompare='1';
    document.body.appendChild(script);
  }
  if(!document.querySelector('script[data-vpnbench-compare-sort]')){
    const script=document.createElement('script');
    script.src='/static/compare-sort.js';
    script.dataset.vpnbenchCompareSort='1';
    document.body.appendChild(script);
  }
  if(!document.querySelector('link[data-vpnbench-peer-map]')){
    const link=document.createElement('link');
    link.rel='stylesheet';
    link.href='/static/peer-map.css';
    link.dataset.vpnbenchPeerMap='1';
    document.head.appendChild(link);
  }
  if(!document.querySelector('script[data-vpnbench-peer-map]')){
    const script=document.createElement('script');
    script.src='/static/peer-map.js';
    script.dataset.vpnbenchPeerMap='1';
    document.body.appendChild(script);
  }

  const filesInput=document.querySelector('#configFiles');
  const dropzone=document.querySelector('#dropzone');
  const uploadBtn=document.querySelector('#uploadBtn');
  const selectedEl=document.querySelector('#selectedFiles');
  const statusEl=document.querySelector('#uploadStatus');
  if(!filesInput||!dropzone||!uploadBtn)return;

  let selected=[];
  const h=v=>String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot',"'":'&#39;'}[m]));
  const valid=name=>/\.(conf|ovpn)$/i.test(String(name||''));

  function setFiles(files){
    const all=[...(files||[])];
    selected=all.filter(f=>valid(f.name));
    const ignored=all.length-selected.length;
    if(!selected.length){
      selectedEl.textContent=ignored?'Keine gültigen .conf/.ovpn-Dateien ausgewählt.':'Keine Dateien ausgewählt.';
    }else{
      selectedEl.innerHTML=`<span class="upload-count">${selected.length} ausgewählt</span>${selected.map(f=>`<span class="upload-file-chip">${h(f.name)}</span>`).join('')}${ignored?`<span class="upload-file-chip muted">${ignored} ignoriert</span>`:''}`;
    }
    uploadBtn.disabled=!selected.length;
  }

  function status(message,error=false){
    statusEl.className='uploadstatus on'+(error?' error':'');
    statusEl.innerHTML=message;
  }

  async function upload(){
    if(!selected.length)return;
    uploadBtn.disabled=true;
    uploadBtn.textContent='Lade hoch…';
    statusEl.className='uploadstatus';
    const data=new FormData();
    data.append('overwrite','1');
    selected.forEach(file=>data.append('files',file,file.name));
    try{
      const response=await fetch('/api/configs/upload',{method:'POST',body:data});
      const result=await response.json();
      const uploaded=result.uploaded||[];
      const skipped=result.skipped||[];
      const lines=[];
      if(uploaded.length){
        const replaced=uploaded.filter(x=>x.overwritten).length;
        lines.push(`<b>${uploaded.length} Config${uploaded.length===1?'':'s'} gespeichert.</b>${replaced?` ${replaced} ersetzt.`:''}`);
      }
      if(skipped.length){
        lines.push(skipped.map(x=>`${h(x.name)}: ${h(x.error)}`).join('<br>'));
      }
      status(lines.join('<br>')||h(result.error||'Upload fehlgeschlagen'),!response.ok&&!uploaded.length);
      if(uploaded.length){
        selected=[];
        filesInput.value='';
        selectedEl.textContent='Keine Dateien ausgewählt.';
        if(typeof window.loadConfigs==='function')await window.loadConfigs();
      }
    }catch(error){
      status(h(error.message||String(error)),true);
    }finally{
      uploadBtn.textContent='Hochladen';
      uploadBtn.disabled=!selected.length;
    }
  }

  filesInput.addEventListener('change',()=>setFiles(filesInput.files));
  ['dragenter','dragover'].forEach(type=>dropzone.addEventListener(type,event=>{event.preventDefault();dropzone.classList.add('drag')}));
  ['dragleave','drop'].forEach(type=>dropzone.addEventListener(type,event=>{event.preventDefault();dropzone.classList.remove('drag')}));
  dropzone.addEventListener('drop',event=>setFiles(event.dataTransfer.files));
  uploadBtn.addEventListener('click',upload);
})();
