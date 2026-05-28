import os
import json
import time
import requests
from datetime import datetime, timezone, timedelta
from urllib.parse import quote

API_KEY = os.environ.get("NEWS_API_KEY", "")
NOW = datetime.now(timezone(timedelta(hours=8)))

# ── 翻译（Google 非官方接口，无需 Key）────────────────────
def translate(text, retries=2):
    if not text or not text.strip():
        return text
    try:
        url = (
            "https://translate.googleapis.com/translate_a/single"
            f"?client=gtx&sl=en&tl=zh-CN&dt=t&q={quote(text[:500])}"
        )
        r = requests.get(url, timeout=8)
        parts = r.json()
        result = "".join(seg[0] for seg in parts[0] if seg[0])
        time.sleep(0.15)
        return result
    except Exception:
        return text

# ── 分类配置 ──────────────────────────────────────────────
CATEGORIES = [
    {"cat":"geopolitics","label":"地缘政治","tag":"geo",
     "q":"war OR military strikes OR sanctions OR NATO OR Iran OR Ukraine","en":"en"},
    {"cat":"politics",   "label":"政治",    "tag":"pol",
     "q":"Trump OR Congress OR White House OR Senate OR election policy","en":"en"},
    {"cat":"business",   "label":"商业",    "tag":"biz",
     "q":"stock market OR economy OR Federal Reserve OR inflation OR earnings OR IPO","en":"en"},
    {"cat":"tech",       "label":"科技",    "tag":"tech",
     "q":"artificial intelligence OR semiconductor OR chip OR SpaceX OR Apple OR Google OR Tesla","en":"en"},
    {"cat":"health",     "label":"健康",    "tag":"hlth",
     "q":"medical breakthrough OR drug approval OR vaccine OR cancer treatment OR disease","en":"en"},
    {"cat":"science",    "label":"科学",    "tag":"sci",
     "q":"scientists discover OR research breakthrough OR NASA OR space OR quantum physics","en":"en"},
    {"cat":"climate",    "label":"气候",    "tag":"cli",
     "q":"climate change OR global warming OR sea level OR carbon emissions OR renewable energy","en":"en"},
]

def fetch_articles(query, page_size=4):
    if not API_KEY:
        return []
    try:
        r = requests.get(
            "https://newsapi.org/v2/everything",
            params={"q":query,"language":"en","sortBy":"publishedAt",
                    "pageSize":page_size,"apiKey":API_KEY},
            timeout=12
        )
        return r.json().get("articles", [])
    except Exception as e:
        print(f"  fetch error: {e}")
        return []

def score(a):
    s = 50
    t = ((a.get("title") or "") + " " + (a.get("description") or "")).lower()
    for w in ["war","nuclear","crisis","collapse","record","breakthrough","historic","emergency","killed"]:
        if w in t: s += 9
    for w in ["deal","vote","rate","inflation","ban","warning","risk","growth","agreement"]:
        if w in t: s += 4
    return min(s, 99)

def process_article(a, cat_info):
    title_en = (a.get("title") or "").split(" - ")[0].strip()
    desc_en  = (a.get("description") or "")[:300].strip()
    pub_date = (a.get("publishedAt") or "")[:10]
    source   = (a.get("source") or {}).get("name", "")
    print(f"  翻译: {title_en[:40]}...")
    title_zh = translate(title_en)
    desc_zh  = translate(desc_en)
    return {
        "cat":   cat_info["cat"],
        "tag":   cat_info["tag"],
        "label": cat_info["label"],
        "title": title_zh or title_en,
        "desc":  desc_zh  or desc_en,
        "url":   a.get("url", ""),
        "src":   f"{source}  ·  {pub_date}",
        "imp":   score(a),
    }

def build_data():
    feat  = None
    cards = []
    seen  = set()

    # 头条
    try:
        r = requests.get(
            "https://newsapi.org/v2/top-headlines",
            params={"language":"en","pageSize":1,"apiKey":API_KEY},
            timeout=10
        )
        arts = r.json().get("articles", [])
        if arts:
            a = arts[0]
            url = a.get("url","")
            if url: seen.add(url)
            print("处理头条...")
            feat = process_article(a, {"cat":"geopolitics","tag":"geo","label":"头条"})
            feat["imp"] = max(feat["imp"], 88)
    except Exception as e:
        print(f"头条错误: {e}")

    # 各分类
    for cat in CATEGORIES:
        print(f"\n[{cat['label']}] 抓取中...")
        arts = fetch_articles(cat["q"], page_size=5)
        count = 0
        for a in arts:
            url = a.get("url","")
            if url in seen or not a.get("title") or not a.get("description"):
                continue
            seen.add(url)
            cards.append(process_article(a, cat))
            count += 1
            if count >= 2:
                break

    return feat, cards

