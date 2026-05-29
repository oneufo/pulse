#!/usr/bin/env python3
"""
Pulse v7
规则：每分类 6 个不同来源，每源取评分最高的 1 篇
总计：5 × 6 = 30 篇，另选全局最佳 1 篇为头条
设计：Claude 风格 — 温暖克制，编辑感
"""

import os, json, time, re, requests
from datetime import datetime, timezone, timedelta
from urllib.parse import quote
import xml.etree.ElementTree as ET

API_KEY = os.environ.get("NEWS_API_KEY", "37bf8ef8267f4751bd51311507429eab")
CST     = timezone(timedelta(hours=8))
NOW     = datetime.now(CST)

# ═══════════════════════════════════════════════════════════════
# 分类 × 来源定义（每类 6 个固定来源，各不相同）
# ═══════════════════════════════════════════════════════════════
CATEGORY_SOURCES = {
    "politics": {
        "label": "政治", "tag": "pol",
        "sources": [
            {"name": "Reuters",          "rss": "https://feeds.reuters.com/Reuters/PoliticsNews"},
            {"name": "AP News",          "rss": "https://apnews.com/rss"},
            {"name": "The New York Times","rss": "https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml"},
            {"name": "Washington Post",  "rss": "https://feeds.washingtonpost.com/rss/politics"},
            {"name": "Politico",         "rss": "https://www.politico.com/rss/politicopicks.xml"},
            {"name": "Foreign Policy",   "rss": "https://foreignpolicy.com/feed/"},
        ],
    },
    "business": {
        "label": "商业", "tag": "biz",
        "sources": [
            {"name": "Reuters",          "rss": "https://feeds.reuters.com/reuters/businessNews"},
            {"name": "Bloomberg",        "rss": "https://feeds.bloomberg.com/markets/news.rss"},
            {"name": "Financial Times",  "rss": "https://feeds.ft.com/rss/home/uk"},
            {"name": "The Economist",    "rss": "https://www.economist.com/finance-and-economics/rss.xml"},
            {"name": "Wall Street Journal","rss": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml"},
            {"name": "Fortune",          "rss": "https://fortune.com/feed/"},
        ],
    },
    "technology": {
        "label": "科技", "tag": "tech",
        "sources": [
            {"name": "MIT Tech Review",  "rss": "https://www.technologyreview.com/feed/"},
            {"name": "Ars Technica",     "rss": "https://feeds.arstechnica.com/arstechnica/index"},
            {"name": "Wired",            "rss": "https://www.wired.com/feed/rss"},
            {"name": "The Verge",        "rss": "https://www.theverge.com/rss/index.xml"},
            {"name": "TechCrunch",       "rss": "https://techcrunch.com/feed/"},
            {"name": "Reuters",          "rss": "https://feeds.reuters.com/reuters/technologyNews"},
        ],
    },
    "science": {
        "label": "科学", "tag": "sci",
        "sources": [
            {"name": "Nature",           "rss": "https://www.nature.com/nature.rss"},
            {"name": "Science",          "rss": "https://www.science.org/rss/news_current.xml"},
            {"name": "New Scientist",    "rss": "https://www.newscientist.com/feed/home/"},
            {"name": "Scientific American","rss": "https://www.scientificamerican.com/feed/"},
            {"name": "Phys.org",         "rss": "https://phys.org/rss-feed/"},
            {"name": "NYT Science",      "rss": "https://rss.nytimes.com/services/xml/rss/nyt/Science.xml"},
        ],
    },
    "health": {
        "label": "健康", "tag": "hlth",
        "sources": [
            {"name": "NEJM",             "rss": "https://www.nejm.org/action/showFeed?type=etoc&feed=rss&jc=nejm"},
            {"name": "The Lancet",       "rss": "https://www.thelancet.com/rssfeed/lancet_online.xml"},
            {"name": "STAT News",        "rss": "https://www.statnews.com/feed/"},
            {"name": "NYT Health",       "rss": "https://rss.nytimes.com/services/xml/rss/nyt/Health.xml"},
            {"name": "Reuters",          "rss": "https://feeds.reuters.com/reuters/healthNews"},
            {"name": "Medical News Today","rss": "https://www.medicalnewstoday.com/rss"},
        ],
    },
}

# ═══════════════════════════════════════════════════════════════
# 评分词库
# ═══════════════════════════════════════════════════════════════
HIGH_VALUE = [
    "killed","dead","war","attack","crisis","collapse","emergency","record",
    "historic","breakthrough","nuclear","sanctions","resign","arrested",
    "indicted","sentenced","signed","approved","rejected","banned","crashed",
    "surge","plunge","discovery","first time","unprecedented",
]
MED_VALUE = [
    "deal","agreement","summit","election","vote","legislation","policy",
    "earnings","gdp","inflation","interest rate","warning","investigation",
    "trial","verdict","study","research","launch","announced","unveiled",
]
JUNK = [
    "quiz","top 10","ranking","best of","how to watch","watch live",
    "photos:","video:","gallery:","everything you need","here's what",
    "roundup","recap:","week in pictures","opinion:","op-ed:","column:",
    "sponsored","advertisement","celebrity","oscars","grammy","nfl","nba",
    "super bowl","world cup","box office","album review","movie review",
]

def score_article(item):
    title = (item.get("title") or "").lower()
    desc  = (item.get("desc")  or "").lower()
    text  = title + " " + desc
    s = 50
    for w in JUNK:
        if w in title: return 0      # 一票否决
    for w in HIGH_VALUE:
        if w in text: s += 9
    for w in MED_VALUE:
        if w in text: s += 4
    dl = len(item.get("desc") or "")
    if dl > 150: s += 10
    elif dl > 60: s += 5
    elif dl < 25: s -= 20
    tl = len(item.get("title") or "")
    if tl < 18 or tl > 180: s -= 15
    return max(0, min(99, s))

# ═══════════════════════════════════════════════════════════════
# RSS 解析
# ═══════════════════════════════════════════════════════════════
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; PulseBot/7.0)"}

