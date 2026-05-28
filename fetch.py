#!/usr/bin/env python3
"""
fetch.py — Pulse 新闻聚合引擎
每日 08:00 / 12:00 / 18:00 (CST) 由 GitHub Actions 触发
"""

import os, json, time, requests
from datetime import datetime, timezone, timedelta
from urllib.parse import quote

API_KEY = os.environ.get("NEWS_API_KEY", "37bf8ef8267f4751bd51311507429eab")
CST = timezone(timedelta(hours=8))
NOW = datetime.now(CST)

# ──────────────────────────────────────────
# 翻译（Google 非官方接口，无需 Key）
# ──────────────────────────────────────────
def translate(text, retries=2):
    if not text or not text.strip():
        return text
    for _ in range(retries):
        try:
            url = (
                "https://translate.googleapis.com/translate_a/single"
                f"?client=gtx&sl=en&tl=zh-CN&dt=t&q={quote(text[:500])}"
            )
            r = requests.get(url, timeout=8)
            parts = r.json()
            result = "".join(seg[0] for seg in parts[0] if seg[0])
            time.sleep(0.15)
            return result or text
        except Exception:
            time.sleep(0.5)
    return text

# ──────────────────────────────────────────
# 分类配置（5大类 + 头条）
# ──────────────────────────────────────────
CATEGORIES = [
    {
        "cat": "politics", "label": "政治", "tag": "pol",
        "q": 'Trump OR Congress OR "White House" OR Senate OR election OR geopolitics OR NATO OR Ukraine OR sanctions',
        "color": "#e63946"
    },
    {
        "cat": "business", "label": "商业", "tag": "biz",
        "q": '"stock market" OR economy OR "Federal Reserve" OR inflation OR earnings OR IPO OR trade OR tariff',
        "color": "#f4a261"
    },
    {
        "cat": "technology", "label": "科技", "tag": "tech",
        "q": '"artificial intelligence" OR semiconductor OR chip OR Apple OR Google OR Tesla OR SpaceX OR cybersecurity',
        "color": "#2ec4b6"
    },
    {
        "cat": "science", "label": "科学", "tag": "sci",
        "q": '"scientists discover" OR "research breakthrough" OR NASA OR space OR quantum OR "new study" OR biology',
        "color": "#a8dadc"
    },
    {
        "cat": "health", "label": "健康", "tag": "hlth",
        "q": '"medical breakthrough" OR "drug approval" OR vaccine OR cancer OR disease OR "mental health" OR FDA',
        "color": "#95d5b2"
    },
]

# ──────────────────────────────────────────
# 重要性评分
# ──────────────────────────────────────────
def score(article):
    s = 50
    t = ((article.get("title") or "") + " " + (article.get("description") or "")).lower()
    high = ["war", "nuclear", "crisis", "collapse", "record", "breakthrough",
            "historic", "emergency", "killed", "attack", "ban", "resign"]
    mid  = ["deal", "vote", "rate", "inflation", "warning", "risk",
            "agreement", "launch", "approve", "surge", "drop"]
    for w in high:
        if w in t: s += 9
    for w in mid:
        if w in t: s += 4
    return min(s, 99)

# ──────────────────────────────────────────
# 抓取
# ──────────────────────────────────────────
def fetch_articles(query, page_size=6):
    if not API_KEY:
        return []
    try:
        r = requests.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": query, "language": "en",
                "sortBy": "publishedAt",
                "pageSize": page_size,
                "apiKey": API_KEY,
            },
            timeout=12,
        )
        return r.json().get("articles", [])
    except Exception as e:
        print(f"  fetch error: {e}")
        return []

def process_article(a, cat_info):
    title_en = (a.get("title") or "").split(" - ")[0].strip()
    desc_en  = (a.get("description") or "")[:300].strip()
    pub_date = (a.get("publishedAt") or "")[:10]
    source   = (a.get("source") or {}).get("name", "")
    print(f"  翻译: {title_en[:50]}…")
    title_zh = translate(title_en)
    desc_zh  = translate(desc_en)
    return {
        "cat":   cat_info["cat"],
        "tag":   cat_info["tag"],
        "label": cat_info["label"],
        "color": cat_info.get("color", "#888"),
        "title": title_zh or title_en,
        "desc":  desc_zh  or desc_en,
        "url":   a.get("url", ""),
        "src":   f"{source}  ·  {pub_date}",
        "imp":   score(a),
    }