# ── 生成 HTML ─────────────────────────────────────────────
def generate_html(feat, cards):
    date_str  = NOW.strftime("%Y年%-m月%-d日")
    feat_json = json.dumps(feat,  ensure_ascii=False) if feat else "null"
    cards_json= json.dumps(cards, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="zh" data-theme="light">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>要闻 · {date_str}</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
:root{{
  --bg:#f5f5f3;--surface:#fff;--surface2:#fafaf8;
  --border:rgba(0,0,0,.07);--border-md:rgba(0,0,0,.11);
  --t1:#111;--t2:#444;--t3:#999;
  --accent:#d97706;--accent-dim:#fef9ee;--accent-dark:#92400e;
  --radius:10px;
  --sh:0 1px 3px rgba(0,0,0,.06),0 1px 2px rgba(0,0,0,.04);
  --sh-hover:0 6px 20px rgba(0,0,0,.1),0 2px 6px rgba(0,0,0,.06);
}}
[data-theme=dark]{{
  --bg:#0e0e0e;--surface:#191919;--surface2:#141414;
  --border:rgba(255,255,255,.07);--border-md:rgba(255,255,255,.12);
  --t1:#eee;--t2:#888;--t3:#444;
  --accent:#f59e0b;--accent-dim:#1c1608;--accent-dark:#fcd34d;
  --sh:0 1px 3px rgba(0,0,0,.5);
  --sh-hover:0 6px 20px rgba(0,0,0,.6);
}}
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0;}}
body{{background:var(--bg);color:var(--t1);font-family:'Inter',system-ui,sans-serif;font-size:14px;line-height:1.6;}}
a{{text-decoration:none;color:inherit;}}
button{{cursor:pointer;font-family:inherit;}}

/* topbar */
.topbar{{position:sticky;top:0;z-index:99;background:rgba(245,245,243,.92);backdrop-filter:blur(20px);border-bottom:1px solid var(--border);}}
[data-theme=dark] .topbar{{background:rgba(14,14,14,.92);}}
.tb{{display:flex;align-items:center;gap:10px;height:48px;padding:0 20px;max-width:1100px;margin:0 auto;}}
.logo{{font-size:15px;font-weight:700;letter-spacing:-.3px;display:flex;align-items:center;gap:7px;flex-shrink:0;}}
.ldot{{width:7px;height:7px;border-radius:50%;background:var(--accent);animation:pulse 2.2s ease-in-out infinite;}}
@keyframes pulse{{0%,100%{{opacity:1;transform:scale(1);}}50%{{opacity:.3;transform:scale(.6);}}}}
.logo-sub{{font-size:11px;font-weight:400;color:var(--t3);}}
.vsep{{width:1px;height:18px;background:var(--border-md);flex-shrink:0;}}
.ticker-wrap{{flex:1;overflow:hidden;min-width:0;}}
.ticker-track{{display:flex;gap:36px;white-space:nowrap;animation:tk 70s linear infinite;}}
.ticker-track:hover{{animation-play-state:paused;}}
@keyframes tk{{from{{transform:translateX(0);}}to{{transform:translateX(-50%);}}}}
.tk-item{{font-size:11.5px;color:var(--t2);flex-shrink:0;}}
.tk-item::before{{content:'·';color:var(--accent);margin-right:6px;font-weight:700;}}
#live-t{{font-size:11px;color:var(--t3);white-space:nowrap;font-variant-numeric:tabular-nums;flex-shrink:0;}}
.tbtn{{width:30px;height:30px;border-radius:50%;border:1px solid var(--border-md);background:var(--surface);color:var(--t2);font-size:13px;display:flex;align-items:center;justify-content:center;flex-shrink:0;}}
.prog-bar{{height:2px;background:var(--border);}}
.prog-fill{{height:100%;width:0%;background:var(--accent);transition:width .8s linear;}}

/* subnav */
.subnav{{border-bottom:1px solid var(--border);background:var(--surface);overflow-x:auto;scrollbar-width:none;}}
.subnav::-webkit-scrollbar{{display:none;}}
.sn{{display:flex;gap:2px;padding:7px 20px;max-width:1100px;margin:0 auto;}}
.np{{flex-shrink:0;padding:4px 14px;border-radius:99px;font-size:11.5px;font-weight:500;color:var(--t2);background:none;border:1px solid transparent;transition:all .12s;}}
.np:hover{{background:var(--bg);border-color:var(--border-md);color:var(--t1);}}
.np.on{{background:var(--accent-dim);color:var(--accent-dark);border-color:rgba(217,119,6,.2);}}

