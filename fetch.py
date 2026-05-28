#!/usr/bin/env python3
"""
fetch.py — Pulse v4
策略：每分类精确 5 条，内容严格匹配
- 每个分类独立抓取，双接口互补（top-headlines category + 权威来源 everything）
- 分类内容校验：二次确认文章确实属于该分类
- 质量评分后取最佳 5 条
- 头条：从所有分类中取评分最高 1 条
"""

import os, json, time, requests
from datetime import datetime, timezone, timedelta
from urllib.parse import quote

API_KEY = os.environ.get("NEWS_API_KEY", "37bf8ef8267f4751bd51311507429eab")
CST = timezone(timedelta(hours=8))
NOW = datetime.now(CST)

# ── 翻译（Google 非官方，无需 Key）──────────────────────────
def translate(text, retries=2):
    if not text or not text.strip():
        return text
    for attempt in range(retries):
        try:
            url = (
                "https://translate.googleapis.com/translate_a/single"
                f"?client=gtx&sl=en&tl=zh-CN&dt=t&q={quote(text[:500])}"
            )
            r = requests.get(url, timeout=8)
            parts = r.json()
            result = "".join(seg[0] for seg in parts[0] if seg[0])
            time.sleep(0.12)
            return result or text
        except Exception:
            time.sleep(0.5 * (attempt + 1))
    return text

# ── 分类配置 ─────────────────────────────────────────────────
# newsapi_cat:    NewsAPI top-headlines 官方分类（最匹配）
# sources:        权威来源（备用补充）
# must_keywords:  文章必须含有其中至少 1 个词才算属于该分类
# boost_keywords: 含有这些词额外加分
CATEGORIES = [
    {
        "cat":    "politics",
        "label":  "政治",
        "tag":    "pol",
        "newsapi_cat": "politics",
        "sources": "reuters,associated-press,bbc-news,the-washington-post,politico,axios,al-jazeera-english",
        "must_keywords": [
            "president", "congress", "senate", "parliament", "government", "minister",
            "election", "vote", "policy", "law", "legislation", "democrat", "republican",
            "trump", "biden", "harris", "white house", "nato", "united nations", "un ",
            "sanctions", "war", "military", "troops", "conflict", "treaty", "diplomat",
            "ukraine", "russia", "china", "taiwan", "israel", "iran", "gaza",
            "refugee", "immigration", "border", "protest", "coup", "geopolit",
            "foreign policy", "prime minister", "chancellor", "presidency",
        ],
        "boost_keywords": [
            "war", "sanctions", "election", "nuclear", "coup", "treaty", "summit",
        ],
    },
    {
        "cat":    "business",
        "label":  "商业",
        "tag":    "biz",
        "newsapi_cat": "business",
        "sources": "bloomberg,financial-times,the-wall-street-journal,fortune,reuters,the-economist",
        "must_keywords": [
            "economy", "economic", "market", "stock", "shares", "equities", "fund",
            "gdp", "inflation", "recession", "interest rate", "federal reserve", "fed ",
            "central bank", "trade", "tariff", "export", "import", "deal", "merger",
            "acquisition", "ipo", "earnings", "profit", "revenue", "bank", "finance",
            "debt", "imf", "world bank", "wto", "oil price", "energy price",
            "supply chain", "hedge fund", "private equity", "bond", "yield",
            "nasdaq", "s&p", "dow jones", "quarter", "fiscal", "monetary",
            "retail sales", "unemployment", "jobs report", "consumer", "spending",
        ],
        "boost_keywords": [
            "federal reserve", "inflation", "recession", "earnings", "ipo", "merger",
        ],
    },
    {
        "cat":    "technology",
        "label":  "科技",
        "tag":    "tech",
        "newsapi_cat": "technology",
        "sources": "ars-technica,wired,techcrunch,the-verge,mit-technology-review,reuters",
        "must_keywords": [
            "artificial intelligence", " ai ", "machine learning", "chatgpt", "openai",
            "google", "apple", "microsoft", "meta ", "amazon", "nvidia", "tesla",
            "spacex", "semiconductor", "chip", "processor", "software", "app",
            "startup", "cybersecurity", "hack", "data breach", "robot", "autonomous",
            "electric vehicle", " ev ", "battery", "tech ", "social media",
            "tiktok", "algorithm", "cloud", "quantum computing", "5g", "6g",
            "smartphone", "laptop", "iphone", "android", "browser", "internet",
            "data center", "open source", "programming", "developer",
        ],
        "boost_keywords": [
            "artificial intelligence", "breakthrough", "launch", "hack", "regulation",
        ],
    },
    {
        "cat":    "science",
        "label":  "科学",
        "tag":    "sci",
        "newsapi_cat": "science",
        "sources": "national-geographic,new-scientist,reuters,associated-press,bbc-news",
        "must_keywords": [
            "scientists", "researchers", "research", "study", "discovery", "discovered",
            "nasa", "space", "universe", "planet", "asteroid", "black hole", "galaxy",
            "star ", "comet", "telescope", "rocket", "astronaut", "orbit",
            "quantum", "physics", "biology", "chemistry", "genome", "dna", "rna",
            "fossil", "climate", "ocean", "earthquake", "volcano", "species",
            "evolution", "experiment", "laboratory", "scientific", "journal",
            "nature ", "science ", "cell ", "protein", "particle", "atom",
            "atmosphere", "glacier", "coral", "extinction", "biodiversity",
        ],
        "boost_keywords": [
            "breakthrough", "discovery", "nasa", "first time", "new species", "evidence",
        ],
    },
    {
        "cat":    "health",
        "label":  "健康",
        "tag":    "hlth",
        "newsapi_cat": "health",
        "sources": "medical-news-today,health-day,reuters,associated-press,bbc-news,stat-news",
        "must_keywords": [
            "health", "medical", "medicine", "hospital", "disease", "virus", "vaccine",
            "cancer", "tumor", "drug", "fda", "cdc", "who ", "mental health",
            "obesity", "diabetes", "heart disease", "stroke", "surgery",
            "clinical trial", "pandemic", "epidemic", "patient", "doctor",
            "nurse", "pharmaceutical", "therapy", "treatment", "symptom",
            "nutrition", "diet", "exercise", "fitness", "sleep", "immune",
            "antibiotic", "infection", "outbreak", "mortality", "life expectancy",
            "alzheimer", "dementia", "depression", "anxiety", "autism",
        ],
        "boost_keywords": [
            "fda approved", "breakthrough", "trial", "cure", "vaccine", "outbreak",
        ],
    },
]

