#!/usr/bin/env python3
"""
Pulse v6 — 编辑优先，重要性驱动

核心逻辑变化：
- 废弃"每类5条"配额制
- 从精英媒体 RSS 池广泛抓取 (~150条)
- 多维度评分，像真正的编辑一样筛选
- 去重：同一事件多家报道只保留最佳版本
- 取全局最重要的20条，自然分类
- 某分类今天没有重要新闻 → 显示实际条数，不凑数
"""

import os, json, time, re, requests, hashlib
from datetime import datetime, timezone, timedelta
from urllib.parse import quote
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher

API_KEY = os.environ.get("NEWS_API_KEY", "37bf8ef8267f4751bd51311507429eab")
CST     = timezone(timedelta(hours=8))
NOW     = datetime.now(CST)

# ════════════════════════════════════════════════════════════
# 媒体分级 — 决定评分基础分
# ════════════════════════════════════════════════════════════
# Tier 1: 全球公认最权威，记者直接报道一手信息
TIER1 = {
    "reuters.com":        85,
    "apnews.com":         85,
    "bloomberg.com":      82,
    "ft.com":             82,
}
# Tier 2: 深度报道 + 全球影响力
TIER2 = {
    "nytimes.com":        78,
    "washingtonpost.com": 76,
    "wsj.com":            78,
    "economist.com":      80,
    "theguardian.com":    72,
    "politico.com":       74,
    "foreignpolicy.com":  75,
    "aljazeera.com":      68,
    "axios.com":          70,
    "spiegel.de":         68,
}
# Tier 3: 专业领域权威
TIER3 = {
    "nature.com":              78,
    "science.org":             78,
    "nejm.org":                80,
    "thelancet.com":           78,
    "technologyreview.com":    72,
    "newscientist.com":        68,
    "scientificamerican.com":  66,
    "statnews.com":            70,
    "arstechnica.com":         65,
    "wired.com":               63,
    "techcrunch.com":          58,
    "theverge.com":            58,
}
ALL_TIERS = {**TIER1, **TIER2, **TIER3}

# ════════════════════════════════════════════════════════════
# RSS 源（精选，不求多，只求精）
# ════════════════════════════════════════════════════════════
RSS_FEEDS = [
    # 通讯社（一手信息，最快最准）
    ("reuters_world",    "https://feeds.reuters.com/Reuters/worldNews"),
    ("reuters_politics", "https://feeds.reuters.com/Reuters/PoliticsNews"),
    ("reuters_business", "https://feeds.reuters.com/reuters/businessNews"),
    ("reuters_science",  "https://feeds.reuters.com/reuters/scienceNews"),
    ("reuters_health",   "https://feeds.reuters.com/reuters/healthNews"),
    ("reuters_tech",     "https://feeds.reuters.com/reuters/technologyNews"),
    ("ap_top",          "https://apnews.com/rss"),

    # 财经精英
    ("bloomberg",       "https://feeds.bloomberg.com/markets/news.rss"),
    ("ft",              "https://feeds.ft.com/rss/home/uk"),
    ("wsj_world",       "https://feeds.a.dj.com/rss/RSSWorldNews.xml"),
    ("wsj_markets",     "https://feeds.a.dj.com/rss/RSSMarketsMain.xml"),
    ("economist",       "https://www.economist.com/the-world-this-week/rss.xml"),
    ("economist_fin",   "https://www.economist.com/finance-and-economics/rss.xml"),

    # 政治/外交
    ("nyt_world",       "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"),
    ("nyt_politics",    "https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml"),
    ("wapo_world",      "https://feeds.washingtonpost.com/rss/world"),
    ("politico",        "https://www.politico.com/rss/politicopicks.xml"),
    ("foreignpolicy",   "https://foreignpolicy.com/feed/"),
    ("aljazeera",       "https://www.aljazeera.com/xml/rss/all.xml"),

    # 科技
    ("mit_tech",        "https://www.technologyreview.com/feed/"),
    ("ars_technica",    "https://feeds.arstechnica.com/arstechnica/index"),
    ("wired",           "https://www.wired.com/feed/rss"),
    ("nyt_tech",        "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml"),

    # 科学
    ("nature",          "https://www.nature.com/nature.rss"),
    ("science_mag",     "https://www.science.org/rss/news_current.xml"),
    ("new_scientist",   "https://www.newscientist.com/feed/home/"),
    ("sci_american",    "https://www.scientificamerican.com/feed/"),
    ("nyt_science",     "https://rss.nytimes.com/services/xml/rss/nyt/Science.xml"),

    # 健康/医学
    ("nejm",            "https://www.nejm.org/action/showFeed?type=etoc&feed=rss&jc=nejm"),
    ("lancet",          "https://www.thelancet.com/rssfeed/lancet_online.xml"),
    ("stat_news",       "https://www.statnews.com/feed/"),
    ("nyt_health",      "https://rss.nytimes.com/services/xml/rss/nyt/Health.xml"),
]

# ════════════════════════════════════════════════════════════
# 重要性词库（经过深思熟虑分级）
# ════════════════════════════════════════════════════════════

