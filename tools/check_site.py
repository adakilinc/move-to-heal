#!/usr/bin/env python3
"""Static checks for the Move to Heal site. Usage: check_site.py [root]. Exit 1 on any failure."""
import os, re, sys
from html.parser import HTMLParser
from urllib.parse import urlparse, unquote

root = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), ".."))
fails = []
def fail(m): fails.append(m); print("FAIL:", m)
def ok(m): print("ok:  ", m)

VOID = {"meta","link","img","br","hr","input","source","path","circle","rect","use","col","area","base","wbr"}
class P(HTMLParser):
    def __init__(s):
        super().__init__(convert_charrefs=True); s.stack=[]; s.refs=[]; s.errs=[]; s.text=[]; s.ids=[]; s.noalt=0; s.in_skip=0
    def handle_starttag(s, tag, attrs):
        a = dict(attrs)
        if tag not in VOID: s.stack.append(tag)
        for k in ("href","src"):
            if k in a and a[k]: s.refs.append((tag,a[k]))
        if "id" in a: s.ids.append(a["id"])
        if tag=="img" and "alt" not in a: s.noalt+=1
        if tag in ("script","style"): s.in_skip+=1
    def handle_startendtag(s, tag, attrs):
        a=dict(attrs)
        for k in ("href","src"):
            if k in a and a[k]: s.refs.append((tag,a[k]))
        if "id" in a: s.ids.append(a["id"])
    def handle_endtag(s, tag):
        if tag in ("script","style"): s.in_skip-=1
        if tag in VOID: return
        if not s.stack or s.stack[-1]!=tag: s.errs.append(f"unexpected </{tag}> (open: {s.stack[-3:]})")
        else: s.stack.pop()
    def handle_data(s, d):
        if not s.in_skip: s.text.append(d)

def read(p): return open(p, encoding="utf-8", errors="replace").read()

# 1. HTML validity
pages = [os.path.join(root,f) for f in os.listdir(root) if f.endswith(".html")]
if not pages: fail("no html files")
allt = ""
for pg in pages:
    p = P(); src = read(pg); p.feed(src); p.close()
    name = os.path.basename(pg)
    if p.errs or p.stack: fail(f"{name} malformed: {p.errs[:3]} unclosed={p.stack}")
    else: ok(f"{name} parses, tags balanced")
    if p.noalt: fail(f"{name}: {p.noalt} img without alt")
    if len(p.ids)!=len(set(p.ids)): fail(f"{name}: duplicate ids")
    for need in ("<title>",'<meta name="description"','property="og:image"','lang="en"','rel="icon"','<main','<header','<footer','<nav'):
        if need not in src: fail(f"{name}: missing {need}")
    # 2. local links/assets
    for tag, ref in p.refs:
        u = urlparse(ref)
        if u.scheme in ("http","https","mailto"):
            if u.scheme=="http": fail(f"insecure link {ref}")
            if tag in ("link","script","img") and u.netloc not in ("nsumia.github.io",):
                fail(f"external asset {ref}")
            if tag=="iframe" and u.netloc!="www.youtube-nocookie.com": fail(f"iframe from {u.netloc}")
            continue
        if ref.startswith("#"):
            if ref[1:] and ref[1:] not in p.ids: fail(f"missing anchor {ref}")
            continue
        path = os.path.join(root, unquote(u.path))
        if not os.path.exists(path): fail(f"missing local file {ref}")
    ok(f"{len(p.refs)} links/assets checked")
    allt += " ".join(p.text) + src
text_norm = re.sub(r"\s+"," ",allt).replace("&rsquo;","’").replace("&ldquo;","“").replace("&rdquo;","”").replace("&amp;","&")

# 3. the forbidden name must not appear anywhere (file names + contents); git log is checked by run_tests.sh
W="mil"+"ken"  # built from pieces so this file does not match itself
hits=[]
for d,dirs,files in os.walk(root):
    dirs[:] = [x for x in dirs if x not in ("node_modules",".git")]
    for f in files:
        fp=os.path.join(d,f)
        if W in fp.lower(): hits.append(fp)
        try: b=open(fp,"rb").read()
        except OSError: continue
        if W.encode() in b.lower() or W.encode("utf-16-le") in b.lower(): hits.append(fp)
if hits: fail(f"forbidden name found in: {sorted(set(hits))[:5]}")
else: ok("no forbidden name (case-insensitive) in any repo file")

