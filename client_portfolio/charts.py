# -*- coding: utf-8 -*-
"""
client_portfolio/charts.py  v2
───────────────────────────────
All chart builders use:
  - client_portfolio.theme  for consistent styling
  - client_portfolio.metrics_service.PortfolioMetrics for data
  - automargin=True everywhere
  - Dynamic height based on item count
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from client_portfolio.theme import (
    apply, COLOUR, PALETTE, NAVY, BLUE, GREEN, AMBER, RED, SLATE, TEAL, PURPLE,
    margins, margins_hbar, margins_grouped_bar, fmt_ils, label,
)
from client_portfolio.metrics_service import PortfolioMetrics

# ── Small helpers ─────────────────────────────────────────────────────────────

def _nan(v) -> bool:
    try:
        return math.isnan(float(v))
    except Exception:
        return v is None

def _pct(v, dec=1) -> str:
    return f"{v:.{dec}f}%" if not _nan(v) else "—"

def _coverage_note(cov: float) -> str:
    if cov >= 95:
        return ""
    return f" (כיסוי {cov:.0f}%)"


# ── 1. Executive summary: 4-panel mini-chart ─────────────────────────────────

def chart_executive_summary(m: PortfolioMetrics) -> go.Figure:
    """2×2 grid of the four key allocation splits."""
    a = m.allocation
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=[
            f"מניות / אחר{_coverage_note(a.equity_cov)}",
            f"חו\"ל / ישראל{_coverage_note(a.foreign_cov)}",
            f"מט\"ח / שקל{_coverage_note(a.fx_cov)}",
            f"לא-סחיר{_coverage_note(a.illiquid_cov)}",
        ],
        specs=[[{"type": "domain"}, {"type": "domain"}],
               [{"type": "domain"}, {"type": "domain"}]],
        horizontal_spacing=0.1, vertical_spacing=0.15,
    )

    def _donut(labels, vals, colors, row, col):
        vals_clean = [max(0, v) for v in vals]
        if sum(vals_clean) == 0:
            return
        fig.add_trace(go.Pie(
            labels=labels, values=vals_clean,
            hole=0.55,
            marker=dict(colors=colors, line=dict(color="#fff", width=2)),
            textinfo="label+percent",
            textfont=dict(size=10),
            hovertemplate="<b>%{label}</b><br>%{value:.1f}%<extra></extra>",
            showlegend=False,
        ), row=row, col=col)

    eq  = a.equity_pct or 0;   ot = max(0, 100 - eq)
    fo  = a.foreign_pct or 0;  dom = max(0, 100 - fo)
    fx  = a.fx_pct or 0;       ils = max(0, 100 - fx)
    ill = a.illiquid_pct or 0; liq = max(0, 100 - ill)

    _donut(["מניות", "אחר"],     [eq,  ot],  [BLUE,   SLATE],  1, 1)
    _donut(['חו"ל',  "ישראל"],   [fo,  dom], [TEAL,   NAVY],   1, 2)
    _donut(['מט"ח',  "שקל"],     [fx,  ils], [AMBER,  SLATE],  2, 1)
    _donut(["לא-סחיר", "סחיר"],  [ill, liq], [RED,    GREEN],  2, 2)

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Segoe UI, sans-serif", size=12),
        margin=dict(l=10, r=10, t=50, b=10),
        height=380,
    )
    return fig


# ── 2. Manager breakdown ──────────────────────────────────────────────────────

def chart_by_manager(m: PortfolioMetrics) -> go.Figure:
    df = m.by_manager
    if df.empty:
        return go.Figure()

    df = df.copy()
    df["label"] = df["מנהל"].apply(label)
    df = df.sort_values("משקל %", ascending=True)

    colors = [RED if w > 30 else BLUE for w in df["משקל %"]]
    fig = go.Figure(go.Bar(
        x=df["משקל %"], y=df["label"],
        orientation="h",
        marker_color=colors,
        text=df.apply(lambda r: f"{r['משקל %']:.1f}%  {fmt_ils(r['סכום'])}", axis=1),
        textposition="outside",
        hovertemplate="<b>%{y}</b><br>%{x:.1f}%<br>%{text}<extra></extra>",
    ))
    fig.add_vline(x=30, line_dash="dash", line_color=AMBER,
                  annotation_text="30%", annotation_position="top right",
                  annotation_font=dict(size=10))
    apply(fig, "חלוקה בין מנהלים",
          height=max(280, 50 + 38 * len(df)),
          margin=margins_hbar(len(df)),
          show_legend=False)
    fig.update_xaxes(ticksuffix="%")
    return fig


# ── 3. Stocks vs Bonds (stacked bar) ─────────────────────────────────────────

def chart_stocks_bonds(m: PortfolioMetrics) -> go.Figure:
    a = m.allocation
    categories = [("מניות",   a.equity_pct   or 0, BLUE),
                  ('אג"ח/אחר', a.bonds_pct    or 0, GREEN),
                  ("לא-סחיר", a.illiquid_pct  or 0, RED)]
    fig = go.Figure()
    for name, val, color in categories:
        fig.add_trace(go.Bar(
            x=["תמהיל"], y=[val], name=f"{name} ({val:.1f}%)",
            marker_color=color,
            text=[f"{val:.1f}%"], textposition="inside",
            hovertemplate=f"<b>{name}</b><br>%{{y:.1f}}%<extra></extra>",
        ))
    cov = a.equity_cov
    apply(fig, f'מניות / אג"ח / לא-סחיר{_coverage_note(cov)}',
          height=320, margin=margins(l=40, r=40, t=50, b=90), show_legend=True)
    fig.update_layout(barmode="stack")
    fig.update_yaxes(ticksuffix="%", range=[0, 105])
    return fig


# ── 4. Foreign vs Domestic (horizontal stacked bar) ──────────────────────────

def chart_foreign_domestic(m: PortfolioMetrics) -> go.Figure:
    a = m.allocation
    fo = a.foreign_pct or 0; dom = a.domestic_pct or 0
    fig = go.Figure()
    for name, val, color in [('חו"ל', fo, TEAL), ("ישראל", dom, NAVY)]:
        fig.add_trace(go.Bar(
            y=["חשיפה"], x=[val], orientation="h",
            name=f"{name} ({val:.1f}%)", marker_color=color,
            text=[f"{val:.1f}%"], textposition="inside",
        ))
    apply(fig, f'חו"ל / ישראל{_coverage_note(a.foreign_cov)}',
          height=200, margin=margins(l=60, r=40, t=50, b=80), show_legend=True)
    fig.update_layout(barmode="stack")
    fig.update_xaxes(ticksuffix="%", range=[0, 105])
    return fig


# ── 5. FX vs ILS (horizontal stacked bar) ────────────────────────────────────

def chart_fx_ils(m: PortfolioMetrics) -> go.Figure:
    a = m.allocation
    fx = a.fx_pct or 0; ils = a.ils_pct or 0
    fig = go.Figure()
    for name, val, color in [('מט"ח', fx, AMBER), ("שקל", ils, SLATE)]:
        fig.add_trace(go.Bar(
            y=["חשיפה"], x=[val], orientation="h",
            name=f"{name} ({val:.1f}%)", marker_color=color,
            text=[f"{val:.1f}%"], textposition="inside",
        ))
    apply(fig, f'מט"ח / שקל{_coverage_note(a.fx_cov)}',
          height=200, margin=margins(l=60, r=40, t=50, b=80), show_legend=True)
    fig.update_layout(barmode="stack")
    fig.update_xaxes(ticksuffix="%", range=[0, 105])
    return fig


# ── 6. Asset breakdown per product ───────────────────────────────────────────

def chart_asset_breakdown(df: pd.DataFrame) -> go.Figure:
    active = df[~df.get("excluded", pd.Series([False]*len(df))).astype(bool)].copy()
    if active.empty:
        return go.Figure()

    # Truncate labels
    active["lbl"] = (active["provider"] + " | " + active.get("product_name", active["provider"]))\
                    .apply(lambda s: s[:28] + "…" if len(s) > 30 else s)
    active = active.sort_values("amount", ascending=False)

    cols_show = [
        ("equity_pct",   "מניות",    BLUE),
        ("foreign_pct",  'חו"ל',     TEAL),
        ("fx_pct",       'מט"ח',     AMBER),
        ("illiquid_pct", "לא סחיר",  RED),
    ]
    fig = go.Figure()
    for col, name, color in cols_show:
        vals = active[col].fillna(0).tolist() if col in active.columns else [0]*len(active)
        fig.add_trace(go.Bar(
            name=name, x=active["lbl"].tolist(), y=vals,
            marker_color=color, opacity=0.85,
            hovertemplate=f"<b>%{{x}}</b><br>{name}: %{{y:.1f}}%<extra></extra>",
        ))

    n = len(active)
    apply(fig, "פיזור סוגי נכסים לפי מוצר",
          height=max(380, 200 + n * 15),
          margin=margins_grouped_bar(n),
          show_legend=True)
    fig.update_layout(barmode="group")
    fig.update_xaxes(tickangle=-40, tickfont=dict(size=9), automargin=True)
    fig.update_yaxes(ticksuffix="%")
    return fig


# ── 7. Annuity vs Capital ─────────────────────────────────────────────────────

def chart_annuity_capital(m: PortfolioMetrics) -> go.Figure:
    df = m.by_type
    if df.empty:
        return go.Figure()

    cat_agg = df.groupby("category")["amount"].sum().reset_index()
    total = cat_agg["amount"].sum()
    cat_agg["w"] = cat_agg["amount"] / total * 100

    color_map = {"קצבה": PURPLE, "הון": TEAL, "אחר": SLATE}
    labels_  = cat_agg["category"].tolist()
    values_  = cat_agg["w"].tolist()
    colors_  = [color_map.get(l, SLATE) for l in labels_]

    fig = go.Figure(go.Pie(
        labels=labels_, values=values_, hole=0.5,
        marker=dict(colors=colors_, line=dict(color="#fff", width=2)),
        textinfo="label+percent+value",
        texttemplate="%{label}<br>%{percent}<br>" + "₪%{value:,.0f}",
        hovertemplate="<b>%{label}</b><br>₪%{value:,.0f}<br>%{percent}<extra></extra>",
    ))
    apply(fig, "מוצרי קצבה vs מוצרי הון", height=360,
          margin=margins(l=20, r=20, t=50, b=110), show_legend=False)
    return fig


# ── 8. Costs ──────────────────────────────────────────────────────────────────

def chart_costs(df: pd.DataFrame) -> go.Figure:
    if "annual_cost_pct" not in df.columns:
        return go.Figure()
    active = df[~df.get("excluded", pd.Series([False]*len(df))).astype(bool)]
    sub = active[active["annual_cost_pct"].notna()].copy()
    if sub.empty:
        return go.Figure()

    sub["cost_ils"] = sub["amount"] * sub["annual_cost_pct"] / 100
    sub["lbl"] = (sub["provider"] + " | " + sub.get("product_name", sub["provider"]))\
                 .apply(lambda s: s[:28] + "…" if len(s) > 30 else s)
    sub = sub.sort_values("cost_ils", ascending=False)

    wc = sub["cost_ils"].sum() / sub["amount"].sum() * 100 if sub["amount"].sum() > 0 else 0

    fig = make_subplots(rows=1, cols=2,
                        subplot_titles=["עלות שנתית (₪)", "דמי ניהול (%)"])
    fig.add_trace(go.Bar(
        x=sub["lbl"], y=sub["cost_ils"],
        marker_color=RED, name="עלות ₪",
        text=sub["cost_ils"].map(fmt_ils), textposition="outside",
    ), row=1, col=1)
    fig.add_trace(go.Bar(
        x=sub["lbl"], y=sub["annual_cost_pct"],
        marker_color=AMBER, name="דמי ניהול %",
        text=sub["annual_cost_pct"].map(lambda v: f"{v:.2f}%"), textposition="outside",
    ), row=1, col=2)

    n = len(sub)
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(248,249,252,1)",
        title=dict(text=f"עלויות — משוקלל: {wc:.2f}% | שנתי: {fmt_ils(sub['cost_ils'].sum())}",
                   font=dict(size=14, color=NAVY), x=0.5),
        height=max(380, 200 + n * 15),
        margin=margins_grouped_bar(n),
        showlegend=False,
    )
    fig.update_xaxes(tickangle=-40, tickfont=dict(size=9), automargin=True)
    fig.update_yaxes(gridcolor="#E5E7EB", automargin=True)
    return fig


# ── 9a. Concentration ─────────────────────────────────────────────────────────

def chart_concentration(m: PortfolioMetrics) -> go.Figure:
    df = m.by_manager
    if df.empty:
        return go.Figure()

    conc = m.concentration
    df = df.copy().sort_values("משקל %", ascending=False)
    df["lbl"] = df["מנהל"].apply(label)
    colors = [RED if w > 30 else BLUE for w in df["משקל %"]]

    fig = go.Figure(go.Bar(
        x=df["lbl"], y=df["משקל %"],
        marker_color=colors,
        text=df["משקל %"].map(lambda v: f"{v:.1f}%"),
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>%{y:.1f}%<extra></extra>",
    ))
    fig.add_hline(y=30, line_dash="dash", line_color=AMBER,
                  annotation_text="30% — סף ריכוז",
                  annotation_position="top right",
                  annotation_font=dict(size=10))
    apply(fig, f"ריכוז מנהלים — HHI: {conc.hhi_managers:.0f} ({conc.hhi_label})",
          height=360, margin=margins(l=30, r=60, t=55, b=100), show_legend=False)
    fig.update_xaxes(tickangle=-30, tickfont=dict(size=10), automargin=True)
    fig.update_yaxes(ticksuffix="%")
    return fig


# ── 9b. Sharpe comparison ────────────────────────────────────────────────────

def chart_sharpe(df: pd.DataFrame) -> go.Figure:
    active = df[~df.get("excluded", pd.Series([False]*len(df))).astype(bool)]
    if "sharpe" not in active.columns:
        return go.Figure()
    sub = active[active["sharpe"].notna()].copy()
    if sub.empty:
        return go.Figure()

    sub["lbl"] = (sub["provider"] + " | " + sub.get("product_name", sub["provider"]))\
                 .apply(lambda s: s[:30] + "…" if len(s) > 32 else s)
    sub = sub.sort_values("sharpe", ascending=True)

    colors = [GREEN if v > 0.6 else AMBER if v > 0.3 else RED for v in sub["sharpe"]]
    fig = go.Figure(go.Bar(
        x=sub["sharpe"], y=sub["lbl"],
        orientation="h",
        marker_color=colors,
        text=sub["sharpe"].map(lambda v: f"{v:.2f}"),
        textposition="outside",
        hovertemplate="<b>%{y}</b><br>שארפ: %{x:.2f}<extra></extra>",
    ))
    fig.add_vline(x=0.5, line_dash="dash", line_color=SLATE,
                  annotation_text="0.5", annotation_position="top right",
                  annotation_font=dict(size=10))
    apply(fig, "השוואת שארפ",
          height=max(300, 60 + 40 * len(sub)),
          margin=margins_hbar(len(sub)),
          show_legend=False)
    return fig


# ── 9c. Radar ─────────────────────────────────────────────────────────────────

def chart_radar(m: PortfolioMetrics) -> go.Figure:
    a = m.allocation
    cats = ["מניות", 'חו"ל', 'מט"ח', "לא-סחיר"]
    vals = [a.equity_pct or 0, a.foreign_pct or 0,
            a.fx_pct or 0,     a.illiquid_pct or 0]
    cats_c = cats + [cats[0]]; vals_c = vals + [vals[0]]

    fig = go.Figure(go.Scatterpolar(
        r=vals_c, theta=cats_c, fill="toself",
        fillcolor=f"rgba(58,122,254,0.15)",
        line=dict(color=BLUE, width=2.5),
        marker=dict(size=7, color=BLUE),
        hovertemplate="%{theta}: %{r:.1f}%<extra></extra>",
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        title=dict(text="מפת נכסים — Radar", font=dict(size=14, color=NAVY), x=0.5),
        polar=dict(radialaxis=dict(visible=True, range=[0, 100],
                                   ticksuffix="%", gridcolor="#E5E7EB")),
        showlegend=False, height=340,
        margin=dict(l=20, r=20, t=50, b=20),
    )
    return fig
