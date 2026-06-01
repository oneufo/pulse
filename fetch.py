#!/usr/bin/env python3
"""
Pulse v8
内容：多维评分 + 新鲜度加权 + 严格分类校验 + 同事件去重
页面：Claude 编辑风格重设计 — 宽幅左栏头条 + 分类双列精读卡
"""

import os, json, time, re, hashlib, requests
from datetime import datetime, timezone, timedelta
from urllib.parse import quote
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

API_KEY = os.environ.get("NEWS_API_KEY", "37bf8ef8267f4751bd51311507429eab")
CST     = timezone(timedelta(hours=8))
NOW     = datetime.now(CST)

# ══════════════════════════════════════════════════════════════
# 分类 × 来源（6 源 × 5 类，每源 RSS 质量经过验证）
# ══════════════════════════════════════════════════════════════
CATEGORIES = {
    "politics": {
        "label": "政治", "tag": "pol",
        "color": "#6D1F6D",
        "sources": [
            {"name": "Reuters",          "rss": "https://feeds.reuters.com/Reuters/PoliticsNews"},
            {"name": "AP News",          "rss": "https://apnews.com/rss"},
            {"name": "NYT Politics",     "rss": "https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml"},
            {"name": "Washington Post",  "rss": "https://feeds.washingtonpost.com/rss/politics"},
            {"name": "Politico",         "rss": "https://www.politico.com/rss/politicopicks.xml"},
            {"name": "Foreign Policy",   "rss": "https://foreignpolicy.com/feed/"},
        ],
        "must": [
            "president","congress","senate","parliament","government","minister",
            "election","vote","legislation","policy","democrat","republican",
            "trump","white house","nato","united nations","sanctions","military",
            "war","troops","conflict","treaty","diplomat","ukraine","russia",
            "china","taiwan","israel","iran","immigration","coup","geopolit",
            "prime minister","foreign policy","executive order","administration",
        ],
    },
    "business": {
        "label": "商业", "tag": "biz",
        "color": "#7A3800",
        "sources": [
            {"name": "Reuters",          "rss": "https://feeds.reuters.com/reuters/businessNews"},
            {"name": "Bloomberg",        "rss": "https://feeds.bloomberg.com/markets/news.rss"},
            {"name": "Financial Times",  "rss": "https://feeds.ft.com/rss/home/uk"},
            {"name": "The Economist",    "rss": "https://www.economist.com/finance-and-economics/rss.xml"},
            {"name": "Wall St. Journal", "rss": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml"},
            {"name": "Fortune",          "rss": "https://fortune.com/feed/"},
        ],
        "must": [
            "economy","economic","market","stock","shares","fund","gdp",
            "inflation","recession","interest rate","federal reserve","central bank",
            "trade","tariff","merger","acquisition","ipo","earnings","profit",
            "revenue","bankruptcy","default","imf","oil price","supply chain",
            "bond yield","nasdaq","s&p","investor","billion","quarter","fiscal",
            "monetary","retail","unemployment","consumer spending","export","import",
        ],
    },
    "technology": {
        "label": "科技", "tag": "tech",
        "color": "#025A3C",
        "sources": [
            {"name": "MIT Tech Review",  "rss": "https://www.technologyreview.com/feed/"},
            {"name": "Ars Technica",     "rss": "https://feeds.arstechnica.com/arstechnica/index"},
            {"name": "Wired",            "rss": "https://www.wired.com/feed/rss"},
            {"name": "The Verge",        "rss": "https://www.theverge.com/rss/index.xml"},
            {"name": "TechCrunch",       "rss": "https://techcrunch.com/feed/"},
            {"name": "Reuters Tech",     "rss": "https://feeds.reuters.com/reuters/technologyNews"},
        ],
        "must": [
            "artificial intelligence"," ai ","machine learning","chatgpt","openai",
            "google","apple","microsoft","meta ","amazon","nvidia","tesla","spacex",
            "semiconductor","chip","software","cybersecurity","hack","data breach",
            "electric vehicle","social media","algorithm","big tech","antitrust",
            "quantum","cloud","startup","tech company","regulation","autonomous",
            "robot","5g","deepmind","anthropic","llm","model",
        ],
    },
    "science": {
        "label": "科学", "tag": "sci",
        "color": "#0A3C6E",
        "sources": [
            {"name": "Nature",           "rss": "https://www.nature.com/nature.rss"},
            {"name": "Science",          "rss": "https://www.science.org/rss/news_current.xml"},
            {"name": "New Scientist",    "rss": "https://www.newscientist.com/feed/home/"},
            {"name": "Sci. American",    "rss": "https://www.scientificamerican.com/feed/"},
            {"name": "Phys.org",         "rss": "https://phys.org/rss-feed/"},
            {"name": "NYT Science",      "rss": "https://rss.nytimes.com/services/xml/rss/nyt/Science.xml"},
        ],
        "must": [
            "scientists","researchers","research","study","discovery","discovered",
            "nasa","space","universe","planet","asteroid","black hole","galaxy",
            "telescope","rocket","astronaut","quantum","physics","biology",
            "chemistry","genome","dna","fossil","earthquake","volcano","species",
            "evolution","experiment","scientific","journal","nature","climate science",
            "ocean","biodiversity","particle","atmosphere","glacier","extinction",
        ],
    },
    "health": {
        "label": "健康", "tag": "hlth",
        "color": "#2C5445",
        "sources": [
            {"name": "NEJM",             "rss": "https://www.nejm.org/action/showFeed?type=etoc&feed=rss&jc=nejm"},
            {"name": "The Lancet",       "rss": "https://www.thelancet.com/rssfeed/lancet_online.xml"},
            {"name": "STAT News",        "rss": "https://www.statnews.com/feed/"},
            {"name": "NYT Health",       "rss": "https://rss.nytimes.com/services/xml/rss/nyt/Health.xml"},
            {"name": "Reuters Health",   "rss": "https://feeds.reuters.com/reuters/healthNews"},
            {"name": "Medical News",     "rss": "https://www.medicalnewstoday.com/rss"},
        ],
        "must": [
            "health","medical","medicine","hospital","disease","virus","vaccine",
            "cancer","tumor","drug","fda","cdc","pandemic","epidemic","outbreak",
            "clinical trial","pharmaceutical","therapy","treatment","symptom",
            "mental health","surgery","patient","mortality","alzheimer","dementia",
            "diabetes","obesity","heart disease","stroke","antibiotic","infection",
            "life expectancy","nejm","lancet","drug approval","immunotherapy",
        ],
    },
}

# ══════════════════════════════════════════════════════════════
# 评分词库
# ══════════════════════════════════════════════════════════════
CRITICAL   = ["nuclear","war declared","ceasefire","invaded","coup","pandemic",
               "global emergency","mass casualty","financial crisis","market crash",
               "assassinated","genocide","catastrophic","tipping point"]
HIGH       = ["killed","dead","attack","crisis","collapse","emergency","record",
               "historic","breakthrough","sanctions","resign","arrested","indicted",
               "sentenced","approved","rejected","banned","surge","plunge","signed",
               "discovery","first time","unprecedented","deployed","troops"]
MEDIUM     = ["deal","agreement","summit","election","vote","legislation","policy",
               "earnings","gdp","inflation","interest rate","warning","investigation",
               "trial","verdict","study","research","launched","announced","unveiled",
               "quarterly","reform","merger","ruling"]
JUNK_EXACT = {"quiz","listicle","roundup","recap","explainer","opinion","op-ed",
               "column","letters","sponsored","advertisement","horoscope"}
JUNK_PARTS = ["top 10","top 5","best of","worst of","ranking","ranked",
               "how to watch","watch live","stream","photos:","video:","gallery:",
               "everything you need","here's what","your guide","week in review",
               "week in pictures","morning briefing","evening briefing",
               "celebrity","oscars","grammy","golden globe","nfl","nba","super bowl",
               "world cup","box office","movie review","album review"]

def is_junk(title):
    t = title.lower()
    first = t.split(":")[0].strip()
    if first in JUNK_EXACT:
        return True
    return any(p in t for p in JUNK_PARTS)

# ══════════════════════════════════════════════════════════════
# 新鲜度解析
# ══════════════════════════════════════════════════════════════
def parse_age_hours(pub_str):
    """返回文章距今小时数，解析失败返回 999"""
    if not pub_str:
        return 999
    try:
        dt = parsedate_to_datetime(pub_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        diff = NOW.astimezone(timezone.utc) - dt.astimezone(timezone.utc)
        return diff.total_seconds() / 3600
    except Exception:
        try:
            # ISO 8601
            dt = datetime.fromisoformat(pub_str[:19])
            diff = NOW.replace(tzinfo=None) - dt
            return diff.total_seconds() / 3600
        except Exception:
            return 999

def freshness_bonus(age_hours):
    """越新鲜加分越多"""
    if age_hours < 2:   return 18
    if age_hours < 6:   return 12
    if age_hours < 12:  return 7
    if age_hours < 24:  return 3
    if age_hours < 48:  return 0
    return -8   # 超过2天扣分

# ══════════════════════════════════════════════════════════════
# 主评分
# ══════════════════════════════════════════════════════════════
SOURCE_TIER = {
    # Tier 1 — 80分起
    "reuters.com":80, "apnews.com":80, "bloomberg.com":78,
    "ft.com":78, "economist.com":80,
    # Tier 2 — 72分起
    "nytimes.com":74, "washingtonpost.com":72, "wsj.com":76,
    "politico.com":72, "foreignpolicy.com":74, "axios.com":68,
    "theguardian.com":68, "aljazeera.com":64,
    # Tier 3 — 专业领域
    "nature.com":80, "science.org":80, "nejm.org":82,
    "thelancet.com":80, "technologyreview.com":72,
    "newscientist.com":66, "scientificamerican.com":64,
    "statnews.com":70, "arstechnica.com":64,
    "wired.com":60, "techcrunch.com":56, "theverge.com":56,
    "fortune.com":58, "phys.org":58, "medicalnewstoday.com":54,
}

def score(item, cat_cfg, age_hours):
    title  = (item.get("title") or "").lower()
    desc   = (item.get("desc")  or "").lower()
    url    = (item.get("url")   or "").lower()
    text   = title + " " + desc

    if is_junk(title):
        return 0

    domain = url.split("/")[2].replace("www.","").replace("feeds.","") if "/" in url else ""
    base   = SOURCE_TIER.get(domain, 42)
    s      = base

    # 新鲜度
    s += freshness_bonus(age_hours)

    # 重要性词
    for w in CRITICAL:
        if w in text: s += 16
    high_hits = sum(1 for w in HIGH   if w in text)
    med_hits  = sum(1 for w in MEDIUM if w in text)
    s += min(high_hits * 9, 45)
    s += min(med_hits  * 4, 20)

    # 分类相关度（命中越多越好）
    cat_hits = sum(1 for kw in cat_cfg["must"] if kw in text)
    s += min(cat_hits * 3, 18)

    # 描述质量
    dl = len(item.get("desc") or "")
    if   dl > 160: s += 10
    elif dl > 80:  s += 5
    elif dl < 25:  s -= 18

    # 标题质量
    tl = len(item.get("title") or "")
    if tl < 18 or tl > 180: s -= 14

    return max(0, min(99, s))

def is_relevant(item, cat_cfg):
    text = ((item.get("title") or "") + " " + (item.get("desc") or "")).lower()
    return any(kw in text for kw in cat_cfg["must"])

# ══════════════════════════════════════════════════════════════
# 同事件去重
# ══════════════════════════════════════════════════════════════
STOP = {"the","a","an","is","are","was","were","in","on","at","to","for",
        "of","and","or","but","with","says","said","will","has","have",
        "after","over","as","its","by","from","that","this","it","be"}

def fingerprint(title):
    words = re.sub(r"[^\w\s]", "", title.lower()).split()
    key   = [w for w in words if w not in STOP and len(w) > 3]
    return frozenset(key[:10])

def is_duplicate(fp, seen_fps, threshold=3):
    return any(len(fp & s) >= threshold for s in seen_fps)

# ══════════════════════════════════════════════════════════════
# RSS 解析
# ══════════════════════════════════════════════════════════════
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; PulseBot/8.0)"}

def parse_rss(url, timeout=10):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        ns   = {"atom": "http://www.w3.org/2005/Atom"}
        out  = []
        for item in root.findall(".//item"):
            title = (item.findtext("title")       or "").strip()
            desc  = re.sub(r"<[^>]+>", "", item.findtext("description") or "")[:480].strip()
            link  = (item.findtext("link")        or "").strip()
            pub   = (item.findtext("pubDate")     or "").strip()
            if title and link:
                out.append({"title":title,"desc":desc,"url":link,"pub":pub})
        if not out:
            for e in root.findall("atom:entry", ns):
                title = (e.findtext("atom:title",   namespaces=ns) or "").strip()
                desc  = re.sub(r"<[^>]+>", "",
                    e.findtext("atom:summary", namespaces=ns) or "")[:480].strip()
                le    = e.find("atom:link", ns)
                link  = le.get("href","") if le is not None else ""
                pub   = (e.findtext("atom:updated", namespaces=ns) or "").strip()
                if title and link:
                    out.append({"title":title,"desc":desc,"url":link,"pub":pub})
        return out
    except Exception as ex:
        print(f"    ✗ {url.split('/')[2][:28]}: {ex}")
        return []

# ══════════════════════════════════════════════════════════════
# 翻译
# ══════════════════════════════════════════════════════════════
_trans_cache = {}

def translate(text, retries=2):
    if not text or not text.strip(): return text
    if text in _trans_cache:        return _trans_cache[text]
    for attempt in range(retries):
        try:
            url = ("https://translate.googleapis.com/translate_a/single"
                   f"?client=gtx&sl=en&tl=zh-CN&dt=t&q={quote(text[:500])}")
            r = requests.get(url, timeout=8)
            parts  = r.json()
            result = "".join(seg[0] for seg in parts[0] if seg[0])
            time.sleep(0.1)
            if result:
                _trans_cache[text] = result
                return result
        except Exception:
            time.sleep(0.5*(attempt+1))
    return text

# ══════════════════════════════════════════════════════════════
# NewsAPI 兜底
# ══════════════════════════════════════════════════════════════
_na_cache = {}
CAT_NA = {"politics":"general","business":"business",
          "technology":"technology","science":"science","health":"health"}

def newsapi_fetch(cat):
    if cat in _na_cache: return _na_cache[cat]
    if not API_KEY: return []
    try:
        r = requests.get("https://newsapi.org/v2/top-headlines",
            params={"category":CAT_NA.get(cat,"general"),
                    "language":"en","pageSize":20,"apiKey":API_KEY}, timeout=12)
        arts = [{"title":(a.get("title") or "").split(" - ")[0].strip(),
                 "desc": (a.get("description") or "")[:480],
                 "url":   a.get("url",""),
                 "pub":  (a.get("publishedAt") or "")}
                for a in r.json().get("articles",[])
                if a.get("title") and a.get("url")]
        _na_cache[cat] = arts
        time.sleep(0.2)
        return arts
    except Exception as ex:
        print(f"    ✗ NewsAPI: {ex}")
        return []

# ══════════════════════════════════════════════════════════════
# 单来源最佳文章
# ══════════════════════════════════════════════════════════════
def best_from_source(src, cat_key, cat_cfg, global_seen, global_fps):
    items = parse_rss(src["rss"])
    time.sleep(0.12)

    candidates = []
    for item in items:
        url   = item.get("url","")
        title = (item.get("title") or "").strip()
        if not url or url in global_seen: continue
        if not title or "[Removed]" in title: continue
        if not item.get("desc"): continue
        if not is_relevant(item, cat_cfg): continue
        fp = fingerprint(title)
        if is_duplicate(fp, global_fps): continue
        age = parse_age_hours(item.get("pub",""))
        s   = score(item, cat_cfg, age)
        if s > 0:
            candidates.append((s, age, item, fp))

    # 若 RSS 无结果，用 NewsAPI 兜底
    if not candidates:
        print(f"    → {src['name']}: 空，启用 NewsAPI 兜底")
        for item in newsapi_fetch(cat_key):
            url   = item.get("url","")
            title = (item.get("title") or "").strip()
            if not url or url in global_seen: continue
            if not is_relevant(item, cat_cfg): continue
            fp  = fingerprint(title)
            if is_duplicate(fp, global_fps): continue
            age = parse_age_hours(item.get("pub",""))
            s   = score(item, cat_cfg, age)
            if s > 0:
                candidates.append((s, age, item, fp))

    if not candidates:
        print(f"    ✗ {src['name']}: 无可用文章")
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    imp, age, best, fp = candidates[0]

    # 注册
    global_seen.add(best["url"])
    global_fps.append(fp)

    title_en = best["title"].split(" - ")[0].strip()
    desc_en  = best["desc"]
    pub      = best.get("pub","")

    # 格式化日期
    try:
        dt  = parsedate_to_datetime(pub)
        pub_fmt = dt.astimezone(CST).strftime("%-m月%-d日 %H:%M")
    except Exception:
        pub_fmt = pub[:10]

    print(f"    [{imp:2d}|{age:.0f}h] {src['name']:<22} {title_en[:36]}…")
    title_zh = translate(title_en); time.sleep(0.07)
    desc_zh  = translate(desc_en);  time.sleep(0.07)

    return {
        "cat":    cat_key,
        "tag":    cat_cfg["tag"],
        "label":  cat_cfg["label"],
        "color":  cat_cfg["color"],
        "src":    src["name"],
        "title":  title_zh or title_en,
        "title_en": title_en,
        "desc":   desc_zh  or desc_en,
        "url":    best["url"],
        "pub":    pub_fmt,
        "age":    round(age, 1),
        "imp":    imp,
    }

# ══════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════
def build_data():
    print(f"\n{'═'*56}")
    print(f"  PULSE v8  —  {NOW.strftime('%Y-%m-%d %H:%M')} CST")
    print(f"{'═'*56}\n")

    global_seen = set()
    global_fps  = []
    cat_articles = {}

    for cat_key, cat_cfg in CATEGORIES.items():
        print(f"\n── {cat_cfg['label']} ({'─'*(18-len(cat_cfg['label']))})")
        arts = []
        for src in cat_cfg["sources"]:
            art = best_from_source(src, cat_key, cat_cfg, global_seen, global_fps)
            if art:
                arts.append(art)
        cat_articles[cat_key] = arts
        print(f"   → {len(arts)}/6 篇入选")

    # 全局头条 = 所有文章中 imp 最高且最新鲜
    all_arts = [a for arts in cat_articles.values() for a in arts]
    all_arts.sort(key=lambda x: (x["imp"], -x["age"]), reverse=True)
    feat = all_arts[0].copy() if all_arts else None
    if feat:
        feat["imp"] = max(feat["imp"], 88)

    # 打印摘要
    print(f"\n{'─'*56}")
    if feat:
        print(f"  头条 [{feat['imp']}] {feat['src']}: {feat['title'][:32]}…")
    for cat_key, arts in cat_articles.items():
        label = CATEGORIES[cat_key]["label"]
        srcs  = [a["src"] for a in arts]
        print(f"  {label}: {len(arts)}篇 | {', '.join(srcs)}")

    return feat, cat_articles

# ══════════════════════════════════════════════════════════════
# HTML — Claude 编辑风格 v8
# ══════════════════════════════════════════════════════════════
def generate_html(feat, cat_articles):
    date_str = NOW.strftime("%-m月%-d日")
    weekdays = ["一","二","三","四","五","六","日"]
    weekday  = weekdays[NOW.weekday()]
    slot     = "早报" if NOW.hour < 10 else ("午报" if NOW.hour < 14 else "晚报")
    total    = sum(len(v) for v in cat_articles.values())

    feat_json = json.dumps(feat, ensure_ascii=False) if feat else "null"
    cats_json = json.dumps(cat_articles, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<meta name="description" content="Pulse — 今日全球最重要的新闻">
<title>PULSE · {slot} · {date_str}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:ital,wght@0,400;0,500;0,700;1,400&family=Noto+Sans+SC:wght@300;400;500&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
/* ─── DESIGN TOKENS ─────────────────────────────────────── */
:root {{
  --bg:        #F3F1EC;
  --surf:      #FDFCF9;
  --surf2:     #F7F5F0;
  --bd:        rgba(0,0,0,.08);
  --bd2:       rgba(0,0,0,.15);
  --t1:        #1A1816;
  --t2:        #635E57;
  --t3:        #A09A91;
  --acc:       #B83510;
  --acc-bg:    rgba(184,53,16,.07);
  --gold:      #946A0C;
  --gold-bg:   rgba(148,106,12,.07);
  --r:         8px;
  --r-s:       5px;
  --tr:        .14s ease;
  --sh0:       0 1px 2px rgba(0,0,0,.05);
  --sh1:       0 2px 8px rgba(0,0,0,.07), 0 1px 2px rgba(0,0,0,.04);
  --sh2:       0 6px 24px rgba(0,0,0,.1),  0 2px 6px rgba(0,0,0,.06);
  --max:       1120px;
  --serif:     'Noto Serif SC', Georgia, serif;
  --sans:      'Noto Sans SC', system-ui, sans-serif;
  --mono:      'JetBrains Mono', monospace;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg:      #141311;
    --surf:    #1E1D1A;
    --surf2:   #252320;
    --bd:      rgba(255,255,255,.08);
    --bd2:     rgba(255,255,255,.16);
    --t1:      #EBE8E2;
    --t2:      #97928A;
    --t3:      #575249;
    --acc:     #D95F32;
    --acc-bg:  rgba(217,95,50,.1);
    --gold:    #C9932A;
    --gold-bg: rgba(201,147,42,.1);
    --sh0:     0 1px 2px rgba(0,0,0,.25);
    --sh1:     0 2px 8px rgba(0,0,0,.35);
    --sh2:     0 6px 24px rgba(0,0,0,.5);
  }}
}}
/* ─── RESET ─────────────────────────────────────────────── */
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0;}}
html{{scroll-behavior:smooth;}}
body{{
  background:var(--bg);
  color:var(--t1);
  font-family:var(--sans);
  font-size:14px;
  line-height:1.7;
  -webkit-font-smoothing:antialiased;
}}
a{{text-decoration:none;color:inherit;}}
button{{cursor:pointer;font-family:inherit;border:none;background:none;}}