def parse_rss(url, timeout=10):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        ns   = {"atom": "http://www.w3.org/2005/Atom"}
        items = []
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            desc  = re.sub(r"<[^>]+>", "", item.findtext("description") or "")[:450].strip()
            link  = (item.findtext("link") or "").strip()
            pub   = (item.findtext("pubDate") or "")[:16]
            if title and link:
                items.append({"title": title, "desc": desc, "url": link, "pub": pub})
        if not items:
            for e in root.findall("atom:entry", ns):
                title = (e.findtext("atom:title", namespaces=ns) or "").strip()
                desc  = re.sub(r"<[^>]+>", "", e.findtext("atom:summary", namespaces=ns) or "")[:450].strip()
                le    = e.find("atom:link", ns)
                link  = le.get("href") if le is not None else ""
                pub   = (e.findtext("atom:updated", namespaces=ns) or "")[:16]
                if title and link:
                    items.append({"title": title, "desc": desc, "url": link, "pub": pub})
        return items
    except Exception as ex:
        print(f"    ✗ RSS failed ({url.split('/')[2][:28]}): {ex}")
        return []

# ═══════════════════════════════════════════════════════════════
# 翻译
# ═══════════════════════════════════════════════════════════════
def translate(text, retries=2):
    if not text or not text.strip(): return text
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

# ═══════════════════════════════════════════════════════════════
# NewsAPI 兜底（某 RSS 源失败时）
# ═══════════════════════════════════════════════════════════════
NEWSAPI_CAT = {
    "politics": "general", "business": "business",
    "technology": "technology", "science": "science", "health": "health",
}
_newsapi_cache = {}

def newsapi_fallback(cat):
    if cat in _newsapi_cache:
        return _newsapi_cache[cat]
    if not API_KEY:
        return []
    try:
        r = requests.get(
            "https://newsapi.org/v2/top-headlines",
            params={"category": NEWSAPI_CAT.get(cat, "general"),
                    "language": "en", "pageSize": 20, "apiKey": API_KEY},
            timeout=12,
        )
        arts = [
            {"title": (a.get("title") or "").split(" - ")[0].strip(),
             "desc":  (a.get("description") or "")[:450],
             "url":   a.get("url", ""),
             "pub":   (a.get("publishedAt") or "")[:10]}
            for a in r.json().get("articles", [])
            if a.get("title") and a.get("url")
        ]
        _newsapi_cache[cat] = arts
        time.sleep(0.2)
        return arts
    except Exception as ex:
        print(f"    ✗ NewsAPI fallback failed: {ex}")
        return []

# ═══════════════════════════════════════════════════════════════
# 主流程：每源取最佳 1 篇
# ═══════════════════════════════════════════════════════════════
def fetch_best_from_source(src_cfg, cat, global_seen):
    """从单个来源获取评分最高的 1 篇文章"""
    items = parse_rss(src_cfg["rss"])
    time.sleep(0.15)

    # 过滤已见 URL
    candidates = [
        (score_article(i), i)
        for i in items
        if i.get("url") and i["url"] not in global_seen
        and i.get("title") and "[Removed]" not in i.get("title", "")
        and i.get("desc")
    ]
    candidates = [(s, i) for s, i in candidates if s > 0]
    candidates.sort(key=lambda x: x[0], reverse=True)

    if not candidates:
        # RSS 无结果 → NewsAPI 兜底
        print(f"    → {src_cfg['name']}: RSS 空，尝试 NewsAPI 兜底")
        fallback = newsapi_fallback(cat)
        candidates = [
            (score_article(i), i)
            for i in fallback
            if i.get("url") and i["url"] not in global_seen and i.get("desc")
        ]
        candidates = [(s, i) for s, i in candidates if s > 0]
        candidates.sort(key=lambda x: x[0], reverse=True)

    if not candidates:
        print(f"    ✗ {src_cfg['name']}: 无可用文章")
        return None

    imp, best = candidates[0]
    global_seen.add(best["url"])

    title_en = best["title"].split(" - ")[0].strip()
    desc_en  = best["desc"]
    pub      = best.get("pub", "")[:10]

    print(f"    [{imp:2d}] {src_cfg['name']:<22} {title_en[:38]}…")
    title_zh = translate(title_en); time.sleep(0.08)
    desc_zh  = translate(desc_en);  time.sleep(0.08)

    return {
        "source_name": src_cfg["name"],
        "title": title_zh or title_en,
        "desc":  desc_zh  or desc_en,
        "url":   best["url"],
        "pub":   pub,
        "imp":   imp,
    }

