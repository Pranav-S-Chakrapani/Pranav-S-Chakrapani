#!/usr/bin/env python3
"""
Renders the whole README card stack into cards/*.svg:

  cards/hero.svg              name + one-liner + portrait
  cards/tile-1.svg ..tile-3.svg  three linked tiles (place side-by-side at width="32.5%")
  cards/chart.svg             contributions/month + streak/active days/busiest day
  cards/repo-<slug>.svg       one per featured repo in data/config.json
  cards/graph.svg             daily contribution graph in the brand colour

Run `python scripts/generate_cards.py`. Set STATIC=1 to render only the
final frame (no running animation) for screenshotting before you push:

  STATIC=1 python scripts/generate_cards.py

Reads:
  data/config.json          static content: name, bio, colors, tiles, repos
  data/contributions.json   daily counts, refreshed by the scheduled Action
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
    esc,
    font_face_css,
    reduced_motion_css,
    stagger,
    subset_font_b64,
    wrap_svg,
)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CARDS_DIR = os.path.join(ROOT, "cards")
MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
WEEKDAY_NAME = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

CARD_W = 800


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
    """Monthly totals (last 12 months), current streak, active-day rate,
    and the single weekday that accumulates the most contributions."""
    if not days:
        return {
            "months": [(m, 0) for m in MONTH_ABBR],
            "streak": 0,
            "active_pct": 0,
            "busiest_day": "--",
            "total": 0,
        }

    by_date = {d["date"]: d["count"] for d in days}
    ordered_dates = sorted(by_date)

    # current streak: walk backwards from the most recent day with data
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
        key = (dt.year, dt.month)
        month_totals[key] += count
    last_12_keys = sorted(month_totals)[-12:]
    # pad to exactly 12 points even on a short history
    while len(last_12_keys) < 12:
        y, m = last_12_keys[0] if last_12_keys else (datetime.now().year, datetime.now().month)
        m -= 1
        if m == 0:
            m, y = 12, y - 1
        last_12_keys.insert(0, (y, m))
    months = [(MONTH_ABBR[m - 1], month_totals.get((y, m), 0)) for (y, m) in last_12_keys]

    return {
        "months": months,
        "streak": streak,
        "active_pct": active_pct,
        "busiest_day": busiest_day,
        "total": sum(by_date.values()),
    }


# --------------------------------------------------------------------------- shared style

def base_style(cfg: dict, font_uri_reg: str, font_uri_bold: str) -> str:
    c = cfg["colors"]
    family = cfg["font"]["family"]
    anim = "" if STATIC else """
      @keyframes fadeUp {
        from { opacity: 0; transform: translateY(10px); }
        to   { opacity: 1; transform: translateY(0); }
      }
      @keyframes popIn {
        0%   { opacity: 0; transform: scale(.85); }
        70%  { opacity: 1; transform: scale(1.03); }
        100% { opacity: 1; transform: scale(1); }
      }
      @keyframes growBar {
        from { transform: scaleY(0); }
        to   { transform: scaleY(1); }
      }
      @keyframes growWidth {
        from { transform: scaleX(0); }
        to   { transform: scaleX(1); }
      }
      @keyframes dash {
        from { stroke-dashoffset: var(--dash, 300); }
        to   { stroke-dashoffset: 0; }
      }
      @keyframes pulseGlow {
        0%, 100% { filter: drop-shadow(0 0 0px var(--glow, #7F5AF0)); }
        50%      { filter: drop-shadow(0 0 6px var(--glow, #7F5AF0)); }
      }
      @keyframes borderSweep {
        from { stroke-dashoffset: 900; }
        to   { stroke-dashoffset: 0; }
      }
    """
    return f"""
    {font_face_css(family, font_uri_reg, font_uri_bold)}
    svg {{ background: {c['bg']}; }}
    text {{ font-family: '{family}', 'Courier New', monospace; fill: {c['text']}; }}
    .muted {{ fill: {c['muted']}; }}
    .accent {{ fill: {c['accent']}; }}
    .primary {{ fill: {c['primary']}; }}
    .bold {{ font-weight: 700; }}
    .card-border {{
      fill: none; stroke: {c['border']}; stroke-width: 1.4; rx: 14; ry: 14;
    }}
    a {{ cursor: pointer; }}
    {anim}
    {reduced_motion_css('.anim')}
    """


def animated(el_class: str, delay: float, name: str, duration: float = 0.6, fill: str = "both") -> str:
    """Returns a CSS class + inline style snippet applying `name` keyframes
    with a stagger `delay`, or nothing at all in STATIC mode (where the
    element is simply drawn already in its resting state)."""
    if STATIC:
        return ""
    # No class attribute here (several callers already set their own class=
    # on the same element, and SVG/XML disallows a duplicate attribute) --
    # the global "* { animation: none !important }" reduced-motion rule
    # overrides this inline style regardless of class.
    return f'style="animation: {name} {duration}s cubic-bezier(.2,.7,.3,1) {delay}s {fill} 1;"'


def card_frame(cfg: dict, width: int, height: int, radius: int = 14) -> str:
    c = cfg["colors"]
    return (
        f'<rect x="1" y="1" width="{width - 2}" height="{height - 2}" rx="{radius}" ry="{radius}" '
        f'fill="{c["bg"]}" stroke="{c["border"]}" stroke-width="1.4"/>'
    )


# --------------------------------------------------------------------------- hero

def render_hero(cfg: dict) -> str:
    c = cfg["colors"]
    w, h = CARD_W, 200
    text_all = cfg["name"] + cfg["tagline"] + "github.com/" + cfg["username"]
    f_reg = subset_font_b64(cfg["font"]["regular"], text_all)
    f_bold = subset_font_b64(cfg["font"]["bold"], text_all)
    style = base_style(cfg, f_reg, f_bold)

    portrait_r = 56
    cx, cy = 96, h / 2

    portrait = ""
    if cfg.get("portrait"):
        portrait = f"""
        <clipPath id="pClip"><circle cx="{cx}" cy="{cy}" r="{portrait_r}"/></clipPath>
        """
    defs = portrait

    portrait_body = ""
    if cfg.get("portrait"):
        ring_anim = "" if STATIC else (
            f'class="anim" style="animation: pulseGlow 2.4s ease-in-out {stagger(0)}s infinite; '
            f'--glow: {c["primary"]};"'
        )
        portrait_body = f"""
        <circle cx="{cx}" cy="{cy}" r="{portrait_r + 4}" fill="none" stroke="{c['primary']}"
          stroke-width="2" {ring_anim}/>
        <image href="{esc(cfg['portrait'])}" x="{cx - portrait_r}" y="{cy - portrait_r}"
          width="{portrait_r * 2}" height="{portrait_r * 2}" clip-path="url(#pClip)"
          preserveAspectRatio="xMidYMid slice"/>
        """

    name_a = animated("", stagger(1), "fadeUp")
    tag_a = animated("", stagger(2), "fadeUp")
    tag_lines = _wrap_text(cfg["tagline"], 54)

    tag_tspans = "".join(
        f'<tspan x="190" dy="{0 if i == 0 else 22}">{esc(line)}</tspan>'
        for i, line in enumerate(tag_lines)
    )

    body = f"""
    <style>{style}</style>
    {card_frame(cfg, w, h)}
    {portrait_body}
    <text x="190" y="78" font-size="30" class="bold" {name_a}>{esc(cfg['name'])}</text>
    <text x="190" y="108" font-size="15" class="muted" {tag_a}>{tag_tspans}</text>
    <text x="190" y="{108 + 22 * len(tag_lines) + 20}" font-size="13" class="accent"
      {animated("", stagger(3), "fadeUp")}>&gt; github.com/{esc(cfg['username'])}</text>
    """
    return wrap_svg(w, h, body, defs=defs, title=f"{cfg['name']} — profile header")


def _wrap_text(text: str, width_chars: int) -> list[str]:
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
    return lines[:2]


# --------------------------------------------------------------------------- tiles

ICON_PATHS = {
    "octocat": (
        "M8 .3a8 8 0 0 0-2.5 15.6c.4.1.5-.2.5-.4v-1.5c-2.2.5-2.7-1-2.7-1-.4-.9-.9-1.2-.9-1.2"
        "-.7-.5.1-.5.1-.5.8.1 1.2.8 1.2.8.7 1.2 1.9.9 2.3.7.1-.5.3-.9.5-1.1-1.8-.2-3.6-.9-3.6-4 "
        "0-.9.3-1.6.8-2.1-.1-.2-.4-1.1.1-2.3 0 0 .7-.2 2.2.8a7.6 7.6 0 0 1 4 0c1.5-1 2.2-.8 2.2-.8"
        ".5 1.2.2 2.1.1 2.3.5.5.8 1.2.8 2.1 0 3.1-1.8 3.8-3.6 4 .3.3.6.8.6 1.6v2.4c0 .2.1.5.6.4"
        "A8 8 0 0 0 8 .3Z"
    ),
    "mail": "M1 3h14v10H1V3Zm0 0 7 5 7-5",
    "shield": "M8 .6 14 3v4.4C14 11.7 11.4 15 8 15.4 4.6 15 2 11.7 2 7.4V3L8 .6Z",
}


def render_tile(cfg: dict, index: int, tile: dict) -> str:
    c = cfg["colors"]
    w, h = 380, 168
    text_all = tile["label"] + tile["sub"]
    f_reg = subset_font_b64(cfg["font"]["regular"], text_all)
    f_bold = subset_font_b64(cfg["font"]["bold"], text_all)
    style = base_style(cfg, f_reg, f_bold)

    icon_path = ICON_PATHS.get(tile.get("icon"), ICON_PATHS["shield"])
    delay = stagger(4 + index, step=0.22)
    tile_anim = animated("", delay, "fadeUp")
    icon_anim = animated("", delay + 0.1, "popIn")

    sub_lines = _wrap_text(tile["sub"], 30)
    sub_tspans = "".join(
        f'<tspan x="86" dy="{0 if i == 0 else 20}">{esc(line)}</tspan>'
        for i, line in enumerate(sub_lines)
    )

    body = f"""
    <style>{style}</style>
    <a xlink:href="{esc(tile['url'])}" target="_blank">
      {card_frame(cfg, w, h, radius=16)}
      <g transform="translate(34,34)" {icon_anim}>
        <circle cx="26" cy="26" r="26" fill="{c['bg_soft']}" stroke="{c['accent']}" stroke-width="1.4"/>
        <path d="{icon_path}" transform="translate(18,18) scale(1.3)" fill="{c['accent']}"/>
      </g>
      <text x="86" y="52" font-size="19" class="bold primary" {tile_anim}>{esc(tile['label'])}</text>
      <text x="86" y="78" font-size="13" class="muted" {tile_anim}>{sub_tspans}</text>
    </a>
    """
    return wrap_svg(w, h, body, title=tile["label"])


# --------------------------------------------------------------------------- chart

def render_chart(cfg: dict, stats: dict) -> str:
    c = cfg["colors"]
    w, h = CARD_W, 320
    months = stats["months"]
    labels = [m for m, _ in months]
    values = [v for _, v in months]
    max_v = max(values) if max(values, default=0) > 0 else 1

    text_all = "".join(labels) + "Contributions / monthCurrent streakActive daysBusiest day" + \
        str(stats["streak"]) + str(stats["active_pct"]) + stats["busiest_day"]
    f_reg = subset_font_b64(cfg["font"]["regular"], text_all)
    f_bold = subset_font_b64(cfg["font"]["bold"], text_all)
    style = base_style(cfg, f_reg, f_bold)

    chart_x0, chart_y0, chart_w, chart_h = 40, 40, 460, 190
    bar_gap = 10
    bar_w = (chart_w / len(values)) - bar_gap
    bars = []
    for i, v in enumerate(values):
        bar_h = max(2, (v / max_v) * chart_h)
        x = chart_x0 + i * (bar_w + bar_gap)
        y = chart_y0 + (chart_h - bar_h)
        delay = stagger(i, step=0.06, base=0.2)
        bar_style = "" if STATIC else (
            f'style="transform-origin: {x + bar_w / 2}px {chart_y0 + chart_h}px; '
            f'animation: growBar .7s cubic-bezier(.2,.8,.3,1) {delay}s both;"'
        )
        bar_class = "" if STATIC else 'class="anim"'
        bars.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" rx="3" '
            f'fill="{c["primary"]}" {bar_class} {bar_style}/>'
            f'<text x="{x + bar_w / 2:.1f}" y="{chart_y0 + chart_h + 18}" font-size="11" '
            f'class="muted" text-anchor="middle">{labels[i]}</text>'
        )

    stat_items = [
        ("Current streak", f"{stats['streak']}d", c["accent"]),
        ("Active days", f"{stats['active_pct']}%", c["primary"]),
        ("Busiest day", stats["busiest_day"], c["mid"]),
    ]
    panel_x = chart_x0 + chart_w + 40
    panel_items = []
    for i, (label, value, color) in enumerate(stat_items):
        y = chart_y0 + 16 + i * 62
        delay = stagger(i, step=0.18, base=0.9)
        a = animated("", delay, "fadeUp")
        panel_items.append(f"""
        <g {a}>
          <text x="{panel_x}" y="{y}" font-size="12" class="muted">{esc(label)}</text>
          <text x="{panel_x}" y="{y + 28}" font-size="26" class="bold" fill="{color}">{esc(value)}</text>
        </g>
        """)

    title_anim = animated("", 0, "fadeUp")
    body = f"""
    <style>{style}</style>
    {card_frame(cfg, w, h)}
    <text x="40" y="26" font-size="15" class="bold primary" {title_anim}>&gt; contributions / month</text>
    {''.join(bars)}
    <line x1="{panel_x - 20}" y1="30" x2="{panel_x - 20}" y2="{h - 30}" stroke="{c['border']}" stroke-opacity="0.35"/>
    {''.join(panel_items)}
    """
    return wrap_svg(w, h, body, title="Contribution activity")


# --------------------------------------------------------------------------- repo cards

def render_repo(cfg: dict, index: int, repo: dict) -> str:
    c = cfg["colors"]
    w, h = CARD_W, 150
    text_all = repo["name"] + repo["desc"] + repo["lang"]
    f_reg = subset_font_b64(cfg["font"]["regular"], text_all)
    f_bold = subset_font_b64(cfg["font"]["bold"], text_all)
    style = base_style(cfg, f_reg, f_bold)

    delay = stagger(index, step=0.25)
    a = animated("", delay, "fadeUp")
    desc_lines = _wrap_text(repo["desc"], 78)
    desc_tspans = "".join(
        f'<tspan x="30" dy="{0 if i == 0 else 20}">{esc(line)}</tspan>'
        for i, line in enumerate(desc_lines)
    )

    body = f"""
    <style>{style}</style>
    <a xlink:href="{esc(repo['url'])}" target="_blank">
      {card_frame(cfg, w, h)}
      <circle cx="{w - 34}" cy="30" r="5" fill="{repo['lang_color']}" {a}/>
      <text x="{w - 46}" y="34" font-size="12" class="muted" text-anchor="end" {a}>{esc(repo['lang'])}</text>
      <text x="30" y="40" font-size="19" class="bold accent" {a}>{esc(repo['name'])}</text>
      <text x="30" y="68" font-size="13" class="muted" {a}>{desc_tspans}</text>
    </a>
    """
    return wrap_svg(w, h, body, title=repo["name"])


# --------------------------------------------------------------------------- contribution graph

def render_graph(cfg: dict, days: list[dict]) -> str:
    c = cfg["colors"]
    w = CARD_W
    cell, gap = 11, 3
    cols = 53
    grid_h = 7 * (cell + gap)
    h = grid_h + 70

    text_all = "Daily contributions"
    f_reg = subset_font_b64(cfg["font"]["regular"], text_all)
    f_bold = subset_font_b64(cfg["font"]["bold"], text_all)
    style = base_style(cfg, f_reg, f_bold)

    # pad/trim to a whole number of weeks ending today, Sunday-first columns
    ordered = sorted(days, key=lambda d: d["date"])[-(cols * 7):]
    counts = [d["count"] for d in ordered]
    while len(counts) < cols * 7:
        counts.insert(0, 0)
    max_v = max(counts) if counts else 0

    def shade(v: int) -> str:
        if max_v == 0 or v == 0:
            return c["bg_soft"]
        ratio = v / max_v
        # interpolate bg_soft -> primary purple across 4 buckets
        steps = [c["bg_soft"], "#3a2e66", "#5b3fb0", c["primary"]]
        idx = min(len(steps) - 1, int(ratio * (len(steps) - 1)) + 1)
        return steps[idx]

    grid_x0, grid_y0 = 40, 50
    cells = []
    i = 0
    for col in range(cols):
        for row in range(7):
            v = counts[i]
            i += 1
            x = grid_x0 + col * (cell + gap)
            y = grid_y0 + row * (cell + gap)
            fill = shade(v)
            if STATIC:
                cells.append(
                    f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" fill="{fill}"/>'
                )
            else:
                delay = stagger(col, step=0.012, base=0.1)
                cells.append(
                    f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" fill="{c["bg_soft"]}">'
                    f'<animate attributeName="fill" from="{c["bg_soft"]}" to="{fill}" '
                    f'begin="{delay}s" dur="0.4s" fill="freeze"/>'
                    f'</rect>'
                )

    title_anim = animated("", 0, "fadeUp")
    body = f"""
    <style>{style}</style>
    {card_frame(cfg, w, h)}
    <text x="40" y="28" font-size="15" class="bold primary" {title_anim}>&gt; contribution graph</text>
    {''.join(cells)}
    """
    return wrap_svg(w, h, body, title="Contribution graph")


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
