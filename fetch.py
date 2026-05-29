#!/usr/bin/env python3
"""
Pulse v5 — 高价值新闻引擎
架构：直接抓取权威媒体 RSS → 内容质量评分 → 分类匹配 → 每类取最佳5条

为什么放弃 NewsAPI top-headlines？
- top-headlines 按"热度"排序，混入大量娱乐/体育/软新闻
- RSS 直接来自编辑精选，质量可控
- 可精准控制每个分类的来源

NewsAPI 作为补充兜底（RSS 条数不足时）
"""

import os, json, time, re, requests
from datetime import datetime, timezone, timedelta
from urllib.parse import quote
import xml.etree.ElementTree as ET

API_KEY = os.environ.get("NEWS_API_KEY", "37bf8ef8267f4751bd51311507429eab")
CST     = timezone(timedelta(hours=8))
NOW     = datetime.now(CST)

# ════════════════════════════════════════════════════════════
# RSS 源配置 — 按分类，只选编辑质量最高的来源
# ════════════════════════════════════════════════════════════
RSS_SOURCES = {
    "politics": [
        "https://feeds.reuters.com/Reuters/PoliticsNews",
        "https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml",
        "https://feeds.washingtonpost.com/rss/politics",
        "https://feeds.a.dj.com/rss/RSSWorldNews.xml",
        "https://www.politico.com/rss/politicopicks.xml",
        "https://apnews.com/rss",
        "https://www.theguardian.com/world/rss",
        "https://foreignpolicy.com/feed/",
        "https://www.aljazeera.com/xml/rss/all.xml",
        "https://www.spiegel.de/international/index.rss",
    ],
    "business": [
        "https://feeds.reuters.com/reuters/businessNews",
        "https://feeds.bloomberg.com/markets/news.rss",
        "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
        "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
        "https://www.economist.com/finance-and-economics/rss.xml",
        "https://feeds.ft.com/rss/home/uk",
        "https://fortune.com/feed/",
        "https://feeds.washingtonpost.com/rss/business",
    ],
    "technology": [
        "https://feeds.arstechnica.com/arstechnica/index",
        "https://www.wired.com/feed/rss",
        "https://techcrunch.com/feed/",
        "https://www.theverge.com/rss/index.xml",
        "https://feeds.reuters.com/reuters/technologyNews",
        "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
        "https://www.technologyreview.com/feed/",
        "https://feeds.feedburner.com/venturebeat/SZYF",
    ],
    "science": [
        "https://www.nature.com/nature.rss",
        "https://rss.nytimes.com/services/xml/rss/nyt/Science.xml",
        "https://www.science.org/rss/news_current.xml",
        "https://feeds.reuters.com/reuters/scienceNews",
        "https://www.newscientist.com/feed/home/",
        "https://phys.org/rss-feed/",
        "https://www.sciencedaily.com/rss/top.xml",
        "https://www.scientificamerican.com/feed/",
        "https://feeds.nationalgeographic.com/ng/News/News_Main",
    ],
    "health": [
        "https://rss.nytimes.com/services/xml/rss/nyt/Health.xml",
        "https://www.statnews.com/feed/",
        "https://feeds.reuters.com/reuters/healthNews",
        "https://www.nejm.org/action/showFeed?type=etoc&feed=rss&jc=nejm",
        "https://www.thelancet.com/rssfeed/lancet_online.xml",
        "https://www.medscape.com/rss/news",
        "https://feeds.webmd.com/rss/rss.aspx?RSSSource=RSS_PUBLIC",
        "https://www.medicalnewstoday.com/rss",
    ],
}