# ── 质量评分 ─────────────────────────────────────────────────
JUNK_TITLES = [
    "quiz", "top 10", "best of", "how to", "watch live", "live updates",
    "photos:", "video:", "why you should", "what to know", "here's what",
    "everything you need", "ranking", "listicle", "opinion:", "letters to",
    "your questions", "week in review", "roundup", "recap",
]
HIGH_IMPACT = [
    "killed", "dead", "death", "war", "attack", "strike", "explosion",
    "crisis", "collapse", "emergency", "historic", "record", "breakthrough",
    "nuclear", "resign", "arrested", "sentenced", "crash", "disaster",
    "ban", "signed", "approved", "rejected", "surge", "plunge",
]
MED_IMPACT = [
    "deal", "agreement", "vote", "launched", "announced", "warning",
    "risk", "rise", "fall", "investigation", "report", "growth", "decline",
    "new ", "first ", "major ", "key ",
]
TRUSTED_SOURCES = {
    "reuters", "associated-press", "bbc-news", "the-new-york-times",
    "financial-times", "the-economist", "bloomberg", "the-wall-street-journal",
    "axios", "politico", "wired", "ars-technica", "techcrunch", "the-verge",
    "national-geographic", "new-scientist", "mit-technology-review",
    "medical-news-today", "stat-news", "al-jazeera-english", "time",
}