# 极高重要性：影响全球格局的事件
CRITICAL = [
    "nuclear", "war declared", "ceasefire", "invaded", "invasion",
    "assassinated", "assassination", "coup", "revolution",
    "pandemic", "global emergency", "catastrophic",
    "default", "market crash", "financial crisis", "bank run",
    "mass casualty", "genocide", "war crimes",
    "climate tipping point", "extinction",
]
# 高重要性：重大政策、决定、突破
HIGH = [
    "killed", "dead", "deaths", "attack", "strikes", "sanctions",
    "emergency", "crisis", "collapse", "record", "historic",
    "resign", "resigned", "indicted", "arrested", "sentenced",
    "signed", "passed", "vetoed", "approved", "rejected", "banned",
    "breakthrough", "discovery", "first time ever",
    "interest rate", "inflation", "recession",
    "trade war", "tariff", "embargo",
    "deployed", "troops", "military",
]
# 中等重要性：值得关注但非紧急
MEDIUM = [
    "deal", "agreement", "treaty", "summit", "election",
    "vote", "legislation", "policy", "reform",
    "quarterly earnings", "gdp", "unemployment",
    "launched", "announced", "unveiled",
    "investigation", "inquiry", "hearing",
    "warning", "risk", "threat",
    "trial", "verdict", "ruling",
    "study", "research", "findings",
]
# 负面词（软新闻、娱乐、点击诱饵）
JUNK = [
    # 娱乐
    "celebrity", "oscars", "grammy", "golden globe", "emmy",
    "kardashian", "taylor swift", "beyoncé", "drake",
    "nfl", "nba", "nhl", "mlb", "fifa", "premier league",
    "super bowl", "world cup", "champions league",
    "box office", "movie review", "album review",
    # 点击诱饵
    "quiz", "top 10", "top 5", "best of", "worst of",
    "ranking", "ranked", "listicle",
    "how to watch", "watch live", "stream",
    "photos:", "video:", "gallery:",
    "everything you need to know",
    "here's what you need", "what to know",
    "your guide to", "explainer:",
    "week in review", "week in pictures",
    "morning briefing", "evening briefing",
    # 观点专栏（通常重要性低于新闻报道）
    "opinion:", "op-ed:", "commentary:", "column:",
    "letters to the editor",
    # 商业/赞助
    "sponsored", "advertisement", "partner content",
    "subscribe", "sign up",
]

# ════════════════════════════════════════════════════════════
# 分类规则（内容优先匹配）
# ════════════════════════════════════════════════════════════
CAT_RULES = [
    ("health", [
        "health", "medical", "medicine", "hospital", "disease", "virus",
        "vaccine", "cancer", "tumor", "drug trial", "fda approved", "fda ",
        "cdc ", "pandemic", "epidemic", "outbreak", "infection",
        "clinical trial", "pharmaceutical", "therapy", "treatment",
        "mental health", "surgery", "patient", "mortality",
        "alzheimer", "dementia", "diabetes", "obesity",
        "nejm", "lancet", "drug approval", "life expectancy",
    ]),
    ("science", [
        "scientists discover", "researchers find", "new study",
        "nasa ", "space ", "universe", "planet ", "asteroid",
        "black hole", "galaxy", "telescope", "quantum",
        "physics", "biology", "chemistry", "genome", "dna",
        "fossil", "earthquake", "volcano", "species",
        "scientific american", "nature journal", "climate science",
        "ocean ", "biodiversity", "evolution", "particle physics",
        "research breakthrough", "scientific discovery",
    ]),
    ("technology", [
        "artificial intelligence", " ai ", "machine learning",
        "chatgpt", "openai", "deepmind", "anthropic",
        "google", "apple", "microsoft", "meta ", "amazon",
        "nvidia", "tesla", "spacex", "semiconductor", "chip ",
        "cybersecurity", "hacked", "data breach", "ransomware",
        "electric vehicle", "self-driving", "autonomous",
        "social media", "algorithm", "big tech", "antitrust",
        "regulation tech", "quantum computing", "5g ", "6g ",
        "tech company", "silicon valley", "startup",
    ]),
    ("business", [
        "economy", "economic", "stock market", "shares",
        "gdp", "inflation", "recession", "interest rate",
        "federal reserve", "central bank", "monetary policy",
        "trade", "tariff", "export", "import",
        "merger", "acquisition", "ipo ", "earnings",
        "profit", "revenue", "bankruptcy", "default",
        "imf ", "world bank", "wto ", "opec",
        "oil price", "supply chain", "hedge fund",
        "bond yield", "nasdaq", "s&p 500", "dow jones",
        "investor", "billion dollar", "trillion dollar",
    ]),
    ("politics", [
        "president", "congress", "senate", "parliament",
        "government", "minister", "prime minister", "chancellor",
        "election", "vote", "policy", "legislation",
        "democrat", "republican", "white house",
        "nato ", "united nations", "un security council",
        "sanctions", "war", "military", "troops", "conflict",
        "treaty", "diplomat", "foreign policy",
        "ukraine", "russia", "china", "taiwan", "israel", "iran",
        "immigration", "border", "coup",
        "geopolitics", "administration", "executive order",
    ]),
]