# ════════════════════════════════════════════════════════════
# 分类关键词（用于校验内容是否真的属于该分类）
# ════════════════════════════════════════════════════════════
CAT_KEYWORDS = {
    "politics": [
        "president", "congress", "senate", "parliament", "government", "minister",
        "election", "vote", "policy", "law", "democrat", "republican",
        "trump", "white house", "nato", "united nations", "sanctions",
        "war", "military", "troops", "conflict", "treaty", "diplomat",
        "ukraine", "russia", "china", "taiwan", "israel", "iran", "gaza",
        "immigration", "border", "coup", "geopolit", "prime minister",
        "foreign policy", "administration", "legislation", "executive",
    ],
    "business": [
        "economy", "economic", "market", "stock", "shares", "fund",
        "gdp", "inflation", "recession", "interest rate", "federal reserve",
        "central bank", "trade", "tariff", "merger", "acquisition",
        "ipo", "earnings", "profit", "revenue", "bank", "finance",
        "debt", "imf", "oil price", "supply chain", "bond", "yield",
        "nasdaq", "s&p", "quarter", "fiscal", "monetary", "investor",
        "startup", "venture capital", "billion", "trillion",
    ],
    "technology": [
        "artificial intelligence", " ai ", "machine learning", "chatgpt", "openai",
        "google", "apple", "microsoft", "meta", "amazon", "nvidia", "tesla",
        "spacex", "semiconductor", "chip", "software", "cybersecurity",
        "hack", "data breach", "robot", "electric vehicle", "battery",
        "social media", "tiktok", "algorithm", "cloud", "quantum",
        "smartphone", "iphone", "android", "data center", "programming",
        "tech company", "big tech", "regulation", "antitrust",
    ],
    "science": [
        "scientists", "researchers", "research", "study", "discovery",
        "nasa", "space", "universe", "planet", "asteroid", "black hole",
        "galaxy", "telescope", "rocket", "astronaut", "quantum",
        "physics", "biology", "chemistry", "genome", "dna",
        "fossil", "climate", "ocean", "earthquake", "volcano", "species",
        "evolution", "experiment", "scientific", "journal", "nature",
        "atmosphere", "glacier", "extinction", "biodiversity", "particle",
    ],
    "health": [
        "health", "medical", "medicine", "hospital", "disease", "virus",
        "vaccine", "cancer", "tumor", "drug", "fda", "cdc", "who",
        "mental health", "obesity", "diabetes", "heart disease", "stroke",
        "surgery", "clinical trial", "pandemic", "epidemic", "patient",
        "pharmaceutical", "therapy", "treatment", "symptom", "nutrition",
        "antibiotic", "infection", "outbreak", "alzheimer", "dementia",
        "depression", "anxiety", "life expectancy", "mortality",
    ],
}

# ════════════════════════════════════════════════════════════
# 高价值信号词（全局，不分类）
# ════════════════════════════════════════════════════════════
HIGH_VALUE = [
    # 重大事件
    "killed", "dead", "death", "war", "attack", "strike", "explosion",
    "crisis", "collapse", "emergency", "disaster", "catastrophe",
    # 政策/决定
    "nuclear", "sanctions", "resign", "arrested", "sentenced", "banned",
    "signed", "approved", "rejected", "passed", "vetoed", "indicted",
    # 市场/经济
    "record high", "record low", "crash", "surge", "plunge", "historic",
    "unprecedented", "first time", "breakthrough",
    # 重要人物
    "president", "prime minister", "chancellor", "secretary",
]
LOW_VALUE = [
    # 软新闻/娱乐
    "celebrity", "oscars", "grammy", "kardashian", "taylor swift",
    "nfl", "nba", "fifa", "super bowl", "world cup",
    # 点击诱饵
    "quiz", "top 10", "ranking", "best of", "how to watch",
    "photos:", "video:", "everything you need to know",
    "here's what", "what to know about", "your guide",
    "listicle", "roundup", "recap:", "week in pictures",
    # 广告/推广
    "sponsored", "partner content", "advertisement",
    # 观点/专栏（有时质量低）
    "opinion:", "editorial:", "letters:", "dear",
]
PRESTIGE_DOMAINS = [
    "reuters.com", "nytimes.com", "washingtonpost.com",
    "bloomberg.com", "ft.com", "economist.com",
    "wsj.com", "theguardian.com", "apnews.com", "politico.com",
    "nature.com", "science.org", "newscientist.com", "scientificamerican.com",
    "statnews.com", "nejm.org", "thelancet.com",
    "axios.com", "foreignpolicy.com", "aljazeera.com",
    "technologyreview.com", "wired.com", "arstechnica.com",
    "spiegel.de",
]

# ════════════════════════════════════════════════════════════
# RSS 解析
# ════════════════════════════════════════════════════════════
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; PulseBot/5.0; "
        "+https://github.com/pulse-news)"
    )
}

