from flask import Flask, render_template, jsonify, request
import docker, json, os, sqlite3, time
from pathlib import Path

app=Flask(__name__)
CONFIG_DIR=Path(os.environ.get('CONFIG_DIR','/config/vpns'))
DB_PATH=Path(os.environ.get('DB_PATH','/config/results.db'))
IMAGE=os.environ.get('WORKER_IMAGE','vpn-exit-bench:latest')
HOST_CONFIG_DIR=os.environ.get('HOST_CONFIG_DIR','/mnt/cache/appdata/vpn-exit-bench/vpns')
DOWNLOAD_MB=int(os.environ.get('DOWNLOAD_MB','100'))
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

def db():
    c=sqlite3.connect(DB_PATH)
    c.execute('''CREATE TABLE IF NOT EXISTS results(id INTEGER PRIMARY KEY, ts INTEGER, provider TEXT, name TEXT, type TEXT, payload TEXT)''')
    return c

def configs():
    rows=[]
    for p in sorted(CONFIG_DIR.rglob('*')):
        if p.is_file() and p.suffix.lower() in {'.conf','.ovpn'}:
            rel=p.relative_to(CONFIG_DIR)
            provider=rel.parts[0] if len(rel.parts)>1 else 'Other'
            typ='openvpn' if p.suffix.lower()=='.ovpn' else 'wireguard'
            rows.append({'provider':provider,'name':p.name,'rel':str(rel),'type':typ})
    return rows

@app.get('/')
def index(): return render_template('index.html')

@app.get('/api/configs')
def api_configs(): return jsonify(configs())

@app.get('/api/results')
def results():
    c=db(); cur=c.execute('SELECT id,ts,provider,name,type,payload FROM results ORDER BY id DESC LIMIT 200')
    out=[]
    for i,ts,pr,n,t,p in cur:
        x=json.loads(p); x.update({'id':i,'ts':ts,'provider':pr,'name':n,'type':t}); out.append(x)
    c.close(); return jsonify(out)

@app.post('/api/test')
def test():
    rel=request.json.get('rel','')
    allowed={x['rel']:x for x in configs()}
    if rel not in allowed: return jsonify({'error':'Unknown config'}),404
    cfg=allowed[rel]
    client=docker.from_env()
    host_path=str(Path(HOST_CONFIG_DIR)/rel)
    try:
        container=client.containers.run(
            IMAGE, command=['python','worker.py'], detach=True,
            cap_add=['NET_ADMIN'], devices=['/dev/net/tun:/dev/net/tun'],
            volumes={host_path:{'bind':'/vpn/config','mode':'ro'}},
            environment={'VPN_CONFIG':'/vpn/config','VPN_TYPE':cfg['type'],'DOWNLOAD_BYTES':str(DOWNLOAD_MB*1024*1024)},
            labels={'vpn-exit-bench-worker':'1'}, network_mode='bridge')
        result=container.wait(timeout=90)
        logs=container.logs(stdout=True, stderr=True).decode(errors='ignore').strip().splitlines()
        container.remove(force=True)
        payload=None
        for line in reversed(logs):
            try: payload=json.loads(line); break
            except Exception: pass
        if payload is None: payload={'ok':False,'error':'Worker returned no JSON','logs':'\n'.join(logs[-20:])}
    except Exception as e:
        payload={'ok':False,'error':str(e)}
    c=db(); c.execute('INSERT INTO results(ts,provider,name,type,payload) VALUES(?,?,?,?,?)',(int(time.time()),cfg['provider'],cfg['name'],cfg['type'],json.dumps(payload)))
    c.commit(); c.close(); return jsonify(payload)

@app.post('/api/test-all')
def test_all():
    # Intentionally sequential to avoid saturating the WAN and invalid comparisons.
    out=[]
    for cfg in configs():
        with app.test_request_context('/api/test', method='POST', json={'rel':cfg['rel']}):
            resp=test()
            data=resp.get_json() if not isinstance(resp,tuple) else resp[0].get_json()
            out.append({'config':cfg, 'result':data})
    return jsonify(out)

if __name__=='__main__': app.run(host='0.0.0.0', port=8787, threaded=True)
