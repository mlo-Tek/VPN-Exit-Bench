(()=>{
  if(window.__vpnBenchSecurityLoaded)return;
  window.__vpnBenchSecurityLoaded=true;

  const token=document.querySelector('meta[name="vpnbench-csrf"]')?.content||'';
  const originalFetch=window.fetch.bind(window);
  const mutating=new Set(['POST','PUT','PATCH','DELETE']);

  function isSameOrigin(input){
    try{
      const raw=input instanceof Request?input.url:String(input);
      const url=new URL(raw,window.location.href);
      return url.origin===window.location.origin;
    }catch(_){
      return false;
    }
  }

  window.fetch=function(input,init={}){
    const method=String(init.method||(input instanceof Request?input.method:'GET')||'GET').toUpperCase();
    if(!token||!mutating.has(method)||!isSameOrigin(input)){
      return originalFetch(input,init);
    }

    const baseHeaders=input instanceof Request?input.headers:undefined;
    const headers=new Headers(baseHeaders||{});
    if(init.headers){
      new Headers(init.headers).forEach((value,key)=>headers.set(key,value));
    }
    headers.set('X-VPN-Bench-CSRF',token);

    if(input instanceof Request){
      return originalFetch(new Request(input,{...init,headers}));
    }
    return originalFetch(input,{...init,headers});
  };

  document.querySelector('#refreshResultsBtn')?.addEventListener('click',()=>{
    if(typeof window.loadResults==='function')window.loadResults();
  });
})();
