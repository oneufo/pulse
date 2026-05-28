import os, json, requests
from datetime import datetime, timezone

API_KEY = os.environ.get("NEWS_API_KEY", "")

CATEGORIES = [
    {"id": "geopolitics", "label": "地缘政治", "tag": "tag-geo", "q": "Iran war Trump Middle East"},
    {"id": "politics",    "label": "政治",     "tag": "tag-pol", "q": "US politics Congress White House"},
    {"id": "business",    "label": "商业",     "tag": "tag-biz", "q": "economy markets stocks business"},
    {"id": "tech",        "label": "科技",     "tag": "tag-tech","q": "AI technology silicon valley"},
    {"id": "health",      "label": "健康",     "tag": "tag-hlth","q": "health medicine research drug"},
    {"id": "science",     "label": "科学",     "tag": "tag-sci", "q": "science discovery space NASA"},
    {"id": "climate",     "label": "气候",     "tag": "tag-cli", "q": "climate change environment sea level"},
]

def fetch(q):
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": q,
        "sortBy": "publishedAt",
        "pageSize": 3,
        "language": "en",
        "apiKey": API_KEY,
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json().get("articles", [])
    except Exception as e:
        print(f"Error fetching '{q}': {e}")
        return []

def score(article):
    title = article.get("title") or ""
    desc  = article.get("description") or ""
    src   = article.get("source", {}).get("name") or ""
    trusted = ["Reuters","AP","BBC","NPR","CNBC","Bloomberg","NYT","Washington Post","Guardian","FT"]
    base = 60
    if any(t.lower() in src.lower() for t in trusted):
        base += 15
    if len(desc) > 100:
        base += 10
    keywords = ["breakthrough","record","war","deal","crisis","collapse","surge","ban","historic"]
    if any(k in (title+desc).lower() for k in keywords):
        base += 10
    return min(base, 99)

def build_cards():
    cards = []
    for cat in CATEGORIES:
        articles = fetch(cat["q"])
        for a in articles[:2]:
            title = (a.get("title") or "").split(" - ")[0].strip()
            desc  = (a.get("description") or "")[:180].strip()
            src   = a.get("source", {}).get("name", "")
            pub   = (a.get("publishedAt") or "")[:10]
            url   = a.get("url") or "#"
            if not title or title == "[Removed]":
                continue
            cards.append({
                "cat":   cat["id"],
                "tag":   cat["tag"],
                "label": cat["label"],
                "hl":    title,
                "body":  desc or "点击阅读全文。",
                "imp":   score(a),
                "src":   f"{src} · {pub}",
                "url":   url,
            })
    return cards

def build_featured(cards):
    if not cards:
        return None
    return max(cards, key=lambda c: c["imp"])

