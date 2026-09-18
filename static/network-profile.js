(()=>{
  if(window.__vpnBenchNetworkProfileLoaded)return;
  window.__vpnBenchNetworkProfileLoaded=true;

  let results=[];
  let refreshTimer=null;

  const esc=value=>String(value??'').replace(/[&<>"']/g,ch=>({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[ch]));

  function parsedOrg(value){
    const text=String(value||'').trim();
    const match=text.match(/^(AS\d+)\s+(.+)$/i);
    return {
      asn:match?match[1].toUpperCase():null,
      organization:match?match[2].trim():(text||null)
    };
  }

  function profileOf(result){
    const exit=result?.exit||{};
    const network=exit?.network||{};
    const fallback=parsedOrg(exit.org);
    const organization=network.organization||fallback.organization||null;
    return {
      ip:exit.ip||null,
      asn:network.asn||fallback.asn||null,
      organization,
      isp:network.hosting_provider||network.isp||organization||null,
      prefix:network.bgp_prefix||null,
      rdns:network.rdns||null,
      catalogMatch:Boolean(network.catalog_match)
    };
  }

  function uniq(values){
    return [...new Set(values.filter(Boolean).map(value=>String(value).trim()).filter(Boolean))];
  }

  function enhanceRows(){
    const byId=new Map(results.map(result=>[Number(result.id),result]));
    document.querySelectorAll('#results tr[data-result-id]').forEach(row=>{
      const result=byId.get(Number(row.dataset.resultId));
      if(!result)return;
      const profile=profileOf(result);
      const meta=row.querySelector('.endpoint-meta');
      if(!meta)return;

      const main=uniq([profile.ip,profile.asn,profile.isp]);
      meta.textContent=main.length?main.join(' · '):'Netzwerk nicht ermittelt';
      meta.classList.add('network-profile-main');
      meta.title=uniq([
        profile.organization&&`Organisation: ${profile.organization}`,
        profile.prefix&&`BGP: ${profile.prefix}`,
        profile.rdns&&`rDNS: ${profile.rdns}`
      ]).join('\n');

      let sub=row.querySelector('.endpoint-network-sub');
      const details=uniq([
        profile.prefix&&`BGP ${profile.prefix}`,
        profile.rdns&&`rDNS ${profile.rdns}`
      ]);
      if(details.length){
        if(!sub){
          sub=document.createElement('div');
          sub.className='endpoint-network-sub';
          meta.insertAdjacentElement('afterend',sub);
        }
        sub.textContent=details.join(' · ');
      }else if(sub){
        sub.remove();
      }
    });
  }

  function renderSummary(){
    const tbody=document.querySelector('#results');
    const card=tbody?.closest('.card');
    if(!tbody||!card)return;

    let box=card.querySelector('#networkProfileSummary');
    const groups=new Map();

    for(const result of results){
      if(!result?.ok)continue;
      const profile=profileOf(result);
      if(!profile.asn&&!profile.isp&&!profile.organization)continue;
      const isp=profile.isp||profile.organization||'Unbekannt';
      const key=`${profile.asn||'–'}\u0000${isp}`;
      if(!groups.has(key)){
        groups.set(key,{
          asn:profile.asn,
          isp,
          organization:profile.organization,
          prefix:profile.prefix,
          count:0
        });
      }
      groups.get(key).count+=1;
    }

    if(!groups.size){
      if(box)box.remove();
      return;
    }

    const items=[...groups.values()].sort((a,b)=>
      b.count-a.count||
      String(a.isp).localeCompare(String(b.isp),'de')
    );

    if(!box){
      box=document.createElement('div');
      box.id='networkProfileSummary';
      box.className='network-profile-summary';
      const tableWrap=card.querySelector('.result-table-wrap')||
        [...card.children].find(el=>el.tagName==='DIV'&&String(el.getAttribute('style')||'').includes('overflow'));
      if(tableWrap)card.insertBefore(box,tableWrap);
      else card.appendChild(box);
    }

    box.innerHTML=`
      <div class="network-summary-head">
        <div>
          <span class="network-summary-kicker">Exit-Infrastruktur</span>
          <strong>Netze / ISPs der aktuellen Ergebnisse</strong>
        </div>
        <span class="muted small">${items.length} Netz${items.length===1?'':'e'}</span>
      </div>
      <div class="network-summary-chips">
        ${items.map(item=>{
          const count=`${item.count} Exit${item.count===1?'':'s'}`;
          const label=[item.asn,item.isp].filter(Boolean).join(' · ');
          const title=uniq([item.organization,item.prefix&&`BGP ${item.prefix}`]).join(' · ');
          return `<span class="network-summary-chip" title="${esc(title)}"><b>${esc(label)}</b><span>${esc(count)}</span></span>`;
        }).join('')}
      </div>`;
  }

  function paint(){
    renderSummary();
    enhanceRows();
  }

  async function refresh(){
    try{
      const response=await fetch('/api/results');
      if(!response.ok)return;
      results=await response.json();
      paint();
    }catch(error){
      console.warn('VPN Exit Bench network profile refresh failed',error);
    }
  }

  function scheduleRefresh(){
    clearTimeout(refreshTimer);
    refreshTimer=setTimeout(refresh,120);
  }

  const tbody=document.querySelector('#results');
  if(tbody){
    new MutationObserver(scheduleRefresh).observe(tbody,{childList:true});
  }

  refresh();
})();
