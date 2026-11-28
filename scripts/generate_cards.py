#!/usr/bin/env python3
"""
Renders the whole README card stack into cards/*.svg -- editorial design:
one accent colour, a serif display headline, monospace used only as small
uppercase "eyebrow" labels and data, generous dark paper backgrounds, no
drawn borders.

  cards/hero.svg               name + eyebrow + bio + portrait
  cards/tile-1.svg ..tile-3.svg  three solid-accent stat blocks (place at width="32.5%")
  cards/chart.svg               contributions/month + streak/active days/busiest day
  cards/repo-<slug>.svg         one per featured repo in data/config.json
  cards/graph.svg               daily contribution graph, tinted in the accent colour

Run `python scripts/generate_cards.py`. Set STATIC=1 to render only the
final frame (no running animation) for screenshotting before you push:

  STATIC=1 python scripts/generate_cards.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from svgkit import (  # noqa: E402
    STATIC,
    arrow_icon,
    esc,
    font_face_css_one,
    reduced_motion_css,
    stagger,
    subset_font_b64,
    wrap_svg,
)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CARDS_DIR = os.path.join(ROOT, "cards")
MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
WEEKDAY_NAME = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

CARD_W = 880


# --------------------------------------------------------------------------- data

def load_config() -> dict:
    with open(os.path.join(ROOT, "data", "config.json")) as f:
        return json.load(f)


def load_contributions() -> list[dict]:
    path = os.path.join(ROOT, "data", "contributions.json")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)["days"]


def compute_stats(days: list[dict]) -> dict:
    if not days:
        return {"months": [(m, 0) for m in MONTH_ABBR], "streak": 0,
                "active_pct": 0, "busiest_day": "--", "total": 0}

    by_date = {d["date"]: d["count"] for d in days}
    ordered_dates = sorted(by_date)

    streak = 0
    for date_str in reversed(ordered_dates):
        if by_date[date_str] > 0:
            streak += 1
        else:
            break

    active_days = sum(1 for c in by_date.values() if c > 0)
    active_pct = round(100 * active_days / len(by_date)) if by_date else 0

    weekday_totals = defaultdict(int)
    for date_str, count in by_date.items():
        wd = datetime.strptime(date_str, "%Y-%m-%d").weekday()
        weekday_totals[wd] += count
    busiest_wd = max(weekday_totals, key=weekday_totals.get) if weekday_totals else 0
    busiest_day = WEEKDAY_NAME[busiest_wd]

    month_totals = Counter()
    for date_str, count in by_date.items():
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        month_totals[(dt.year, dt.month)] += count
    last_12_keys = sorted(month_totals)[-12:]
    while len(last_12_keys) < 12:
        y, m = last_12_keys[0] if last_12_keys else (datetime.now().year, datetime.now().month)
        m -= 1
        if m == 0:
            m, y = 12, y - 1
        last_12_keys.insert(0, (y, m))
    months = [(MONTH_ABBR[m - 1], month_totals.get((y, m), 0)) for (y, m) in last_12_keys]

    return {"months": months, "streak": streak, "active_pct": active_pct,
            "busiest_day": busiest_day, "total": sum(by_date.values())}


# --------------------------------------------------------------------------- shared style

def all_font_faces(cfg: dict, text: str) -> str:
    """One @font-face per weight/style actually offered by the type system
    (serif regular/italic/semibold, sans regular/semibold, mono
    regular/bold), each subset down to the characters in `text`. Unused
    declarations cost nothing real -- pyftsubset still emits a tiny valid
    font even with zero matched glyphs -- so every card just includes the
    whole system and only ever loads the handful of KB it actually draws
    glyphs from."""
    f = cfg["font"]
    specs = [
        (f["serif"], f["serif_regular"], 400, "normal"),
        (f["serif"], f["serif_italic"], 500, "italic"),
        (f["serif"], f["serif_semibold"], 600, "normal"),
        (f["sans"], f["sans_regular"], 400, "normal"),
        (f["sans"], f["sans_semibold"], 600, "normal"),
        (f["mono"], f["mono_regular"], 400, "normal"),
        (f["mono"], f["mono_bold"], 700, "normal"),
    ]
    out = []
    for family, path, weight, style in specs:
        uri = subset_font_b64(path, text)
        out.append(font_face_css_one(family, uri, weight, style))
    return "\n".join(out)


def base_style(cfg: dict, text: str) -> str:
    c = cfg["colors"]
    f = cfg["font"]
    anim = "" if STATIC else """
      @keyframes fadeUp {
        from { opacity: 0; transform: translateY(12px); }
        to   { opacity: 1; transform: translateY(0); }
      }
      @keyframes growBar {
        from { transform: scaleY(0); }
        to   { transform: scaleY(1); }
      }
      @keyframes ring {
        from { stroke-dashoffset: 220; }
        to   { stroke-dashoffset: 0; }
      }
    """
    return f"""
    {all_font_faces(cfg, text)}
    svg {{ background: {c['bg']}; }}
    text {{ fill: {c['text']}; }}
    .serif {{ font-family: '{f['serif']}', Georgia, serif; }}
    .sans  {{ font-family: '{f['sans']}', -apple-system, sans-serif; }}
    .mono  {{ font-family: '{f['mono']}', ui-monospace, Menlo, monospace; }}
    .muted {{ fill: {c['muted']}; }}
    .accent {{ fill: {c['accent']}; }}
    .on-accent {{ fill: {c['on_accent']}; }}
    .eyebrow {{ letter-spacing: 2px; }}
    {anim}
    {reduced_motion_css()}
    """


def animated(delay: float, name: str, duration: float = 0.7, fill: str = "both") -> str:
    if STATIC:
        return ""
    return f'style="animation: {name} {duration}s cubic-bezier(.16,.84,.3,1) {delay}s {fill} 1;"'


def shine_gradient(gid: str, base_color: str, accent: str, delay: float = 1.2) -> str:
    """A linearGradient that sweeps a one-off highlight across whatever
    text/shape references it via fill="url(#{gid})". Disabled cleanly
    under reduced motion (see reduced_motion_css) -- the gradient then
    just renders at its authored (static two-tone) position."""
    anim_el = "" if STATIC else (
        f'<animateTransform attributeName="gradientTransform" type="translate" '
        f'values="-400 0;400 0;400 0" keyTimes="0;.5;1" dur="2.6s" begin="{delay}s" '
        f'repeatCount="indefinite"/>'
    )
    return f"""
    <linearGradient id="{gid}" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="300" y2="0">
      <stop offset="0" stop-color="{base_color}"/>
      <stop offset="0.42" stop-color="{base_color}"/>
      <stop offset="0.5" stop-color="{accent}"/>
      <stop offset="0.58" stop-color="{base_color}"/>
      <stop offset="1" stop-color="{base_color}"/>
      {anim_el}
    </linearGradient>
    """


def _wrap_text(text: str, width_chars: int, max_lines: int = 3) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if len(trial) > width_chars and cur:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines[:max_lines]


def eyebrow(x: int, y: int, label: str, color: str, delay: float = 0) -> str:
    a = animated(delay, "fadeUp", 0.5)
    return f"""
    <g {a}>
      <rect x="{x}" y="{y - 9}" width="7" height="7" rx="1.5" fill="{color}"/>
      <text x="{x + 15}" y="{y}" font-size="11" class="mono eyebrow muted"
        text-transform="uppercase">{esc(label)}</text>
    </g>
    """


# --------------------------------------------------------------------------- hero

def render_hero(cfg: dict) -> str:
    c = cfg["colors"]
    w, h = CARD_W, 320
    tag_lines = _wrap_text(cfg["tagline"], 68, max_lines=3)
    text_all = (cfg["name_line1"] + cfg["name_line2"] + cfg["eyebrow"] +
                cfg["tagline"] + cfg["link_label"])
    style = base_style(cfg, text_all)

    portrait_size = 84
    px, py = w - 60 - portrait_size, 46

    defs = shine_gradient("heroShine", c["text"], c["accent"], delay=1.3)

    portrait_body = ""
    if cfg.get("portrait"):
        defs += f'<clipPath id="pClip"><rect x="0" y="0" width="{portrait_size}" height="{portrait_size}" rx="16"/></clipPath>'
        ring_a = animated(1.5, "fadeUp", 0.6)
        portrait_body = f"""
        <g transform="translate({px},{py})" {ring_a}>
          <rect x="-1" y="-1" width="{portrait_size + 2}" height="{portrait_size + 2}" rx="17"
            fill="none" stroke="{c['accent']}" stroke-width="1"/>
          <image href="{esc(cfg['portrait'])}" width="{portrait_size}" height="{portrait_size}"
            clip-path="url(#pClip)" preserveAspectRatio="xMidYMid slice"/>
        </g>
        """

    tag_tspans = "".join(
        f'<tspan x="60" dy="{0 if i == 0 else 24}">{esc(line)}</tspan>'
        for i, line in enumerate(tag_lines)
    )

    name1_a = animated(0.15, "fadeUp")
    name2_a = animated(0.3, "fadeUp")
    tag_a = animated(0.55, "fadeUp")
    link_a = animated(0.8, "fadeUp")

    body = f"""
    <style>{style}</style>
    <rect width="{w}" height="{h}" rx="20" fill="{c['bg']}"/>
    {eyebrow(60, 56, cfg['eyebrow'], c['accent'])}
    {portrait_body}
    <text x="58" y="128" font-size="64" class="serif" fill="{c['text']}" letter-spacing="-1.5" {name1_a}>{esc(cfg['name_line1'])}</text>
    <text x="58" y="190" font-size="64" font-style="italic" class="serif" fill="url(#heroShine)" letter-spacing="-1.5" {name2_a}>{esc(cfg['name_line2'])}</text>
    <text x="60" y="224" font-size="15" class="sans muted" {tag_a}>{tag_tspans}</text>
    <g {link_a}>
      <text x="60" y="{224 + 24 * len(tag_lines) + 28}" font-size="13" class="mono accent">{esc(cfg['link_label'])}</text>
      {arrow_icon(60 + len(cfg['link_label']) * 7.8 + 10, 224 + 24 * len(tag_lines) + 20, c['accent'], 11)}
    </g>
    """
    return wrap_svg(w, h, body, defs=defs, title=f"{cfg['name_line1']} {cfg['name_line2']} \u2014 {cfg['eyebrow']}")


# --------------------------------------------------------------------------- tiles (solid stat blocks)

def render_tile(cfg: dict, index: int, tile: dict) -> str:
    c = cfg["colors"]
    w, h = 283, 172
    text_all = tile["eyebrow"] + tile["headline"] + tile["sub"]
    style = base_style(cfg, text_all)

    delay = stagger(index, step=0.18, base=0.2)
    block_a = animated(delay, "fadeUp")
    sub_lines = _wrap_text(tile["sub"], 24, max_lines=2)
    sub_tspans = "".join(
        f'<tspan x="22" dy="{0 if i == 0 else 17}">{esc(line)}</tspan>'
        for i, line in enumerate(sub_lines)
    )

    body = f"""
    <style>{style}</style>
    <a xlink:href="{esc(tile['url'])}" target="_blank">
      <g {block_a}>
        <rect width="{w}" height="{h}" rx="18" fill="{c['accent']}"/>
        <text x="22" y="34" font-size="11" class="mono eyebrow" fill="{c['on_accent']}" opacity="0.85">{esc(tile['eyebrow'])}</text>
        {arrow_icon(w - 36, 22, c['on_accent'], 11)}
        <text x="20" y="104" font-size="30" class="serif" fill="{c['on_accent']}">{esc(tile['headline'])}</text>
        <text x="22" y="134" font-size="12.5" class="sans" fill="{c['on_accent']}" opacity="0.8">{sub_tspans}</text>
      </g>
    </a>
    """
    return wrap_svg(w, h, body, title=f"{tile['eyebrow']}: {tile['headline']}")


# --------------------------------------------------------------------------- chart

def render_chart(cfg: dict, stats: dict) -> str:
    c = cfg["colors"]
    w, h = CARD_W, 340
    months = stats["months"]
    labels = [m for m, _ in months]
    values = [v for _, v in months]
    max_v = max(values) if max(values, default=0) > 0 else 1
    peak_i = values.index(max(values)) if values else 0

    text_all = ("".join(labels) + "THE LAST 12 MONTHSContributions" +
                "Current streakActive daysBusiest day" +
                str(stats["total"]) + str(stats["streak"]) + str(stats["active_pct"]) + stats["busiest_day"])
    style = base_style(cfg, text_all)

    chart_x0, chart_y0, chart_w, chart_h = 60, 150, 480, 130
    bar_gap = 9
    bar_w = (chart_w / len(values)) - bar_gap
    bars = []
    for i, v in enumerate(values):
        bar_h = max(2, (v / max_v) * chart_h)
        x = chart_x0 + i * (bar_w + bar_gap)
        y = chart_y0 + (chart_h - bar_h)
        delay = stagger(i, step=0.05, base=0.5)
        fill = c["accent"] if i == peak_i else c["accent_dim"]
        bar_style = "" if STATIC else (
            f'style="transform-origin: {x + bar_w / 2:.1f}px {chart_y0 + chart_h}px; '
            f'animation: growBar .6s cubic-bezier(.16,.84,.3,1) {delay}s both;"'
        )
        peak_label = (
            f'<text x="{x + bar_w / 2:.1f}" y="{y - 10}" font-size="11" class="mono accent" '
            f'text-anchor="middle">{v}</text>' if i == peak_i else ""
        )
        bars.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" rx="3" '
            f'fill="{fill}" {bar_style}/>{peak_label}'
            f'<text x="{x + bar_w / 2:.1f}" y="{chart_y0 + chart_h + 22}" font-size="11" '
            f'class="mono muted" text-anchor="middle">{labels[i]}</text>'
        )

    stat_items = [
        ("Current streak", f"{stats['streak']}d"),
        ("Active days", f"{stats['active_pct']}%"),
        ("Busiest day", stats["busiest_day"]),
    ]
    panel_x = chart_x0 + chart_w + 50
    panel_items = []
    for i, (label, value) in enumerate(stat_items):
        y = chart_y0 - 70 + i * 68
        delay = stagger(i, step=0.15, base=1.1)
        a = animated(delay, "fadeUp")
        panel_items.append(f"""
        <g {a}>
          <text x="{panel_x}" y="{y}" font-size="11" class="mono muted eyebrow">{esc(label.upper())}</text>
          <text x="{panel_x}" y="{y + 36}" font-size="30" class="serif" fill="{c['text']}">{esc(value)}</text>
        </g>
        """)

    headline_a = animated(0.3, "fadeUp")
    body = f"""
    <style>{style}</style>
    <rect width="{w}" height="{h}" rx="20" fill="{c['bg']}"/>
    {eyebrow(60, 56, "THE LAST 12 MONTHS", c['accent'])}
    <text x="58" y="104" font-size="38" class="serif" fill="{c['text']}" {headline_a}>{stats['total']:,} <tspan font-style="italic" fill="{c['accent']}">contributions</tspan></text>
    {''.join(bars)}
    <line x1="{panel_x - 25}" y1="{chart_y0 - 80}" x2="{panel_x - 25}" y2="{chart_y0 + chart_h}" stroke="{c['muted']}" stroke-opacity="0.2"/>
    {''.join(panel_items)}
    """
    return wrap_svg(w, h, body, title=f"{stats['total']} contributions in the last 12 months, {stats['streak']}-day streak")


# --------------------------------------------------------------------------- repo cards

def render_repo(cfg: dict, index: int, repo: dict) -> str:
    c = cfg["colors"]
    w, h = CARD_W, 128
    text_all = repo["name"] + repo["desc"] + repo["lang"]
    style = base_style(cfg, text_all)

    delay = stagger(index, step=0.2, base=0.1)
    a = animated(delay, "fadeUp")
    desc_lines = _wrap_text(repo["desc"], 92, max_lines=2)
    desc_tspans = "".join(
        f'<tspan x="60" dy="{0 if i == 0 else 20}">{esc(line)}</tspan>'
        for i, line in enumerate(desc_lines)
    )

    body = f"""
    <style>{style}</style>
    <a xlink:href="{esc(repo['url'])}" target="_blank">
      <g {a}>
        <rect width="{w}" height="{h}" rx="18" fill="{c['bg']}"/>
        <rect x="60" y="30" width="7" height="7" rx="1.5" fill="{repo['lang_color']}"/>
        <text x="77" y="37" font-size="18" class="sans" font-weight="600" fill="{c['text']}">{esc(repo['name'])}</text>
        {arrow_icon(w - 76, 26, c['muted'], 10)}
        <text x="60" y="66" font-size="13.5" class="sans muted">{desc_tspans}</text>
        <text x="60" y="{h - 22}" font-size="11" class="mono muted eyebrow">{esc(repo['lang'].upper())} \u00b7 PUBLIC</text>
      </g>
    </a>
    """
    return wrap_svg(w, h, body, title=f"{repo['name']}: {repo['desc']}")


# --------------------------------------------------------------------------- contribution graph

def render_graph(cfg: dict, days: list[dict]) -> str:
    c = cfg["colors"]
    w = CARD_W
    cell, gap = 11, 3
    cols = 53
    grid_h = 7 * (cell + gap)
    h = grid_h + 130

    text_all = "Every day, in violetREFRESHED DAILY"
    style = base_style(cfg, text_all)

    ordered = sorted(days, key=lambda d: d["date"])[-(cols * 7):]
    counts = [d["count"] for d in ordered]
    while len(counts) < cols * 7:
        counts.insert(0, 0)
    max_v = max(counts) if counts else 0

    steps = [c["surface_1"], c["accent_dim"], "#5a48a8", c["accent"]]

    def shade(v: int) -> str:
        if max_v == 0 or v == 0:
            return steps[0]
        ratio = v / max_v
        idx = min(len(steps) - 1, int(ratio * (len(steps) - 1)) + 1)
        return steps[idx]

    grid_x0, grid_y0 = 60, 100
    cells = []
    i = 0
    for col in range(cols):
        for row in range(7):
            v = counts[i]
            i += 1
            x = grid_x0 + col * (cell + gap)
            y = grid_y0 + row * (cell + gap)
            final = shade(v)
            if STATIC:
                cells.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2.5" fill="{final}"/>')
            else:
                delay = stagger(col, step=0.012, base=0.3)
                cells.append(
                    f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2.5" fill="{final}">'
                    f'<animate attributeName="fill" from="{steps[0]}" to="{final}" '
                    f'begin="{delay}s" dur="0.35s" fill="freeze"/></rect>'
                )

    headline_a = animated(0.1, "fadeUp")
    body = f"""
    <style>{style}</style>
    <rect width="{w}" height="{h}" rx="20" fill="{c['bg']}"/>
    <text x="58" y="56" font-size="34" class="serif" fill="{c['text']}" {headline_a}>Every day, <tspan font-style="italic" fill="{c['accent']}">in violet</tspan></text>
    <text x="{w - 60}" y="54" text-anchor="end" font-size="11" class="mono muted eyebrow">REFRESHED DAILY</text>
    {''.join(cells)}
    """
    return wrap_svg(w, h, body, title="Daily contribution graph, tinted in the accent colour, refreshed daily")


# --------------------------------------------------------------------------- main

def main() -> None:
    cfg = load_config()
    days = load_contributions()
    stats = compute_stats(days)

    os.makedirs(CARDS_DIR, exist_ok=True)

    def write(name: str, svg: str) -> None:
        path = os.path.join(CARDS_DIR, name)
        with open(path, "w") as f:
            f.write(svg)
        print(f"wrote {path} ({len(svg)} bytes){' [static]' if STATIC else ''}")

    write("hero.svg", render_hero(cfg))
    for i, tile in enumerate(cfg["tiles"][:3]):
        write(f"tile-{i + 1}.svg", render_tile(cfg, i, tile))
    write("chart.svg", render_chart(cfg, stats))
    for i, repo in enumerate(cfg["repos"]):
        write(f"repo-{repo['slug']}.svg", render_repo(cfg, i, repo))
    write("graph.svg", render_graph(cfg, days))

    print(f"\nDone. {'STATIC (final-frame) mode.' if STATIC else 'Animated mode.'}")


if __name__ == "__main__":
    main()