/* ─── HEADER ────────────────────────────────────────────── */
.hdr{{
  position:sticky;top:0;z-index:100;
  background:rgba(243,241,236,.93);
  backdrop-filter:blur(20px) saturate(1.5);
  border-bottom:1px solid var(--bd);
}}
@media(prefers-color-scheme:dark){{
  .hdr{{background:rgba(20,19,17,.93);}}
}}
.hbar{{
  display:flex;align-items:center;gap:11px;
  height:52px;padding:0 24px;
  max-width:var(--max);margin:0 auto;
}}
.logo{{
  font-family:var(--serif);font-size:1.3rem;font-weight:700;
  letter-spacing:.07em;color:var(--t1);flex-shrink:0;
  display:flex;align-items:center;gap:5px;
}}
.ldot{{
  width:5px;height:5px;border-radius:50%;
  background:var(--acc);flex-shrink:0;
  animation:blink 2.8s step-end infinite;
}}
@keyframes blink{{0%,100%{{opacity:1}}50%{{opacity:0}}}}
.slot-chip{{
  font-family:var(--mono);font-size:.56rem;letter-spacing:.05em;
  padding:2px 7px;border-radius:var(--r-s);
  background:var(--acc-bg);color:var(--acc);
  border:1px solid rgba(184,53,16,.18);flex-shrink:0;
}}
.vl{{width:1px;height:14px;background:var(--bd2);flex-shrink:0;}}
.ticker{{
  flex:1;overflow:hidden;min-width:0;
  mask:linear-gradient(90deg,transparent,#000 8%,#000 92%,transparent);
  -webkit-mask:linear-gradient(90deg,transparent,#000 8%,#000 92%,transparent);
}}
.tk{{display:flex;gap:28px;white-space:nowrap;animation:scroll 120s linear infinite;}}
.tk:hover{{animation-play-state:paused;}}
@keyframes scroll{{0%{{transform:translateX(0)}}100%{{transform:translateX(-50%)}}}}
.tk-i{{font-size:11px;color:var(--t2);flex-shrink:0;}}
.tk-i::before{{content:'·';color:var(--acc);margin-right:5px;font-weight:700;}}
.clk{{
  font-family:var(--mono);font-size:.6rem;
  color:var(--t3);white-space:nowrap;flex-shrink:0;
}}
.tbtn{{
  width:28px;height:28px;border-radius:50%;
  border:1px solid var(--bd2);color:var(--t3);
  display:flex;align-items:center;justify-content:center;
  font-size:14px;flex-shrink:0;
  transition:background var(--tr),color var(--tr);
}}
.tbtn:hover{{background:var(--surf2);color:var(--t1);}}
.pbar{{height:1.5px;background:var(--bd);}}
.pfill{{
  height:100%;width:0;
  background:linear-gradient(90deg,var(--acc),var(--gold));
  transition:width 1s linear;
}}

/* ─── SUBNAV ────────────────────────────────────────────── */
.snav{{
  background:var(--surf);
  border-bottom:1px solid var(--bd);
  overflow-x:auto;scrollbar-width:none;
}}
.snav::-webkit-scrollbar{{display:none;}}
.sn{{display:flex;padding:0 24px;max-width:var(--max);margin:0 auto;}}
.nb{{
  display:flex;align-items:center;gap:5px;
  padding:9px 15px;font-size:.76rem;font-weight:400;
  color:var(--t2);border-bottom:2px solid transparent;
  white-space:nowrap;flex-shrink:0;
  transition:color var(--tr),border-color var(--tr);
}}
.nb:hover{{color:var(--t1);}}
.nb.on{{color:var(--t1);font-weight:500;border-color:var(--acc);}}
.nb-n{{
  font-family:var(--mono);font-size:.52rem;
  color:var(--t3);background:var(--surf2);
  padding:1px 5px;border-radius:9px;
  border:1px solid var(--bd);
  transition:color var(--tr),border-color var(--tr);
}}
.nb.on .nb-n{{color:var(--acc);border-color:rgba(184,53,16,.2);}}

/* ─── WRAP ──────────────────────────────────────────────── */
.wrap{{max-width:var(--max);margin:0 auto;padding:28px 24px 80px;}}

/* ─── SECTION HEADER ────────────────────────────────────── */
.sh{{display:flex;align-items:center;gap:11px;margin:36px 0 16px;}}
.sh:first-child{{margin-top:0;}}
.sh-lbl{{
  font-family:var(--mono);font-size:.56rem;
  letter-spacing:.22em;text-transform:uppercase;
  white-space:nowrap;
}}
.sh-line{{flex:1;height:1px;background:var(--bd);}}
.sh-ct{{font-family:var(--mono);font-size:.52rem;color:var(--t3);white-space:nowrap;}}

/* ─── CHIP ──────────────────────────────────────────────── */
.chip{{
  display:inline-flex;align-items:center;
  font-family:var(--mono);font-size:.52rem;
  letter-spacing:.05em;font-weight:500;
  padding:2px 6px;border-radius:3px;white-space:nowrap;
}}

/* ─── HEADLINE CARD ─────────────────────────────────────── */
.hl{{
  display:grid;grid-template-columns:1fr 170px;
  background:var(--surf);
  border:1px solid var(--bd);
  border-radius:var(--r);
  box-shadow:var(--sh1);
  overflow:hidden;margin-bottom:6px;
  transition:box-shadow var(--tr),border-color var(--tr);
}}
.hl:hover{{box-shadow:var(--sh2);border-color:var(--bd2);}}
.hl-main{{padding:26px 30px;}}
.hl-top{{display:flex;align-items:center;gap:7px;margin-bottom:12px;flex-wrap:wrap;}}
.hl-badge{{
  font-family:var(--mono);font-size:.52rem;letter-spacing:.14em;
  padding:2px 8px;border-radius:3px;
  background:var(--acc);color:#fff;
}}
.hl-src{{font-family:var(--mono);font-size:.58rem;color:var(--t3);}}
.hl-title{{
  font-family:var(--serif);
  font-size:clamp(1.22rem,2.1vw,1.65rem);
  font-weight:700;line-height:1.32;
  color:var(--t1);margin-bottom:12px;
  transition:color var(--tr);
}}
.hl:hover .hl-title{{color:var(--acc);}}
.hl-desc{{
  font-size:.86rem;color:var(--t2);
  line-height:1.88;margin-bottom:18px;
}}
.hl-foot{{display:flex;align-items:center;gap:11px;flex-wrap:wrap;}}
.rl{{
  font-family:var(--mono);font-size:.6rem;color:var(--acc);
  border:1px solid rgba(184,53,16,.22);
  padding:3px 11px;border-radius:var(--r-s);
  display:inline-flex;align-items:center;gap:3px;
  transition:background var(--tr);
}}
.rl:hover{{background:var(--acc-bg);}}
.mt{{font-family:var(--mono);font-size:.58rem;color:var(--t3);}}
.imp-row{{display:flex;align-items:center;gap:7px;margin-top:14px;}}
.il{{font-family:var(--mono);font-size:.55rem;color:var(--t3);flex-shrink:0;}}
.itr{{flex:1;height:2px;background:var(--bd);border-radius:1px;overflow:hidden;}}
.ifill{{height:100%;background:var(--acc);border-radius:1px;}}
.in{{
  font-family:var(--mono);font-size:.55rem;
  color:var(--gold);width:18px;text-align:right;flex-shrink:0;
}}
.hl-side{{
  border-left:1px solid var(--bd);
  background:var(--surf2);
  padding:26px 18px;
  display:flex;flex-direction:column;
  justify-content:space-between;
}}
.hs-block{{}}
.hs-l{{
  font-family:var(--mono);font-size:.5rem;
  letter-spacing:.14em;text-transform:uppercase;
  color:var(--t3);margin-bottom:4px;
}}
.hs-big{{
  font-family:var(--serif);font-size:2rem;
  font-weight:700;color:var(--gold);line-height:1;
}}
.hs-sub{{font-family:var(--mono);font-size:.52rem;color:var(--t3);}}
.hs-div{{height:1px;background:var(--bd);margin:16px 0;}}
.hs-age{{
  font-family:var(--mono);font-size:.56rem;
  color:var(--t3);display:flex;flex-direction:column;gap:3px;
}}
.hs-age-n{{color:var(--t2);font-size:.6rem;}}

/* ─── ARTICLE GRID ──────────────────────────────────────── */
.grid{{
  display:grid;
  grid-template-columns:repeat(3,1fr);
  gap:12px;margin-bottom:6px;
}}

/* ─── ARTICLE CARD ──────────────────────────────────────── */
.card{{
  background:var(--surf);
  border:1px solid var(--bd);
  border-radius:var(--r);
  box-shadow:var(--sh0);
  padding:16px 18px 14px;
  display:flex;flex-direction:column;gap:9px;
  text-decoration:none;color:inherit;
  position:relative;overflow:hidden;
  transition:box-shadow var(--tr),border-color var(--tr),background var(--tr);
}}
.card::before{{
  content:'';
  position:absolute;top:0;left:0;right:0;height:3px;
  opacity:0;transition:opacity var(--tr);
}}
.card:hover{{
  background:var(--surf2);
  box-shadow:var(--sh1);
  border-color:var(--bd2);
}}
.card:hover::before{{opacity:1;}}
.ctop{{display:flex;align-items:center;justify-content:space-between;gap:6px;}}
.csrc{{
  font-family:var(--mono);font-size:.58rem;
  color:var(--t3);font-weight:500;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
}}
.cage{{
  font-family:var(--mono);font-size:.52rem;
  color:var(--t3);flex-shrink:0;white-space:nowrap;
}}
.ctitle{{
  font-family:var(--serif);
  font-size:.93rem;font-weight:500;
  line-height:1.48;color:var(--t1);
  display:-webkit-box;-webkit-line-clamp:3;
  -webkit-box-orient:vertical;overflow:hidden;
  flex:1;transition:color var(--tr);
}}
.card:hover .ctitle{{color:var(--acc);}}
.cdesc{{
  font-size:.75rem;color:var(--t2);line-height:1.7;
  display:-webkit-box;-webkit-line-clamp:2;
  -webkit-box-orient:vertical;overflow:hidden;
}}
.cfoot{{
  display:flex;align-items:center;
  justify-content:space-between;
  padding-top:4px;
  border-top:1px solid var(--bd);
  margin-top:auto;
}}
.clink{{
  font-family:var(--mono);font-size:.56rem;
  color:var(--acc);letter-spacing:.02em;
  transition:opacity var(--tr);
}}
.card:hover .clink{{opacity:.75;}}
.cimp{{
  font-family:var(--mono);font-size:.52rem;
  color:var(--t3);
}}

/* ─── EMPTY ─────────────────────────────────────────────── */
.empty{{
  padding:36px;text-align:center;
  font-size:.78rem;color:var(--t3);
  grid-column:1/-1;
}}

/* ─── FOOTER ────────────────────────────────────────────── */
footer{{border-top:1px solid var(--bd);padding:14px 24px;}}
.fi{{
  max-width:var(--max);margin:0 auto;
  display:flex;justify-content:space-between;
  flex-wrap:wrap;gap:5px;
}}
.fl,.fr{{font-family:var(--mono);font-size:.54rem;color:var(--t3);}}
#nxt{{color:var(--gold);}}

/* ─── ANIM ──────────────────────────────────────────────── */
@keyframes fadeUp{{
  from{{opacity:0;transform:translateY(7px)}}
  to  {{opacity:1;transform:translateY(0)}}
}}
.fi{{animation:fadeUp .35s ease both;}}

/* ─── RESPONSIVE ────────────────────────────────────────── */
@media(max-width:960px){{
  .grid{{grid-template-columns:repeat(2,1fr);}}
}}
@media(max-width:640px){{
  .ticker,.vl{{display:none;}}
  .hbar,.sn{{padding:0 16px;}}
  .wrap{{padding:16px 16px 60px;}}
  .grid{{grid-template-columns:1fr;gap:8px;}}
  .hl{{grid-template-columns:1fr;}}
  .hl-side{{display:none;}}
  .hl-main{{padding:18px 20px;}}
}}
</style>
</head>
<body>

<!-- HEADER -->
<header class="hdr">
  <div class="hbar">
    <div class="logo">PULSE<div class="ldot"></div></div>
    <span class="slot-chip">{slot}</span>
    <div class="vl"></div>
    <div class="ticker"><div class="tk" id="tk"></div></div>
    <div class="vl"></div>
    <span class="clk" id="clk">—</span>
    <button class="tbtn" id="tbtn" title="切换主题">◑</button>
  </div>
  <div class="pbar"><div class="pfill" id="prog"></div></div>
</header>

<!-- SUBNAV -->
<nav class="snav">
  <div class="sn" id="nav"></div>
</nav>

<!-- MAIN -->
<main class="wrap" id="wrap"></main>

<!-- FOOTER -->
<footer>
  <div class="fi">
    <span class="fl">
      PULSE · {NOW.strftime(f'%Y年{date_str} 周{weekday}')} {NOW.strftime('%H:%M')} 更新 · 5分类 × 6来源精选
    </span>
    <span class="fr">下次更新 <span id="nxt">—</span> · 08:00 / 12:00 / 18:00</span>
  </div>
</footer>

<script>
const FEAT = {feat_json};
const CATS = {cats_json};

const CAT_ORDER = ['politics','business','technology','science','health'];
const CAT_META  = {{
  politics:  {{name:'政治',  color:'#6D1F6D'}},
  business:  {{name:'商业',  color:'#7A3800'}},
  technology:{{name:'科技',  color:'#025A3C'}},
  science:   {{name:'科学',  color:'#0A3C6E'}},
  health:    {{name:'健康',  color:'#2C5445'}},
}};

/* ── 主题 ─────────────────────────────────────────────── */
let _dark = window.matchMedia('(prefers-color-scheme:dark)').matches;
document.getElementById('tbtn').addEventListener('click', () => {{
  _dark = !_dark;
  let s = document.getElementById('_ts');
  if (!s) {{ s=document.createElement('style'); s.id='_ts'; document.head.appendChild(s); }}
  s.textContent = _dark ? `:root{{
    --bg:#141311;--surf:#1E1D1A;--surf2:#252320;
    --bd:rgba(255,255,255,.08);--bd2:rgba(255,255,255,.16);
    --t1:#EBE8E2;--t2:#97928A;--t3:#575249;
    --acc:#D95F32;--acc-bg:rgba(217,95,50,.1);
    --gold:#C9932A;--gold-bg:rgba(201,147,42,.1);
    --sh0:0 1px 2px rgba(0,0,0,.25);
    --sh1:0 2px 8px rgba(0,0,0,.35);
    --sh2:0 6px 24px rgba(0,0,0,.5);}}` : '';
}});

/* ── 时钟 ─────────────────────────────────────────────── */
function pad(n){{ return String(n).padStart(2,'0'); }}
setInterval(()=>{{
  const n=new Date();
  document.getElementById('clk').textContent =
    `${{n.getFullYear()}}/${{pad(n.getMonth()+1)}}/${{pad(n.getDate())}} ${{pad(n.getHours())}}:${{pad(n.getMinutes())}}:${{pad(n.getSeconds())}}`;
}},1000);

/* ── 倒计时 ───────────────────────────────────────────── */
function secsToNext(){{
  const n=new Date(), s=n.getHours()*3600+n.getMinutes()*60+n.getSeconds();
  for(const h of [8,12,18]){{ if(h*3600>s) return h*3600-s; }}
  return 8*3600+(86400-s);
}}
let rem=secsToNext(), total=rem;
setInterval(()=>{{
  rem--; if(rem<0){{ rem=secsToNext(); total=rem; }}
  document.getElementById('prog').style.width=((total-rem)/total*100)+'%';
  const hh=Math.floor(rem/3600), mm=Math.floor((rem%3600)/60), ss=rem%60;
  const el=document.getElementById('nxt');
  if(el) el.textContent=`${{hh}}时${{pad(mm)}}分${{pad(ss)}}秒`;
}},1000);

/* ── 颜色工具 ─────────────────────────────────────────── */
function hexToRgba(hex, a){{
  const r=parseInt(hex.slice(1,3),16),g=parseInt(hex.slice(3,5),16),b=parseInt(hex.slice(5,7),16);
  return `rgba(${{r}},${{g}},${{b}},${{a}})`;
}}

/* ── chip ────────────────────────────────────────────── */
function chip(cat){{
  const m=CAT_META[cat]; if(!m) return '';
  return `<span class="chip"
    style="background:${{hexToRgba(m.color,.09)}};color:${{m.color}}"
  >${{m.name}}</span>`;
}}

/* ── 年龄格式 ────────────────────────────────────────── */
function ageLabel(h){{
  if(h<1)   return `${{Math.round(h*60)}}分钟前`;
  if(h<24)  return `${{Math.round(h)}}小时前`;
  return    `${{Math.floor(h/24)}}天前`;
}}

/* ── 头条 HTML ───────────────────────────────────────── */
function headlineHTML(d){{
  if(!d) return '';
  const m=CAT_META[d.cat]||{{}};
  return `
<div class="hl" style="animation:fadeUp .38s ease both">
  <div class="hl-main">
    <div class="hl-top">
      ${{chip(d.cat)}}
      <span class="hl-badge">TODAY'S TOP</span>
      <span class="hl-src">${{d.src}}</span>
    </div>
    <a href="${{d.url}}" target="_blank" rel="noopener">
      <div class="hl-title">${{d.title}}</div>
    </a>
    <div class="hl-desc">${{d.desc}}</div>
    <div class="hl-foot">
      <a class="rl" href="${{d.url}}" target="_blank" rel="noopener">阅读原文 ↗</a>
      <span class="mt">${{d.pub}}</span>
    </div>
    <div class="imp-row">
      <span class="il">重要指数</span>
      <div class="itr"><div class="ifill" style="width:${{d.imp}}%"></div></div>
      <span class="in">${{d.imp}}</span>
    </div>
  </div>
  <div class="hl-side">
    <div class="hs-block">
      <div class="hs-l">重要指数</div>
      <div class="hs-big">${{d.imp}}</div>
      <div class="hs-sub">/ 100</div>
    </div>
    <div class="hs-div"></div>
    <div class="hs-block">
      <div class="hs-l">来源</div>
      <div style="font-size:.72rem;color:var(--t2);margin-top:3px;line-height:1.65">
        ${{d.src}}<br>
        <span style="color:var(--t3)">${{d.pub}}</span>
      </div>
    </div>
    <div class="hs-div"></div>
    <div class="hs-age">
      <span class="hs-l">发布时间</span>
      <span class="hs-age-n">${{ageLabel(d.age)}}</span>
    </div>
  </div>
</div>`;
}}

/* ── 文章卡片 HTML ───────────────────────────────────── */
function cardHTML(a, idx){{
  const m=CAT_META[a.cat]||{{}};
  return `
<a class="card" href="${{a.url}}" target="_blank" rel="noopener"
   style="--cat-color:${{m.color||'#888'}};
          animation:fadeUp .36s ${{idx*.04}}s ease both;
          --before-bg:${{m.color||'#888'}}">
  <style>.card:hover::before{{background:var(--before-bg);}}</style>
  <div class="ctop">
    <span class="csrc">${{a.src}}</span>
    <span class="cage">${{a.age < 24 ? ageLabel(a.age) : a.pub}}</span>
  </div>
  ${{chip(a.cat)}}
  <div class="ctitle">${{a.title}}</div>
  <div class="cdesc">${{a.desc}}</div>
  <div class="cfoot">
    <span class="clink">阅读原文 ↗</span>
    <span class="cimp">${{a.imp}}</span>
  </div>
</a>`;
}}

/* ── section header ─────────────────────────────────── */
function sh(label, color, count){{
  return `<div class="sh">
    <span class="sh-lbl" style="color:${{color}}">${{label}}</span>
    <div class="sh-line"></div>
    <span class="sh-ct">${{count}} 篇</span>
  </div>`;
}}

/* ── 导航 ────────────────────────────────────────────── */
function buildNav(active){{
  const total = Object.values(CATS).reduce((s,a)=>s+a.length,0);
  let html = `<button class="nb ${{active==='all'?'on':''}}" data-c="all">
    全部 <span class="nb-n">${{total}}</span></button>`;
  for(const c of CAT_ORDER){{
    const n=(CATS[c]||[]).length; if(!n) continue;
    const m=CAT_META[c]||{{}};
    html += `<button class="nb ${{active===c?'on':''}}" data-c="${{c}}">
      ${{m.name}} <span class="nb-n">${{n}}</span></button>`;
  }}
  document.getElementById('nav').innerHTML = html;
}}

/* ── 渲染 ────────────────────────────────────────────── */
function render(cat){{
  buildNav(cat);
  let html = '';

  if(cat === 'all'){{
    if(FEAT){{
      html += `<div class="sh" style="margin-top:0">
        <span class="sh-lbl" style="color:var(--acc)">今日头条</span>
        <div class="sh-line"></div>
      </div>`;
      html += headlineHTML(FEAT);
    }}
    for(const c of CAT_ORDER){{
      const arts = CATS[c]||[];
      if(!arts.length) continue;
      const m = CAT_META[c]||{{}};
      html += sh(m.name, m.color, arts.length);
      html += `<div class="grid">${{arts.map((a,i)=>cardHTML(a,i)).join('')}}</div>`;
    }}
  }} else {{
    const arts = CATS[cat]||[];
    const m    = CAT_META[cat]||{{}};
    if(FEAT && FEAT.cat===cat){{
      html += `<div class="sh" style="margin-top:0">
        <span class="sh-lbl" style="color:var(--acc)">今日头条</span>
        <div class="sh-line"></div>
      </div>`;
      html += headlineHTML(FEAT);
    }}
    html += sh(m.name||cat, m.color||'#888', arts.length);
    html += arts.length
      ? `<div class="grid">${{arts.map((a,i)=>cardHTML(a,i)).join('')}}</div>`
      : '<div class="grid"><div class="empty">暂无内容</div></div>';
  }}

  const wrap = document.getElementById('wrap');
  wrap.innerHTML = html;
  wrap.scrollTop = 0;
}}

/* ── 点击 ────────────────────────────────────────────── */
document.getElementById('nav').addEventListener('click', e => {{
  const b = e.target.closest('.nb'); if(!b) return;
  render(b.dataset.c);
  window.scrollTo({{top:0,behavior:'smooth'}});
}});

/* ── Ticker ──────────────────────────────────────────── */
const allArts = Object.values(CATS).flat();
const titles  = (FEAT?[FEAT.title]:[]).concat(allArts.map(a=>a.title));
document.getElementById('tk').innerHTML =
  titles.concat(titles).map(t=>`<span class="tk-i">${{t}}</span>`).join('');

render('all');
</script>
</body>
</html>"""

def main():
    feat, cat_articles = build_data()
    html = generate_html(feat, cat_articles)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    total = sum(len(v) for v in cat_articles.values())
    print(f"\n✅  index.html  ({1 if feat else 0} 头条 + {total} 要闻)")

if __name__ == "__main__":
    main()