def quality_score(article, cat_cfg):
    title = (article.get("title") or "").lower()
    desc  = (article.get("description") or "").lower()
    src   = (article.get("source") or {}).get("id", "")
    text  = title + " " + desc
    s = 50

    # 来源权威性
    if src in TRUSTED_SOURCES:
        s += 18

    # 分类相关度加分
    must_hits = sum(1 for kw in cat_cfg["must_keywords"] if kw in text)
    s += min(must_hits * 5, 20)

    boost_hits = sum(1 for kw in cat_cfg["boost_keywords"] if kw in text)
    s += boost_hits * 6

    # 高影响词
    for w in HIGH_IMPACT:
        if w in text:
            s += 8

    # 中等影响词
    for w in MED_IMPACT:
        if w in text:
            s += 3

    # 低质量惩罚
    for w in JUNK_TITLES:
        if w in title:
            s -= 30

    # 描述质量
    desc_len = len(article.get("description") or "")
    if desc_len > 100:
        s += 8
    elif desc_len < 30:
        s -= 10

    # 标题长度
    t_len = len(article.get("title") or "")
    if t_len < 15 or t_len > 200:
        s -= 15

    return max(0, min(99, s))

def is_relevant(article, cat_cfg):
    """内容校验：必须命中至少 1 个该分类关键词"""
    text = (
        (article.get("title") or "") + " " +
        (article.get("description") or "")
    ).lower()
    return any(kw in text for kw in cat_cfg["must_keywords"])

# ── 抓取接口 ─────────────────────────────────────────────────
def fetch_top_headlines_cat(newsapi_cat, page_size=30):
    try:
        r = requests.get(
            "https://newsapi.org/v2/top-headlines",
            params={
                "category": newsapi_cat,
                "language": "en",
                "pageSize": page_size,
                "apiKey": API_KEY,
            },
            timeout=12,
        )
        data = r.json()
        if data.get("status") != "ok":
            print(f"    API 错误: {data.get('message','')}")
            return []
        return data.get("articles", [])
    except Exception as e:
        print(f"    top-headlines/{newsapi_cat} 失败: {e}")
        return []

def fetch_sources(sources_str, page_size=30):
    try:
        r = requests.get(
            "https://newsapi.org/v2/top-headlines",
            params={
                "sources": sources_str,
                "pageSize": page_size,
                "apiKey": API_KEY,
            },
            timeout=12,
        )
        data = r.json()
        if data.get("status") != "ok":
            print(f"    API 错误: {data.get('message','')}")
            return []
        return data.get("articles", [])
    except Exception as e:
        print(f"    sources 失败: {e}")
        return []

# ── 单分类处理 ───────────────────────────────────────────────
def process_category(cat_cfg, global_seen, target=5):
    cat  = cat_cfg["cat"]
    name = cat_cfg["label"]
    print(f"\n{'─'*40}")
    print(f"  [{name}] 开始抓取…")

    raw = []
    seen_in_cat = set()

    def add_articles(articles, source_label):
        added = 0
        for a in articles:
            url   = a.get("url", "")
            title = (a.get("title") or "").strip()
            if not url or url in global_seen or url in seen_in_cat:
                continue
            if not title or title == "[Removed]":
                continue
            t30 = title[:30].lower()
            if t30 in seen_in_cat:
                continue
            if not a.get("description"):
                continue
            if not is_relevant(a, cat_cfg):
                continue
            seen_in_cat.add(url)
            seen_in_cat.add(t30)
            raw.append(a)
            added += 1
        print(f"    {source_label}: +{added} 条 (累计 {len(raw)})")

    # 1. NewsAPI 官方分类（最匹配）
    arts1 = fetch_top_headlines_cat(cat_cfg["newsapi_cat"], page_size=30)
    time.sleep(0.25)
    add_articles(arts1, f"top-headlines/{cat_cfg['newsapi_cat']}")

    # 2. 权威来源补充（如果不够）
    if len(raw) < target:
        arts2 = fetch_sources(cat_cfg["sources"], page_size=30)
        time.sleep(0.25)
        add_articles(arts2, "权威来源")

    # 评分排序，取前 target 条
    scored = [(quality_score(a, cat_cfg), a) for a in raw]
    scored.sort(key=lambda x: x[0], reverse=True)
    best = scored[:target]

    print(f"  [{name}] 评分后保留 {len(best)}/{len(raw)} 条")

    # 翻译
    result = []
    for imp, a in best:
        title_en = (a.get("title") or "").split(" - ")[0].strip()
        desc_en  = (a.get("description") or "")[:300].strip()
        pub_date = (a.get("publishedAt") or "")[:10]
        source   = (a.get("source") or {}).get("name", "")

        print(f"    翻译 [{imp}]: {title_en[:42]}…")
        title_zh = translate(title_en)
        time.sleep(0.1)
        desc_zh  = translate(desc_en)
        time.sleep(0.1)

        article = {
            "cat":   cat,
            "tag":   cat_cfg["tag"],
            "label": name,
            "title": title_zh or title_en,
            "desc":  desc_zh  or desc_en,
            "url":   a.get("url", ""),
            "src":   f"{source}  ·  {pub_date}",
            "imp":   imp,
        }
        result.append(article)
        global_seen.add(a.get("url", ""))

    return result