def build_data():
    print(f"\n{'═'*54}")
    print(f"  PULSE v7  —  {NOW.strftime('%Y-%m-%d %H:%M')} CST")
    print(f"  规则: 每类 6 来源 × 每源 1 篇 = 30 篇")
    print(f"{'═'*54}\n")

    global_seen = set()
    categories  = {}

    for cat, cfg in CATEGORY_SOURCES.items():
        print(f"\n── {cfg['label']} ({cat}) ──────────────────────")
        articles = []
        for src in cfg["sources"]:
            art = fetch_best_from_source(src, cat, global_seen)
            if art:
                art["cat"]   = cat
                art["tag"]   = cfg["tag"]
                art["label"] = cfg["label"]
                articles.append(art)
        categories[cat] = articles
        print(f"  → {len(articles)}/6 篇")

    # 头条 = 全局评分最高 1 篇
    all_arts = [a for arts in categories.values() for a in arts]
    all_arts.sort(key=lambda x: x["imp"], reverse=True)
    feat = all_arts[0].copy() if all_arts else None
    if feat:
        feat["imp"] = max(feat["imp"], 88)

    print(f"\n{'═'*54}")
    print(f"  头条: {feat['source_name']} [{feat['imp']}] {feat['title'][:30]}…" if feat else "  无头条")
    for cat, arts in categories.items():
        label = CATEGORY_SOURCES[cat]["label"]
        srcs  = [a["source_name"] for a in arts]
        print(f"  {label}: {len(arts)}篇  [{', '.join(srcs)}]")

    return feat, categories

# ═══════════════════════════════════════════════════════════════
# HTML 生成 — Claude 风格设计
# ═══════════════════════════════════════════════════════════════
def generate_html(feat, categories):
    date_str  = NOW.strftime("%-m月%-d日")
    weekdays  = ["周一","周二","周三","周四","周五","周六","周日"]
    weekday   = weekdays[NOW.weekday()]
    full_date = NOW.strftime(f"%Y年{date_str} {weekday}")
    time_str  = NOW.strftime("%H:%M")
    slot      = "早报" if NOW.hour < 10 else ("午报" if NOW.hour < 14 else "晚报")

    feat_json = json.dumps(feat, ensure_ascii=False) if feat else "null"
    cats_json = json.dumps(categories, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>PULSE · {slot} · {date_str}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;500;700&family=Noto+Sans+SC:wght@300;400;500&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
/* ── TOKENS ─────────────────────────────────────────────── */
:root {{
  --bg:       #F5F3EE;
  --surf:     #FFFFFF;
  --surf-h:   #FAF9F6;
  --bd:       rgba(0,0,0,.08);
  --bd-h:     rgba(0,0,0,.14);
  --t1:       #1C1917;
  --t2:       #6B6560;
  --t3:       #A8A49D;
  --acc:      #C8410A;
  --acc-bg:   rgba(200,65,10,.07);
  --amber:    #9C6B0E;

  /* category accent colors */
  --pol:      #7B1460;
  --pol-bg:   rgba(123,20,96,.07);
  --biz:      #7A3800;
  --biz-bg:   rgba(122,56,0,.07);
  --tech:     #025A3C;
  --tech-bg:  rgba(2,90,60,.07);
  --sci:      #0A3C6E;
  --sci-bg:   rgba(10,60,110,.07);
  --hlth:     #2C5445;
  --hlth-bg:  rgba(44,84,69,.07);

  --r:        8px;
  --r-sm:     5px;
  --tr:       .15s ease;
  --sh:       0 1px 3px rgba(0,0,0,.06), 0 1px 2px rgba(0,0,0,.04);
  --sh-h:     0 4px 16px rgba(0,0,0,.09), 0 2px 4px rgba(0,0,0,.05);
  --max:      1100px;
  --serif:    'Noto Serif SC', Georgia, serif;
  --sans:     'Noto Sans SC', system-ui, sans-serif;
  --mono:     'JetBrains Mono', monospace;
}}

/* dark */
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg:     #131210;
    --surf:   #1E1D1A;
    --surf-h: #252420;
    --bd:     rgba(255,255,255,.08);
    --bd-h:   rgba(255,255,255,.16);
    --t1:     #EAE7E1;
    --t2:     #96928B;
    --t3:     #58554F;
    --acc:    #E05A28;
    --acc-bg: rgba(224,90,40,.1);
    --amber:  #D4942A;
    --sh:     0 1px 3px rgba(0,0,0,.3), 0 1px 2px rgba(0,0,0,.2);
    --sh-h:   0 4px 16px rgba(0,0,0,.4), 0 2px 4px rgba(0,0,0,.3);
  }}
}}

