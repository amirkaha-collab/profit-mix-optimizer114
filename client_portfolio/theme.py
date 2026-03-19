# -*- coding: utf-8 -*-
"""
client_portfolio/theme.py
──────────────────────────
Single source of truth for all chart styling.
Import from here — never define colors/margins elsewhere.
"""
from __future__ import annotations

import math
import plotly.graph_objects as go

# ── Colours ───────────────────────────────────────────────────────────────────
NAVY    = "#1F3A5F"
BLUE    = "#3A7AFE"
GREEN   = "#10B981"
AMBER   = "#F59E0B"
RED     = "#EF4444"
PURPLE  = "#8B5CF6"
TEAL    = "#06B6D4"
PINK    = "#EC4899"
SLATE   = "#64748B"
LIGHT   = "#F8FAFC"

# Semantic colour assignments — consistent across every chart
COLOUR = {
    "equity":   BLUE,
    "bonds":    GREEN,
    "foreign":  TEAL,
    "domestic": NAVY,
    "fx":       AMBER,
    "ils":      SLATE,
    "illiquid": RED,
    "annuity":  PURPLE,
    "capital":  TEAL,
    "other":    SLATE,
}

# Multi-series palette (ordered)
PALETTE = [BLUE, GREEN, AMBER, RED, PURPLE, TEAL, PINK,
           "#F97316", "#84CC16", "#6366F1", "#14B8A6", "#FB7185"]

# ── Typography ────────────────────────────────────────────────────────────────
FONT_FAMILY = "Segoe UI, -apple-system, BlinkMacSystemFont, sans-serif"
FONT        = dict(family=FONT_FAMILY, color="#374151", size=12)

# ── Margins ───────────────────────────────────────────────────────────────────
# Base margins — wide enough for Hebrew labels; overridden per-chart if needed.
def margins(l: int = 20, r: int = 20, t: int = 50, b: int = 20) -> dict:
    return dict(l=l, r=r, t=t, b=b)

def margins_hbar(n_items: int = 10) -> dict:
    """Left margin sized for horizontal-bar Hebrew labels."""
    left = min(220, 30 + n_items * 8)
    return dict(l=left, r=50, t=50, b=30)

def margins_grouped_bar(n_groups: int = 5) -> dict:
    """Bottom margin sized for rotated x-axis labels."""
    bottom = min(220, 80 + n_groups * 12)
    return dict(l=30, r=20, t=55, b=bottom)

# ── Legend ─────────────────────────────────────────────────────────────────────
def legend_bottom() -> dict:
    return dict(
        orientation="h", yanchor="top", y=-0.18,
        xanchor="center", x=0.5,
        font=dict(size=11, family=FONT_FAMILY),
        bgcolor="rgba(255,255,255,0.85)",
        bordercolor="#E5E7EB", borderwidth=1,
    )

# ── Base layout ───────────────────────────────────────────────────────────────
BASE_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(248,249,252,1)",
    font=FONT,
    hovermode="closest",
    hoverlabel=dict(bgcolor="#fff", bordercolor="#E5E7EB",
                    font=dict(family=FONT_FAMILY, size=12)),
)

def apply(
    fig: go.Figure,
    title: str = "",
    height: int = 380,
    margin: dict | None = None,
    show_legend: bool = True,
) -> go.Figure:
    """Apply the standard theme to any figure."""
    layout = dict(
        **BASE_LAYOUT,
        title=dict(text=title, font=dict(size=14, color=NAVY, family=FONT_FAMILY), x=0.5),
        height=height,
        margin=margin or margins(),
        showlegend=show_legend,
    )
    if show_legend:
        layout["legend"] = legend_bottom()
    fig.update_layout(**layout)
    fig.update_xaxes(gridcolor="#E5E7EB", automargin=True)
    fig.update_yaxes(gridcolor="#E5E7EB", zeroline=False, automargin=True)
    return fig

def label(text: str) -> str:
    """Truncate long Hebrew labels for axes."""
    return text if len(text) <= 22 else text[:20] + "…"

def fmt_ils(v: float) -> str:
    if math.isnan(v) or v == 0:
        return "—"
    if v >= 1_000_000:
        return f"₪{v/1_000_000:.2f}M"
    if v >= 1_000:
        return f"₪{v/1_000:.0f}K"
    return f"₪{v:.0f}"
