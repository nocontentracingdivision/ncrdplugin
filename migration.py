import os,json,time,hashlib,tempfile,urllib.parse
import requests
SRC="nocontentracingdivision/ncrdplugin"
DST=os.environ["GITHUB_REPOSITORY"]
TOKEN=os.environ["GH_TOKEN"]
API="https://api.github.com"
def api(method,path,**kw):
    for attempt in range(8):
        r=requests.request(method,API+path,headers={"Authorization":"Bearer "+TOKEN,"Accept":"application/vnd.github+json"},timeout=180,**kw)
        if r.status_code in (403,429) or r.status_code>=500:
            time.sleep(min(900,max(30,int(r.headers.get("X-RateLimit-Reset","0"))-int(time.time())+5)));continue
        r.raise_for_status()
        return r.json() if r.content else None
    raise RuntimeError("API retries exhausted: "+path)
with open("releases.json") as f: releases=json.load(f)
# Preserve the current channels, rollback version, all manifest dependencies,
# and any releases already copied by the initial archive pass.
import re
bytag={r["tag_name"]:r for r in releases}
selected={"v0.9.112","standalone-v0.1.100","standalone-v0.1.99"}
done=set()
existing={r["tag_name"]:r for page in range(1,4) for r in api("GET",f"/repos/{DST}/releases?per_page=100&page={page}")}
selected.update(existing)
while selected-done:
    tag=next(iter(selected-done))
    if tag not in bytag:raise RuntimeError("Unknown manifest dependency: "+tag)
    for a in bytag[tag]["assets"]:
        if a["name"].startswith("updates") and a["name"].endswith(".json"):
            r=requests.get(a["browser_download_url"],timeout=120);r.raise_for_status()
            manifest=r.text.replace("\\\\/","/")
            for match in re.findall(r"github.com/nocontentracingdivision/ncrdplugin/releases/download/([^/\\s\\\"]+)/",manifest):
                selected.add(urllib.parse.unquote(match))
    done.add(tag)
releases=[bytag[t] for t in selected]
print("Active channels and dependencies:",sorted(selected),flush=True)
head=api("GET",f"/repos/{DST}/git/ref/heads/main")["object"]["sha"]
allowed=lambda n: n.endswith((".exe",".dll",".simhubdash")) or n in ("SHA256SUMS.txt","NCRD.UpdateFeed.txt") or (n.startswith("updates") and n.endswith(".json")) or (n.startswith("NCRD-Overlays-") and n.endswith("-win-x64.zip"))
# Oldest first preserves release ordering; explicitly retain the plugin latest channel.
for release in sorted(releases,key=lambda r:r["published_at"] or r["created_at"]):
    if release["draft"]:continue
    tag=release["tag_name"]
    assets=release["assets"]
    if not all(allowed(a["name"]) for a in assets):raise RuntimeError("Unreviewed asset: "+tag)
    dest=existing.get(tag)
    if not dest:
        dest=api("POST",f"/repos/{DST}/releases",json={"tag_name":tag,"target_commitish":head,"name":release["name"],"body":release["body"] or "","draft":True,"prerelease":release["prerelease"],"make_latest":"false"})
    destassets={a["name"]:a for a in api("GET",f"/repos/{DST}/releases/{dest['id']}/assets?per_page=100")}
    for asset in assets:
        name=asset["name"]
        if name in destassets:
            assert destassets[name]["size"]==asset["size"]
            if asset.get("digest"):assert destassets[name].get("digest")==asset["digest"]
            continue
        with tempfile.TemporaryFile() as f:
            h=hashlib.sha256();size=0
            with requests.get(asset["browser_download_url"],stream=True,timeout=180) as r:
                r.raise_for_status()
                for chunk in r.iter_content(1024*1024):
                    f.write(chunk);h.update(chunk);size+=len(chunk)
            digest="sha256:"+h.hexdigest()
            assert size==asset["size"],name
            if asset.get("digest"):assert digest==asset["digest"],name
            f.seek(0)
            url=dest["upload_url"].split("{")[0]+"?name="+urllib.parse.quote(name)
            r=requests.post(url,headers={"Authorization":"Bearer "+TOKEN,"Content-Type":"application/octet-stream","Content-Length":str(size)},data=f,timeout=600)
            r.raise_for_status();uploaded=r.json()
            assert uploaded["size"]==size
            assert uploaded.get("digest")==digest
    api("PATCH",f"/repos/{DST}/releases/{dest['id']}",json={"draft":False,"make_latest":"true" if tag=="v0.9.112" else "false"})
    print("Verified",tag,len(assets),"assets",flush=True)
print("All release assets copied and verified.",flush=True)