# 4. no glow CSS
css_files=[os.path.join(d,f) for d,_,fs in os.walk(root) for f in fs if f.endswith(".css")]
html_styles=[]
for pg in pages: html_styles += re.findall(r"<style[^>]*>(.*?)</style>|style=\"([^\"]*)\"", read(pg), re.S)
blobs=[(c,read(c)) for c in css_files]+[("inline"," ".join(a+b for a,b in html_styles))]
for name,css in blobs:
    css=re.sub(r"/\*.*?\*/","",css,flags=re.S)
    if re.search(r"text-shadow\s*:\s*(?!none)",css): fail(f"{name}: text-shadow")
    if re.search(r"filter\s*:[^;}]*(drop-shadow|blur)",css): fail(f"{name}: filter drop-shadow/blur")
    if re.search(r"backdrop-filter",css): fail(f"{name}: backdrop-filter")
    for m in re.finditer(r"box-shadow\s*:\s*([^;}]*)",css):
        v=m.group(1).strip()
        if v=="none": continue
        for sh in re.split(r",(?![^(]*\))",v):
            cols=re.findall(r"(rgba?\([^)]*\)|#[0-9a-fA-F]{3,8}\b)",sh)
            nums=[float(x) for x in re.findall(r"(?<![\w#.])(-?\d+(?:\.\d+)?)(?:px)?(?=\s|$)",re.sub(r"rgba?\([^)]*\)|#[0-9a-fA-F]{3,8}\b","",sh))]
            blur=nums[2] if len(nums)>=3 else 0
            neutral=all(re.match(r"rgba\(\s*0\s*,\s*0\s*,\s*0",c) for c in cols) and bool(cols)
            if not neutral or blur>8: fail(f"{name}: glow-like box-shadow '{sh.strip()}'")
    for m in re.finditer(r"(neon|glow)",css,re.I): fail(f"{name}: word '{m.group(0)}' in css")
ok("glow CSS scan done") if not any("glow" in f or "shadow" in f or "filter" in f for f in fails) else None

# 5. page weight (html+css+js+images actually referenced, excl. video embed)
tot=0
for d,dirs,files in os.walk(root):
    dirs[:]=[x for x in dirs if x not in (".git","tools","node_modules")]
    for f in files:
        if f.endswith((".html",".css",".js",".svg",".webp",".jpg",".png",".woff2")): tot+=os.path.getsize(os.path.join(d,f))
(ok if tot<=1_500_000 else fail)(f"page weight {tot/1024:.0f} KB (limit 1465 KB)")

# 6. required texts
req=["Youth Team Winner · Global AI Hackathon 2025","Youth Team Winner, Global AI Hackathon 2025",
 "Creative Innovation Award, MIT AI & Education Summit 2025",
 "Ada Kilinc","Batuhan Pekcan","Defne Nil Pekdemir","Deniz Derya Gokcek","Eylul Karabulak",
 "“Don’t wait for everything to be perfect; once you take the first step and set up the overall flow of your app, you can improve everything gradually, step by step.”",
 "“Doing physical therapy incorrectly at home is a serious issue that often goes unnoticed.”",
 "“We wanted to create something that supports people on their healing journey.”",
 "Cross-Body Shoulder Stretch","Neck Stretch with Hand Assistance","Double Knee to Chest","Inner Thigh Lift","Wall Shoulder Press",
 "Side-Lying Leg Raise","Wall Sit","Cobra Stretch","Glute Bridge",
 "Watch our video","Our story","Photo and quote: MIT App Inventor Winners Spotlight","© 2026 Move to Heal team","Built with MIT App Inventor",
 "does not replace a physiotherapist","3,000+ skeleton images","Meet Mova, your AI rehab assistant","Mova does not replace a doctor or physiotherapist","High accuracy across all 9 exercises in our tests","17 body keypoints","9 models","Can’t see you","PoseNet","https://youtu.be/oen8PSz9ios","youtube-nocookie.com/embed/oen8PSz9ios"]
miss=[r for r in req if r not in text_norm and r.replace("&","&amp;") not in allt]
(fail(f"missing required text: {miss}") if miss else ok(f"{len(req)} required texts present"))
# no numbers/percentages for accuracy; no percent sign in visible text at all; username must not appear
vis=re.sub(r"<(script|style)[^>]*>.*?</\1>","",allt,flags=re.S)
vis=re.sub(r"<[^>]+>"," ",vis)
vis=re.sub(r"\s+"," ",vis)
if re.search(r"accura[a-z]*[^.]{0,80}%|%[^.]{0,80}accura",vis,re.I): fail("percentage near 'accuracy'")
elif "%" in vis: fail("percent sign in visible text")
else: ok("no percentages in visible text")
u="say"+"brone"
if u in vis.lower(): fail("app username appears in page text")
# banned third-party logos
for f in os.listdir(os.path.join(root,"img")) if os.path.isdir(os.path.join(root,"img")) else []:
    if re.search(r"logo|spotlight|appathon",f,re.I): fail(f"suspect image file {f}")

print("RESULT:", "FAIL" if fails else "PASS", f"({len(fails)} problems)")
sys.exit(1 if fails else 0)