# ════════════════════════════════════════════════════════════
# 工具函数
# ════════════════════════════════════════════════════════════
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; PulseBot/6.0)"}

def parse_rss(url, timeout=10):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        items = []
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            desc  = re.sub(r"<[^>]+>", "", item.findtext("description") or "")[:400].strip()
            link  = (item.findtext("link") or "").strip()
            pub   = (item.findtext("pubDate") or "")[:16]
            if title and link:
                items.append({"title": title, "desc": desc, "url": link, "pub": pub})
        if not items:
            for entry in root.findall("atom:entry", ns):
                title = (entry.findtext("atom:title", namespaces=ns) or "").strip()
                desc  = re.sub(r"<[^>]+>", "",
                    entry.findtext("atom:summary", namespaces=ns) or "")[:400].strip()
                link_el = entry.find("atom:link", ns)
                link  = (link_el.get("href") if link_el is not None else "")
                pub   = (entry.findtext("atom:updated", namespaces=ns) or "")[:16]
                if title and link:
                    items.append({"title": title, "desc": desc, "url": link, "pub": pub})
        return items
    except Exception as e:
        print(f"    ✗ {url.split('/')[2][:30]}: {e}")
        return []

def get_domain(url):
    try:
        return url.split("/")[2].replace("www.", "").replace("feeds.", "")
    except:
        return ""

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
            time.sleep(0.1)
            return result or text
        except Exception:
            time.sleep(0.5 * (attempt + 1))
    return text

def classify(title, desc):
    text = (title + " " + (desc or "")).lower()
    for cat, keywords in CAT_RULES:
        hits = sum(1 for kw in keywords if kw in text)
        if hits >= 2:
            return cat
    # 单词命中兜底
    for cat, keywords in CAT_RULES:
        for kw in keywords:
            if kw in text:
                return cat
    return "politics"

# ════════════════════════════════════════════════════════════
# 核心评分
# ════════════════════════════════════════════════════════════
def score(item):
    title  = (item.get("title") or "").lower()
    desc   = (item.get("desc")  or "").lower()
    url    = (item.get("url")   or "").lower()
    text   = title + " " + desc
    domain = get_domain(url)

    # 基础分来自媒体级别（差异化很大）
    base = ALL_TIERS.get(domain, 40)
    s    = base

    # 垃圾内容直接大幅扣分（优先检查）
    for w in JUNK:
        if w in title:
            s -= 35
            break  # 一票否决

    if s < 0:
        return 0

    # 极高重要性词
    for w in CRITICAL:
        if w in text:
            s += 15

    # 高重要性词
    high_hits = sum(1 for w in HIGH if w in text)
    s += min(high_hits * 8, 40)

    # 中等重要性词
    med_hits = sum(1 for w in MEDIUM if w in text)
    s += min(med_hits * 4, 20)

    # 描述质量
    dl = len(item.get("desc") or "")
    if dl > 150: s += 10
    elif dl > 80: s += 5
    elif dl < 30: s -= 15

    # 标题质量
    tl = len(item.get("title") or "")
    if tl < 20 or tl > 160: s -= 12

    return max(0, min(99, s))

# ════════════════════════════════════════════════════════════
# 故事去重（同一事件只保留最佳版本）
# ════════════════════════════════════════════════════════════
def title_fingerprint(title):
    """提取标题核心词作为指纹"""
    stop = {"the","a","an","is","are","was","were","has","have","had",
            "in","on","at","to","for","of","and","or","but","with",
            "says","said","will","would","could","may","might"}
    words = re.sub(r"[^\w\s]", "", title.lower()).split()
    key_words = [w for w in words if w not in stop and len(w) > 3]
    return frozenset(key_words[:8])

def deduplicate(scored_items):
    """同一事件多家报道 → 保留分数最高的那条"""
    kept = []
    fingerprints = []

    for imp, item in scored_items:
        fp = title_fingerprint(item["title"])
        # 检查是否与已有条目重复（≥3个关键词重合）
        is_dup = False
        for existing_fp in fingerprints:
            overlap = len(fp & existing_fp)
            if overlap >= 3:
                is_dup = True
                break
        if not is_dup:
            kept.append((imp, item))
            fingerprints.append(fp)

    return kept