def parse_rss(url, timeout=10):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        ns   = {"atom": "http://www.w3.org/2005/Atom"}
        items = []

        # RSS 2.0
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            desc  = (item.findtext("description") or "").strip()
            link  = (item.findtext("link") or "").strip()
            pub   = (item.findtext("pubDate") or "")[:16]
            # 清理 HTML 标签
            desc = re.sub(r"<[^>]+>", "", desc)[:400]
            if title and link:
                items.append({"title": title, "desc": desc,
                              "url": link, "pub": pub})

        # Atom
        if not items:
            for entry in root.findall("atom:entry", ns):
                title = (entry.findtext("atom:title", namespaces=ns) or "").strip()
                desc  = (entry.findtext("atom:summary", namespaces=ns) or "").strip()
                link_el = entry.find("atom:link", ns)
                link  = (link_el.get("href") if link_el is not None else "")
                pub   = (entry.findtext("atom:updated", namespaces=ns) or "")[:16]
                desc  = re.sub(r"<[^>]+>", "", desc)[:400]
                if title and link:
                    items.append({"title": title, "desc": desc,
                                  "url": link, "pub": pub})
        return items
    except Exception as e:
        print(f"    RSS 解析失败 {url[:50]}: {e}")
        return []

# ════════════════════════════════════════════════════════════
# 翻译
# ════════════════════════════════════════════════════════════
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

# ════════════════════════════════════════════════════════════
# 评分
# ════════════════════════════════════════════════════════════
def score_article(item, cat):
    title = (item.get("title") or "").lower()
    desc  = (item.get("desc")  or "").lower()
    url   = (item.get("url")   or "").lower()
    text  = title + " " + desc
    s = 50

    # 权威域名
    for d in PRESTIGE_DOMAINS:
        if d in url:
            s += 20
            break

    # 分类相关度
    kws = CAT_KEYWORDS.get(cat, [])
    hits = sum(1 for kw in kws if kw in text)
    s += min(hits * 4, 24)

    # 高价值词
    for w in HIGH_VALUE:
        if w in text:
            s += 7

    # 低价值惩罚
    for w in LOW_VALUE:
        if w in title:
            s -= 25

    # 描述质量
    dl = len(item.get("desc") or "")
    if dl > 120: s += 10
    elif dl < 40: s -= 12

    # 标题长度
    tl = len(item.get("title") or "")
    if tl < 15 or tl > 180: s -= 15

    return max(0, min(99, s))

def is_relevant(item, cat):
    text = (
        (item.get("title") or "") + " " + (item.get("desc") or "")
    ).lower()
    return any(kw in text for kw in CAT_KEYWORDS.get(cat, []))

# ════════════════════════════════════════════════════════════
# NewsAPI 兜底（RSS 不足时补充）
# ════════════════════════════════════════════════════════════
NEWSAPI_CAT_MAP = {
    "politics":   "general",
    "business":   "business",
    "technology": "technology",
    "science":    "science",
    "health":     "health",
}
def newsapi_fallback(cat, page_size=20):
    if not API_KEY:
        return []
    try:
        r = requests.get(
            "https://newsapi.org/v2/top-headlines",
            params={
                "category": NEWSAPI_CAT_MAP.get(cat, cat),
                "language": "en",
                "pageSize": page_size,
                "apiKey":   API_KEY,
            },
            timeout=12,
        )
        arts = r.json().get("articles", [])
        return [
            {
                "title": (a.get("title") or "").split(" - ")[0].strip(),
                "desc":  (a.get("description") or "")[:400],
                "url":   a.get("url", ""),
                "pub":   (a.get("publishedAt") or "")[:10],
            }
            for a in arts
            if a.get("title") and a.get("description") and a.get("url")
        ]
    except Exception as e:
        print(f"    NewsAPI 兜底失败: {e}")
        return []