# ──────────────────────────────────────────
# 主数据构建（头条 1 条 + 各分类 3 条 = 16 条）
# ──────────────────────────────────────────
def build_data():
    feat  = None
    cards = []
    seen  = set()

    # 头条
    print("📰 抓取头条…")
    try:
        r = requests.get(
            "https://newsapi.org/v2/top-headlines",
            params={"language": "en", "pageSize": 3, "apiKey": API_KEY},
            timeout=10,
        )
        arts = r.json().get("articles", [])
        for a in arts:
            if a.get("title") and a.get("description"):
                url = a.get("url", "")
                if url: seen.add(url)
                feat = process_article(a, {"cat": "top", "tag": "top", "label": "头条", "color": "#e63946"})
                feat["imp"] = max(feat.get("imp", 80), 88)
                break
    except Exception as e:
        print(f"  头条错误: {e}")

    # 5 大分类，每类取 3 条
    for cat in CATEGORIES:
        print(f"\n[{cat['label']}] 抓取中…")
        arts = fetch_articles(cat["q"], page_size=8)
        count = 0
        for a in arts:
            url = a.get("url", "")
            if url in seen or not a.get("title") or not a.get("description"):
                continue
            seen.add(url)
            cards.append(process_article(a, cat))
            count += 1
            if count >= 3:
                break

    # 按重要性排序
    cards.sort(key=lambda x: x["imp"], reverse=True)
    return feat, cards[:15]

