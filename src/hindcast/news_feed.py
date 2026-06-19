"""实时新闻 feed（历史回响落地页热点源）.

来源（全免费、无 key、本机直连实测可达）：
  - Google News RSS（按政治经济关键词搜索，聚合真实媒体）
  - BBC Business RSS / 美联储 press RSS（补充）

流程：
  fetch_raw_headlines()  —— 并行拉多个 RSS，xml.etree 解析，去重
  build_trending_feed()  —— 1 次便宜 LLM 调用：从原始标题里【策展】出高影响事件
                            + 给每条打【生活维度标签】（生活影响看板用）+ 一句话 why
                            结果服务端缓存（TTL），避免每次请求都拉+调 LLM
真实来源/时间/链接全部来自 RSS 原文（不经 LLM，防编造）；LLM 只做选择 + 打标 + 改写一句话。

热度曲线（GDELT timelinevol）走单独的 lazy 端点，因 GDELT 限流 1 req/5s。
"""
from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from hindcast.llm import chat_json, get_client

# 6 个生活维度（与 translator._CARD_META 对齐）
_DIMENSIONS = {
    "wallet": "钱包(物价/购买力/汇率)",
    "job": "饭碗(就业/行业冲击)",
    "social": "人际(社会信任/分化)",
    "identity": "认同(身份/文化/归属)",
    "power": "规则(权力/政策/制度)",
    "tempo": "节奏(影响多久显现)",
}

# RSS 源（name, url, default_source）—— 直连，无需代理（实测）
_RSS_SOURCES: list[tuple[str, str, str]] = [
    ("geo_trade", "https://news.google.com/rss/search?q=(tariff%20OR%20sanctions%20OR%20trade%20war%20OR%20geopolitics)%20when:7d&hl=en-US&gl=US&ceid=US:en", ""),
    ("monetary", "https://news.google.com/rss/search?q=(central%20bank%20OR%20interest%20rate%20OR%20inflation%20OR%20Federal%20Reserve)%20when:7d&hl=en-US&gl=US&ceid=US:en", ""),
    ("tech_reg", "https://news.google.com/rss/search?q=(AI%20regulation%20OR%20chip%20export%20OR%20semiconductor%20OR%20antitrust)%20when:7d&hl=en-US&gl=US&ceid=US:en", ""),
    ("bbc_biz", "https://feeds.bbci.co.uk/news/business/rss.xml", "BBC"),
]

_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15) Hindcast/0.6"}

# 服务端缓存
_CACHE: dict[str, Any] = {"ts": 0.0, "feed": None}
_TTL_SEC = 1800  # 30 分钟


def _parse_rss(xml_text: str, default_source: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return out
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        if not title:
            continue
        # Google News: <source url="...">Outlet</source> + 标题尾部 " - Outlet"
        src_el = item.find("source")
        source = (src_el.text.strip() if src_el is not None and src_el.text else default_source) or "新闻"
        clean = title
        if src_el is not None and source and clean.endswith(f" - {source}"):
            clean = clean[: -(len(source) + 3)].strip()
        out.append({"title": clean, "url": link, "published": pub, "source": source})
    return out


def fetch_raw_headlines(per_source: int = 12) -> list[dict[str, Any]]:
    """并行拉所有 RSS 源，解析 + 去重，返回原始标题列表。"""
    try:
        import requests
    except ImportError:
        return []

    def _one(name_url_src: tuple[str, str, str]) -> list[dict[str, Any]]:
        _name, url, default_source = name_url_src
        try:
            resp = requests.get(url, headers=_UA, timeout=12)
            if resp.status_code != 200:
                return []
            return _parse_rss(resp.text, default_source)[:per_source]
        except Exception:
            return []

    collected: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=len(_RSS_SOURCES)) as ex:
        for items in ex.map(_one, _RSS_SOURCES):
            collected.extend(items)

    # 去重（按标题归一化）
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for it in collected:
        key = it["title"].lower().strip()
        if key and key not in seen:
            seen.add(key)
            deduped.append(it)
    return deduped


_CURATE_SYSTEM = """\
你是「历史回响」热点策展编辑。从一堆原始新闻标题里，挑出对【普通人生活影响最大】的政治/经济事件。

挑选门槛（高影响才入选）：影响数千万人 OR 显著改变物价/就业/政策/地缘格局。
丢掉：娱乐八卦、纯财报、体育、重复事件。

为每条入选事件：
- 给一句【大白话 blurb】（≤40字，高中生能懂，讲为什么值得看），不要照抄标题。
- 标【生活维度】：从 wallet/job/social/identity/power/tempo 里选 1~3 个它主要砸到的维度，primary 是最主要那个。
  ⚠️ primary 要选【最有区分度】的那个，别动不动就归 wallet——
  地缘/制裁/外交多是 power，技术管制常是 job，身份/移民/文化是 identity，长期格局是 tempo。
  让 6 个维度在整批事件里尽量分散，反映真实的影响热区分布。
- why_dim：一句话说为什么砸这个维度（≤25字）。

维度含义：
  wallet=钱包(物价/购买力/汇率)  job=饭碗(就业/行业)  social=人际(信任/分化)
  identity=认同(身份/文化)  power=规则(权力/政策/制度)  tempo=节奏(影响多久显现)

只输出 JSON，无多余文字：
{
  "events": [
    {"idx": <原始列表下标整数>, "blurb": "…", "primary": "power", "dimensions": ["power","wallet"], "why_dim": "…"}
  ]
}
按影响力从高到低排，最多 10 条。
"""