/* ── RESET ──────────────────────────────────────────────── */
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
html {{ scroll-behavior: smooth; }}
body {{
  background: var(--bg);
  color: var(--t1);
  font-family: var(--sans);
  font-size: 14px;
  line-height: 1.7;
  -webkit-font-smoothing: antialiased;
}}
a {{ text-decoration: none; color: inherit; }}
button {{ cursor: pointer; font-family: inherit; border: none; background: none; }}

/* ── HEADER ─────────────────────────────────────────────── */
.hdr {{
  position: sticky; top: 0; z-index: 100;
  background: rgba(245,243,238,.94);
  backdrop-filter: blur(20px) saturate(1.4);
  border-bottom: 1px solid var(--bd);
}}
@media (prefers-color-scheme: dark) {{
  .hdr {{ background: rgba(19,18,16,.94); }}
}}
.hbar {{
  display: flex; align-items: center; gap: 12px;
  height: 52px; padding: 0 24px;
  max-width: var(--max); margin: 0 auto;
}}
.logo {{
  font-family: var(--serif);
  font-size: 1.35rem; font-weight: 700;
  letter-spacing: .06em; color: var(--t1);
  flex-shrink: 0; display: flex; align-items: center; gap: 5px;
}}
.logo-dot {{
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--acc); flex-shrink: 0;
  animation: blink 2.8s step-end infinite;
}}
@keyframes blink {{ 0%,100%{{ opacity:1 }} 50%{{ opacity:0 }} }}
.slot-tag {{
  font-family: var(--mono); font-size: .58rem;
  padding: 2px 7px; border-radius: var(--r-sm);
  background: var(--acc-bg); color: var(--acc);
  border: 1px solid rgba(200,65,10,.18);
  flex-shrink: 0; letter-spacing: .04em;
}}
.hdiv {{ width: 1px; height: 16px; background: var(--bd-h); flex-shrink: 0; }}
.ticker {{
  flex: 1; overflow: hidden; min-width: 0;
  mask: linear-gradient(90deg,transparent,#000 7%,#000 93%,transparent);
  -webkit-mask: linear-gradient(90deg,transparent,#000 7%,#000 93%,transparent);
}}
.tk-inner {{
  display: flex; gap: 30px; white-space: nowrap;
  animation: scroll 110s linear infinite;
}}
.tk-inner:hover {{ animation-play-state: paused; }}
@keyframes scroll {{ 0%{{ transform:translateX(0) }} 100%{{ transform:translateX(-50%) }} }}
.tk-item {{ font-size: 11.5px; color: var(--t2); flex-shrink: 0; }}
.tk-item::before {{ content: '·'; color: var(--acc); margin-right: 6px; font-weight: 700; }}
.clk {{
  font-family: var(--mono); font-size: .62rem;
  color: var(--t3); white-space: nowrap; flex-shrink: 0;
}}
.theme-btn {{
  width: 30px; height: 30px; border-radius: 50%;
  border: 1px solid var(--bd-h); color: var(--t3);
  display: flex; align-items: center; justify-content: center;
  font-size: 14px; flex-shrink: 0;
  transition: background var(--tr), color var(--tr);
}}
.theme-btn:hover {{ background: var(--surf-h); color: var(--t1); }}
.pbar {{ height: 2px; background: var(--bd); }}
.pfill {{
  height: 100%; width: 0;
  background: linear-gradient(90deg, var(--acc), var(--amber));
  transition: width 1s linear;
}}

/* ── SUBNAV ─────────────────────────────────────────────── */
.subnav {{
  background: var(--surf);
  border-bottom: 1px solid var(--bd);
  overflow-x: auto; scrollbar-width: none;
}}
.subnav::-webkit-scrollbar {{ display: none; }}
.sn {{
  display: flex; padding: 0 24px;
  max-width: var(--max); margin: 0 auto;
}}
.nb {{
  display: flex; align-items: center; gap: 6px;
  padding: 10px 16px; font-size: .78rem; font-weight: 400;
  color: var(--t2); border-bottom: 2px solid transparent;
  white-space: nowrap; flex-shrink: 0;
  transition: color var(--tr), border-color var(--tr);
}}
.nb:hover {{ color: var(--t1); }}
.nb.on {{ color: var(--t1); font-weight: 500; border-color: var(--acc); }}
.nb-ct {{
  font-family: var(--mono); font-size: .55rem;
  color: var(--t3); background: var(--surf-h);
  padding: 1px 5px; border-radius: 10px;
  border: 1px solid var(--bd);
  transition: color var(--tr), border-color var(--tr);
}}
.nb.on .nb-ct {{ color: var(--acc); border-color: rgba(200,65,10,.2); }}

/* ── LAYOUT ─────────────────────────────────────────────── */
.wrap {{ max-width: var(--max); margin: 0 auto; padding: 28px 24px 80px; }}

/* section header */
.sec {{
  display: flex; align-items: center; gap: 12px;
  margin: 36px 0 18px;
}}
.sec:first-child {{ margin-top: 0; }}
.sec-label {{
  font-family: var(--mono); font-size: .58rem;
  letter-spacing: .2em; text-transform: uppercase;
  white-space: nowrap;
}}
.sec-line {{ flex: 1; height: 1px; background: var(--bd); }}
.sec-count {{
  font-family: var(--mono); font-size: .55rem;
  color: var(--t3); white-space: nowrap;
}}

/* category colors for section labels */
.lbl-pol  {{ color: var(--pol); }}
.lbl-biz  {{ color: var(--biz); }}
.lbl-tech {{ color: var(--tech); }}
.lbl-sci  {{ color: var(--sci); }}
.lbl-hlth {{ color: var(--hlth); }}
.lbl-top  {{ color: var(--acc); }}

/* ── CHIPS ──────────────────────────────────────────────── */
.chip {{
  display: inline-flex; align-items: center;
  font-family: var(--mono); font-size: .54rem;
  letter-spacing: .06em; padding: 2px 6px;
  border-radius: var(--r-sm); white-space: nowrap;
  font-weight: 500;
}}
.chip-pol  {{ background: var(--pol-bg);  color: var(--pol); }}
.chip-biz  {{ background: var(--biz-bg);  color: var(--biz); }}
.chip-tech {{ background: var(--tech-bg); color: var(--tech); }}
.chip-sci  {{ background: var(--sci-bg);  color: var(--sci); }}
.chip-hlth {{ background: var(--hlth-bg); color: var(--hlth); }}

/* ── HEADLINE ───────────────────────────────────────────── */
.headline {{
  background: var(--surf);
  border: 1px solid var(--bd);
  border-radius: var(--r);
  box-shadow: var(--sh);
  overflow: hidden;
  display: grid; grid-template-columns: 1fr 164px;
  margin-bottom: 8px;
  transition: box-shadow var(--tr), border-color var(--tr);
}}
.headline:hover {{
  box-shadow: var(--sh-h);
  border-color: var(--bd-h);
}}
.hl-body {{ padding: 26px 30px; }}
.hl-top {{
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 13px;
}}
.hl-badge {{
  font-family: var(--mono); font-size: .54rem;
  letter-spacing: .12em; padding: 2px 8px;
  border-radius: var(--r-sm);
  background: var(--acc); color: #fff;
}}
.hl-title {{
  font-family: var(--serif);
  font-size: clamp(1.25rem, 2.2vw, 1.7rem);
  font-weight: 700; line-height: 1.32;
  color: var(--t1); margin-bottom: 12px;
  transition: color var(--tr);
}}
.headline:hover .hl-title {{ color: var(--acc); }}
.hl-desc {{
  font-size: .87rem; color: var(--t2);
  line-height: 1.85; margin-bottom: 18px;
}}
.hl-footer {{
  display: flex; align-items: center; gap: 12px;
  flex-wrap: wrap;
}}
.read-link {{
  font-family: var(--mono); font-size: .63rem;
  color: var(--acc); border: 1px solid rgba(200,65,10,.24);
  padding: 4px 12px; border-radius: var(--r-sm);
  display: inline-flex; align-items: center; gap: 4px;
  transition: background var(--tr);
}}
.read-link:hover {{ background: var(--acc-bg); }}
.meta-txt {{
  font-family: var(--mono); font-size: .6rem; color: var(--t3);
}}
.imp-row {{
  display: flex; align-items: center; gap: 8px;
  margin-top: 14px;
}}
.imp-lbl {{
  font-family: var(--mono); font-size: .56rem;
  color: var(--t3); flex-shrink: 0;
}}
.imp-track {{
  flex: 1; height: 2px;
  background: var(--bd); border-radius: 1px; overflow: hidden;
}}
.imp-fill {{ height: 100%; background: var(--acc); border-radius: 1px; }}
.imp-num {{
  font-family: var(--mono); font-size: .56rem;
  color: var(--amber); width: 18px; text-align: right;
  flex-shrink: 0;
}}
.hl-side {{
  border-left: 1px solid var(--bd);
  background: var(--surf-h);
  padding: 26px 18px;
  display: flex; flex-direction: column;
  justify-content: center; gap: 20px;
}}
.hs-lbl {{
  font-family: var(--mono); font-size: .52rem;
  letter-spacing: .14em; text-transform: uppercase;
  color: var(--t3); margin-bottom: 3px;
}}
.hs-big {{
  font-family: var(--serif); font-size: 2.1rem;
  font-weight: 700; color: var(--amber); line-height: 1;
}}
.hs-sub {{
  font-family: var(--mono); font-size: .55rem; color: var(--t3);
}}

/* ── CARD GRID ──────────────────────────────────────────── */
.card-grid {{
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 8px;
}}

/* ── ARTICLE CARD ───────────────────────────────────────── */
.card {{
  background: var(--surf);
  border: 1px solid var(--bd);
  border-radius: var(--r);
  box-shadow: var(--sh);
  padding: 18px 20px;
  display: flex; flex-direction: column;
  gap: 10px;
  transition: box-shadow var(--tr), border-color var(--tr), background var(--tr);
  text-decoration: none; color: inherit;
  cursor: pointer;
}}
.card:hover {{
  background: var(--surf-h);
  box-shadow: var(--sh-h);
  border-color: var(--bd-h);
}}
.card-top {{
  display: flex; align-items: center;
  justify-content: space-between; gap: 8px;
}}
.card-source {{
  font-family: var(--mono); font-size: .6rem;
  color: var(--t3); font-weight: 500;
  letter-spacing: .02em; white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis;
}}
.card-date {{
  font-family: var(--mono); font-size: .56rem;
  color: var(--t3); flex-shrink: 0;
}}
.card-title {{
  font-family: var(--serif);
  font-size: .96rem; font-weight: 500;
  line-height: 1.48; color: var(--t1);
  display: -webkit-box; -webkit-line-clamp: 3;
  -webkit-box-orient: vertical; overflow: hidden;
  transition: color var(--tr);
  flex: 1;
}}
.card:hover .card-title {{ color: var(--acc); }}
.card-desc {{
  font-size: .77rem; color: var(--t2); line-height: 1.68;
  display: -webkit-box; -webkit-line-clamp: 2;
  -webkit-box-orient: vertical; overflow: hidden;
}}
.card-foot {{
  display: flex; align-items: center;
  justify-content: space-between;
  margin-top: auto; padding-top: 2px;
}}
.card-link {{
  font-family: var(--mono); font-size: .58rem;
  color: var(--acc); letter-spacing: .02em;
  transition: opacity var(--tr);
}}
.card:hover .card-link {{ opacity: .7; }}
.card-imp {{
  font-family: var(--mono); font-size: .56rem;
  color: var(--t3);
}}

/* ── FOOTER ─────────────────────────────────────────────── */
footer {{
  border-top: 1px solid var(--bd);
  padding: 14px 24px;
}}
.foot-inner {{
  max-width: var(--max); margin: 0 auto;
  display: flex; justify-content: space-between;
  flex-wrap: wrap; gap: 6px;
}}
.foot-l, .foot-r {{
  font-family: var(--mono); font-size: .56rem;
  color: var(--t3);
}}
#nxt {{ color: var(--amber); }}

/* ── EMPTY ──────────────────────────────────────────────── */
.empty {{
  padding: 40px; text-align: center;
  font-size: .8rem; color: var(--t3);
  grid-column: 1 / -1;
}}

/* ── ANIMATIONS ─────────────────────────────────────────── */
@keyframes fadeUp {{
  from {{ opacity: 0; transform: translateY(8px); }}
  to   {{ opacity: 1; transform: translateY(0); }}
}}
.fade-in {{ animation: fadeUp .38s ease both; }}

/* ── RESPONSIVE ─────────────────────────────────────────── */
@media (max-width: 900px) {{
  .card-grid {{ grid-template-columns: repeat(2, 1fr); }}
}}
@media (max-width: 640px) {{
  .ticker, .hdiv {{ display: none; }}
  .hbar {{ padding: 0 16px; }}
  .sn {{ padding: 0 16px; }}
  .wrap {{ padding: 16px 16px 60px; }}
  .card-grid {{ grid-template-columns: 1fr; gap: 8px; }}
  .headline {{ grid-template-columns: 1fr; }}
  .hl-side {{ display: none; }}
  .hl-body {{ padding: 18px 20px; }}
}}
</style>
</head>
<body>

<!-- ══ HEADER ════════════════════════════════════════════ -->
<header class="hdr">
  <div class="hbar">
    <div class="logo">PULSE<div class="logo-dot"></div></div>
    <span class="slot-tag">{slot}</span>
    <div class="hdiv"></div>
    <div class="ticker"><div class="tk-inner" id="tk"></div></div>
    <div class="hdiv"></div>
    <span class="clk" id="clk">—</span>
    <button class="theme-btn" id="tbtn" title="切换主题">◑</button>
  </div>
  <div class="pbar"><div class="pfill" id="prog"></div></div>
</header>

<!-- ══ SUBNAV ════════════════════════════════════════════ -->
<nav class="subnav">
  <div class="sn" id="nav"></div>
</nav>

<!-- ══ CONTENT ═══════════════════════════════════════════ -->
<main class="wrap" id="wrap"></main>

<!-- ══ FOOTER ════════════════════════════════════════════ -->
<footer>
  <div class="foot-inner">
    <span class="foot-l">PULSE · {full_date} {time_str} 更新 · 5分类 × 6来源 = 30篇精选</span>
    <span class="foot-r">下次更新 <span id="nxt">—</span> · 08:00 / 12:00 / 18:00</span>
  </div>
</footer>

<script>
const FEAT = {feat_json};
const CATS = {cats_json};

const CAT_ORDER  = ['politics','business','technology','science','health'];
const CAT_NAMES  = {{ politics:'政治', business:'商业', technology:'科技', science:'科学', health:'健康' }};
const CAT_TAGS   = {{ politics:'pol', business:'biz', technology:'tech', science:'sci', health:'hlth' }};
const CAT_LABELS = {{ pol:'lbl-pol', biz:'lbl-biz', tech:'lbl-tech', sci:'lbl-sci', hlth:'lbl-hlth' }};

// ── 主题 ────────────────────────────────────────────────
let _dark = window.matchMedia('(prefers-color-scheme:dark)').matches;
const tbtn = document.getElementById('tbtn');
tbtn.addEventListener('click', () => {{
  _dark = !_dark;
  let s = document.getElementById('_ts');
  if (!s) {{ s = document.createElement('style'); s.id = '_ts'; document.head.appendChild(s); }}
  s.textContent = _dark ? `
    :root {{
      --bg:#131210; --surf:#1E1D1A; --surf-h:#252420;
      --bd:rgba(255,255,255,.08); --bd-h:rgba(255,255,255,.16);
      --t1:#EAE7E1; --t2:#96928B; --t3:#58554F;
      --acc:#E05A28; --acc-bg:rgba(224,90,40,.1);
      --amber:#D4942A;
      --sh:0 1px 3px rgba(0,0,0,.3),0 1px 2px rgba(0,0,0,.2);
      --sh-h:0 4px 16px rgba(0,0,0,.4),0 2px 4px rgba(0,0,0,.3);
    }}` : '';
}});

// ── 时钟 ─────────────────────────────────────────────────
function pad(n) {{ return String(n).padStart(2,'0'); }}
setInterval(() => {{
  const n = new Date();
  document.getElementById('clk').textContent =
    `${{n.getFullYear()}}/${{pad(n.getMonth()+1)}}/${{pad(n.getDate())}} ${{pad(n.getHours())}}:${{pad(n.getMinutes())}}:${{pad(n.getSeconds())}}`;
}}, 1000);

// ── 倒计时 ───────────────────────────────────────────────
function secsToNext() {{
  const n = new Date(), s = n.getHours()*3600 + n.getMinutes()*60 + n.getSeconds();
  for (const h of [8,12,18]) {{ if (h*3600 > s) return h*3600 - s; }}
  return 8*3600 + (86400-s);
}}
let rem = secsToNext(), total = rem;
setInterval(() => {{
  rem--; if (rem < 0) {{ rem = secsToNext(); total = rem; }}
  document.getElementById('prog').style.width = ((total-rem)/total*100) + '%';
  const hh=Math.floor(rem/3600), mm=Math.floor((rem%3600)/60), ss=rem%60;
  const el = document.getElementById('nxt');
  if (el) el.textContent = `${{hh}}时${{pad(mm)}}分${{pad(ss)}}秒`;
}}, 1000);

// ── 渲染工具 ─────────────────────────────────────────────
function chip(tag) {{
  const labels = {{ pol:'政治', biz:'商业', tech:'科技', sci:'科学', hlth:'健康' }};
  return `<span class="chip chip-${{tag}}">${{labels[tag]||tag}}</span>`;
}}

function headlineHTML(d) {{
  if (!d) return '';
  return `
  <div class="headline fade-in">
    <div class="hl-body">
      <div class="hl-top">
        ${{chip(d.tag)}}
        <span class="hl-badge">TODAY'S TOP</span>
        <span class="meta-txt">${{d.source_name}}</span>
      </div>
      <a href="${{d.url}}" target="_blank" rel="noopener">
        <div class="hl-title">${{d.title}}</div>
      </a>
      <div class="hl-desc">${{d.desc}}</div>
      <div class="hl-footer">
        <a class="read-link" href="${{d.url}}" target="_blank" rel="noopener">阅读原文 ↗</a>
        <span class="meta-txt">${{d.pub}}</span>
      </div>
      <div class="imp-row">
        <span class="imp-lbl">重要指数</span>
        <div class="imp-track"><div class="imp-fill" style="width:${{d.imp}}%"></div></div>
        <span class="imp-num">${{d.imp}}</span>
      </div>
    </div>
    <div class="hl-side">
      <div>
        <div class="hs-lbl">重要指数</div>
        <div class="hs-big">${{d.imp}}</div>
        <div class="hs-sub">/ 100</div>
      </div>
      <div style="height:1px;background:var(--bd)"></div>
      <div>
        <div class="hs-lbl">来源</div>
        <div style="font-size:.75rem;color:var(--t2);margin-top:3px;line-height:1.7">
          ${{d.source_name}}<br>
          <span style="color:var(--t3)">${{d.pub}}</span>
        </div>
      </div>
    </div>
  </div>`;
}}

function cardHTML(a, idx) {{
  return `
  <a class="card fade-in" href="${{a.url}}" target="_blank" rel="noopener"
     style="animation-delay:${{idx * .04}}s">
    <div class="card-top">
      <span class="card-source">${{a.source_name}}</span>
      <span class="card-date">${{a.pub}}</span>
    </div>
    ${{chip(a.tag)}}
    <div class="card-title">${{a.title}}</div>
    <div class="card-desc">${{a.desc}}</div>
    <div class="card-foot">
      <span class="card-link">阅读原文 ↗</span>
      <span class="card-imp">${{a.imp}}</span>
    </div>
  </a>`;
}}

function sectionHTML(catKey, articles, showAll) {{
  const tag   = CAT_TAGS[catKey];
  const name  = CAT_NAMES[catKey];
  const lbl   = CAT_LABELS[tag] || '';
  const cards = articles.map((a, i) => cardHTML(a, i)).join('');
  return `
    <div class="sec">
      <span class="sec-label ${{lbl}}">${{name}}</span>
      <div class="sec-line"></div>
      <span class="sec-count">${{articles.length}} 篇</span>
    </div>
    <div class="card-grid">${{cards || '<div class="empty">暂无内容</div>'}}</div>`;
}}

// ── 导航 ─────────────────────────────────────────────────
function buildNav(active) {{
  let html = `<button class="nb ${{active==='all'?'on':''}}" data-c="all">
    全部 <span class="nb-ct">30</span></button>`;
  for (const c of CAT_ORDER) {{
    const n = (CATS[c] || []).length;
    if (!n) continue;
    html += `<button class="nb ${{active===c?'on':''}}" data-c="${{c}}">
      ${{CAT_NAMES[c]}} <span class="nb-ct">${{n}}</span></button>`;
  }}
  document.getElementById('nav').innerHTML = html;
}}

// ── 主渲染 ───────────────────────────────────────────────
function render(cat) {{
  buildNav(cat);
  let html = '';

  if (cat === 'all') {{
    // 头条
    if (FEAT) {{
      html += `<div class="sec">
        <span class="sec-label lbl-top">今日头条</span>
        <div class="sec-line"></div>
      </div>`;
      html += headlineHTML(FEAT);
    }}
    // 各分类
    for (const c of CAT_ORDER) {{
      const arts = CATS[c] || [];
      if (!arts.length) continue;
      html += sectionHTML(c, arts, true);
    }}
  }} else {{
    const arts = CATS[cat] || [];
    html += sectionHTML(cat, arts, false);
  }}

  const wrap = document.getElementById('wrap');
  wrap.innerHTML = html;
  wrap.scrollTop = 0;
}}

// ── 导航事件 ─────────────────────────────────────────────
document.getElementById('nav').addEventListener('click', e => {{
  const b = e.target.closest('.nb');
  if (!b) return;
  render(b.dataset.c);
  window.scrollTo({{ top: 0, behavior: 'smooth' }});
}});

// ── Ticker ───────────────────────────────────────────────
const allArts = Object.values(CATS).flat();
const titles  = (FEAT ? [FEAT.title] : []).concat(allArts.map(a => a.title));
document.getElementById('tk').innerHTML =
  titles.concat(titles).map(t => `<span class="tk-item">${{t}}</span>`).join('');

// ── 初始化 ───────────────────────────────────────────────
render('all');
</script>
</body>
</html>"""

def main():
    feat, categories = build_data()
    html = generate_html(feat, categories)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n✅ index.html 已生成")

if __name__ == "__main__":
    main()