# ── 头条（独立抓取，全局最高分）────────────────────────────
def fetch_headline(global_seen):
    print(f"\n{'─'*40}")
    print("  [头条] 抓取全球头条…")
    try:
        r = requests.get(
            "https://newsapi.org/v2/top-headlines",
            params={"language": "en", "pageSize": 10, "apiKey": API_KEY},
            timeout=10,
        )
        arts = r.json().get("articles", [])
        time.sleep(0.2)
    except Exception as e:
        print(f"  头条失败: {e}")
        return None

    best_score, best_art = 0, None
    for a in arts:
        url = a.get("url", "")
        if not url or url in global_seen:
            continue
        if not a.get("title") or not a.get("description"):
            continue
        # 临时评分（不限分类）
        s = 50
        text = ((a.get("title") or "") + " " + (a.get("description") or "")).lower()
        for w in HIGH_IMPACT:
            if w in text: s += 8
        src = (a.get("source") or {}).get("id", "")
        if src in TRUSTED_SOURCES: s += 18
        if s > best_score:
            best_score, best_art = s, a

    if not best_art:
        return None

    a = best_art
    title_en = (a.get("title") or "").split(" - ")[0].strip()
    desc_en  = (a.get("description") or "")[:300].strip()
    pub_date = (a.get("publishedAt") or "")[:10]
    source   = (a.get("source") or {}).get("name", "")

    print(f"  头条: {title_en[:50]}…")
    title_zh = translate(title_en)
    time.sleep(0.1)
    desc_zh  = translate(desc_en)
    time.sleep(0.1)

    global_seen.add(a.get("url", ""))

    # 自动判断分类
    text_full = (title_en + " " + desc_en).lower()
    feat_cat = "politics"
    feat_tag = "pol"
    feat_label = "政治"
    for cfg in CATEGORIES:
        if any(kw in text_full for kw in cfg["must_keywords"]):
            feat_cat   = cfg["cat"]
            feat_tag   = cfg["tag"]
            feat_label = cfg["label"]
            break

    return {
        "cat":   feat_cat,
        "tag":   feat_tag,
        "label": feat_label,
        "title": title_zh or title_en,
        "desc":  desc_zh  or desc_en,
        "url":   a.get("url", ""),
        "src":   f"{source}  ·  {pub_date}",
        "imp":   max(best_score, 88),
    }

# ── 主流程 ────────────────────────────────────────────────────
def build_data():
    global_seen = set()

    feat  = fetch_headline(global_seen)
    cards = []

    for cat_cfg in CATEGORIES:
        cat_articles = process_category(cat_cfg, global_seen, target=5)
        cards.extend(cat_articles)

    print(f"\n{'═'*40}")
    print(f"  头条: {1 if feat else 0} 条")
    dist = {}
    for c in cards:
        dist[c["label"]] = dist.get(c["label"], 0) + 1
    for label, count in dist.items():
        print(f"  {label}: {count} 条")
    print(f"  合计: {len(cards)} 条")

    return feat, cards