# ════════════════════════════════════════════════════════════
# 主抓取流程
# ════════════════════════════════════════════════════════════
def build_data():
    print(f"\n{'═'*52}")
    print(f"  PULSE v6  —  {NOW.strftime('%Y-%m-%d %H:%M')} CST")
    print(f"  策略: 编辑优先 · 重要性驱动 · 无配额")
    print(f"{'═'*52}\n")

    pool   = []
    seen_urls   = set()
    seen_titles = set()

    # 广泛抓取
    print("[ 抓取 RSS 源 ]")
    for label, rss_url in RSS_FEEDS:
        items = parse_rss(rss_url)
        added = 0
        for item in items:
            url   = item.get("url", "")
            title = (item.get("title") or "").strip()
            if not url or url in seen_urls: continue
            if not title or "[Removed]" in title: continue
            t20 = title[:20].lower()
            if t20 in seen_titles: continue
            if not item.get("desc"): continue
            seen_urls.add(url)
            seen_titles.add(t20)
            pool.append(item)
            added += 1
        if added:
            print(f"  {label:<20} +{added:<3} (累计 {len(pool)})")
        time.sleep(0.12)

    print(f"\n  原始池: {len(pool)} 条")

    # 评分
    print("\n[ 评分 & 筛选 ]")
    scored = [(score(item), item) for item in pool]
    scored = [(s, item) for s, item in scored if s >= 50]  # 低于50分直接淘汰
    scored.sort(key=lambda x: x[0], reverse=True)
    print(f"  评分≥50: {len(scored)} 条")

    # 去重
    deduped = deduplicate(scored)
    print(f"  去重后:  {len(deduped)} 条")

    # 取前21条（1头条 + 20要闻）
    top = deduped[:21]

    # 翻译 + 分类
    print(f"\n[ 翻译 {len(top)} 条 ]")
    results = []
    for imp, item in top:
        title_en = item["title"].split(" - ")[0].strip()
        desc_en  = item["desc"]
        domain   = get_domain(item["url"])
        pub      = item.get("pub", "")[:10]

        print(f"  [{imp:2d}] {domain:<22} {title_en[:40]}…")
        title_zh = translate(title_en); time.sleep(0.08)
        desc_zh  = translate(desc_en);  time.sleep(0.08)

        cat = classify(title_en, desc_en)
        CAT_META = {
            "politics":   ("政治", "pol"),
            "business":   ("商业", "biz"),
            "technology": ("科技", "tech"),
            "science":    ("科学", "sci"),
            "health":     ("健康", "hlth"),
        }
        label, tag = CAT_META.get(cat, ("政治", "pol"))

        results.append({
            "cat":   cat,
            "tag":   tag,
            "label": label,
            "title": title_zh or title_en,
            "desc":  desc_zh  or desc_en,
            "url":   item["url"],
            "src":   f"{domain}  ·  {pub}",
            "imp":   imp,
        })

    # 头条 = 得分最高
    feat  = results[0] if results else None
    if feat:
        feat["imp"] = max(feat["imp"], 88)
    cards = results[1:]

    # 统计分布
    print(f"\n[ 分类分布 ]")
    dist = {}
    for c in cards:
        dist[c["label"]] = dist.get(c["label"], 0) + 1
    for label, n in dist.items():
        bar = "█" * n
        print(f"  {label:<6} {bar} {n}条")

    return feat, cards

# ════════════════════════════════════════════════════════════
# HTML 生成
# ════════════════════════════════════════════════════════════
def generate_html(feat, cards):
    date_str  = NOW.strftime("%-m月%-d日")
    weekdays  = ["周一","周二","周三","周四","周五","周六","周日"]
    weekday   = weekdays[NOW.weekday()]
    full_date = NOW.strftime(f"%Y年{date_str}  {weekday}")
    time_str  = NOW.strftime("%H:%M")
    h_now     = NOW.hour
    slot      = "早报" if h_now < 10 else ("午报" if h_now < 14 else "晚报")

    # 统计各分类数量（供 JS 显示）
    cat_counts = {}
    for c in cards:
        cat_counts[c["cat"]] = cat_counts.get(c["cat"], 0) + 1

    feat_json   = json.dumps(feat,       ensure_ascii=False) if feat  else "null"
    cards_json  = json.dumps(cards,      ensure_ascii=False)
    counts_json = json.dumps(cat_counts, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<meta name="description" content="Pulse — 每日精选全球最重要新闻">
<title>PULSE · {slot} · {date_str}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;600;700&family=Noto+Sans+SC:wght@300;400;500&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{{
  --bg:#f5f4f0; --surf:#fff; --surf2:#f9f8f5;
  --bd:rgba(0,0,0,.07); --bd2:rgba(0,0,0,.13);
  --t1:#1a1a18; --t2:#58574f; --t3:#a09e96;
  --red:#b5341e; --red-l:rgba(181,52,30,.08);
  --amber:#9c6b0e; --amber-l:rgba(156,107,14,.08);
  --r:5px; --tr:.15s ease;
  --max:1080px;
}}
@media(prefers-color-scheme:dark){{
  :root{{
    --bg:#111110; --surf:#1b1b18; --surf2:#161613;
    --bd:rgba(255,255,255,.07); --bd2:rgba(255,255,255,.14);
    --t1:#eae8e2; --t2:#96938b; --t3:#57554e;
    --red:#d9503a; --red-l:rgba(217,80,58,.1);
    --amber:#d4942a; --amber-l:rgba(212,148,42,.1);
  }}
}}
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0;}}
html{{scroll-behavior:smooth;}}
body{{background:var(--bg);color:var(--t1);
  font-family:'Noto Sans SC',system-ui,sans-serif;
  font-size:14px;line-height:1.7;min-height:100vh;}}
a{{text-decoration:none;color:inherit;}}
button{{cursor:pointer;font-family:inherit;border:none;background:none;}}