# ════════════════════════════════════════════════════════════
# 主抓取流程
# ════════════════════════════════════════════════════════════
def fetch_category(cat, global_seen, target=5):
    print(f"\n  ── [{cat}] ──────────────────────────")
    raw   = []
    seen  = set()

    def add(items, label):
        added = 0
        for item in items:
            url   = item.get("url", "")
            title = (item.get("title") or "").strip()
            if not url or url in global_seen or url in seen: continue
            if not title or "[Removed]" in title: continue
            t30 = title[:30].lower()
            if t30 in seen: continue
            if not item.get("desc"): continue
            if not is_relevant(item, cat): continue
            seen.add(url); seen.add(t30)
            raw.append(item); added += 1
        if added:
            print(f"    {label}: +{added} (累计 {len(raw)})")

    # 1. RSS 源（主力）
    for rss_url in RSS_SOURCES.get(cat, []):
        items = parse_rss(rss_url)
        add(items, rss_url.split("/")[2])
        time.sleep(0.15)
        if len(raw) >= target * 4:
            break

    # 2. NewsAPI 兜底
    if len(raw) < target:
        print(f"    RSS 仅 {len(raw)} 条，启用 NewsAPI 兜底…")
        add(newsapi_fallback(cat), "NewsAPI")
        time.sleep(0.2)

    # 评分 → 排序 → 取前 target 条
    scored = sorted(
        [(score_article(a, cat), a) for a in raw],
        key=lambda x: x[0], reverse=True
    )
    best = scored[:target]
    print(f"    评分后: {len(best)}/{len(raw)} 条入选")

    # 翻译
    results = []
    for imp, item in best:
        title_en = item["title"]
        desc_en  = item["desc"]
        pub      = item.get("pub", "")[:10]
        domain   = item.get("url","").split("/")[2].replace("www.","")

        print(f"    [{imp:2d}] {title_en[:45]}…")
        title_zh = translate(title_en);  time.sleep(0.08)
        desc_zh  = translate(desc_en);   time.sleep(0.08)

        CAT_META = {
            "politics":   ("政治", "pol"),
            "business":   ("商业", "biz"),
            "technology": ("科技", "tech"),
            "science":    ("科学", "sci"),
            "health":     ("健康", "hlth"),
        }
        label, tag = CAT_META.get(cat, ("综合","top"))

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
        global_seen.add(item["url"])

    return results

def fetch_headline(global_seen):
    """头条：从所有 RSS 中挑全局评分最高的一篇"""
    print("\n  ── [头条] ──────────────────────────")
    candidates = []
    priority_feeds = [
        "https://feeds.reuters.com/Reuters/PoliticsNews",
        "https://feeds.reuters.com/reuters/businessNews",
        "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
        "https://feeds.washingtonpost.com/rss/world",
        "https://feeds.a.dj.com/rss/RSSWorldNews.xml",
        "https://apnews.com/rss",
        "https://www.theguardian.com/world/rss",
        "https://feeds.bloomberg.com/markets/news.rss",
        "https://www.economist.com/the-world-this-week/rss.xml",
        "https://www.spiegel.de/international/index.rss",
    ]
    seen = set()
    for feed in priority_feeds:
        for item in parse_rss(feed):
            url = item.get("url","")
            title = (item.get("title") or "").strip()
            if not url or url in global_seen or url in seen: continue
            if not title or not item.get("desc"): continue
            seen.add(url)
            # 全局评分（不限分类）
            s = score_article(item, "politics")
            for w in HIGH_VALUE:
                if w in title.lower(): s += 5
            candidates.append((s, item))
        time.sleep(0.12)

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    imp, item = candidates[0]

    title_en = item["title"]
    desc_en  = item["desc"]
    pub      = item.get("pub","")[:10]
    domain   = item.get("url","").split("/")[2].replace("www.","")

    print(f"    选中 [{imp}]: {title_en[:50]}…")
    title_zh = translate(title_en); time.sleep(0.1)
    desc_zh  = translate(desc_en);  time.sleep(0.1)

    global_seen.add(item["url"])

    # 自动识别分类
    text = (title_en + " " + desc_en).lower()
    feat_cat, feat_tag, feat_label = "politics", "pol", "政治"
    for cat, kws in CAT_KEYWORDS.items():
        if sum(1 for kw in kws if kw in text) >= 2:
            meta = {"politics":("政治","pol"), "business":("商业","biz"),
                    "technology":("科技","tech"), "science":("科学","sci"),
                    "health":("健康","hlth")}
            feat_label, feat_tag = meta.get(cat, ("政治","pol"))
            feat_cat = cat
            break

    return {
        "cat":   feat_cat, "tag": feat_tag, "label": feat_label,
        "title": title_zh or title_en,
        "desc":  desc_zh  or desc_en,
        "url":   item["url"],
        "src":   f"{domain}  ·  {pub}",
        "imp":   max(imp, 88),
    }

