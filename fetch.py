#!/usr/bin/env python3
"""
fetch.py — Pulse 新闻引擎 v3
策略：质量优先 + 智能分类
- 抓取来源：top-headlines（质量最高）+ 精选权威来源
- 分类方式：内容关键词二次分类（不按搜索词强行归类）
- 筛选方式：综合评分取前 15 条
"""

import os, json, time, requests
from datetime import datetime, timezone, timedelta
from urllib.parse import quote

API_KEY = os.environ.get("NEWS_API_KEY", "37bf8ef8267f4751bd51311507429eab")
CST = timezone(timedelta(hours=8))
NOW = datetime.now(CST)

# ── 权威来源白名单（NewsAPI source id）──────────────────────
TRUSTED_SOURCES = [
    "reuters", "associated-press", "bbc-news", "the-new-york-times",
    "the-washington-post", "financial-times", "the-economist",
    "bloomberg", "the-wall-street-journal", "axios", "politico",
    "abc-news", "cbs-news", "nbc-news", "cnn", "npr",
    "ars-technica", "wired", "techcrunch", "the-verge",
    "national-geographic", "new-scientist", "science-daily",
    "medical-news-today", "health-day",
    "al-jazeera-english", "bbc-sport", "time", "fortune", "mit-technology-review",
]

# ── 分类判断规则（关键词 → 分类）────────────────────────────
# 顺序重要：越前面优先级越高
CLASSIFY_RULES = [
    ("health", [
        "health", "medical", "medicine", "hospital", "disease", "virus", "vaccine",
        "cancer", "drug", "fda", "cdc", "mental health", "obesity", "diabetes",
        "surgery", "clinical trial", "pandemic", "epidemic", "patient", "doctor",
        "pharmaceutical", "therapy", "treatment", "symptom", "nutrition",
    ]),
    ("science", [
        "scientists", "research", "study finds", "researchers", "discovery",
        "nasa", "space", "universe", "planet", "asteroid", "black hole", "galaxy",
        "quantum", "physics", "biology", "chemistry", "genome", "dna", "fossil",
        "climate", "ocean", "earthquake", "volcano", "species", "evolution",
        "experiment", "laboratory", "scientific",
    ]),
    ("technology", [
        "artificial intelligence", "ai ", " ai,", "openai", "chatgpt", "google", "apple",
        "microsoft", "meta ", "amazon", "tesla", "spacex", "nvidia", "semiconductor",
        "chip", "software", "app", "startup", "cybersecurity", "hack", "data breach",
        "robot", "autonomous", "electric vehicle", "ev ", "battery", "tech ",
        "social media", "twitter", "x.com", "tiktok", "algorithm",
    ]),
    ("business", [
        "economy", "economic", "market", "stock", "share", "fund", "investor",
        "gdp", "inflation", "recession", "interest rate", "federal reserve", "central bank",
        "trade", "tariff", "export", "import", "deal", "merger", "acquisition",
        "ipo", "earnings", "profit", "revenue", "bank", "finance", "debt",
        "imf", "world bank", "wto", "oil", "energy price", "supply chain",
    ]),
    ("politics", [
        "president", "congress", "senate", "parliament", "government", "minister",
        "election", "vote", "policy", "law", "legislation", "democrat", "republican",
        "trump", "biden", "white house", "nato", "un ", "united nations", "sanctions",
        "war", "military", "troops", "attack", "conflict", "treaty", "diplomat",
        "ukraine", "russia", "china", "taiwan", "middle east", "israel", "iran",
        "refugee", "immigration", "border", "protest", "coup",
    ]),
]

def classify(title, desc):
    text = (title + " " + (desc or "")).lower()
    for cat, keywords in CLASSIFY_RULES:
        for kw in keywords:
            if kw in text:
                return cat
    return "politics"  # 默认归政治/综合