# ── HTML 生成 ─────────────────────────────────────────────────
def generate_html(feat, cards):
    date_str  = NOW.strftime("%-m月%-d日")
    weekdays  = ["周一","周二","周三","周四","周五","周六","周日"]
    weekday   = weekdays[NOW.weekday()]
    full_date = NOW.strftime(f"%Y年{date_str}  {weekday}")
    time_str  = NOW.strftime("%H:%M")
    h         = NOW.hour
    slot      = "早报" if h < 10 else ("午报" if h < 14 else "晚报")

    feat_json  = json.dumps(feat,  ensure_ascii=False) if feat else "null"
    cards_json = json.dumps(cards, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<meta name="description" content="Pulse — 每日精选全球最有价值的新闻，五大分类各5条">
<title>PULSE · {slot} · {date_str}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;600;700&family=Noto+Sans+SC:wght@300;400;500&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{{
  --bg:#f7f6f3; --surf:#fff; --surf2:#fafaf8;
  --bd:rgba(0,0,0,.07); --bd2:rgba(0,0,0,.12);
  --t1:#1a1a1a; --t2:#5a5a5a; --t3:#a0a09a;
  --red:#c0392b; --red-bg:#fdf2f1;
  --amber:#b7791f; --amber-bg:#fffbeb;
  --r:6px; --tr:.18s ease;
}}
@media(prefers-color-scheme:dark){{
  :root{{
    --bg:#111110; --surf:#1c1c1a; --surf2:#181816;
    --bd:rgba(255,255,255,.07); --bd2:rgba(255,255,255,.13);
    --t1:#ede9e3; --t2:#9a9690; --t3:#5a5652;
    --red:#e05a4f; --red-bg:rgba(192,57,43,.12);
    --amber:#e9a825; --amber-bg:rgba(183,121,31,.12);
  }}
}}
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0;}}
html{{scroll-behavior:smooth;}}
body{{background:var(--bg);color:var(--t1);font-family:'Noto Sans SC',system-ui,sans-serif;font-size:14px;line-height:1.7;}}
a{{text-decoration:none;color:inherit;}}
button{{cursor:pointer;font-family:inherit;border:none;background:none;}}