def build_data():
    global_seen = set()
    feat  = fetch_headline(global_seen)
    cards = []
    for cat in ["politics", "business", "technology", "science", "health"]:
        cards.extend(fetch_category(cat, global_seen, target=5))

    print(f"\n  头条: {1 if feat else 0}")
    for cat in ["politics","business","technology","science","health"]:
        n = sum(1 for c in cards if c["cat"]==cat)
        label = {"politics":"政治","business":"商业","technology":"科技",
                 "science":"科学","health":"健康"}[cat]
        print(f"  {label}: {n} 条")
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
    h         = NOW.hour
    slot      = "早报" if h < 10 else ("午报" if h < 14 else "晚报")
    feat_json  = json.dumps(feat,  ensure_ascii=False) if feat else "null"
    cards_json = json.dumps(cards, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<meta name="description" content="Pulse — 每日精选全球最有价值新闻">
<title>PULSE · {slot} · {date_str}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;600;700&family=Noto+Sans+SC:wght@300;400;500&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{{
  --bg:#f7f6f3;--surf:#fff;--surf2:#fafaf8;
  --bd:rgba(0,0,0,.07);--bd2:rgba(0,0,0,.12);
  --t1:#1a1a1a;--t2:#5a5a5a;--t3:#a0a09a;
  --red:#c0392b;--red-bg:#fdf2f1;
  --amber:#b7791f;--amber-bg:#fffbeb;
  --r:6px;--tr:.18s ease;
}}
@media(prefers-color-scheme:dark){{
  :root{{
    --bg:#111110;--surf:#1c1c1a;--surf2:#181816;
    --bd:rgba(255,255,255,.07);--bd2:rgba(255,255,255,.13);
    --t1:#ede9e3;--t2:#9a9690;--t3:#5a5652;
    --red:#e05a4f;--red-bg:rgba(192,57,43,.12);
    --amber:#e9a825;--amber-bg:rgba(183,121,31,.12);
  }}
}}
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0;}}
html{{scroll-behavior:smooth;}}
body{{background:var(--bg);color:var(--t1);
  font-family:'Noto Sans SC',system-ui,sans-serif;
  font-size:14px;line-height:1.7;}}
a{{text-decoration:none;color:inherit;}}
button{{cursor:pointer;font-family:inherit;border:none;background:none;}}

.hdr{{position:sticky;top:0;z-index:50;
  background:rgba(247,246,243,.95);
  backdrop-filter:blur(16px);
  border-bottom:1px solid var(--bd);}}
@media(prefers-color-scheme:dark){{.hdr{{background:rgba(17,17,16,.95);}}}}
.hbar{{display:flex;align-items:center;gap:10px;
  height:48px;padding:0 20px;
  max-width:1080px;margin:0 auto;}}
.logo{{font-family:'Noto Serif SC',serif;
  font-size:1.35rem;font-weight:700;letter-spacing:.06em;
  flex-shrink:0;display:flex;align-items:center;gap:5px;}}
.logo-dot{{width:6px;height:6px;border-radius:50%;background:var(--red);
  animation:blink 2.4s step-end infinite;}}
@keyframes blink{{0%,100%{{opacity:1}}50%{{opacity:0}}}}
.slot-tag{{font-family:'JetBrains Mono',monospace;
  font-size:.6rem;padding:2px 7px;
  background:var(--amber-bg);color:var(--amber);
  border:1px solid rgba(183,121,31,.25);border-radius:3px;flex-shrink:0;}}