# ── 翻译（Google 非官方，无需 Key）──────────────────────────
def translate(text, retries=2):
    if not text or not text.strip():
        return text
    for _ in range(retries):
        try:
            url = ("https://translate.googleapis.com/translate_a/single"
                   f"?client=gtx&sl=en&tl=zh-CN&dt=t&q={quote(text[:500])}")
            r = requests.get(url, timeout=8)
            parts = r.json()
            result = "".join(seg[0] for seg in parts[0] if seg[0])
            time.sleep(0.12)
            return result or text
        except Exception:
            time.sleep(0.6)
    return text

# ── 质量评分 ─────────────────────────────────────────────────
TRUSTED_DOMAIN_KEYWORDS = [
    "reuters", "bbc", "nytimes", "washingtonpost", "bloomberg",
    "wsj", "ft.com", "economist", "axios", "apnews", "theguardian",
    "nature.com", "science.org", "techcrunch", "wired", "politico",
]

HIGH_IMPACT = [
    "killed", "dead", "death", "war", "attack", "strike", "explosion",
    "crisis", "collapse", "emergency", "historic", "record", "breakthrough",
    "nuclear", "sanctions", "resign", "arrested", "sentenced", "acquitted",
    "crash", "disaster", "catastrophe", "breakthrough", "ban", "signed",
]
MED_IMPACT = [
    "deal", "agreement", "vote", "approved", "rejected", "launched",
    "announced", "warning", "risk", "surge", "drop", "rise", "fall",
    "investigation", "report", "study", "data", "growth", "decline",
]
LOW_QUALITY = [
    "quiz", "ranking", "top 10", "best of", "how to", "watch live",
    "live updates", "photos:", "video:", "why you should", "what to know",
    "here's what", "everything you need", "listicle",
]

def score(article):
    title = (article.get("title") or "").lower()
    desc  = (article.get("description") or "").lower()
    url   = (article.get("url") or "").lower()
    src   = (article.get("source") or {}).get("id", "")
    text  = title + " " + desc

    s = 50

    # 来源权威性
    if src in TRUSTED_SOURCES:
        s += 20
    for d in TRUSTED_DOMAIN_KEYWORDS:
        if d in url:
            s += 10
            break

    # 高影响词
    for w in HIGH_IMPACT:
        if w in text:
            s += 10
    # 中等影响词
    for w in MED_IMPACT:
        if w in text:
            s += 4

    # 质量惩罚
    for w in LOW_QUALITY:
        if w in title:
            s -= 25

    # 有描述奖励
    if article.get("description") and len(article.get("description", "")) > 80:
        s += 8

    # 有图片奖励
    if article.get("urlToImage"):
        s += 3

    # 标题过短或过长惩罚
    tlen = len(article.get("title") or "")
    if tlen < 20 or tlen > 200:
        s -= 15

    return max(0, min(99, s))

# ── 抓取 ─────────────────────────────────────────────────────
def fetch_top_headlines(country="us", page_size=30):
    try:
        r = requests.get("https://newsapi.org/v2/top-headlines",
            params={"country": country, "pageSize": page_size, "apiKey": API_KEY},
            timeout=12)
        return r.json().get("articles", [])
    except Exception as e:
        print(f"  [!] top-headlines/{country} 失败: {e}")
        return []

def fetch_top_headlines_category(category, page_size=20):
    """NewsAPI 官方分类接口（质量更高）"""
    try:
        r = requests.get("https://newsapi.org/v2/top-headlines",
            params={"category": category, "language": "en",
                    "pageSize": page_size, "apiKey": API_KEY},
            timeout=12)
        return r.json().get("articles", [])
    except Exception as e:
        print(f"  [!] top-headlines/{category} 失败: {e}")
        return []

def fetch_sources_headlines(sources, page_size=20):
    """按权威来源抓取"""
    src_str = ",".join(sources[:20])
    try:
        r = requests.get("https://newsapi.org/v2/top-headlines",
            params={"sources": src_str, "pageSize": page_size, "apiKey": API_KEY},
            timeout=12)
        return r.json().get("articles", [])
    except Exception as e:
        print(f"  [!] sources 失败: {e}")
        return []