def render(cards, featured, updated):
    cards_json    = json.dumps(cards,    ensure_ascii=False)
    featured_json = json.dumps(featured, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="zh" data-theme="light">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>要闻 · Dispatch</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
:root{{--bg:#f6f6f4;--surface:#fff;--surface2:#fafaf8;--border:rgba(0,0,0,0.07);--border-md:rgba(0,0,0,0.12);--t1:#0d0d0d;--t2:#555;--t3:#999;--accent:#d97706;--accent-dim:#fef3c7;--accent-dark:#92400e;--geopolitics-bg:#dbeafe;--geopolitics-t:#1e3a5f;--politics-bg:#fce7f3;--politics-t:#831843;--business-bg:#d1fae5;--business-t:#064e3b;--tech-bg:#ede9fe;--tech-t:#4c1d95;--health-bg:#fee2e2;--health-t:#7f1d1d;--science-bg:#e0f2fe;--science-t:#0c4a6e;--climate-bg:#dcfce7;--climate-t:#14532d;--r-lg:12px;--sh:0 1px 2px rgba(0,0,0,.05);--sh-md:0 4px 14px rgba(0,0,0,.08);}}
[data-theme=dark]{{--bg:#101010;--surface:#1c1c1c;--surface2:#161616;--border:rgba(255,255,255,.07);--border-md:rgba(255,255,255,.13);--t1:#f0f0f0;--t2:#888;--t3:#4a4a4a;--accent:#f59e0b;--accent-dim:#231a08;--accent-dark:#fcd34d;--geopolitics-bg:#1a2f46;--geopolitics-t:#93c5fd;--politics-bg:#3b0a24;--politics-t:#f9a8d4;--business-bg:#052e1c;--business-t:#6ee7b7;--tech-bg:#2a1545;--tech-t:#c4b5fd;--health-bg:#380e0e;--health-t:#fca5a5;--science-bg:#0a2535;--science-t:#7dd3fc;--climate-bg:#052612;--climate-t:#86efac;--sh:0 1px 3px rgba(0,0,0,.4);--sh-md:0 4px 16px rgba(0,0,0,.5);}}
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{background:var(--bg);color:var(--t1);font-family:'Inter',system-ui,sans-serif;font-size:14px;line-height:1.6;transition:background .2s,color .2s;}}
button{{cursor:pointer;font-family:inherit;}} a{{text-decoration:none;color:inherit;}}
.topbar{{position:sticky;top:0;z-index:90;background:rgba(246,246,244,.9);backdrop-filter:blur(16px);border-bottom:1px solid var(--border);}}
[data-theme=dark] .topbar{{background:rgba(16,16,16,.9);}}
.tb{{display:flex;align-items:center;gap:12px;height:50px;padding:0 24px;max-width:1180px;margin:0 auto;}}
.logo{{font-size:16px;font-weight:700;letter-spacing:-.4px;display:flex;align-items:center;gap:8px;white-space:nowrap;flex-shrink:0;}}
.logo-dot{{width:7px;height:7px;border-radius:50%;background:var(--accent);animation:pulse 2.4s ease-in-out infinite;}}
@keyframes pulse{{0%,100%{{opacity:1;transform:scale(1);}}50%{{opacity:.35;transform:scale(.65);}}}}
.logo-sub{{font-size:11px;font-weight:400;color:var(--t3);}}
.sep{{width:1px;height:20px;background:var(--border-md);flex-shrink:0;}}
.live-dot{{width:6px;height:6px;border-radius:50%;background:#22c55e;flex-shrink:0;animation:pulse 1.8s ease-in-out infinite;}}
.live-lbl{{font-size:11px;color:var(--t3);white-space:nowrap;}}
.ticker-wrap{{flex:1;overflow:hidden;min-width:0;}}
.ticker-track{{display:flex;gap:40px;white-space:nowrap;animation:tk 65s linear infinite;}}
.ticker-track:hover{{animation-play-state:paused;}}
@keyframes tk{{from{{transform:translateX(0);}}to{{transform:translateX(-50%);}}}}
.tk-item{{font-size:11.5px;color:var(--t2);flex-shrink:0;}}
.tk-item::before{{content:'·';color:var(--accent);margin-right:7px;font-weight:700;}}
#ltime{{font-size:11px;color:var(--t3);white-space:nowrap;font-variant-numeric:tabular-nums;flex-shrink:0;}}
.tbtn{{width:32px;height:32px;border-radius:50%;border:1px solid var(--border-md);background:var(--surface);color:var(--t2);font-size:14px;display:flex;align-items:center;justify-content:center;flex-shrink:0;}}
.prog-bar{{height:2px;background:var(--border);}}
.prog-fill{{height:100%;width:0%;background:var(--accent);transition:width .8s linear;}}
.subnav{{border-bottom:1px solid var(--border);background:var(--surface);overflow-x:auto;scrollbar-width:none;}}
.sni{{display:flex;gap:2px;padding:8px 24px;max-width:1180px;margin:0 auto;}}
.np{{flex-shrink:0;padding:5px 14px;border-radius:99px;font-size:11.5px;font-weight:500;color:var(--t2);background:none;border:1px solid transparent;transition:all .14s;}}
.np:hover{{background:var(--bg);border-color:var(--border-md);color:var(--t1);}}
.np.on{{background:var(--accent-dim);color:var(--accent-dark);}}
.main{{padding:24px 24px 80px;max-width:1180px;margin:0 auto;}}
.sec-h{{display:flex;align-items:center;gap:10px;margin:28px 0 14px;}}
.sec-line{{flex:1;height:1px;background:var(--border);}}
.sec-title{{font-size:10px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:var(--t3);white-space:nowrap;}}
.sec-badge{{font-size:10px;font-weight:500;color:var(--accent);background:var(--accent-dim);padding:2px 8px;border-radius:99px;}}
.feat{{display:grid;grid-template-columns:1fr 240px;background:var(--surface);border:1px solid var(--border);border-radius:var(--r-lg);overflow:hidden;box-shadow:var(--sh);margin-bottom:10px;transition:box-shadow .2s;}}
.feat:hover{{box-shadow:var(--sh-md);}}
.f-body{{padding:28px;}}
.f-side{{border-left:1px solid var(--border);padding:24px 20px;background:var(--surface2);display:flex;flex-direction:column;gap:20px;}}
.f-div{{height:1px;background:var(--border);}}
.g3{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:10px;}}
.g2{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;}}
.g1{{margin-bottom:10px;}}
.card{{background:var(--surface);border:1px solid var(--border);border-radius:var(--r-lg);padding:20px 20px 16px;box-shadow:var(--sh);display:flex;flex-direction:column;transition:box-shadow .2s,transform .18s;}}
.card:hover{{box-shadow:var(--sh-md);transform:translateY(-1px);}}
.tag{{display:inline-flex;font-size:10px;font-weight:600;letter-spacing:.04em;padding:3px 8px;border-radius:4px;margin-bottom:10px;}}
.tag-geo{{background:var(--geopolitics-bg);color:var(--geopolitics-t);}}
.tag-pol{{background:var(--politics-bg);color:var(--politics-t);}}
.tag-biz{{background:var(--business-bg);color:var(--business-t);}}
.tag-tech{{background:var(--tech-bg);color:var(--tech-t);}}
.tag-hlth{{background:var(--health-bg);color:var(--health-t);}}
.tag-sci{{background:var(--science-bg);color:var(--science-t);}}
.tag-cli{{background:var(--climate-bg);color:var(--climate-t);}}
.hl{{font-size:clamp(17px,1.9vw,23px);font-weight:700;line-height:1.3;letter-spacing:-.4px;margin-bottom:10px;}}
.hsm{{font-size:clamp(13px,1.3vw,15px);font-weight:600;line-height:1.38;letter-spacing:-.2px;margin-bottom:8px;transition:color .15s;}}
.card:hover .hsm{{color:var(--accent);}}
.body{{font-size:13.5px;color:var(--t2);line-height:1.7;margin-bottom:12px;}}
.body-sm{{font-size:12.5px;color:var(--t2);line-height:1.65;flex:1;margin-bottom:10px;}}
.imp{{margin-top:auto;}}
.imp-row{{display:flex;align-items:center;gap:8px;}}
.imp-lbl{{font-size:10.5px;color:var(--t3);flex-shrink:0;}}
.imp-track{{flex:1;height:3px;background:var(--border);border-radius:99px;overflow:hidden;}}
.imp-fill{{height:100%;border-radius:99px;background:var(--accent);opacity:.75;}}
.imp-score{{font-size:10.5px;font-weight:600;color:var(--accent);width:24px;text-align:right;}}
.src{{font-size:10.5px;color:var(--t3);margin-top:7px;}}
.read-more{{font-size:11px;color:var(--accent);margin-top:8px;display:inline-block;font-weight:500;}}
.side-lbl{{font-size:9.5px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--t3);margin-bottom:5px;}}
.big-score{{font-size:36px;font-weight:700;letter-spacing:-.8px;color:var(--accent);line-height:1;}}
.chip{{font-size:11px;font-weight:500;color:var(--accent-dark);background:var(--accent-dim);padding:4px 10px;border-radius:4px;display:inline-block;}}
footer{{border-top:1px solid var(--border);padding:14px 24px;display:flex;justify-content:space-between;max-width:1180px;margin:0 auto;}}
.fl,.fr{{font-size:10.5px;color:var(--t3);}}
#nxt{{color:var(--accent);}}
.empty{{padding:60px 0;text-align:center;color:var(--t3);}}
@keyframes fu{{from{{opacity:0;transform:translateY(8px);}}to{{opacity:1;transform:translateY(0);}}}}
@media(max-width:860px){{.feat{{grid-template-columns:1fr;}}.f-side,.ticker-wrap,.sep{{display:none;}}.g3,.g2{{grid-template-columns:1fr;}}footer{{flex-direction:column;gap:4px;text-align:center;}}}}
</style></head><body>
<div class="topbar">
  <div class="tb">
    <div class="logo"><div class="logo-dot"></div>要闻<span class="logo-sub">Dispatch</span></div>
    <div class="sep"></div><div class="live-dot"></div><span class="live-lbl">每日自动更新</span>
    <div class="sep"></div>
    <div class="ticker-wrap"><div class="ticker-track" id="tk"></div></div>
    <div class="sep"></div>
    <span id="ltime">—</span>
    <button class="tbtn" id="tbtn">☀</button>
  </div>
  <div class="prog-bar"><div class="prog-fill" id="prog"></div></div>
</div>
<div class="subnav"><div class="sni" id="nav">
  <button class="np on" data-c="all">全部</button>
  <button class="np" data-c="geopolitics">地缘</button>
  <button class="np" data-c="politics">政治</button>
  <button class="np" data-c="business">商业</button>
  <button class="np" data-c="tech">科技</button>
  <button class="np" data-c="health">健康</button>
  <button class="np" data-c="science">科学</button>
  <button class="np" data-c="climate">气候</button>
</div></div>
<main class="main" id="grid"></main>
<footer>
  <span class="fl">要闻 · Dispatch · 最后更新：{updated}</span>
  <span class="fr">下次更新 <span id="nxt">—</span></span>
</footer>
<script>
const CARDS={cards_json};
const FEAT={featured_json};
let dark=false;
document.getElementById('tbtn').addEventListener('click',()=>{{
  dark=!dark;
  document.documentElement.setAttribute('data-theme',dark?'dark':'light');
  document.getElementById('tbtn').textContent=dark?'☾':'☀';
}});
function pad(n){{return String(n).padStart(2,'0');}}
setInterval(()=>{{const n=new Date();document.getElementById('ltime').textContent=`${{n.getFullYear()}}/${{pad(n.getMonth()+1)}}/${{pad(n.getDate())}} ${{pad(n.getHours())}}:${{pad(n.getMinutes())}}:${{pad(n.getSeconds())}}`;}},1000);
function tagHTML(d){{return`<span class="tag ${{d.tag}}">${{d.label}}</span>`;}}
function impBar(v){{return`<div class="imp"><div class="imp-row"><span class="imp-lbl">重要程度</span><div class="imp-track"><div class="imp-fill" style="width:${{v}}%"></div></div><span class="imp-score">${{v}}</span></div></div>`;}}
function featHTML(d){{if(!d)return'';return`<div class="feat"><div class="f-body">${{tagHTML(d)}}<div class="hl">${{d.hl}}</div><div class="body">${{d.body}}</div>${{impBar(d.imp)}}<div class="src">${{d.src}}</div><a class="read-more" href="${{d.url}}" target="_blank">阅读原文 →</a></div><div class="f-side"><div><div class="side-lbl">重要程度</div><div class="big-score">${{d.imp}}</div></div><div class="f-div"></div><div><div class="side-lbl">分类</div><span class="chip">${{d.label}}</span></div><div class="f-div"></div><div><div class="side-lbl">来源</div><div style="font-size:12px;color:var(--t2)">${{d.src}}</div></div></div></div>`;}}
function cardHTML(d){{return`<div class="card">${{tagHTML(d)}}<div class="hsm">${{d.hl}}</div><div class="body-sm">${{d.body}}</div>${{impBar(d.imp)}}<div class="src">${{d.src}}</div><a class="read-more" href="${{d.url}}" target="_blank">阅读原文 →</a></div>`;}}
function secH(t,b=''){{return`<div class="sec-h"><div class="sec-line"></div><span class="sec-title">${{t}}</span>${{b?`<span class="sec-badge">${{b}}</span>`:''}}<div class="sec-line"></div></div>`;}}
function render(cat){{
  const cards=cat==='all'?CARDS:CARDS.filter(c=>c.cat===cat);
  const sf=cat==='all'||cat===FEAT?.cat;
  let h='';
  if(sf){{h+=secH('今日头条','LIVE');h+=featHTML(FEAT);}}
  if(cards.length){{
    h+=secH('深度精选 · In Depth');
    for(let i=0;i<cards.length;i+=3){{const chunk=cards.slice(i,i+3);h+=`<div class="${{chunk.length===1?'g1':chunk.length===2?'g2':'g3'}}">${{chunk.map(cardHTML).join('')}}</div>`;}}
  }}else if(!sf){{h='<div class="empty">暂无此分类新闻</div>';}}
  document.getElementById('grid').innerHTML=h;
}}
let active='all';
document.getElementById('nav').addEventListener('click',e=>{{const b=e.target.closest('.np');if(!b)return;document.querySelectorAll('.np').forEach(x=>x.classList.remove('on'));b.classList.add('on');active=b.dataset.c;render(active);}});
document.getElementById('tk').innerHTML=CARDS.concat(CARDS).map(c=>`<span class="tk-item">${{c.hl}}</span>`).join('');
const TOTAL=7200;let elapsed=0;
setInterval(()=>{{elapsed++;document.getElementById('prog').style.width=(elapsed/TOTAL*100)+'%';const rem=TOTAL-elapsed,hh=Math.floor(rem/3600),mm=Math.floor((rem%3600)/60),ss=rem%60,el=document.getElementById('nxt');if(el)el.textContent=hh>0?`${{hh}}时${{pad(mm)}}分后更新`:`${{mm}}分${{pad(ss)}}秒后更新`;if(elapsed>=TOTAL){{elapsed=0;render(active);}}}},1000);
render('all');
</script></body></html>"""

def main():
    print("Fetching news...")
    cards = build_cards()
    print(f"Got {len(cards)} articles")
    featured = build_featured(cards)
    updated = datetime.now(timezone.utc).strftime("%Y年%-m月%-d日 %H:%M UTC")
    html = render(cards, featured, updated)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("index.html written.")

if __name__ == "__main__":
    main()