.vsep{{width:1px;height:16px;background:var(--bd2);flex-shrink:0;}}
.ticker{{flex:1;overflow:hidden;
  mask:linear-gradient(90deg,transparent,#000 5%,#000 95%,transparent);
  -webkit-mask:linear-gradient(90deg,transparent,#000 5%,#000 95%,transparent);}}
.tk-inner{{display:flex;gap:32px;white-space:nowrap;
  animation:scroll 100s linear infinite;}}
.tk-inner:hover{{animation-play-state:paused;}}
@keyframes scroll{{0%{{transform:translateX(0)}}100%{{transform:translateX(-50%)}}}}
.tk-item{{font-size:11.5px;color:var(--t2);flex-shrink:0;}}
.tk-item::before{{content:'·';color:var(--red);margin-right:6px;font-weight:700;}}
.clk{{font-family:'JetBrains Mono',monospace;
  font-size:.65rem;color:var(--t3);white-space:nowrap;flex-shrink:0;}}
.tbtn{{width:30px;height:30px;border-radius:50%;
  border:1px solid var(--bd2);color:var(--t2);font-size:14px;
  display:flex;align-items:center;justify-content:center;
  flex-shrink:0;transition:background var(--tr);}}
.tbtn:hover{{background:var(--surf2);}}
.pbar{{height:1.5px;background:var(--bd);}}
.pfill{{height:100%;background:linear-gradient(90deg,var(--red),var(--amber));
  width:0;transition:width 1s linear;}}

.subnav{{background:var(--surf);border-bottom:1px solid var(--bd);
  overflow-x:auto;scrollbar-width:none;}}
.subnav::-webkit-scrollbar{{display:none;}}
.sninner{{display:flex;padding:0 20px;max-width:1080px;margin:0 auto;}}
.nb{{padding:9px 16px;font-size:.78rem;font-weight:400;color:var(--t2);
  border-bottom:2px solid transparent;white-space:nowrap;
  transition:color var(--tr),border-color var(--tr);flex-shrink:0;}}
.nb:hover{{color:var(--t1);}}
.nb.on{{color:var(--t1);font-weight:500;border-color:var(--red);}}

.wrap{{max-width:1080px;margin:0 auto;padding:28px 20px 80px;}}
.sec{{display:flex;align-items:center;gap:10px;margin:36px 0 16px;}}
.sec:first-child{{margin-top:0;}}
.sec-t{{font-family:'JetBrains Mono',monospace;
  font-size:.58rem;letter-spacing:.2em;text-transform:uppercase;
  color:var(--red);white-space:nowrap;}}
.sec-line{{flex:1;height:1px;background:var(--bd);}}
.sec-badge{{font-family:'JetBrains Mono',monospace;
  font-size:.58rem;color:var(--t3);white-space:nowrap;}}

.chip{{display:inline-block;font-family:'JetBrains Mono',monospace;
  font-size:.58rem;letter-spacing:.06em;
  padding:2px 7px;border-radius:3px;white-space:nowrap;}}
.pol {{background:rgba(157,23,77,.1);  color:#9d174d;}}
.biz {{background:rgba(120,53,15,.1);  color:#92400e;}}
.tech{{background:rgba(6,78,59,.1);    color:#065f46;}}
.sci {{background:rgba(12,74,110,.1);  color:#0c4a6e;}}
.hlth{{background:rgba(55,65,81,.1);   color:#374151;}}
@media(prefers-color-scheme:dark){{
  .pol {{background:rgba(157,23,77,.2); color:#f9a8d4;}}
  .biz {{background:rgba(217,119,6,.18);color:#fcd34d;}}
  .tech{{background:rgba(16,185,129,.15);color:#6ee7b7;}}
  .sci {{background:rgba(59,130,246,.15);color:#93c5fd;}}
  .hlth{{background:rgba(156,163,175,.12);color:#d1d5db;}}
}}

.hero{{background:var(--surf);border:1px solid var(--bd);
  border-radius:var(--r);overflow:hidden;
  display:grid;grid-template-columns:1fr 160px;
  margin-bottom:24px;}}
.hero-body{{padding:24px 28px;}}
.hero-top{{display:flex;align-items:center;gap:8px;margin-bottom:12px;}}
.hbadge{{font-family:'JetBrains Mono',monospace;
  font-size:.56rem;letter-spacing:.12em;
  padding:2px 8px;border-radius:3px;
  background:var(--red);color:#fff;}}
.hero-title{{font-family:'Noto Serif SC',serif;
  font-size:clamp(1.25rem,2.2vw,1.7rem);font-weight:700;
  line-height:1.35;color:var(--t1);margin-bottom:12px;
  transition:color var(--tr);}}
.hero:hover .hero-title{{color:var(--red);}}
.hero-desc{{font-size:.88rem;color:var(--t2);line-height:1.85;margin-bottom:16px;}}
.hero-meta{{display:flex;align-items:center;gap:12px;flex-wrap:wrap;}}
.read-btn{{font-family:'JetBrains Mono',monospace;font-size:.65rem;color:var(--red);
  border:1px solid rgba(192,57,43,.25);padding:4px 12px;border-radius:4px;
  display:inline-flex;align-items:center;gap:4px;transition:background var(--tr);}}
.read-btn:hover{{background:var(--red-bg);}}
.src{{font-family:'JetBrains Mono',monospace;font-size:.62rem;color:var(--t3);}}
.imp-row{{display:flex;align-items:center;gap:8px;margin-top:14px;}}
.imp-lbl{{font-family:'JetBrains Mono',monospace;font-size:.58rem;color:var(--t3);flex-shrink:0;}}
.imp-bar{{flex:1;height:2px;background:var(--bd);border-radius:1px;overflow:hidden;}}
.imp-fill{{height:100%;background:var(--red);border-radius:1px;}}
.imp-n{{font-family:'JetBrains Mono',monospace;font-size:.58rem;color:var(--amber);
  width:20px;text-align:right;flex-shrink:0;}}
.hero-side{{border-left:1px solid var(--bd);background:var(--surf2);
  padding:24px 16px;display:flex;flex-direction:column;
  justify-content:center;gap:20px;}}
.hs-lbl{{font-family:'JetBrains Mono',monospace;
  font-size:.54rem;letter-spacing:.15em;text-transform:uppercase;
  color:var(--t3);margin-bottom:3px;}}
.hs-big{{font-family:'Noto Serif SC',serif;
  font-size:2.2rem;font-weight:700;color:var(--amber);line-height:1;}}
.hs-sub{{font-family:'JetBrains Mono',monospace;font-size:.58rem;color:var(--t3);}}

.list{{background:var(--surf);border:1px solid var(--bd);
  border-radius:var(--r);overflow:hidden;margin-bottom:4px;}}
.ni{{display:grid;grid-template-columns:28px 1fr 60px;
  gap:14px;align-items:start;padding:15px 18px;
  border-bottom:1px solid var(--bd);color:inherit;text-decoration:none;
  transition:background var(--tr);}}
.ni:hover{{background:var(--surf2);}}
.ni:last-child{{border-bottom:none;}}
.ni-n{{font-family:'JetBrains Mono',monospace;font-size:.62rem;color:var(--t3);
  padding-top:3px;text-align:right;}}
.ni-top{{display:flex;align-items:center;gap:7px;margin-bottom:6px;}}
.ni-title{{font-size:.93rem;font-weight:500;line-height:1.5;
  color:var(--t1);margin-bottom:4px;transition:color var(--tr);}}
.ni:hover .ni-title{{color:var(--red);}}
.ni-desc{{font-size:.78rem;color:var(--t2);line-height:1.7;
  display:-webkit-box;-webkit-line-clamp:2;
  -webkit-box-orient:vertical;overflow:hidden;}}
.ni-src{{font-family:'JetBrains Mono',monospace;font-size:.58rem;color:var(--t3);margin-top:5px;}}
.ni-right{{display:flex;flex-direction:column;align-items:flex-end;gap:5px;padding-top:3px;}}
.pill{{font-family:'JetBrains Mono',monospace;font-size:.58rem;color:var(--amber);
  border:1px solid rgba(183,121,31,.25);padding:2px 7px;border-radius:3px;white-space:nowrap;}}
.empty{{padding:32px;text-align:center;font-size:.8rem;color:var(--t3);}}

footer{{border-top:1px solid var(--bd);padding:14px 20px;}}
.fi{{max-width:1080px;margin:0 auto;
  display:flex;justify-content:space-between;flex-wrap:wrap;gap:6px;}}
.fl,.fr{{font-family:'JetBrains Mono',monospace;font-size:.58rem;color:var(--t3);}}
#nxt{{color:var(--amber);}}
@keyframes fu{{from{{opacity:0;transform:translateY(8px)}}to{{opacity:1;transform:translateY(0)}}}}
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
    <button class="tbtn" id="tbtn">◑</button>
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
    <span class="fl">PULSE · {full_date} {time_str} · RSS 直连权威媒体</span>
    <span class="fr">下次更新 <span id="nxt">—</span> · 08:00 / 12:00 / 18:00</span>
  </div>
</footer>
<script>
const FEAT={feat_json};
const CARDS={cards_json};
let _dk=false;
document.getElementById('tbtn').addEventListener('click',()=>{{
  _dk=!_dk;
  let s=document.getElementById('_ts');
  if(!s){{s=document.createElement('style');s.id='_ts';document.head.appendChild(s);}}
  s.textContent=_dk?`:root{{
    --bg:#111110;--surf:#1c1c1a;--surf2:#181816;
    --bd:rgba(255,255,255,.07);--bd2:rgba(255,255,255,.13);
    --t1:#ede9e3;--t2:#9a9690;--t3:#5a5652;
    --red:#e05a4f;--red-bg:rgba(192,57,43,.12);
    --amber:#e9a825;--amber-bg:rgba(183,121,31,.12);}}`:'';
}});
function pad(n){{return String(n).padStart(2,'0');}}
setInterval(()=>{{
  const n=new Date();
  document.getElementById('clk').textContent=
    `${{n.getFullYear()}}/${{pad(n.getMonth()+1)}}/${{pad(n.getDate())}} ${{pad(n.getHours())}}:${{pad(n.getMinutes())}}:${{pad(n.getSeconds())}}`;
}},1000);
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
const chip=(tag,lbl)=>`<span class="chip ${{tag}}">${{lbl}}</span>`;
const heroHTML=d=>!d?'': `<div class="hero">
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
const listHTML=items=>!items.length
  ?'<div class="list"><div class="empty">暂无内容</div></div>'
  :'<div class="list">'+items.map((d,i)=>`
  <a class="ni" href="${{d.url}}" target="_blank" rel="noopener">
    <span class="ni-n">${{String(i+1).padStart(2,'0')}}</span>
    <div>
      <div class="ni-top">${{chip(d.tag,d.label)}}</div>
      <div class="ni-title">${{d.title}}</div>
      <div class="ni-desc">${{d.desc}}</div>
      <div class="ni-src">${{d.src}}</div>
    </div>
    <div class="ni-right"><span class="pill">${{d.imp}}</span></div>
  </a>`).join('')+'</div>';
const sec=(t,b)=>`<div class="sec"><span class="sec-t">${{t}}</span><div class="sec-line"></div>${{b?`<span class="sec-badge">${{b}}</span>`:''}}</div>`;
const CAT_NAMES={{politics:'政治',business:'商业',technology:'科技',science:'科学',health:'健康'}};
const CAT_ORDER=['politics','business','technology','science','health'];
function render(cat){{
  let h='';
  if(cat==='all'){{
    if(FEAT){{h+=sec('今日头条');h+=heroHTML(FEAT);}}
    for(const c of CAT_ORDER){{
      const items=CARDS.filter(x=>x.cat===c);
      if(!items.length)continue;
      h+=sec(CAT_NAMES[c],items.length+'条');
      h+=listHTML(items);
    }}
  }}else{{
    const items=CARDS.filter(x=>x.cat===cat);
    if(FEAT&&FEAT.cat===cat){{h+=sec('今日头条');h+=heroHTML(FEAT);}}
    h+=sec(CAT_NAMES[cat]||cat,items.length+'条');
    h+=listHTML(items);
  }}
  document.getElementById('wrap').innerHTML=h;
}}
document.getElementById('nav').addEventListener('click',e=>{{
  const b=e.target.closest('.nb');if(!b)return;
  document.querySelectorAll('.nb').forEach(x=>x.classList.remove('on'));
  b.classList.add('on');render(b.dataset.c);
}});
const titles=(FEAT?[FEAT.title]:[]).concat(CARDS.map(c=>c.title));
document.getElementById('tk').innerHTML=
  titles.concat(titles).map(t=>`<span class="tk-item">${{t}}</span>`).join('');
render('all');
</script>
</body>
</html>"""

def main():
    print(f"\n{'═'*52}")
    print(f"  PULSE v5  —  {NOW.strftime('%Y-%m-%d %H:%M')} CST")
    print(f"  策略: RSS 直连权威媒体 + NewsAPI 兜底")
    print(f"{'═'*52}")
    feat, cards = build_data()
    html = generate_html(feat, cards)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n✅ 完成 → index.html")

if __name__ == "__main__":
    main()