# ── 主流程 ────────────────────────────────────────────────────
def build_data():
    print("\n── 抓取新闻 ───────────────────────────────────")
    raw = []
    seen_urls = set()
    seen_titles = set()

    def add(articles, label=""):
        for a in articles:
            url   = a.get("url", "")
            title = (a.get("title") or "").strip()
            if not url or url in seen_urls: continue
            if not title or title == "[Removed]": continue
            # 相似标题去重（前30字）
            t30 = title[:30].lower()
            if t30 in seen_titles: continue
            if not a.get("description"): continue
            seen_urls.add(url)
            seen_titles.add(t30)
            raw.append(a)
        print(f"  {label}: 累计 {len(raw)} 条")

    # 1. 权威来源直接抓（质量最高）
    print("[1] 权威来源头条…")
    tier1 = ["reuters", "associated-press", "bbc-news",
             "the-new-york-times", "bloomberg", "financial-times",
             "the-wall-street-journal", "the-economist"]
    add(fetch_sources_headlines(tier1, 30), "权威来源")
    time.sleep(0.3)

    # 2. NewsAPI 官方分类（business/technology/health/science/general）
    print("[2] 官方分类头条…")
    for cat in ["general", "business", "technology", "health", "science"]:
        add(fetch_top_headlines_category(cat, 20), cat)
        time.sleep(0.2)

    # 3. 美英头条补充
    print("[3] 美英综合头条…")
    for country in ["us", "gb"]:
        add(fetch_top_headlines(country, 30), country)
        time.sleep(0.2)

    print(f"\n── 去重后共 {len(raw)} 条，开始评分…")

    # 评分 + 排序
    scored = []
    for a in raw:
        s = score(a)
        if s >= 40:  # 过滤低质量
            scored.append((s, a))
    scored.sort(key=lambda x: x[0], reverse=True)

    print(f"── 评分 ≥40 共 {len(scored)} 条，取前 16 条翻译…")

    # 取前 16 条（1 头条 + 15 要闻）
    top = scored[:16]

    # 翻译 + 分类
    result = []
    for imp, a in top:
        title_en = (a.get("title") or "").split(" - ")[0].strip()
        desc_en  = (a.get("description") or "")[:300].strip()
        pub_date = (a.get("publishedAt") or "")[:10]
        source   = (a.get("source") or {}).get("name", "")

        print(f"  [{imp}] 翻译: {title_en[:45]}…")
        title_zh = translate(title_en)
        time.sleep(0.1)
        desc_zh = translate(desc_en)
        time.sleep(0.1)

        cat = classify(title_en, desc_en)
        CAT_META = {
            "politics":   {"label":"政治",  "tag":"pol"},
            "business":   {"label":"商业",  "tag":"biz"},
            "technology": {"label":"科技",  "tag":"tech"},
            "science":    {"label":"科学",  "tag":"sci"},
            "health":     {"label":"健康",  "tag":"hlth"},
        }
        cm = CAT_META.get(cat, CAT_META["politics"])

        result.append({
            "cat":   cat,
            "tag":   cm["tag"],
            "label": cm["label"],
            "title": title_zh or title_en,
            "desc":  desc_zh  or desc_en,
            "url":   a.get("url", ""),
            "img":   a.get("urlToImage", ""),
            "src":   f"{source}  ·  {pub_date}",
            "imp":   imp,
        })

    feat  = result[0]  if result    else None
    cards = result[1:] if len(result) > 1 else []

    # 确保头条是最高分
    if feat:
        feat["imp"] = max(feat["imp"], 88)

    return feat, cards

