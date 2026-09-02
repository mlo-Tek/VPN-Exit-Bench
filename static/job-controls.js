(()=>{
  if(window.__vpnBenchJobControlsLoaded)return;
  window.__vpnBenchJobControlsLoaded=true;

  let currentJob=null;
  let followingJobId=null;
  let cancelledReloadScheduled=false;

  function installControls(){
    const progress=document.querySelector('#progress');
    const progressBar=progress?.querySelector('.progressbar');
    if(!progress||!progressBar||document.querySelector('#jobControlBar'))return false;

    const bar=document.createElement('div');
    bar.id='jobControlBar';
    bar.className='job-control-bar';
    bar.hidden=true;
    bar.innerHTML=`
      <div class="job-control-copy">
        <strong id="jobControlState">Run-Steuerung</strong>
        <span id="jobControlHint">Pause wirkt nach der aktuell laufenden Config.</span>
      </div>
      <div class="job-control-actions">
        <button type="button" class="secondary" id="jobPauseBtn">Pause</button>
        <button type="button" class="resume" id="jobResumeBtn" hidden>Fortsetzen</button>
        <button type="button" class="cancel" id="jobCancelBtn">Abbrechen</button>
      </div>`;
    progressBar.insertAdjacentElement('afterend',bar);

    bar.querySelector('#jobPauseBtn').addEventListener('click',()=>control('pause'));
    bar.querySelector('#jobResumeBtn').addEventListener('click',()=>control('resume'));
    bar.querySelector('#jobCancelBtn').addEventListener('click',()=>control('cancel'));
    return true;
  }

  function terminal(job){
    return ['done','error','cancelled'].includes(String(job?.status||''));
  }

  function render(job){
    currentJob=job||currentJob;
    const bar=document.querySelector('#jobControlBar');
    if(!bar||!currentJob)return;

    const status=String(currentJob.status||'');
    const state=bar.querySelector('#jobControlState');
    const hint=bar.querySelector('#jobControlHint');
    const pause=bar.querySelector('#jobPauseBtn');
    const resume=bar.querySelector('#jobResumeBtn');
    const cancel=bar.querySelector('#jobCancelBtn');
    const title=document.querySelector('#progressTitle');

    bar.hidden=terminal(currentJob);
    pause.hidden=false;
    resume.hidden=true;
    pause.disabled=false;
    cancel.disabled=false;
    cancel.textContent='Abbrechen';

    if(status==='queued'){
      state.textContent='Benchmark wartet';
      hint.textContent='Du kannst den Run schon jetzt pausieren oder abbrechen.';
    }else if(status==='running'){
      state.textContent='Benchmark läuft';
      hint.textContent='Pause lässt die aktuelle Config fertiglaufen und stoppt vor der nächsten.';
    }else if(status==='pausing'){
      state.textContent='Pause angefordert';
      hint.textContent='Die aktuelle Config wird noch sauber abgeschlossen.';
      pause.disabled=true;
      resume.hidden=false;
      resume.textContent='Pause zurücknehmen';
      if(title)title.textContent='Pause angefordert…';
    }else if(status==='paused'){
      state.textContent='Benchmark pausiert';
      hint.textContent=`${currentJob.completed||0}/${currentJob.total||0} Configs abgeschlossen.`;
      pause.hidden=true;
      resume.hidden=false;
      resume.textContent='Fortsetzen';
      if(title)title.textContent='Benchmark pausiert';
    }else if(status==='cancelling'){
      state.textContent='Benchmark wird abgebrochen';
      hint.textContent='Der aktuelle Worker wird beendet; bereits abgeschlossene Ergebnisse bleiben erhalten.';
      pause.disabled=true;
      cancel.disabled=true;
      cancel.textContent='Bricht ab…';
      if(title)title.textContent='Benchmark wird abgebrochen…';
    }else if(status==='cancelled'){
      if(title)title.textContent='Benchmark abgebrochen';
      if(!cancelledReloadScheduled){
        cancelledReloadScheduled=true;
        setTimeout(()=>window.location.reload(),900);
      }
    }

    const total=Number(currentJob.total||0);
    const current=Number(currentJob.current||0);
    if(status==='running'&&(total<=1||current>=total)){
      pause.disabled=true;
      pause.title='Bei der letzten bzw. einzigen Config gibt es keinen nächsten Schritt zum Pausieren.';
    }else{
      pause.title='';
    }
  }

  async function control(action){
    const job=currentJob;
    if(!job?.id||terminal(job))return;
    if(action==='cancel'&&!confirm('Benchmark wirklich abbrechen? Die aktuell laufende Config wird verworfen; bereits abgeschlossene Ergebnisse bleiben erhalten.'))return;

    const button=document.querySelector(action==='pause'?'#jobPauseBtn':action==='resume'?'#jobResumeBtn':'#jobCancelBtn');
    if(button)button.disabled=true;
    try{
      const response=await fetch(`/api/jobs/${encodeURIComponent(job.id)}/${action}`,{method:'POST'});
      const data=await response.json();
      if(!response.ok)throw new Error(data.error||'Aktion fehlgeschlagen');
      if(data.job){
        currentJob=data.job;
        if(typeof window.showProgress==='function')window.showProgress(data.job);
        else render(data.job);
      }
    }catch(error){
      alert(error.message||String(error));
      render(currentJob);
    }
  }

  function patchProgress(){
    if(typeof window.showProgress!=='function'||window.showProgress.__vpnBenchJobControls)return false;
    const original=window.showProgress;
    const wrapped=function(job){
      original(job);
      render(job);
    };
    wrapped.__vpnBenchJobControls=true;
    window.showProgress=wrapped;
    return true;
  }

  function patchFollowJob(){
    if(typeof window.followJob!=='function'||window.followJob.__vpnBenchJobControls)return false;
    const wrapped=async function(jobId,onDone){
      if(followingJobId===jobId)return;
      followingJobId=jobId;
      if(typeof window.setBenchBusy==='function')window.setBenchBusy(true);
      try{
        while(true){
          const response=await fetch('/api/jobs/'+encodeURIComponent(jobId));
          const job=await response.json();
          if(!response.ok)throw new Error(job.error||'Job nicht gefunden');
          if(typeof window.showProgress==='function')window.showProgress(job);
          else render(job);
          if(terminal(job)){
            if(typeof window.loadResults==='function')await window.loadResults();
            if(typeof window.loadBaseline==='function')await window.loadBaseline();
            if(onDone)onDone(job);
            return job;
          }
          await new Promise(resolve=>setTimeout(resolve,750));
        }
      }finally{
        if(followingJobId===jobId)followingJobId=null;
        if(typeof window.setBenchBusy==='function')window.setBenchBusy(false);
      }
    };
    wrapped.__vpnBenchJobControls=true;
    window.followJob=wrapped;
    return true;
  }

  let attempts=0;
  const timer=setInterval(()=>{
    attempts+=1;
    const ready=installControls()&&patchProgress()&&patchFollowJob();
    if(ready||attempts>=50)clearInterval(timer);
  },80);
})();