/* ── HEADER ─────────────────────────────── */
.hdr{{
  position:sticky;top:0;z-index:50;
  background:rgba(245,244,240,.94);
  backdrop-filter:blur(18px);
  border-bottom:1px solid var(--bd);
}}
@media(prefers-color-scheme:dark){{
  .hdr{{background:rgba(17,17,16,.94);}}
}}
.hbar{{
  display:flex;align-items:center;gap:10px;
  height:50px;padding:0 22px;
  max-width:var(--max);margin:0 auto;
}}
.logo{{
  font-family:'Noto Serif SC',serif;
  font-size:1.3rem;font-weight:700;
  letter-spacing:.06em;flex-shrink:0;
  display:flex;align-items:center;gap:5px;
  color:var(--t1);
}}
.logo-dot{{
  width:5px;height:5px;border-radius:50%;
  background:var(--red);flex-shrink:0;
  animation:blink 2.6s step-end infinite;
}}
@keyframes blink{{0%,100%{{opacity:1}}50%{{opacity:0}}}}
.slot{{
  font-family:'JetBrains Mono',monospace;
  font-size:.58rem;padding:1px 6px;
  background:var(--amber-l);color:var(--amber);
  border:1px solid rgba(156,107,14,.2);
  border-radius:3px;flex-shrink:0;
}}
.vl{{width:1px;height:14px;background:var(--bd2);flex-shrink:0;}}
.ticker{{
  flex:1;overflow:hidden;min-width:0;
  mask:linear-gradient(90deg,transparent,#000 6%,#000 94%,transparent);
  -webkit-mask:linear-gradient(90deg,transparent,#000 6%,#000 94%,transparent);
}}
.tk{{display:flex;gap:28px;white-space:nowrap;
  animation:scroll 110s linear infinite;}}
.tk:hover{{animation-play-state:paused;}}
@keyframes scroll{{0%{{transform:translateX(0)}}100%{{transform:translateX(-50%)}}}}
.tk-i{{font-size:11px;color:var(--t2);flex-shrink:0;}}
.tk-i::before{{content:'·';color:var(--red);margin-right:5px;font-weight:700;}}
.clk{{
  font-family:'JetBrains Mono',monospace;
  font-size:.62rem;color:var(--t3);
  white-space:nowrap;flex-shrink:0;
}}
.tbtn{{
  width:28px;height:28px;border-radius:50%;
  border:1px solid var(--bd2);color:var(--t3);
  font-size:13px;display:flex;align-items:center;
  justify-content:center;flex-shrink:0;
  transition:color var(--tr),background var(--tr);
}}
.tbtn:hover{{background:var(--surf2);color:var(--t1);}}
.pbar{{height:1.5px;background:var(--bd);}}
.pfill{{
  height:100%;width:0;
  background:linear-gradient(90deg,var(--red),var(--amber));
  transition:width 1s linear;
}}

/* ── SUBNAV ──────────────────────────────── */
.subnav{{
  background:var(--surf);
  border-bottom:1px solid var(--bd);
  overflow-x:auto;scrollbar-width:none;
}}
.subnav::-webkit-scrollbar{{display:none;}}
.sn{{
  display:flex;padding:0 22px;
  max-width:var(--max);margin:0 auto;
}}
.nb{{
  display:flex;align-items:center;gap:5px;
  padding:8px 14px;font-size:.76rem;font-weight:400;
  color:var(--t2);border-bottom:2px solid transparent;
  white-space:nowrap;flex-shrink:0;
  transition:color var(--tr),border-color var(--tr);
}}
.nb:hover{{color:var(--t1);}}
.nb.on{{color:var(--t1);font-weight:500;border-color:var(--red);}}
.nb-count{{
  font-family:'JetBrains Mono',monospace;
  font-size:.55rem;color:var(--t3);
  background:var(--surf2);
  padding:1px 5px;border-radius:10px;
  border:1px solid var(--bd);
  transition:opacity var(--tr);
}}
.nb.on .nb-count{{color:var(--red);border-color:rgba(181,52,30,.2);}}

/* ── LAYOUT ──────────────────────────────── */
.wrap{{max-width:var(--max);margin:0 auto;padding:24px 22px 80px;}}

/* ── SECTION ─────────────────────────────── */
.sec{{
  display:flex;align-items:center;gap:10px;
  margin:32px 0 14px;
}}
.sec:first-child{{margin-top:0;}}
.sec-t{{
  font-family:'JetBrains Mono',monospace;
  font-size:.56rem;letter-spacing:.22em;
  text-transform:uppercase;color:var(--red);
  white-space:nowrap;
}}
.sec-line{{flex:1;height:1px;background:var(--bd);}}
.sec-n{{
  font-family:'JetBrains Mono',monospace;
  font-size:.55rem;color:var(--t3);white-space:nowrap;
}}

/* ── CHIP ────────────────────────────────── */
.chip{{
  display:inline-block;
  font-family:'JetBrains Mono',monospace;
  font-size:.56rem;letter-spacing:.06em;
  padding:1px 6px;border-radius:3px;white-space:nowrap;
}}
.pol {{background:rgba(124,18,66,.09); color:#7c1242;}}
.biz {{background:rgba(101,44,12,.09); color:#65380d;}}
.tech{{background:rgba(5,66,50,.09);   color:#054232;}}
.sci {{background:rgba(10,62,95,.09);  color:#0a3e5f;}}
.hlth{{background:rgba(50,55,65,.09);  color:#323741;}}
@media(prefers-color-scheme:dark){{
  .pol {{background:rgba(157,23,77,.16); color:#f0abcc;}}
  .biz {{background:rgba(217,119,6,.14); color:#fbbf24;}}
  .tech{{background:rgba(16,185,129,.12);color:#6ee7b7;}}
  .sci {{background:rgba(59,130,246,.12);color:#93c5fd;}}
  .hlth{{background:rgba(156,163,175,.1);color:#cbd5e1;}}
}}

/* ── HERO ────────────────────────────────── */
.hero{{
  background:var(--surf);
  border:1px solid var(--bd);
  border-radius:var(--r);
  display:grid;grid-template-columns:1fr 154px;
  margin-bottom:22px;
  overflow:hidden;
  transition:border-color var(--tr);
}}
.hero:hover{{border-color:var(--bd2);}}
.hb{{padding:22px 26px;}}
.hero-top{{
  display:flex;align-items:center;gap:7px;
  margin-bottom:11px;
}}
.hl-badge{{
  font-family:'JetBrains Mono',monospace;
  font-size:.54rem;letter-spacing:.12em;
  padding:2px 7px;border-radius:3px;
  background:var(--red);color:#fff;
}}
.hero-title{{
  font-family:'Noto Serif SC',serif;
  font-size:clamp(1.2rem,2vw,1.6rem);
  font-weight:700;line-height:1.35;
  color:var(--t1);margin-bottom:11px;
  transition:color var(--tr);
}}
.hero:hover .hero-title{{color:var(--red);}}
.hero-desc{{
  font-size:.86rem;color:var(--t2);
  line-height:1.85;margin-bottom:15px;
}}
.hero-meta{{
  display:flex;align-items:center;gap:10px;
  flex-wrap:wrap;
}}
.rbtn{{
  font-family:'JetBrains Mono',monospace;
  font-size:.62rem;color:var(--red);
  border:1px solid rgba(181,52,30,.22);
  padding:3px 11px;border-radius:4px;
  display:inline-flex;align-items:center;gap:3px;
  transition:background var(--tr);
}}
.rbtn:hover{{background:var(--red-l);}}
.src-s{{
  font-family:'JetBrains Mono',monospace;
  font-size:.6rem;color:var(--t3);
}}
.imp-row{{
  display:flex;align-items:center;gap:7px;
  margin-top:13px;
}}
.imp-l{{
  font-family:'JetBrains Mono',monospace;
  font-size:.56rem;color:var(--t3);flex-shrink:0;
}}
.imp-track{{
  flex:1;height:2px;
  background:var(--bd);border-radius:1px;overflow:hidden;
}}
.imp-bar{{height:100%;background:var(--red);border-radius:1px;}}
.imp-n{{
  font-family:'JetBrains Mono',monospace;
  font-size:.56rem;color:var(--amber);
  width:18px;text-align:right;flex-shrink:0;
}}
.hs{{
  border-left:1px solid var(--bd);
  background:var(--surf2);
  padding:22px 14px;
  display:flex;flex-direction:column;
  justify-content:center;gap:18px;
}}
.hs-lbl{{
  font-family:'JetBrains Mono',monospace;
  font-size:.52rem;letter-spacing:.14em;
  text-transform:uppercase;color:var(--t3);
  margin-bottom:2px;
}}
.hs-big{{
  font-family:'Noto Serif SC',serif;
  font-size:2rem;font-weight:700;
  color:var(--amber);line-height:1;
}}
.hs-sub{{
  font-family:'JetBrains Mono',monospace;
  font-size:.55rem;color:var(--t3);
}}

/* ── NEWS LIST ───────────────────────────── */
.list{{
  background:var(--surf);
  border:1px solid var(--bd);
  border-radius:var(--r);
  overflow:hidden;
  margin-bottom:6px;
}}
.ni{{
  display:grid;
  grid-template-columns:26px 1fr 56px;
  gap:12px;align-items:start;
  padding:14px 16px;
  border-bottom:1px solid var(--bd);
  color:inherit;text-decoration:none;
  transition:background var(--tr);
}}
.ni:hover{{background:var(--surf2);}}
.ni:last-child{{border-bottom:none;}}
.ni-n{{
  font-family:'JetBrains Mono',monospace;
  font-size:.6rem;color:var(--t3);
  padding-top:2px;text-align:right;
}}
.ni-top{{
  display:flex;align-items:center;gap:6px;
  margin-bottom:5px;
}}
.ni-title{{
  font-size:.91rem;font-weight:500;
  line-height:1.52;color:var(--t1);
  margin-bottom:4px;
  transition:color var(--tr);
}}
.ni:hover .ni-title{{color:var(--red);}}
.ni-desc{{
  font-size:.76rem;color:var(--t2);line-height:1.7;
  display:-webkit-box;-webkit-line-clamp:2;
  -webkit-box-orient:vertical;overflow:hidden;
}}
.ni-src{{
  font-family:'JetBrains Mono',monospace;
  font-size:.56rem;color:var(--t3);margin-top:4px;
}}
.ni-r{{
  display:flex;flex-direction:column;
  align-items:flex-end;gap:4px;padding-top:2px;
}}
.pill{{
  font-family:'JetBrains Mono',monospace;
  font-size:.56rem;color:var(--amber);
  border:1px solid rgba(156,107,14,.22);
  padding:1px 6px;border-radius:3px;white-space:nowrap;
}}
.empty{{
  padding:40px;text-align:center;
  font-size:.78rem;color:var(--t3);
}}

/* ── FOOTER ──────────────────────────────── */
footer{{
  border-top:1px solid var(--bd);
  padding:12px 22px;
}}
.fi{{
  max-width:var(--max);margin:0 auto;
  display:flex;justify-content:space-between;
  flex-wrap:wrap;gap:5px;
}}
.fl,.fr{{
  font-family:'JetBrains Mono',monospace;
  font-size:.56rem;color:var(--t3);
}}
#nxt{{color:var(--amber);}}

@keyframes fu{{
  from{{opacity:0;transform:translateY(6px)}}
  to{{opacity:1;transform:translateY(0)}}
}}

@media(max-width:700px){{
  .ticker,.vl{{display:none;}}
  .hero{{grid-template-columns:1fr;}}
  .hs{{display:none;}}
  .ni{{grid-template-columns:20px 1fr;}}
  .ni-r{{display:none;}}
  .wrap{{padding:14px 14px 60px;}}
  .hbar{{padding:0 14px;}}
  .sn{{padding:0 14px;}}
}}
</style>
</head>
<body>

<header class="hdr">
  <div class="hbar">
    <div class="logo">PULSE<div class="logo-dot"></div></div>
    <span class="slot">{slot}</span>
    <div class="vl"></div>
    <div class="ticker"><div class="tk" id="tk"></div></div>
    <div class="vl"></div>
    <span class="clk" id="clk">—</span>
    <button class="tbtn" id="tbtn" title="切换主题">◑</button>
  </div>
  <div class="pbar"><div class="pfill" id="prog"></div></div>
</header>

<nav class="subnav">
  <div class="sn" id="nav"></div>
</nav>

<main class="wrap" id="wrap"></main>

<footer>
  <div class="fi">
    <span class="fl">PULSE · {full_date} {time_str} · 直连 Reuters / AP / FT / Nature 等35家精英媒体</span>
    <span class="fr">下次更新 <span id="nxt">—</span> · 08:00 / 12:00 / 18:00</span>
  </div>
</footer>

<script>
const FEAT   = {feat_json};
const CARDS  = {cards_json};
const COUNTS = {counts_json};

const CAT_ORDER = ['politics','business','technology','science','health'];
const CAT_NAMES = {{
  politics:'政治', business:'商业', technology:'科技',
  science:'科学', health:'健康'
}};

// ── 主题 ──────────────────────────────────────────────
let _dark = false;
document.getElementById('tbtn').addEventListener('click', () => {{
  _dark = !_dark;
  let s = document.getElementById('_ts');
  if (!s) {{ s = document.createElement('style'); s.id = '_ts'; document.head.appendChild(s); }}
  s.textContent = _dark ? `:root{{
    --bg:#111110;--surf:#1b1b18;--surf2:#161613;
    --bd:rgba(255,255,255,.07);--bd2:rgba(255,255,255,.14);
    --t1:#eae8e2;--t2:#96938b;--t3:#57554e;
    --red:#d9503a;--red-l:rgba(217,80,58,.1);
    --amber:#d4942a;--amber-l:rgba(212,148,42,.1);}}` : '';
}});

// ── 时钟 ──────────────────────────────────────────────
function pad(n) {{ return String(n).padStart(2,'0'); }}
setInterval(() => {{
  const n = new Date();
  document.getElementById('clk').textContent =
    `${{n.getFullYear()}}/${{pad(n.getMonth()+1)}}/${{pad(n.getDate())}} ${{pad(n.getHours())}}:${{pad(n.getMinutes())}}:${{pad(n.getSeconds())}}`;
}}, 1000);

// ── 倒计时 ────────────────────────────────────────────
function secsToNext() {{
  const n = new Date(), s = n.getHours()*3600 + n.getMinutes()*60 + n.getSeconds();
  for (const h of [8,12,18]) {{ if (h*3600 > s) return h*3600 - s; }}
  return 8*3600 + (86400 - s);
}}
let rem = secsToNext(), total = rem;
setInterval(() => {{
  rem--; if (rem < 0) {{ rem = secsToNext(); total = rem; }}
  document.getElementById('prog').style.width = ((total-rem)/total*100) + '%';
  const hh=Math.floor(rem/3600), mm=Math.floor((rem%3600)/60), ss=rem%60;
  const el = document.getElementById('nxt');
  if (el) el.textContent = `${{hh}}时${{pad(mm)}}分${{pad(ss)}}秒`;
}}, 1000);

// ── 辅助 ──────────────────────────────────────────────
const chip = (tag, lbl) => `<span class="chip ${{tag}}">${{lbl}}</span>`;

const sec = (text, n) => `
  <div class="sec">
    <span class="sec-t">${{text}}</span>
    <div class="sec-line"></div>
    ${{n !== undefined ? `<span class="sec-n">${{n}} 条</span>` : ''}}
  </div>`;

const heroHTML = d => !d ? '' : `
  <div class="hero">
    <div class="hb">
      <div class="hero-top">
        ${{chip(d.tag, d.label)}}
        <span class="hl-badge">HEAD LINE</span>
      </div>
      <a href="${{d.url}}" target="_blank" rel="noopener">
        <div class="hero-title">${{d.title}}</div>
      </a>
      <div class="hero-desc">${{d.desc}}</div>
      <div class="hero-meta">
        <a class="rbtn" href="${{d.url}}" target="_blank" rel="noopener">阅读原文 ↗</a>
        <span class="src-s">${{d.src}}</span>
      </div>
      <div class="imp-row">
        <span class="imp-l">重要指数</span>
        <div class="imp-track"><div class="imp-bar" style="width:${{d.imp}}%"></div></div>
        <span class="imp-n">${{d.imp}}</span>
      </div>
    </div>
    <div class="hs">
      <div>
        <div class="hs-lbl">重要指数</div>
        <div class="hs-big">${{d.imp}}</div>
        <div class="hs-sub">/ 100</div>
      </div>
      <div style="height:1px;background:var(--bd)"></div>
      <div>
        <div class="hs-lbl">来源</div>
        <div style="font-size:.72rem;color:var(--t2);margin-top:3px;line-height:1.6">${{d.src}}</div>
      </div>
    </div>
  </div>`;

const listHTML = items => !items.length
  ? '<div class="list"><div class="empty">暂无内容</div></div>'
  : '<div class="list">' + items.map((d, i) => `
      <a class="ni" href="${{d.url}}" target="_blank" rel="noopener"
         style="animation:fu .38s ${{i*.03}}s both">
        <span class="ni-n">${{String(i+1).padStart(2,'0')}}</span>
        <div>
          <div class="ni-top">${{chip(d.tag, d.label)}}</div>
          <div class="ni-title">${{d.title}}</div>
          <div class="ni-desc">${{d.desc}}</div>
          <div class="ni-src">${{d.src}}</div>
        </div>
        <div class="ni-r"><span class="pill">${{d.imp}}</span></div>
      </a>`).join('') + '</div>';

// ── 导航栏（动态生成含数量）─────────────────────────
function buildNav(activeCat) {{
  const totalCards = CARDS.length;
  let html = `<button class="nb ${{activeCat==='all'?'on':''}}" data-c="all">
    全部 <span class="nb-count">${{totalCards}}</span>
  </button>`;
  for (const c of CAT_ORDER) {{
    const n = COUNTS[c] || 0;
    if (n === 0) continue;  // 当天无该分类新闻则不显示按钮
    html += `<button class="nb ${{activeCat===c?'on':''}}" data-c="${{c}}">
      ${{CAT_NAMES[c]}} <span class="nb-count">${{n}}</span>
    </button>`;
  }}
  document.getElementById('nav').innerHTML = html;
}}

// ── 渲染 ──────────────────────────────────────────────
function render(cat) {{
  buildNav(cat);
  let h = '';

  if (cat === 'all') {{
    // 头条
    if (FEAT) {{ h += sec('今日头条'); h += heroHTML(FEAT); }}

    // 按分类分组，每组独立标题
    for (const c of CAT_ORDER) {{
      const items = CARDS.filter(x => x.cat === c);
      if (!items.length) continue;
      h += sec(CAT_NAMES[c], items.length);
      h += listHTML(items);
    }}
  }} else {{
    const items = CARDS.filter(x => x.cat === cat);
    // 如果头条属于该分类也显示
    if (FEAT && FEAT.cat === cat) {{
      h += sec('今日头条');
      h += heroHTML(FEAT);
    }}
    h += sec(CAT_NAMES[cat] || cat, items.length);
    h += listHTML(items);
  }}

  document.getElementById('wrap').innerHTML = h;
}}

// ── 导航点击 ──────────────────────────────────────────
document.getElementById('nav').addEventListener('click', e => {{
  const b = e.target.closest('.nb');
  if (!b) return;
  render(b.dataset.c);
}});

// ── Ticker ────────────────────────────────────────────
const titles = (FEAT ? [FEAT.title] : []).concat(CARDS.map(c => c.title));
document.getElementById('tk').innerHTML =
  titles.concat(titles).map(t => `<span class="tk-i">${{t}}</span>`).join('');

render('all');
</script>
</body>
</html>"""

def main():
    feat, cards = build_data()
    html = generate_html(feat, cards)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n✅ index.html 已生成  ({1 if feat else 0} 头条 + {len(cards)} 要闻)")

if __name__ == "__main__":
    main()