# ── HTML 生成 ─────────────────────────────────────────────────
def generate_html(feat, cards):
    date_str  = NOW.strftime("%-m月%-d日")
    weekdays  = ["周一","周二","周三","周四","周五","周六","周日"]
    weekday   = weekdays[NOW.weekday()]
    full_date = NOW.strftime(f"%Y年{date_str}  {weekday}")
    time_str  = NOW.strftime("%H:%M")
    h = NOW.hour
    update_slot = "早报" if h < 10 else ("午报" if h < 14 else "晚报")

    feat_json  = json.dumps(feat,  ensure_ascii=False) if feat  else "null"
    cards_json = json.dumps(cards, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<meta name="description" content="Pulse — 每日精选全球最有价值的15条新闻">
<title>PULSE · {update_slot} · {date_str}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;600;700&family=Noto+Sans+SC:wght@300;400;500&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{{
  --bg:#f7f6f3;
  --surface:#ffffff;
  --surface2:#fafaf8;
  --border:rgba(0,0,0,.07);
  --border-md:rgba(0,0,0,.12);
  --t1:#1a1a1a;
  --t2:#5a5a5a;
  --t3:#a0a09a;
  --red:#c0392b;
  --red-bg:#fdf2f1;
  --amber:#b7791f;
  --amber-bg:#fffbeb;
  --r:6px;
  --tr:.18s ease;
}}
@media(prefers-color-scheme:dark){{
  :root{{
    --bg:#111110;--surface:#1c1c1a;--surface2:#181816;
    --border:rgba(255,255,255,.07);--border-md:rgba(255,255,255,.13);
    --t1:#ede9e3;--t2:#9a9690;--t3:#5a5652;
    --red:#e05a4f;--red-bg:rgba(192,57,43,.12);
    --amber:#e9a825;--amber-bg:rgba(183,121,31,.12);
  }}
}}
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0;}}
html{{scroll-behavior:smooth;}}
body{{background:var(--bg);color:var(--t1);font-family:'Noto Sans SC',system-ui,sans-serif;font-size:14px;line-height:1.7;}}
a{{text-decoration:none;color:inherit;}}
button{{cursor:pointer;font-family:inherit;border:none;background:none;}}