def _curate_and_tag(raw: list[dict[str, Any]], client) -> list[dict[str, Any]] | None:
    """1 次 LLM 调用：从原始标题策展 + 打生活维度标签。失败返回 None。"""
    if not raw:
        return None
    listing = "\n".join(f"[{i}] {it['title']} （{it['source']}）" for i, it in enumerate(raw[:40]))
    result = chat_json(
        client,
        system=_CURATE_SYSTEM,
        user=f"## 原始新闻标题（{len(raw[:40])} 条）\n\n{listing}",
        max_tokens=1800,
    )
    if result.get("_failed"):
        return None

    events: list[dict[str, Any]] = []
    for e in result.get("events", []):
        try:
            idx = int(e.get("idx"))
        except (TypeError, ValueError):
            continue
        if not (0 <= idx < len(raw)):
            continue
        src = raw[idx]
        dims = [d for d in e.get("dimensions", []) if d in _DIMENSIONS]
        primary = e.get("primary") if e.get("primary") in _DIMENSIONS else (dims[0] if dims else "power")
        if primary not in dims:
            dims = [primary] + dims
        events.append({
            "id": f"news-{idx}-{abs(hash(src['title'])) % 100000}",
            "title": src["title"],
            "blurb": str(e.get("blurb", "")),
            "source": src["source"],
            "url": src["url"],
            "published": src["published"],
            "primary": primary,
            "dimensions": dims[:3],
            "why_dim": str(e.get("why_dim", "")),
        })
    return events or None


def build_trending_feed(client=None, force: bool = False) -> list[dict[str, Any]] | None:
    """构建（或取缓存的）实时热点 feed。失败返回 None（调用方降级到种子列表）。"""
    now = time.time()
    if not force and _CACHE["feed"] is not None and (now - _CACHE["ts"]) < _TTL_SEC:
        return _CACHE["feed"]

    raw = fetch_raw_headlines()
    if not raw:
        return None
    client = client or get_client()
    feed = _curate_and_tag(raw, client)
    if feed:
        _CACHE["feed"] = feed
        _CACHE["ts"] = now
    return feed


# ── 热度趋势（GDELT timelinevol，lazy + 限流友好）──────────────────────────────
_HEAT_CACHE: dict[str, Any] = {}
_HEAT_TTL = 3600  # 1 小时


def fetch_heat(query: str, timespan_days: int = 14) -> list[dict[str, Any]]:
    """返回某话题近 N 天的新闻量曲线 [{date, value}]，供 sparkline。

    GDELT timelinevol mode。限流 1 req/5s → 由前端逐个 lazy 触发 + 此处缓存兜底。
    失败 / 无数据 → []。
    """
    q = (query or "").strip()
    if not q:
        return []
    now = time.time()
    cached = _HEAT_CACHE.get(q)
    if cached and (now - cached["ts"]) < _HEAT_TTL:
        return cached["points"]

    try:
        import requests
        from hindcast.knowledge import _PROXY
    except ImportError:
        return []

    url = "https://api.gdeltproject.org/api/v2/doc/doc"
    params = {
        "query": q,
        "mode": "timelinevol",
        "format": "json",
        "timespan": f"{timespan_days}d",
    }
    points: list[dict[str, Any]] = []
    for attempt in range(2):
        try:
            resp = requests.get(url, params=params, headers=_UA, timeout=20)
            if resp.status_code == 200 and resp.text.lstrip().startswith("{"):
                data = resp.json()
                series = data.get("timeline", [])
                if series:
                    for pt in series[0].get("data", []):
                        points.append({"date": pt.get("date", ""), "value": pt.get("value", 0)})
                break
            # 429 限流 → 退避一次（用代理重试，换出口）
            if resp.status_code == 429 and attempt == 0:
                resp = requests.get(url, params=params, headers=_UA, timeout=20, proxies=_PROXY)
                if resp.status_code == 200 and resp.text.lstrip().startswith("{"):
                    data = resp.json()
                    series = data.get("timeline", [])
                    if series:
                        for pt in series[0].get("data", []):
                            points.append({"date": pt.get("date", ""), "value": pt.get("value", 0)})
                break
        except Exception:
            break

    if points:
        _HEAT_CACHE[q] = {"ts": now, "points": points}
    return points
