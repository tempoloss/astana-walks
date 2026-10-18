import urllib.request, ssl, json, sys, time
ctx=ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
def get(url):
    return json.load(urllib.request.urlopen(urllib.request.Request(url),context=ctx,timeout=40))
ids=sys.argv[1:]
for dsid in ids:
    try:
        d=get(f"https://ashyq.data.gov.kz/api/v0/registry/records/{dsid}?aspect=dataset-distributions")
        dists=d['aspects']['dataset-distributions']['distributions']
        print(f"### {dsid} :: {d.get('name')} :: {len(dists)} distributions")
        for dist in dists:
            try:
                dd=get(f"https://ashyq.data.gov.kz/api/v0/registry/records/{dist}?aspect=dcat-distribution-strings")
                s=dd['aspects']['dcat-distribution-strings']
                print(f"  {dist} | {s.get('format')} | {s.get('byteSize')} | lic={s.get('license')!r} | {s.get('downloadURL')}")
            except Exception as e:
                print(f"  {dist} ERR {e}")
            time.sleep(0.1)
    except Exception as e:
        print(dsid,'ERR',e)
    time.sleep(0.2)