# ──────────────────────────────────────────
# HTML 生成
# ──────────────────────────────────────────
def generate_html(feat, cards):
    date_str   = NOW.strftime("%-m月%-d日")
    time_str   = NOW.strftime("%H:%M")
    weekdays   = ["周一","周二","周三","周四","周五","周六","周日"]
    weekday    = weekdays[NOW.weekday()]
    full_date  = NOW.strftime(f"%Y年{date_str}  {weekday}")
    feat_json  = json.dumps(feat,  ensure_ascii=False) if feat  else "null"
    cards_json = json.dumps(cards, ensure_ascii=False)

    # 判断本次更新时段标签
    h = NOW.hour
    if h < 10:
        update_slot = "早报"
    elif h < 14:
        update_slot = "午报"
    else:
        update_slot = "晚报"

    return f"""<!DOCTYPE html>
<html lang="zh" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="description" content="Pulse — 今日脉搏，每日精选全球15条最重要新闻">
<title>PULSE · {update_slot} · {date_str}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;900&family=Noto+Sans+SC:wght@300;400;500;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
/* ═══ PULSE CSS ═══════════════════════════════════════════ */
:root {{
  --bg:       #0a0a0b;
  --surface:  #111114;
  --card:     #16161a;
  --card2:    #1c1c22;
  --border:   rgba(255,255,255,.07);
  --bord-md:  rgba(255,255,255,.13);
  --t1: #f0ede8; --t2: #9e9b96; --t3: #5a5855;
  --red:    #e63946; --amber:  #f4a261;
  --teal:   #2ec4b6; --sky:    #a8dadc; --green: #95d5b2;
  --r: 4px;
  --tr: .22s cubic-bezier(.4,0,.2,1);
  --sh: 0 1px 3px rgba(0,0,0,.5);
  --sh2:0 8px 32px rgba(0,0,0,.6),0 2px 8px rgba(0,0,0,.4);
}}
[data-theme=light]{{
  --bg:#f4f4f2; --surface:#fff; --card:#fafaf8; --card2:#f0f0ee;
  --border:rgba(0,0,0,.07); --bord-md:rgba(0,0,0,.13);
  --t1:#111; --t2:#555; --t3:#aaa;
  --sh:0 1px 3px rgba(0,0,0,.08);
  --sh2:0 8px 32px rgba(0,0,0,.1),0 2px 8px rgba(0,0,0,.06);
}}
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0;}}
html{{scroll-behavior:smooth;}}
body{{background:var(--bg);color:var(--t1);font-family:'Noto Sans SC',system-ui,sans-serif;
  font-size:14px;line-height:1.7;min-height:100vh;overflow-x:hidden;}}
a{{text-decoration:none;color:inherit;}}
button{{cursor:pointer;font-family:inherit;border:none;background:none;}}

/* ── NOISE ── */
body::before{{
  content:''; position:fixed; inset:0; z-index:0; pointer-events:none;
  opacity:.018;
  background-image:url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
  background-size:200px;
}}

/* ── HEADER ── */
.header{{
  position:sticky;top:0;z-index:100;
  background:rgba(10,10,11,.88);
  backdrop-filter:blur(24px) saturate(1.5);
  border-bottom:1px solid var(--border);
}}
[data-theme=light] .header{{background:rgba(244,244,242,.9);}}

.hbar{{
  display:flex;align-items:center;gap:12px;
  height:52px;padding:0 24px;
  max-width:1200px;margin:0 auto;
}}
.logo{{
  display:flex;align-items:baseline;gap:6px;
  font-family:'Playfair Display',serif;
  font-size:1.5rem;font-weight:900;
  letter-spacing:.18em;color:var(--t1);
  flex-shrink:0;
}}
.logo-dot{{
  font-size:.6rem;color:var(--red);
  animation:blink 2.2s step-end infinite;
}}
@keyframes blink{{0%,100%{{opacity:1}}50%{{opacity:0}}}}
.logo-slot{{
  font-family:'JetBrains Mono',monospace;
  font-size:.6rem;color:var(--t3);
  letter-spacing:.06em;padding:2px 6px;
  border:1px solid var(--border);border-radius:3px;
  flex-shrink:0;
}}
.sep{{width:1px;height:18px;background:var(--bord-md);flex-shrink:0;}}

/* ticker */
.ticker{{flex:1;overflow:hidden;mask:linear-gradient(90deg,transparent,#000 4%,#000 96%,transparent);}}
.ticker-track{{
  display:flex;gap:40px;white-space:nowrap;
  animation:tk 80s linear infinite;
}}
.ticker-track:hover{{animation-play-state:paused;}}
@keyframes tk{{from{{transform:translateX(0)}}to{{transform:translateX(-50%)}}}}
.tk-item{{font-size:11.5px;color:var(--t2);flex-shrink:0;}}
.tk-item::before{{content:'●';font-size:5px;color:var(--red);margin-right:8px;vertical-align:middle;}}

#live-t{{
  font-family:'JetBrains Mono',monospace;
  font-size:.68rem;color:var(--t3);
  white-space:nowrap;flex-shrink:0;
}}
.icon-btn{{
  width:32px;height:32px;border-radius:50%;
  border:1px solid var(--bord-md);background:var(--card);
  color:var(--t2);font-size:13px;
  display:flex;align-items:center;justify-content:center;
  transition:background var(--tr),color var(--tr);flex-shrink:0;
}}
.icon-btn:hover{{background:var(--card2);color:var(--t1);}}

/* progress bar */
.pbar{{height:2px;background:var(--border);}}
.pfill{{height:100%;background:linear-gradient(90deg,var(--red),var(--amber));width:0;transition:width .8s linear;}}

/* ── NAV ── */
.subnav{{
  background:var(--surface);
  border-bottom:1px solid var(--border);
  overflow-x:auto;scrollbar-width:none;
}}
.subnav::-webkit-scrollbar{{display:none;}}
.sn{{display:flex;padding:0 24px;max-width:1200px;margin:0 auto;}}
.np{{
  padding:10px 16px;font-size:.78rem;font-weight:500;
  color:var(--t2);border-bottom:2px solid transparent;
  white-space:nowrap;transition:color var(--tr),border-color var(--tr);
}}
.np:hover{{color:var(--t1);}}
.np.on{{color:var(--t1);border-color:var(--red);}}

/* ── LAYOUT ── */
.wrap{{max-width:1200px;margin:0 auto;padding:32px 24px 80px;}}

.sec-lbl{{
  display:flex;align-items:center;gap:12px;
  margin:40px 0 18px;
}}
.sec-lbl:first-child{{margin-top:0;}}
.sl-text{{
  font-family:'JetBrains Mono',monospace;
  font-size:.6rem;letter-spacing:.2em;
  text-transform:uppercase;color:var(--red);
  white-space:nowrap;
}}
.sl-line{{flex:1;height:1px;background:linear-gradient(90deg,var(--bord-md),transparent);}}
.sl-badge{{
  font-family:'JetBrains Mono',monospace;
  font-size:.58rem;color:var(--t3);white-space:nowrap;
}}

/* ── CATEGORY CHIPS ── */
.chip{{
  display:inline-flex;align-items:center;
  font-family:'JetBrains Mono',monospace;
  font-size:.58rem;font-weight:500;letter-spacing:.1em;
  padding:2px 8px;border-radius:3px;
  text-transform:uppercase;white-space:nowrap;
}}
.chip-pol  {{background:rgba(230,57,70,.15); color:#e63946;}}
.chip-biz  {{background:rgba(244,162,97,.15);color:#f4a261;}}
.chip-tech {{background:rgba(46,196,182,.15);color:#2ec4b6;}}
.chip-sci  {{background:rgba(168,218,220,.15);color:#a8dadc;}}
.chip-hlth {{background:rgba(149,213,178,.15);color:#95d5b2;}}
.chip-top  {{background:rgba(230,57,70,.2); color:#e63946;}}

/* ── HERO ── */
.hero{{
  background:var(--card);border:1px solid var(--border);
  border-radius:var(--r);overflow:hidden;
  box-shadow:var(--sh2);
  display:grid;grid-template-columns:1fr 180px;
  animation:fadeUp .5s both;
}}
.hero-body{{padding:28px 32px;}}
.hero-top{{display:flex;align-items:center;gap:10px;margin-bottom:14px;}}
.hero-badge{{
  font-family:'JetBrains Mono',monospace;
  font-size:.58rem;letter-spacing:.15em;
  padding:3px 8px;border-radius:3px;
  background:var(--red);color:#fff;
}}
.hero-title{{
  font-family:'Playfair Display',serif;
  font-size:clamp(1.4rem,2.5vw,2rem);
  font-weight:700;line-height:1.25;
  letter-spacing:-.02em;color:var(--t1);
  margin-bottom:14px;
  transition:color var(--tr);
}}
.hero:hover .hero-title{{color:var(--red);}}
.hero-desc{{font-size:.88rem;color:var(--t2);line-height:1.8;margin-bottom:18px;}}
.hero-meta{{display:flex;align-items:center;gap:12px;flex-wrap:wrap;}}
.read-link{{
  display:inline-flex;align-items:center;gap:5px;
  font-family:'JetBrains Mono',monospace;
  font-size:.68rem;color:var(--red);
  border:1px solid rgba(230,57,70,.35);
  padding:4px 12px;border-radius:3px;
  transition:background var(--tr);
}}
.read-link:hover{{background:rgba(230,57,70,.12);}}
.src-txt{{font-family:'JetBrains Mono',monospace;font-size:.65rem;color:var(--t3);}}
.imp-row{{display:flex;align-items:center;gap:8px;margin-top:14px;}}
.imp-lbl{{font-family:'JetBrains Mono',monospace;font-size:.6rem;color:var(--t3);flex-shrink:0;}}
.imp-track{{flex:1;height:2px;background:var(--border);border-radius:2px;overflow:hidden;}}
.imp-fill{{height:100%;background:linear-gradient(90deg,var(--red),var(--amber));border-radius:2px;}}
.imp-num{{font-family:'JetBrains Mono',monospace;font-size:.6rem;color:var(--amber);width:22px;text-align:right;flex-shrink:0;}}

/* hero side */
.hero-side{{
  border-left:1px solid var(--border);
  background:rgba(255,255,255,.02);
  padding:28px 20px;
  display:flex;flex-direction:column;justify-content:center;gap:20px;
}}
[data-theme=light] .hero-side{{background:rgba(0,0,0,.02);}}
.hs-lbl{{
  font-family:'JetBrains Mono',monospace;
  font-size:.55rem;letter-spacing:.15em;
  text-transform:uppercase;color:var(--t3);margin-bottom:4px;
}}
.hs-big{{
  font-family:'Playfair Display',serif;
  font-size:2.4rem;font-weight:900;
  color:var(--amber);line-height:1;
}}
.hs-sub{{font-family:'JetBrains Mono',monospace;font-size:.6rem;color:var(--t3);margin-top:2px;}}

/* ── NEWS LIST ── */
.news-list{{display:flex;flex-direction:column;}}
.ni{{
  display:grid;grid-template-columns:28px 1fr 80px;
  gap:16px;align-items:start;
  padding:18px 12px;
  border-bottom:1px solid var(--border);
  cursor:pointer;
  transition:background var(--tr);
  text-decoration:none;color:inherit;
  animation:fadeUp .45s both;
}}
.ni:hover{{background:var(--card);}}
.ni:last-child{{border-bottom:none;}}
.ni-num{{
  font-family:'JetBrains Mono',monospace;
  font-size:.65rem;color:var(--t3);
  padding-top:3px;text-align:right;
}}
.ni-body{{min-width:0;}}
.ni-top{{display:flex;align-items:center;gap:8px;margin-bottom:6px;flex-wrap:wrap;}}
.ni-title{{
  font-size:.95rem;font-weight:600;
  line-height:1.5;color:var(--t1);
  margin-bottom:5px;
  transition:color var(--tr);
}}
.ni:hover .ni-title{{color:var(--red);}}
.ni-desc{{
  font-size:.8rem;color:var(--t2);line-height:1.7;
  display:-webkit-box;-webkit-line-clamp:2;
  -webkit-box-orient:vertical;overflow:hidden;
}}
.ni-meta{{
  font-family:'JetBrains Mono',monospace;
  font-size:.6rem;color:var(--t3);margin-top:6px;
}}
.ni-right{{
  display:flex;flex-direction:column;
  align-items:flex-end;gap:6px;padding-top:3px;
}}
.imp-pill{{
  font-family:'JetBrains Mono',monospace;
  font-size:.6rem;font-weight:500;
  color:var(--amber);
  border:1px solid rgba(244,162,97,.3);
  padding:2px 8px;border-radius:3px;white-space:nowrap;
}}

/* ── FOOTER ── */
.site-footer{{
  border-top:1px solid var(--border);
  padding:16px 24px;margin-top:0;
}}
.footer-inner{{
  display:flex;align-items:center;justify-content:space-between;
  max-width:1200px;margin:0 auto;flex-wrap:wrap;gap:8px;
}}
.fl,.fr{{
  font-family:'JetBrains Mono',monospace;
  font-size:.62rem;color:var(--t3);
}}
#nxt{{color:var(--amber);}}

/* ── ANIM ── */
@keyframes fadeUp{{from{{opacity:0;transform:translateY(10px)}}to{{opacity:1;transform:translateY(0)}}}}

/* ── RESPONSIVE ── */
@media(max-width:780px){{
  .hbar{{padding:0 16px;}}
  .ticker,.sep{{display:none;}}
  .hero{{grid-template-columns:1fr;}}
  .hero-side{{display:none;}}
  .ni{{grid-template-columns:24px 1fr;}}
  .ni-right{{display:none;}}
  .wrap{{padding:20px 16px 60px;}}
  .sn{{padding:0 12px;}}
  .hero-body{{padding:20px;}}
}}
</style>
</head>
<body>

<!-- ═══ HEADER ═══════════════════════════════════════════ -->
<header class="header">
  <div class="hbar">
    <div class="logo">
      PULSE<span class="logo-dot">●</span>
    </div>
    <span class="logo-slot" id="slotLabel">{update_slot}</span>
    <div class="sep"></div>
    <div class="ticker"><div class="ticker-track" id="tk"></div></div>
    <div class="sep"></div>
    <span id="live-t">—</span>
    <button class="icon-btn" id="themeBtn" title="切换主题">☀</button>
  </div>
  <div class="pbar"><div class="pfill" id="prog"></div></div>
</header>

<!-- ═══ SUBNAV ════════════════════════════════════════════ -->
<nav class="subnav">
  <div class="sn" id="nav">
    <button class="np on" data-c="all">全部</button>
    <button class="np" data-c="politics">政治</button>
    <button class="np" data-c="business">商业</button>
    <button class="np" data-c="technology">科技</button>
    <button class="np" data-c="science">科学</button>
    <button class="np" data-c="health">健康</button>
  </div>
</nav>

<!-- ═══ MAIN ══════════════════════════════════════════════ -->
<main class="wrap" id="wrap"></main>

<!-- ═══ FOOTER ════════════════════════════════════════════ -->
<footer class="site-footer">
  <div class="footer-inner">
    <span class="fl">PULSE · 今日脉搏 · {full_date} {time_str} 更新</span>
    <span class="fr">下次更新 <span id="nxt">—</span> · 每日 08:00 / 12:00 / 18:00</span>
  </div>
</footer>

<script>
// ── 数据 ──────────────────────────────────────────────────
const FEAT  = {feat_json};
const CARDS = {cards_json};

// ── 主题切换 ───────────────────────────────────────────────
let dark = true;
const themeBtn = document.getElementById('themeBtn');
themeBtn.addEventListener('click', () => {{
  dark = !dark;
  document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
  themeBtn.textContent = dark ? '☀' : '☾';
}});

// ── 实时时钟 ───────────────────────────────────────────────
function pad(n) {{ return String(n).padStart(2,'0'); }}
setInterval(() => {{
  const n = new Date();
  document.getElementById('live-t').textContent =
    `${{n.getFullYear()}}/${{pad(n.getMonth()+1)}}/${{pad(n.getDate())}} ${{pad(n.getHours())}}:${{pad(n.getMinutes())}}:${{pad(n.getSeconds())}}`;
}}, 1000);

// ── 倒计时（下一个整点：08/12/18）─────────────────────────
function secsToNextSlot() {{
  const n = new Date();
  const h = n.getHours(), m = n.getMinutes(), s = n.getSeconds();
  const slots = [8,12,18];
  const nowSec = h*3600 + m*60 + s;
  for (const sh of slots) {{
    const target = sh*3600;
    if (target > nowSec) return target - nowSec;
  }}
  return 8*3600 + (86400 - nowSec); // 明天08:00
}}
let rem = secsToNextSlot(), total = rem;
setInterval(() => {{
  rem--; if (rem < 0) {{ rem = secsToNextSlot(); total = rem; }}
  document.getElementById('prog').style.width = ((total-rem)/total*100) + '%';
  const hh=Math.floor(rem/3600), mm=Math.floor((rem%3600)/60), ss=rem%60;
  const el = document.getElementById('nxt');
  if (el) el.textContent = `${{hh}}时${{pad(mm)}}分${{pad(ss)}}秒`;
}}, 1000);

// ── chip HTML ──────────────────────────────────────────────
function chip(tag, label) {{
  return `<span class="chip chip-${{tag}}">${{label}}</span>`;
}}

// ── Hero ───────────────────────────────────────────────────
function heroHTML(d) {{
  if (!d) return '';
  return `
  <div class="hero">
    <div class="hero-body">
      <div class="hero-top">
        ${{chip(d.tag, d.label)}}
        <span class="hero-badge">HEAD LINE</span>
      </div>
      <a href="${{d.url}}" target="_blank" rel="noopener">
        <h1 class="hero-title">${{d.title}}</h1>
      </a>
      <p class="hero-desc">${{d.desc}}</p>
      <div class="hero-meta">
        <a class="read-link" href="${{d.url}}" target="_blank" rel="noopener">阅读原文 ↗</a>
        <span class="src-txt">${{d.src}}</span>
      </div>
      <div class="imp-row">
        <span class="imp-lbl">重要指数</span>
        <div class="imp-track"><div class="imp-fill" style="width:${{d.imp}}%"></div></div>
        <span class="imp-num">${{d.imp}}</span>
      </div>
    </div>
    <div class="hero-side">
      <div>
        <div class="hs-lbl">重要指数</div>
        <div class="hs-big">${{d.imp}}</div>
        <div class="hs-sub">/ 100</div>
      </div>
      <div style="height:1px;background:var(--border)"></div>
      <div>
        <div class="hs-lbl">数据来源</div>
        <div style="font-size:.75rem;color:var(--t2);margin-top:4px;line-height:1.6">${{d.src}}</div>
      </div>
    </div>
  </div>`;
}}

// ── List ───────────────────────────────────────────────────
function listHTML(cards) {{
  if (!cards.length) return '<p style="color:var(--t3);padding:40px 0;text-align:center;font-size:.8rem;">暂无此分类新闻</p>';
  return '<div class="news-list">' + cards.map((d,i) => `
    <a class="ni" href="${{d.url}}" target="_blank" rel="noopener" style="animation-delay:${{i*.04}}s">
      <span class="ni-num">${{String(i+1).padStart(2,'0')}}</span>
      <div class="ni-body">
        <div class="ni-top">${{chip(d.tag, d.label)}}</div>
        <div class="ni-title">${{d.title}}</div>
        <div class="ni-desc">${{d.desc}}</div>
        <div class="ni-meta">${{d.src}}</div>
      </div>
      <div class="ni-right">
        <span class="imp-pill">${{d.imp}}</span>
      </div>
    </a>`).join('') + '</div>';
}}

// ── Section label ──────────────────────────────────────────
function secLbl(text, badge='') {{
  return `<div class="sec-lbl">
    <span class="sl-text">${{text}}</span>
    <div class="sl-line"></div>
    ${{badge ? `<span class="sl-badge">${{badge}}</span>` : ''}}
  </div>`;
}}

// ── Render ─────────────────────────────────────────────────
const CAT_NAMES = {{
  politics:'政治', business:'商业', technology:'科技', science:'科学', health:'健康'
}};

function render(cat) {{
  const filtered = cat === 'all' ? CARDS : CARDS.filter(c => c.cat === cat);
  const showFeat = FEAT && (cat === 'all' || cat === FEAT.cat);
  let h = '';
  if (showFeat) {{
    h += secLbl('今日头条');
    h += heroHTML(FEAT);
  }}
  const label = cat === 'all' ? '今日要闻' : (CAT_NAMES[cat] || cat);
  h += secLbl(label, filtered.length + ' 条');
  h += listHTML(filtered);
  document.getElementById('wrap').innerHTML = h;
}}

// ── Nav ────────────────────────────────────────────────────
document.getElementById('nav').addEventListener('click', e => {{
  const b = e.target.closest('.np'); if (!b) return;
  document.querySelectorAll('.np').forEach(x => x.classList.remove('on'));
  b.classList.add('on');
  render(b.dataset.c);
}});

// ── Ticker ─────────────────────────────────────────────────
const titles = (FEAT ? [FEAT.title] : []).concat(CARDS.map(c => c.title));
const doubled = titles.concat(titles);
document.getElementById('tk').innerHTML =
  doubled.map(t => `<span class="tk-item">${{t}}</span>`).join('');

// ── Init ───────────────────────────────────────────────────
render('all');
</script>
</body>
</html>"""

def main():
    print(f"\n{'='*50}")
    print(f"PULSE 新闻引擎  {NOW.strftime('%Y-%m-%d %H:%M')} CST")
    print(f"{'='*50}\n")
    feat, cards = build_data()
    html = generate_html(feat, cards)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n✅ 完成：头条 1 条 + 要闻 {len(cards)} 条")
    print(f"   文件：index.html")

if __name__ == "__main__":
    main()