/* layout */
.wrap{{max-width:1100px;margin:0 auto;padding:24px 20px 80px;}}
.sec-h{{display:flex;align-items:center;gap:10px;margin:32px 0 16px;}}
.sec-h:first-child{{margin-top:0;}}
.sec-line{{flex:1;height:1px;background:var(--border);}}
.sec-title{{font-size:10px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:var(--t3);white-space:nowrap;}}
.badge{{font-size:9.5px;font-weight:600;color:var(--accent);background:var(--accent-dim);padding:2px 8px;border-radius:99px;border:1px solid rgba(217,119,6,.2);}}

/* TAG chips */
.tag{{display:inline-flex;align-items:center;font-size:9.5px;font-weight:600;letter-spacing:.05em;padding:2px 8px;border-radius:4px;margin-bottom:0;white-space:nowrap;}}
.geo {{background:#dbeafe;color:#1e3a5f;}}[data-theme=dark] .geo {{background:#1a2f46;color:#93c5fd;}}
.pol {{background:#fce7f3;color:#831843;}}[data-theme=dark] .pol {{background:#3b0a24;color:#f9a8d4;}}
.biz {{background:#d1fae5;color:#064e3b;}}[data-theme=dark] .biz {{background:#052e1c;color:#6ee7b7;}}
.tech{{background:#ede9fe;color:#4c1d95;}}[data-theme=dark] .tech{{background:#2a1545;color:#c4b5fd;}}
.hlth{{background:#fee2e2;color:#7f1d1d;}}[data-theme=dark] .hlth{{background:#380e0e;color:#fca5a5;}}
.sci {{background:#e0f2fe;color:#0c4a6e;}}[data-theme=dark] .sci {{background:#0a2535;color:#7dd3fc;}}
.cli {{background:#dcfce7;color:#14532d;}}[data-theme=dark] .cli {{background:#052612;color:#86efac;}}

/* FEATURE */
.feat{{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);box-shadow:var(--sh);overflow:hidden;margin-bottom:16px;animation:fu .5s both;}}
.feat-inner{{display:grid;grid-template-columns:1fr 200px;}}
.feat-body{{padding:22px 24px;}}
.feat-side{{border-left:1px solid var(--border);background:var(--surface2);padding:22px 18px;display:flex;flex-direction:column;gap:16px;}}
.feat-title{{font-size:clamp(17px,2vw,22px);font-weight:700;line-height:1.32;letter-spacing:-.4px;color:var(--t1);margin:10px 0 10px;}}
.feat-desc{{font-size:13px;color:var(--t2);line-height:1.72;margin-bottom:14px;}}
.feat-meta{{display:flex;align-items:center;gap:10px;flex-wrap:wrap;}}
.read-btn{{display:inline-flex;align-items:center;gap:5px;font-size:11.5px;font-weight:500;color:var(--accent);border:1px solid rgba(217,119,6,.3);padding:4px 12px;border-radius:6px;transition:background .15s;}}
.read-btn:hover{{background:var(--accent-dim);}}
.src-txt{{font-size:11px;color:var(--t3);}}
.side-lbl{{font-size:9px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:var(--t3);margin-bottom:4px;}}
.big-num{{font-size:34px;font-weight:700;letter-spacing:-.8px;color:var(--accent);line-height:1;}}
.big-sub{{font-size:10px;color:var(--t3);margin-top:2px;}}

/* IMP bar */
.imp-row{{display:flex;align-items:center;gap:8px;margin-top:12px;}}
.imp-lbl{{font-size:10px;color:var(--t3);flex-shrink:0;white-space:nowrap;}}
.imp-track{{flex:1;height:3px;background:var(--border);border-radius:99px;overflow:hidden;}}
.imp-fill{{height:100%;border-radius:99px;background:var(--accent);opacity:.7;}}
.imp-score{{font-size:10px;font-weight:600;color:var(--accent);width:22px;text-align:right;flex-shrink:0;}}

/* NEWS LIST */
.news-list{{display:flex;flex-direction:column;gap:2px;margin-bottom:16px;}}
.news-item{{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:14px 18px;display:grid;grid-template-columns:auto 1fr auto;gap:14px;align-items:start;box-shadow:var(--sh);animation:fu .4s both;transition:box-shadow .18s,transform .18s;}}
.news-item:hover{{box-shadow:var(--sh-hover);transform:translateX(2px);}}
.news-item:nth-child(2){{animation-delay:.04s;}}
.news-item:nth-child(3){{animation-delay:.08s;}}
.news-item:nth-child(4){{animation-delay:.12s;}}
.news-item:nth-child(5){{animation-delay:.16s;}}
.ni-left{{display:flex;flex-direction:column;align-items:center;gap:6px;padding-top:2px;}}
.ni-num{{font-size:11px;font-weight:700;color:var(--t3);line-height:1;}}
.ni-body{{min-width:0;}}
.ni-top{{display:flex;align-items:center;gap:8px;margin-bottom:6px;flex-wrap:wrap;}}
.ni-title{{font-size:14px;font-weight:600;line-height:1.4;letter-spacing:-.2px;color:var(--t1);margin-bottom:5px;transition:color .15s;}}
.news-item:hover .ni-title{{color:var(--accent);}}
.ni-desc{{font-size:12.5px;color:var(--t2);line-height:1.62;}}
.ni-right{{display:flex;flex-direction:column;align-items:flex-end;gap:6px;padding-top:2px;flex-shrink:0;}}
.imp-pill{{font-size:10px;font-weight:600;color:var(--accent);background:var(--accent-dim);padding:2px 8px;border-radius:99px;white-space:nowrap;}}
.ni-src{{font-size:10.5px;color:var(--t3);text-align:right;}}
.ni-link{{font-size:10.5px;font-weight:500;color:var(--accent);display:inline-flex;align-items:center;gap:3px;margin-top:8px;}}
.ni-link:hover{{text-decoration:underline;}}

.empty{{padding:60px 0;text-align:center;color:var(--t3);}}
footer{{border-top:1px solid var(--border);padding:14px 20px;display:flex;justify-content:space-between;max-width:1100px;margin:0 auto;}}
.fl,.fr{{font-size:10.5px;color:var(--t3);}}
#nxt{{color:var(--accent);}}

@keyframes fu{{from{{opacity:0;transform:translateY(6px);}}to{{opacity:1;transform:translateY(0);}}}}

@media(max-width:760px){{
  .feat-inner{{grid-template-columns:1fr;}}.feat-side{{display:none;}}
  .news-item{{grid-template-columns:auto 1fr;}}.ni-right{{display:none;}}
  .ticker-wrap,.vsep{{display:none;}}
  footer{{flex-direction:column;gap:4px;}}
  .wrap{{padding:16px 14px 60px;}}
}}
</style>
</head>
<body>

<div class="topbar">
  <div class="tb">
    <div class="logo">
      <div class="ldot"></div>要闻
      <span class="logo-sub">Dispatch</span>
    </div>
    <div class="vsep"></div>
    <div class="ticker-wrap"><div class="ticker-track" id="tk"></div></div>
    <div class="vsep"></div>
    <span id="live-t">—</span>
    <button class="tbtn" id="tbtn" title="切换主题">☀</button>
  </div>
  <div class="prog-bar"><div class="prog-fill" id="prog"></div></div>
</div>

<div class="subnav">
  <div class="sn" id="nav">
    <button class="np on" data-c="all">全部</button>
    <button class="np" data-c="geopolitics">地缘政治</button>
    <button class="np" data-c="politics">政治</button>
    <button class="np" data-c="business">商业</button>
    <button class="np" data-c="tech">科技</button>
    <button class="np" data-c="health">健康</button>
    <button class="np" data-c="science">科学</button>
    <button class="np" data-c="climate">气候</button>
  </div>
</div>

<div class="wrap" id="wrap"></div>

<footer>
  <span class="fl">要闻 · Dispatch · {date_str}</span>
  <span class="fr">下次更新 <span id="nxt">—</span> · 每日 08:00 自动刷新</span>
</footer>

<script>
const FEAT={feat_json};
const CARDS={cards_json};

// theme
let dark=false;
const tbtn=document.getElementById('tbtn');
tbtn.addEventListener('click',()=>{{
  dark=!dark;
  document.documentElement.setAttribute('data-theme',dark?'dark':'light');
  tbtn.textContent=dark?'☾':'☀';
}});

// time
function pad(n){{return String(n).padStart(2,'0');}}
setInterval(()=>{{
  const n=new Date();
  document.getElementById('live-t').textContent=
    `${{n.getFullYear()}}/${{pad(n.getMonth()+1)}}/${{pad(n.getDate())}} ${{pad(n.getHours())}}:${{pad(n.getMinutes())}}:${{pad(n.getSeconds())}}`;
}},1000);

// helpers
function tagHTML(tag,label){{return`<span class="tag ${{tag}}">${{label}}</span>`;}}

function featHTML(d){{
  if(!d)return'';
  return`<div class="feat">
    <div class="feat-inner">
      <div class="feat-body">
        <div style="display:flex;align-items:center;gap:8px;">
          ${{tagHTML(d.tag,d.label)}}
          <span class="badge">头条</span>
        </div>
        <div class="feat-title">${{d.title}}</div>
        <div class="feat-desc">${{d.desc}}</div>
        <div class="feat-meta">
          <a class="read-btn" href="${{d.url}}" target="_blank" rel="noopener">阅读原文 →</a>
          <span class="src-txt">${{d.src}}</span>
        </div>
        <div class="imp-row">
          <span class="imp-lbl">重要程度</span>
          <div class="imp-track"><div class="imp-fill" style="width:${{d.imp}}%"></div></div>
          <span class="imp-score">${{d.imp}}</span>
        </div>
      </div>
      <div class="feat-side">
        <div>
          <div class="side-lbl">重要程度</div>
          <div class="big-num">${{d.imp}}</div>
          <div class="big-sub">/ 100</div>
        </div>
        <div style="height:1px;background:var(--border);"></div>
        <div>
          <div class="side-lbl">来源</div>
          <div style="font-size:12px;color:var(--t2);margin-top:3px;">${{d.src}}</div>
        </div>
      </div>
    </div>
  </div>`;
}}

function listHTML(cards){{
  if(!cards.length)return'<div class="empty">暂无此分类新闻</div>';
  return`<div class="news-list">${{cards.map((d,i)=>`
    <div class="news-item" style="animation-delay:${{i*.04}}s">
      <div class="ni-left">
        <span class="ni-num">${{String(i+1).padStart(2,'0')}}</span>
        ${{tagHTML(d.tag,d.label)}}
      </div>
      <div class="ni-body">
        <div class="ni-title">${{d.title}}</div>
        <div class="ni-desc">${{d.desc}}</div>
        <a class="ni-link" href="${{d.url}}" target="_blank" rel="noopener">阅读原文 →</a>
      </div>
      <div class="ni-right">
        <span class="imp-pill">${{d.imp}}</span>
        <span class="ni-src">${{d.src}}</span>
      </div>
    </div>`).join('')}}</div>`;
}}

function secH(t,badge=''){{
  return`<div class="sec-h"><div class="sec-line"></div><span class="sec-title">${{t}}</span>${{badge?`<span class="badge">${{badge}}</span>`:''}} <div class="sec-line"></div></div>`;
}}

function render(cat){{
  const cards=cat==='all'?CARDS:CARDS.filter(c=>c.cat===cat);
  const showFeat=FEAT&&(cat==='all'||cat===FEAT.cat);
  let h='';
  if(showFeat){{
    h+=secH('今日头条');
    h+=featHTML(FEAT);
  }}
  h+=secH('最新要闻',cards.length+'条');
  h+=listHTML(cards);
  document.getElementById('wrap').innerHTML=h;
}}

// nav
let active='all';
document.getElementById('nav').addEventListener('click',e=>{{
  const b=e.target.closest('.np');if(!b)return;
  document.querySelectorAll('.np').forEach(x=>x.classList.remove('on'));
  b.classList.add('on');active=b.dataset.c;render(active);
}});

// ticker
const titles=(FEAT?[FEAT.title]:[]).concat(CARDS.map(c=>c.title));
const tks=titles.concat(titles);
document.getElementById('tk').innerHTML=tks.map(t=>`<span class="tk-item">${{t}}</span>`).join('');

// countdown to next 08:00 CST
function secsToNext8(){{
  const n=new Date();
  const next=new Date(n);
  next.setHours(8,0,0,0);
  if(next<=n)next.setDate(next.getDate()+1);
  return Math.floor((next-n)/1000);
}}
let rem=secsToNext8(),total=rem;
setInterval(()=>{{
  rem--;if(rem<0)rem=86400;
  document.getElementById('prog').style.width=((total-rem)/total*100)+'%';
  const hh=Math.floor(rem/3600),mm=Math.floor((rem%3600)/60),ss=rem%60;
  const el=document.getElementById('nxt');
  if(el)el.textContent=`${{hh}}时${{pad(mm)}}分${{pad(ss)}}秒`;
}},1000);

render('all');
</script>
</body>
</html>"""

def main():
    print(f"[{NOW.strftime('%Y-%m-%d %H:%M')} CST] 开始...")
    feat, cards = build_data()
    html = generate_html(feat, cards)
    with open("index.html","w",encoding="utf-8") as f:
        f.write(html)
    print(f"\n完成，共 {len(cards)} 条新闻")

if __name__ == "__main__":
    main()
