import requests,hashlib,subprocess,json,concurrent.futures
PUBLIC="nocontentracingdivision/ncrdplugin"
SOURCE="nocontentracingdivision/ncrd-source"
BASE="https://api.github.com/repos/"
# Deliberately no Authorization header: validate ordinary customers' access.
assert requests.get(BASE+SOURCE,timeout=60).status_code==404,"Source is publicly accessible"
assert requests.get(BASE+PUBLIC+"/git/commits/50d11c4861cce181fb77a0c85d75dcc1b51c7b41",timeout=60).status_code==404,"Old source commit accessible in downloads repository"
r=requests.get(BASE+PUBLIC+"/releases?per_page=100",timeout=60);r.raise_for_status()
releases=r.json()
assert any(x["tag_name"]=="standalone-v0.1.100" for x in releases)
r=requests.get(BASE+PUBLIC+"/releases/latest",timeout=60);r.raise_for_status()
plugin=r.json();assert plugin["tag_name"]=="v0.9.112"
urls=set()
def collect(v):
    if isinstance(v,dict):
        for x in v.values():collect(x)
    elif isinstance(v,list):
        for x in v:collect(x)
    elif isinstance(v,str) and v.startswith("https://github.com/"+PUBLIC+"/releases/download/"):
        urls.add(v)
for a in plugin["assets"]:
    if a["name"].startswith("updates") and a["name"].endswith(".json"):
        r=requests.get(a["browser_download_url"],timeout=120);r.raise_for_status();collect(r.json())
def check(url):
    r=requests.head(url,allow_redirects=True,timeout=120);r.raise_for_status()
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(check,sorted(urls)))
for a in [{"name":"NCRD-Overlays-0.1.100-win-x64.zip","digest":"sha256:50bf44ac63ad648d25067a0a25f5397e49a0bbc6561df534378e23b94821fa43","size":76806962},{"name":"NCRD-Overlays-Setup-0.1.100.exe","digest":"sha256:e7fe65ad750ac0c81072e0a13fbda6806d0a3dae6d9eda7f413a750742834bde","size":74083585}]:
    url="https://github.com/"+PUBLIC+"/releases/download/standalone-v0.1.100/"+a["name"]
    h=hashlib.sha256();size=0
    with requests.get(url,stream=True,timeout=180) as r:
        r.raise_for_status()
        for b in r.iter_content(1024*1024):h.update(b);size+=len(b)
    assert size==a["size"]
    assert "sha256:"+h.hexdigest()==a["digest"]
    print("Anonymous download SHA-256 verified:",a["name"])
allowed={"README.md","migration.py","releases.json",".github/workflows/migrate.yml",".github/workflows/verify.yml","verify_downloads.py"}
commits=subprocess.check_output(["git","rev-list","--all"],text=True).split()
for c in commits:
    paths=set(subprocess.check_output(["git","ls-tree","-r","--name-only",c],text=True).splitlines())
    assert paths<=allowed,paths-allowed
print("PASS: private source inaccessible; public history has no app source;",len(urls),"manifest URLs reachable;",len(releases),"release entries available without authentication.")