/* HEADER */
.hdr{{
  position:sticky;top:0;z-index:50;
  background:rgba(247,246,243,.95);
  backdrop-filter:blur(16px);
  border-bottom:1px solid var(--bd);
}}
@media(prefers-color-scheme:dark){{.hdr{{background:rgba(17,17,16,.95);}}}}
.hbar{{
  display:flex;align-items:center;gap:10px;
  height:48px;padding:0 20px;
  max-width:1080px;margin:0 auto;
}}
.logo{{
  font-family:'Noto Serif SC',serif;
  font-size:1.35rem;font-weight:700;
  letter-spacing:.06em;flex-shrink:0;
  display:flex;align-items:center;gap:5px;
}}
.logo-dot{{
  width:6px;height:6px;border-radius:50%;
  background:var(--red);
  animation:blink 2.4s step-end infinite;
}}
@keyframes blink{{0%,100%{{opacity:1}}50%{{opacity:0}}}}
.slot-tag{{
  font-family:'JetBrains Mono',monospace;
  font-size:.6rem;padding:2px 7px;
  background:var(--amber-bg);color:var(--amber);
  border:1px solid rgba(183,121,31,.25);
  border-radius:3px;flex-shrink:0;
}}
.vsep{{width:1px;height:16px;background:var(--bd2);flex-shrink:0;}}
.ticker{{
  flex:1;overflow:hidden;
  mask:linear-gradient(90deg,transparent,#000 5%,#000 95%,transparent);
  -webkit-mask:linear-gradient(90deg,transparent,#000 5%,#000 95%,transparent);
}}
.tk-inner{{
  display:flex;gap:32px;white-space:nowrap;
  animation:scroll 100s linear infinite;
}}
.tk-inner:hover{{animation-play-state:paused;}}
@keyframes scroll{{0%{{transform:translateX(0)}}100%{{transform:translateX(-50%)}}}}
.tk-item{{font-size:11.5px;color:var(--t2);flex-shrink:0;}}
.tk-item::before{{content:'·';color:var(--red);margin-right:6px;font-weight:700;}}
.clk{{
  font-family:'JetBrains Mono',monospace;
  font-size:.65rem;color:var(--t3);
  white-space:nowrap;flex-shrink:0;
}}
.tbtn{{
  width:30px;height:30px;border-radius:50%;
  border:1px solid var(--bd2);color:var(--t2);
  font-size:14px;display:flex;align-items:center;
  justify-content:center;flex-shrink:0;
  transition:background var(--tr);
}}
.tbtn:hover{{background:var(--surf2);}}
.pbar{{height:1.5px;background:var(--bd);}}
.pfill{{height:100%;background:linear-gradient(90deg,var(--red),var(--amber));width:0;transition:width 1s linear;}}

/* SUBNAV */
.subnav{{
  background:var(--surf);border-bottom:1px solid var(--bd);
  overflow-x:auto;scrollbar-width:none;
}}
.subnav::-webkit-scrollbar{{display:none;}}
.sninner{{display:flex;padding:0 20px;max-width:1080px;margin:0 auto;}}
.nb{{
  padding:9px 16px;font-size:.78rem;font-weight:400;
  color:var(--t2);border-bottom:2px solid transparent;
  white-space:nowrap;transition:color var(--tr),border-color var(--tr);flex-shrink:0;
}}
.nb:hover{{color:var(--t1);}}
.nb.on{{color:var(--t1);font-weight:500;border-color:var(--red);}}

/* LAYOUT */
.wrap{{max-width:1080px;margin:0 auto;padding:28px 20px 80px;}}
.sec{{display:flex;align-items:center;gap:10px;margin:36px 0 16px;}}
.sec:first-child{{margin-top:0;}}
.sec-t{{
  font-family:'JetBrains Mono',monospace;
  font-size:.58rem;letter-spacing:.2em;text-transform:uppercase;
  color:var(--red);white-space:nowrap;
}}
.sec-line{{flex:1;height:1px;background:var(--bd);}}
.sec-badge{{
  font-family:'JetBrains Mono',monospace;
  font-size:.58rem;color:var(--t3);white-space:nowrap;
}}

/* CHIP */
.chip{{
  display:inline-block;
  font-family:'JetBrains Mono',monospace;
  font-size:.58rem;letter-spacing:.06em;
  padding:2px 7px;border-radius:3px;white-space:nowrap;
}}
.pol {{background:rgba(157,23,77,.1);color:#9d174d;}}
.biz {{background:rgba(120,53,15,.1);color:#92400e;}}
.tech{{background:rgba(6,78,59,.1);color:#065f46;}}
.sci {{background:rgba(12,74,110,.1);color:#0c4a6e;}}
.hlth{{background:rgba(55,65,81,.1);color:#374151;}}
@media(prefers-color-scheme:dark){{
  .pol {{background:rgba(157,23,77,.18);color:#f9a8d4;}}
  .biz {{background:rgba(217,119,6,.15);color:#fcd34d;}}
  .tech{{background:rgba(16,185,129,.12);color:#6ee7b7;}}
  .sci {{background:rgba(59,130,246,.12);color:#93c5fd;}}
  .hlth{{background:rgba(156,163,175,.1);color:#d1d5db;}}
}}

/* HERO */
.hero{{
  background:var(--surf);border:1px solid var(--bd);
  border-radius:var(--r);overflow:hidden;
  display:grid;grid-template-columns:1fr 160px;
  margin-bottom:24px;
}}
.hero-body{{padding:24px 28px;}}
.hero-top{{display:flex;align-items:center;gap:8px;margin-bottom:12px;}}
.hbadge{{
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
.hero-desc{{font-size:.88rem;color:var(--t2);line-height:1.85;margin-bottom:16px;}}
.hero-meta{{display:flex;align-items:center;gap:12px;flex-wrap:wrap;}}
.read-btn{{
  font-family:'JetBrains Mono',monospace;
  font-size:.65rem;color:var(--red);
  border:1px solid rgba(192,57,43,.25);
  padding:4px 12px;border-radius:4px;
  display:inline-flex;align-items:center;gap:4px;
  transition:background var(--tr);
}}
.read-btn:hover{{background:var(--red-bg);}}
.src{{font-family:'JetBrains Mono',monospace;font-size:.62rem;color:var(--t3);}}
.imp-row{{display:flex;align-items:center;gap:8px;margin-top:14px;}}
.imp-lbl{{font-family:'JetBrains Mono',monospace;font-size:.58rem;color:var(--t3);flex-shrink:0;}}
.imp-bar{{flex:1;height:2px;background:var(--bd);border-radius:1px;overflow:hidden;}}
.imp-fill{{height:100%;background:var(--red);border-radius:1px;}}
.imp-n{{font-family:'JetBrains Mono',monospace;font-size:.58rem;color:var(--amber);width:20px;text-align:right;flex-shrink:0;}}
.hero-side{{
  border-left:1px solid var(--bd);background:var(--surf2);
  padding:24px 16px;display:flex;flex-direction:column;
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
.hs-sub{{font-family:'JetBrains Mono',monospace;font-size:.58rem;color:var(--t3);}}

/* NEWS LIST */
.list{{background:var(--surf);border:1px solid var(--bd);border-radius:var(--r);overflow:hidden;}}
.ni{{
  display:grid;grid-template-columns:28px 1fr 60px;
  gap:14px;align-items:start;
  padding:15px 18px;border-bottom:1px solid var(--bd);
  color:inherit;text-decoration:none;
  transition:background var(--tr);
}}
.ni:hover{{background:var(--surf2);}}
.ni:last-child{{border-bottom:none;}}
.ni-n{{
  font-family:'JetBrains Mono',monospace;
  font-size:.62rem;color:var(--t3);
  padding-top:3px;text-align:right;
}}
.ni-top{{display:flex;align-items:center;gap:7px;margin-bottom:6px;}}
.ni-title{{
  font-size:.93rem;font-weight:500;
  line-height:1.5;color:var(--t1);
  margin-bottom:4px;transition:color var(--tr);
}}
.ni:hover .ni-title{{color:var(--red);}}
.ni-desc{{
  font-size:.78rem;color:var(--t2);line-height:1.7;
  display:-webkit-box;-webkit-line-clamp:2;
  -webkit-box-orient:vertical;overflow:hidden;
}}
.ni-src{{font-family:'JetBrains Mono',monospace;font-size:.58rem;color:var(--t3);margin-top:5px;}}
.ni-right{{display:flex;flex-direction:column;align-items:flex-end;gap:5px;padding-top:3px;}}
.pill{{
  font-family:'JetBrains Mono',monospace;
  font-size:.58rem;color:var(--amber);
  border:1px solid rgba(183,121,31,.25);
  padding:2px 7px;border-radius:3px;white-space:nowrap;
}}
.empty{{padding:32px;text-align:center;font-size:.8rem;color:var(--t3);}}

/* FOOTER */
footer{{border-top:1px solid var(--bd);padding:14px 20px;}}
.fi{{
  max-width:1080px;margin:0 auto;
  display:flex;justify-content:space-between;flex-wrap:wrap;gap:6px;
}}
.fl,.fr{{font-family:'JetBrains Mono',monospace;font-size:.58rem;color:var(--t3);}}
#nxt{{color:var(--amber);}}

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

<header class="hdr">
  <div class="hbar">
    <div class="logo">PULSE<div class="logo-dot"></div></div>
    <span class="slot-tag">{slot}</span>
    <div class="vsep"></div>
    <div class="ticker"><div class="tk-inner" id="tk"></div></div>
    <div class="vsep"></div>
    <span class="clk" id="clk">—</span>
    <button class="tbtn" id="tbtn" title="切换主题">◑</button>
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
  <div class="fi">
    <span class="fl">PULSE · {full_date} {time_str} 更新 · NewsAPI</span>
    <span class="fr">下次更新 <span id="nxt">—</span> · 08:00 / 12:00 / 18:00</span>
  </div>
</footer>

<script>
const FEAT={feat_json};
const CARDS={cards_json};

// 主题
let _dark=false;
document.getElementById('tbtn').addEventListener('click',()=>{{
  _dark=!_dark;
  let s=document.getElementById('_ts');
  if(!s){{s=document.createElement('style');s.id='_ts';document.head.appendChild(s);}}
  s.textContent=_dark?`:root{{
    --bg:#111110;--surf:#1c1c1a;--surf2:#181816;
    --bd:rgba(255,255,255,.07);--bd2:rgba(255,255,255,.13);
    --t1:#ede9e3;--t2:#9a9690;--t3:#5a5652;
    --red:#e05a4f;--red-bg:rgba(192,57,43,.12);
    --amber:#e9a825;--amber-bg:rgba(183,121,31,.12);
  }}`:'';
  document.querySelectorAll('.chip.pol').forEach(el=>{{
    el.style.background=_dark?'rgba(157,23,77,.18)':'';
    el.style.color=_dark?'#f9a8d4':'';
  }});
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
  const n=new Date(),s=n.getHours()*3600+n.getMinutes()*60+n.getSeconds();
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
  return`<div class="hero fu">
    <div class="hero-body">
      <div class="hero-top">${{chip(d.tag,d.label)}}<span class="hbadge">HEAD LINE</span></div>
      <a href="${{d.url}}" target="_blank" rel="noopener"><div class="hero-title">${{d.title}}</div></a>
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
      <div><div class="hs-lbl">重要指数</div><div class="hs-big">${{d.imp}}</div><div class="hs-sub">/ 100</div></div>
      <div style="height:1px;background:var(--bd)"></div>
      <div><div class="hs-lbl">来源</div><div style="font-size:.75rem;color:var(--t2);margin-top:3px;line-height:1.6">${{d.src}}</div></div>
    </div>
  </div>`;
}}
function listHTML(items){{
  if(!items.length)return`<div class="list"><div class="empty">暂无此分类内容</div></div>`;
  return`<div class="list">`+items.map((d,i)=>`
    <a class="ni" href="${{d.url}}" target="_blank" rel="noopener" style="animation-delay:${{i*.03}}s">
      <span class="ni-n">${{String(i+1).padStart(2,'0')}}</span>
      <div>
        <div class="ni-top">${{chip(d.tag,d.label)}}</div>
        <div class="ni-title">${{d.title}}</div>
        <div class="ni-desc">${{d.desc}}</div>
        <div class="ni-src">${{d.src}}</div>
      </div>
      <div class="ni-right"><span class="pill">${{d.imp}}</span></div>
    </a>`).join('')+`</div>`;
}}
function sec(text,badge){{
  return`<div class="sec">
    <span class="sec-t">${{text}}</span>
    <div class="sec-line"></div>
    ${{badge?`<span class="sec-badge">${{badge}}</span>`:''}}
  </div>`;
}}

const CAT_NAMES={{politics:'政治',business:'商业',technology:'科技',science:'科学',health:'健康'}};
const CAT_ORDER=['politics','business','technology','science','health'];

function render(cat){{
  let h='';
  if(cat==='all'){{
    // 头条
    if(FEAT){{h+=sec('今日头条');h+=heroHTML(FEAT);}}
    // 分类分组显示
    for(const c of CAT_ORDER){{
      const items=CARDS.filter(x=>x.cat===c);
      if(!items.length)continue;
      h+=sec(CAT_NAMES[c],items.length+'条');
      h+=listHTML(items);
    }}
  }}else{{
    const items=CARDS.filter(x=>x.cat===cat);
    const showFeat=FEAT&&FEAT.cat===cat;
    if(showFeat){{h+=sec('今日头条');h+=heroHTML(FEAT);}}
    h+=sec(CAT_NAMES[cat]||cat,items.length+'条');
    h+=listHTML(items);
  }}
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
    print(f"\n{'═'*50}")
    print(f"  PULSE v4  —  {NOW.strftime('%Y-%m-%d %H:%M')} CST")
    print(f"{'═'*50}")
    feat, cards = build_data()
    html = generate_html(feat, cards)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n✅ index.html 已生成")

if __name__ == "__main__":
    main()
