(()=>{
  if(window.__vpnBenchCompareSortLoaded)return;
  window.__vpnBenchCompareSortLoaded=true;

  const num=text=>{
    const match=String(text||'').replace(',','.').match(/-?\d+(?:\.\d+)?/);
    return match?Number(match[0]):null;
  };
  const finiteOr=(value,fallback)=>Number.isFinite(value)?value:fallback;

  function sortChildren(container,compare){
    if(!container)return;
    const nodes=[...container.children];
    nodes.sort(compare).forEach(node=>container.appendChild(node));
  }

  function scoreOfCard(card){
    return num(card.querySelector('.run-score')?.textContent);
  }
  function metricOfCard(card,label){
    const blocks=[...card.querySelectorAll('.run-card-metrics > div')];
    const block=blocks.find(el=>el.querySelector('span')?.textContent.trim()===label);
    return num(block?.querySelector('b')?.textContent);
  }
  function sortOverview(){
    const grid=document.querySelector('#comparisonPanel .compare-run-grid');
    sortChildren(grid,(a,b)=>{
      const scoreDelta=finiteOr(scoreOfCard(b),-Infinity)-finiteOr(scoreOfCard(a),-Infinity);
      if(scoreDelta)return scoreDelta;
      const downDelta=finiteOr(metricOfCard(b,'Download'),-Infinity)-finiteOr(metricOfCard(a,'Download'),-Infinity);
      if(downDelta)return downDelta;
      const upDelta=finiteOr(metricOfCard(b,'Upload'),-Infinity)-finiteOr(metricOfCard(a,'Upload'),-Infinity);
      if(upDelta)return upDelta;
      return finiteOr(metricOfCard(a,'Ping'),Infinity)-finiteOr(metricOfCard(b,'Ping'),Infinity);
    });
  }

  function sortBars(card,direction='desc'){
    const bars=card?.querySelector('.compare-bars');
    sortChildren(bars,(a,b)=>{
      const av=num(a.querySelector('.compare-bar-value')?.textContent);
      const bv=num(b.querySelector('.compare-bar-value')?.textContent);
      if(direction==='asc')return finiteOr(av,Infinity)-finiteOr(bv,Infinity);
      return finiteOr(bv,-Infinity)-finiteOr(av,-Infinity);
    });
  }

  function sortCharts(){
    sortBars(document.querySelector('#comparisonPanel .compare-score-card'),'desc');
    document.querySelectorAll('#comparisonPanel .compare-throughput-grid .compare-chart-card').forEach(card=>{
      sortBars(card,'desc');
    });
  }

  function qualityMetric(card,label){
    const blocks=[...card.querySelectorAll('.quality-metrics > div')];
    const block=blocks.find(el=>el.querySelector('span')?.textContent.trim()===label);
    return num(block?.querySelector('b')?.textContent);
  }
  function qualityPortRank(card){
    const pill=card.querySelector('.port-pill');
    if(!pill)return 0;
    if(pill.classList.contains('ok'))return 3;
    if(pill.classList.contains('mapped'))return 2;
    if(pill.classList.contains('unknown'))return 1;
    return 0;
  }
  function sortQuality(){
    const grid=document.querySelector('#comparisonPanel .quality-card-grid');
    sortChildren(grid,(a,b)=>{
      const portDelta=qualityPortRank(b)-qualityPortRank(a);
      if(portDelta)return portDelta;
      const lossDelta=finiteOr(qualityMetric(a,'Packet Loss'),Infinity)-finiteOr(qualityMetric(b,'Packet Loss'),Infinity);
      if(lossDelta)return lossDelta;
      const pingDelta=finiteOr(qualityMetric(a,'Ping'),Infinity)-finiteOr(qualityMetric(b,'Ping'),Infinity);
      if(pingDelta)return pingDelta;
      const jitterDelta=finiteOr(qualityMetric(a,'Jitter'),Infinity)-finiteOr(qualityMetric(b,'Jitter'),Infinity);
      if(jitterDelta)return jitterDelta;
      return String(a.textContent||'').localeCompare(String(b.textContent||''),'de');
    });
  }

  function applyCategorySorting(){
    const panel=document.querySelector('#comparisonPanel');
    if(!panel||panel.hidden)return;
    sortOverview();
    sortCharts();
    sortQuality();
  }

  function bind(){
    const button=document.querySelector('#openCompare');
    if(!button||button.dataset.categorySortBound==='1')return false;
    button.dataset.categorySortBound='1';
    button.addEventListener('click',()=>{
      requestAnimationFrame(()=>requestAnimationFrame(applyCategorySorting));
    });
    if(document.querySelector('#comparisonPanel:not([hidden])'))applyCategorySorting();
    return true;
  }

  let attempts=0;
  const timer=setInterval(()=>{
    attempts+=1;
    if(bind()||attempts>=80)clearInterval(timer);
  },250);
})();