.header{{
  position:sticky;top:0;z-index:50;
  background:rgba(247,246,243,.95);
  backdrop-filter:blur(16px);
  border-bottom:1px solid var(--border);
}}
@media(prefers-color-scheme:dark){{
  .header{{background:rgba(17,17,16,.95);}}
}}
.hbar{{
  display:flex;align-items:center;gap:10px;
  height:48px;padding:0 20px;max-width:1080px;margin:0 auto;
}}
.logo{{
  font-family:'Noto Serif SC',serif;
  font-size:1.35rem;font-weight:700;
  letter-spacing:.06em;color:var(--t1);
  flex-shrink:0;
  display:flex;align-items:center;gap:4px;
}}
.logo-dot{{
  width:6px;height:6px;border-radius:50%;
  background:var(--red);margin-left:1px;
  animation:blink 2.4s step-end infinite;
}}
@keyframes blink{{0%,100%{{opacity:1}}50%{{opacity:0}}}}
.slot-tag{{
  font-family:'JetBrains Mono',monospace;
  font-size:.6rem;padding:2px 7px;
  background:var(--amber-bg);color:var(--amber);
  border:1px solid rgba(183,121,31,.2);border-radius:3px;
  flex-shrink:0;
}}
.vsep{{width:1px;height:16px;background:var(--border-md);flex-shrink:0;}}
.ticker{{
  flex:1;overflow:hidden;
  mask:linear-gradient(90deg,transparent,#000 5%,#000 95%,transparent);
  -webkit-mask:linear-gradient(90deg,transparent,#000 5%,#000 95%,transparent);
}}
.ticker-inner{{
  display:flex;gap:32px;white-space:nowrap;
  animation:scroll 90s linear infinite;
}}
.ticker-inner:hover{{animation-play-state:paused;}}
@keyframes scroll{{0%{{transform:translateX(0)}}100%{{transform:translateX(-50%)}}}}
.tk-item{{font-size:11.5px;color:var(--t2);flex-shrink:0;}}
.tk-item::before{{content:'·';color:var(--red);margin-right:6px;font-weight:700;}}
.clock{{
  font-family:'JetBrains Mono',monospace;
  font-size:.65rem;color:var(--t3);white-space:nowrap;flex-shrink:0;
}}
.theme-btn{{
  width:30px;height:30px;border-radius:50%;
  border:1px solid var(--border-md);
  color:var(--t2);font-size:14px;
  display:flex;align-items:center;justify-content:center;
  flex-shrink:0;
  transition:background var(--tr);
}}
.theme-btn:hover{{background:var(--surface2);}}
.pbar{{height:1.5px;background:var(--border);}}
.pfill{{height:100%;background:linear-gradient(90deg,var(--red),var(--amber));width:0;transition:width 1s linear;}}

.subnav{{
  background:var(--surface);
  border-bottom:1px solid var(--border);
  overflow-x:auto;scrollbar-width:none;
}}
.subnav::-webkit-scrollbar{{display:none;}}
.sninner{{
  display:flex;padding:0 20px;
  max-width:1080px;margin:0 auto;
}}
.nb{{
  padding:9px 16px;font-size:.78rem;font-weight:400;
  color:var(--t2);border-bottom:2px solid transparent;
  white-space:nowrap;transition:color var(--tr),border-color var(--tr);
  flex-shrink:0;
}}
.nb:hover{{color:var(--t1);}}
.nb.on{{color:var(--t1);font-weight:500;border-color:var(--red);}}

.wrap{{max-width:1080px;margin:0 auto;padding:28px 20px 80px;}}

.sec{{
  display:flex;align-items:center;gap:10px;
  margin:36px 0 16px;
}}
.sec:first-child{{margin-top:0;}}
.sec-t{{
  font-family:'JetBrains Mono',monospace;
  font-size:.58rem;letter-spacing:.2em;text-transform:uppercase;
  color:var(--red);white-space:nowrap;
}}
.sec-line{{flex:1;height:1px;background:var(--border);}}
.sec-badge{{
  font-family:'JetBrains Mono',monospace;
  font-size:.58rem;color:var(--t3);white-space:nowrap;
}}

/* chip */
.chip{{
  display:inline-block;
  font-family:'JetBrains Mono',monospace;
  font-size:.58rem;letter-spacing:.06em;
  padding:2px 7px;border-radius:3px;
  white-space:nowrap;
}}
.pol {{background:rgba(157,23,77,.1);   color:#9d174d;}}
.biz {{background:rgba(120,53,15,.1);   color:#92400e;}}
.tech{{background:rgba(6,78,59,.1);     color:#065f46;}}
.sci {{background:rgba(12,74,110,.1);   color:#0c4a6e;}}
.hlth{{background:rgba(55,65,81,.1);    color:#374151;}}
@media(prefers-color-scheme:dark){{
  .pol {{background:rgba(157,23,77,.18); color:#f9a8d4;}}
  .biz {{background:rgba(217,119,6,.15); color:#fcd34d;}}
  .tech{{background:rgba(16,185,129,.12);color:#6ee7b7;}}
  .sci {{background:rgba(59,130,246,.12);color:#93c5fd;}}
  .hlth{{background:rgba(156,163,175,.1);color:#d1d5db;}}
}}

/* hero */
.hero{{
  background:var(--surface);
  border:1px solid var(--border);
  border-radius:var(--r);
  overflow:hidden;
  display:grid;grid-template-columns:1fr 160px;
  margin-bottom:24px;
}}
.hero-body{{padding:24px 28px;}}
.hero-top{{display:flex;align-items:center;gap:8px;margin-bottom:12px;}}
.headline-badge{{
  font-family:'JetBrains Mono',monospace;
  font-size:.56rem;letter-spacing:.12em;
  padding:2px 8px;border-radius:3px;
  background:var(--red);color:#fff;
}}
.hero-title{{
  font-family:'Noto Serif SC',serif;
  font-size:clamp(1.25rem,2.2vw,1.7rem);
  font-weight:700;line-height:1.35;
  color:var(--t1);margin-bottom:12px;
  transition:color var(--tr);
}}
.hero:hover .hero-title{{color:var(--red);}}
.hero-desc{{
  font-size:.88rem;color:var(--t2);
  line-height:1.85;margin-bottom:16px;
}}
.hero-meta{{
  display:flex;align-items:center;
  gap:12px;flex-wrap:wrap;
}}
.read-btn{{
  font-family:'JetBrains Mono',monospace;
  font-size:.65rem;color:var(--red);
  border:1px solid rgba(192,57,43,.25);
  padding:4px 12px;border-radius:4px;
  display:inline-flex;align-items:center;gap:4px;
  transition:background var(--tr);
}}
.read-btn:hover{{background:var(--red-bg);}}
.src{{
  font-family:'JetBrains Mono',monospace;
  font-size:.62rem;color:var(--t3);
}}
.imp-row{{display:flex;align-items:center;gap:8px;margin-top:14px;}}
.imp-lbl{{font-family:'JetBrains Mono',monospace;font-size:.58rem;color:var(--t3);flex-shrink:0;}}
.imp-bar{{flex:1;height:2px;background:var(--border);border-radius:1px;overflow:hidden;}}
.imp-fill{{height:100%;background:var(--red);border-radius:1px;}}
.imp-n{{font-family:'JetBrains Mono',monospace;font-size:.58rem;color:var(--amber);width:20px;text-align:right;flex-shrink:0;}}

.hero-side{{
  border-left:1px solid var(--border);
  background:var(--surface2);
  padding:24px 16px;
  display:flex;flex-direction:column;
  justify-content:center;gap:20px;
}}
.hs-lbl{{
  font-family:'JetBrains Mono',monospace;
  font-size:.54rem;letter-spacing:.15em;text-transform:uppercase;
  color:var(--t3);margin-bottom:3px;
}}
.hs-big{{
  font-family:'Noto Serif SC',serif;
  font-size:2.2rem;font-weight:700;
  color:var(--amber);line-height:1;
}}
.hs-sub{{font-family:'JetBrains Mono',monospace;font-size:.58rem;color:var(--t3)}}

/* list */
.list{{
  background:var(--surface);
  border:1px solid var(--border);
  border-radius:var(--r);
  overflow:hidden;
}}
.ni{{
  display:grid;
  grid-template-columns:28px 1fr 64px;
  gap:14px;align-items:start;
  padding:15px 18px;
  border-bottom:1px solid var(--border);
  cursor:pointer;
  transition:background var(--tr);
  color:inherit;text-decoration:none;
}}
.ni:hover{{background:var(--surface2);}}
.ni:last-child{{border-bottom:none;}}
.ni-n{{
  font-family:'JetBrains Mono',monospace;
  font-size:.62rem;color:var(--t3);
  padding-top:3px;text-align:right;
}}
.ni-body{{min-width:0;}}
.ni-top{{display:flex;align-items:center;gap:7px;margin-bottom:6px;flex-wrap:wrap;}}
.ni-title{{
  font-size:.93rem;font-weight:500;
  line-height:1.5;color:var(--t1);
  margin-bottom:4px;
  transition:color var(--tr);
}}
.ni:hover .ni-title{{color:var(--red);}}
.ni-desc{{
  font-size:.78rem;color:var(--t2);line-height:1.7;
  display:-webkit-box;-webkit-line-clamp:2;
  -webkit-box-orient:vertical;overflow:hidden;
}}
.ni-src{{
  font-family:'JetBrains Mono',monospace;
  font-size:.58rem;color:var(--t3);margin-top:5px;
}}
.ni-right{{
  display:flex;flex-direction:column;
  align-items:flex-end;gap:5px;padding-top:3px;
}}
.pill{{
  font-family:'JetBrains Mono',monospace;
  font-size:.58rem;color:var(--amber);
  border:1px solid rgba(183,121,31,.25);
  padding:2px 7px;border-radius:3px;white-space:nowrap;
}}

footer{{
  border-top:1px solid var(--border);
  padding:14px 20px;
}}
.footer-inner{{
  max-width:1080px;margin:0 auto;
  display:flex;justify-content:space-between;
  flex-wrap:wrap;gap:6px;
}}
.fl,.fr{{
  font-family:'JetBrains Mono',monospace;
  font-size:.58rem;color:var(--t3);
}}
#nxt{{color:var(--amber);}}

.empty{{padding:40px;text-align:center;font-size:.8rem;color:var(--t3);}}

@keyframes fu{{from{{opacity:0;transform:translateY(8px)}}to{{opacity:1;transform:translateY(0)}}}}
.fu{{animation:fu .4s both;}}

@media(max-width:700px){{
  .ticker,.vsep{{display:none;}}
  .hero{{grid-template-columns:1fr;}}
  .hero-side{{display:none;}}
  .ni{{grid-template-columns:22px 1fr;}}
  .ni-right{{display:none;}}
  .wrap{{padding:16px 14px 60px;}}
}}
</style>
</head>
<body>

<header class="header">
  <div class="hbar">
    <div class="logo">PULSE<div class="logo-dot"></div></div>
    <span class="slot-tag">{update_slot}</span>
    <div class="vsep"></div>
    <div class="ticker"><div class="ticker-inner" id="tk"></div></div>
    <div class="vsep"></div>
    <span class="clock" id="clk">—</span>
    <button class="theme-btn" id="tbtn" title="切换主题">◑</button>
  </div>
  <div class="pbar"><div class="pfill" id="prog"></div></div>
</header>

<nav class="subnav">
  <div class="sninner" id="nav">
    <button class="nb on" data-c="all">全部</button>
    <button class="nb" data-c="politics">政治</button>
    <button class="nb" data-c="business">商业</button>
    <button class="nb" data-c="technology">科技</button>
    <button class="nb" data-c="science">科学</button>
    <button class="nb" data-c="health">健康</button>
  </div>
</nav>

<main class="wrap" id="wrap"></main>

<footer>
  <div class="footer-inner">
    <span class="fl">PULSE · {full_date} {time_str} 更新 · 数据来源 NewsAPI</span>
    <span class="fr">下次更新 <span id="nxt">—</span> · 08:00 / 12:00 / 18:00</span>
  </div>
</footer>

<script>
const FEAT={feat_json};
const CARDS={cards_json};

// 主题（跟随系统，可手动覆盖）
let manualTheme=null;
const tbtn=document.getElementById('tbtn');
tbtn.addEventListener('click',()=>{{
  const isDark=document.documentElement.classList.toggle('force-dark');
  // 简单切换 CSS 变量覆盖
  if(!document.getElementById('theme-override')){{
    const s=document.createElement('style');
    s.id='theme-override';
    document.head.appendChild(s);
  }}
  const s=document.getElementById('theme-override');
  s.textContent=isDark?`
    :root{{--bg:#111110;--surface:#1c1c1a;--surface2:#181816;
    --border:rgba(255,255,255,.07);--border-md:rgba(255,255,255,.13);
    --t1:#ede9e3;--t2:#9a9690;--t3:#5a5652;
    --red:#e05a4f;--red-bg:rgba(192,57,43,.12);
    --amber:#e9a825;--amber-bg:rgba(183,121,31,.12);}}`:'';
}});

// 时钟
function pad(n){{return String(n).padStart(2,'0');}}
setInterval(()=>{{
  const n=new Date();
  document.getElementById('clk').textContent=
    `${{n.getFullYear()}}/${{pad(n.getMonth()+1)}}/${{pad(n.getDate())}} ${{pad(n.getHours())}}:${{pad(n.getMinutes())}}:${{pad(n.getSeconds())}}`;
}},1000);

// 倒计时
function secsToNext(){{
  const n=new Date(), s=n.getHours()*3600+n.getMinutes()*60+n.getSeconds();
  for(const h of [8,12,18]){{if(h*3600>s)return h*3600-s;}}
  return 8*3600+(86400-s);
}}
let rem=secsToNext(),total=rem;
setInterval(()=>{{
  rem--;if(rem<0){{rem=secsToNext();total=rem;}}
  document.getElementById('prog').style.width=((total-rem)/total*100)+'%';
  const hh=Math.floor(rem/3600),mm=Math.floor((rem%3600)/60),ss=rem%60;
  const el=document.getElementById('nxt');
  if(el)el.textContent=`${{hh}}时${{pad(mm)}}分${{pad(ss)}}秒`;
}},1000);

function chip(tag,label){{
  return`<span class="chip ${{tag}}">${{label}}</span>`;
}}

function heroHTML(d){{
  if(!d)return'';
  return`
  <div class="hero fu">
    <div class="hero-body">
      <div class="hero-top">
        ${{chip(d.tag,d.label)}}
        <span class="headline-badge">HEAD LINE</span>
      </div>
      <a href="${{d.url}}" target="_blank" rel="noopener">
        <div class="hero-title">${{d.title}}</div>
      </a>
      <div class="hero-desc">${{d.desc}}</div>
      <div class="hero-meta">
        <a class="read-btn" href="${{d.url}}" target="_blank" rel="noopener">阅读原文 ↗</a>
        <span class="src">${{d.src}}</span>
      </div>
      <div class="imp-row">
        <span class="imp-lbl">重要指数</span>
        <div class="imp-bar"><div class="imp-fill" style="width:${{d.imp}}%"></div></div>
        <span class="imp-n">${{d.imp}}</span>
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
        <div class="hs-lbl">来源</div>
        <div style="font-size:.75rem;color:var(--t2);margin-top:3px;line-height:1.6">${{d.src}}</div>
      </div>
    </div>
  </div>`;
}}

function listHTML(cards){{
  if(!cards.length)return`<div class="list"><div class="empty">暂无此分类内容</div></div>`;
  return`<div class="list">`+cards.map((d,i)=>`
    <a class="ni" href="${{d.url}}" target="_blank" rel="noopener" style="animation-delay:${{i*.03}}s">
      <span class="ni-n">${{String(i+1).padStart(2,'0')}}</span>
      <div class="ni-body">
        <div class="ni-top">${{chip(d.tag,d.label)}}</div>
        <div class="ni-title">${{d.title}}</div>
        <div class="ni-desc">${{d.desc}}</div>
        <div class="ni-src">${{d.src}}</div>
      </div>
      <div class="ni-right"><span class="pill">${{d.imp}}</span></div>
    </a>`).join('')+`</div>`;
}}

function sec(text,badge=''){{
  return`<div class="sec">
    <span class="sec-t">${{text}}</span>
    <div class="sec-line"></div>
    ${{badge?`<span class="sec-badge">${{badge}}</span>`:''}}
  </div>`;
}}

const CAT={{politics:'政治',business:'商业',technology:'科技',science:'科学',health:'健康'}};

function render(cat){{
  const list=cat==='all'?CARDS:CARDS.filter(c=>c.cat===cat);
  const showFeat=FEAT&&(cat==='all'||cat===FEAT.cat);
  let h='';
  if(showFeat){{h+=sec('今日头条');h+=heroHTML(FEAT);}}
  const lbl=cat==='all'?'今日要闻':(CAT[cat]||cat);
  h+=sec(lbl,list.length+'条');
  h+=listHTML(list);
  document.getElementById('wrap').innerHTML=h;
}}

// 导航
document.getElementById('nav').addEventListener('click',e=>{{
  const b=e.target.closest('.nb');if(!b)return;
  document.querySelectorAll('.nb').forEach(x=>x.classList.remove('on'));
  b.classList.add('on');render(b.dataset.c);
}});

// Ticker
const titles=(FEAT?[FEAT.title]:[]).concat(CARDS.map(c=>c.title));
const dbl=titles.concat(titles);
document.getElementById('tk').innerHTML=dbl.map(t=>`<span class="tk-item">${{t}}</span>`).join('');

render('all');
</script>
</body>
</html>"""

def main():
    print(f"\n{'═'*52}")
    print(f"  PULSE v3  {NOW.strftime('%Y-%m-%d %H:%M')} CST")
    print(f"{'═'*52}")
    feat, cards = build_data()
    html = generate_html(feat, cards)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    cats = {}
    for c in ([feat] if feat else []) + cards:
        cats[c["label"]] = cats.get(c["label"], 0) + 1
    print(f"\n✅ 完成：{1 if feat else 0} 头条 + {len(cards)} 要闻")
    print(f"   分类分布：{cats}")
    print(f"   输出：index.html")

if __name__ == "__main__":
    main()
