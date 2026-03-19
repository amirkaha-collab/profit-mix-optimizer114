# -*- coding: utf-8 -*-
"""
client_portfolio/metrics_service.py
─────────────────────────────────────
Single source of truth for ALL portfolio calculations.
Every KPI card, chart, table and export uses this module.

Public API
──────────
    compute_all(df) -> PortfolioMetrics
    PortfolioMetrics is a dataclass — attribute access, never re-computed.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

# ── Helpers ───────────────────────────────────────────────────────────────────

def _nan(v) -> bool:
    try:
        return math.isnan(float(v))
    except Exception:
        return v is None

def _wsum(df: pd.DataFrame, col: str) -> float:
    """Weighted average of `col` using `amount` as weight. NaN if no data."""
    if col not in df.columns:
        return float("nan")
    sub = df[df[col].notna()].copy()
    if sub.empty:
        return float("nan")
    t = sub["amount"].sum()
    return float((sub[col] * sub["amount"]).sum() / t) if t > 0 else float("nan")

def _coverage(df: pd.DataFrame, col: str) -> float:
    """% of total amount that has a value for `col`. 0-100."""
    if col not in df.columns or df.empty:
        return 0.0
    total = df["amount"].sum()
    if total <= 0:
        return 0.0
    covered = df[df[col].notna()]["amount"].sum()
    return round(covered / total * 100, 1)

# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class AllocationMetrics:
    equity_pct:   float = float("nan")   # weighted avg
    bonds_pct:    float = float("nan")   # derived: 100 - equity - illiquid - fx
    foreign_pct:  float = float("nan")
    domestic_pct: float = float("nan")   # derived: 100 - foreign
    fx_pct:       float = float("nan")
    ils_pct:      float = float("nan")   # derived: 100 - fx
    illiquid_pct: float = float("nan")
    sharpe:       float = float("nan")
    cost_pct:     float = float("nan")   # annual_cost_pct weighted avg

    # Coverage % for each metric
    equity_cov:   float = 0.0
    foreign_cov:  float = 0.0
    fx_cov:       float = 0.0
    illiquid_cov: float = 0.0
    cost_cov:     float = 0.0

@dataclass
class ConcentrationMetrics:
    hhi_managers: float = 0.0       # 0-10000
    hhi_label:    str   = ""        # "פיזור טוב" | "ריכוז בינוני" | "ריכוז גבוה"
    top1_pct:     float = 0.0
    top3_pct:     float = 0.0
    top5_pct:     float = 0.0
    dominant_manager: str = ""

@dataclass
class QualityMetrics:
    n_total:      int   = 0
    n_complete:   int   = 0    # all 4 alloc cols present
    n_partial:    int   = 0    # some alloc cols present
    n_missing:    int   = 0    # no alloc cols
    n_manual:     int   = 0
    n_auto:       int   = 0
    n_imported:   int   = 0
    pct_complete:  float = 0.0  # % of total amount with complete alloc
    pct_missing:   float = 0.0
    overall_score: str  = ""   # "מלא" | "חלקי" | "חסר"

@dataclass
class PortfolioMetrics:
    # Totals
    total_amount:  float = 0.0
    n_products:    int   = 0
    n_managers:    int   = 0
    n_product_types: int = 0

    allocation:    AllocationMetrics    = field(default_factory=AllocationMetrics)
    concentration: ConcentrationMetrics = field(default_factory=ConcentrationMetrics)
    quality:       QualityMetrics       = field(default_factory=QualityMetrics)

    # By-manager breakdown (sorted by amount desc)
    by_manager: pd.DataFrame = field(default_factory=pd.DataFrame)
    # By-product-type breakdown
    by_type:    pd.DataFrame = field(default_factory=pd.DataFrame)


# ── Alloc columns ─────────────────────────────────────────────────────────────
_ALLOC_COLS = ["equity_pct", "foreign_pct", "fx_pct", "illiquid_pct"]
_ANNUITY_TYPES = {"קרנות פנסיה"}
_CAPITAL_TYPES = {"קרנות השתלמות", "פוליסות חיסכון", "קופות גמל", "גמל להשקעה"}


# ── Main compute function ─────────────────────────────────────────────────────

def compute_all(df: pd.DataFrame) -> PortfolioMetrics:
    """
    Compute every metric from the canonical holdings DataFrame.
    Call once; pass the result to all charts and UI components.
    """
    m = PortfolioMetrics()
    if df is None or df.empty:
        return m

    # Work only on non-excluded rows
    active = df[~df.get("excluded", pd.Series([False] * len(df))).astype(bool)].copy()
    if active.empty:
        return m

    # Ensure numeric
    for col in _ALLOC_COLS + ["sharpe", "amount"]:
        if col in active.columns:
            active[col] = pd.to_numeric(active[col], errors="coerce")
    if "annual_cost_pct" in active.columns:
        active["annual_cost_pct"] = pd.to_numeric(active["annual_cost_pct"], errors="coerce")

    total = float(active["amount"].sum())
    m.total_amount   = total
    m.n_products     = len(active)
    m.n_managers     = active["provider"].nunique() if "provider" in active.columns else 0
    m.n_product_types = active["product_type"].nunique() if "product_type" in active.columns else 0

    # ── Allocation ────────────────────────────────────────────────────────
    eq  = _wsum(active, "equity_pct")
    fo  = _wsum(active, "foreign_pct")
    fx  = _wsum(active, "fx_pct")
    ill = _wsum(active, "illiquid_pct")
    sh  = _wsum(active, "sharpe")
    co  = _wsum(active, "annual_cost_pct") if "annual_cost_pct" in active.columns else float("nan")

    # Derived
    bonds = max(0.0, 100 - (eq or 0) - (ill or 0) - (fx or 0)) if not _nan(eq) else float("nan")
    dom   = max(0.0, 100 - (fo or 0)) if not _nan(fo) else float("nan")
    ils   = max(0.0, 100 - (fx or 0)) if not _nan(fx) else float("nan")

    m.allocation = AllocationMetrics(
        equity_pct=round(eq, 2)  if not _nan(eq)  else float("nan"),
        bonds_pct =round(bonds, 2) if not _nan(bonds) else float("nan"),
        foreign_pct=round(fo, 2) if not _nan(fo)  else float("nan"),
        domestic_pct=round(dom, 2) if not _nan(dom) else float("nan"),
        fx_pct    =round(fx, 2)  if not _nan(fx)  else float("nan"),
        ils_pct   =round(ils, 2) if not _nan(ils) else float("nan"),
        illiquid_pct=round(ill, 2) if not _nan(ill) else float("nan"),
        sharpe    =round(sh, 3)  if not _nan(sh)  else float("nan"),
        cost_pct  =round(co, 3)  if not _nan(co)  else float("nan"),
        equity_cov   =_coverage(active, "equity_pct"),
        foreign_cov  =_coverage(active, "foreign_pct"),
        fx_cov       =_coverage(active, "fx_pct"),
        illiquid_cov =_coverage(active, "illiquid_pct"),
        cost_cov     =_coverage(active, "annual_cost_pct") if "annual_cost_pct" in active.columns else 0.0,
    )

    # ── Concentration ─────────────────────────────────────────────────────
    if "provider" in active.columns and total > 0:
        mgr = active.groupby("provider")["amount"].sum().reset_index()
        mgr["w"] = mgr["amount"] / total * 100
        mgr = mgr.sort_values("w", ascending=False).reset_index(drop=True)

        hhi = float(((mgr["w"] / 100) ** 2).sum() * 10000)
        label = "ריכוז גבוה" if hhi > 2500 else "ריכוז בינוני" if hhi > 1500 else "פיזור טוב"

        m.concentration = ConcentrationMetrics(
            hhi_managers    = round(hhi, 0),
            hhi_label       = label,
            top1_pct        = round(float(mgr.iloc[0]["w"]), 1) if len(mgr) >= 1 else 0,
            top3_pct        = round(float(mgr.head(3)["w"].sum()), 1),
            top5_pct        = round(float(mgr.head(5)["w"].sum()), 1),
            dominant_manager= str(mgr.iloc[0]["provider"]) if len(mgr) >= 1 else "",
        )
        m.by_manager = mgr.rename(columns={"provider": "מנהל", "amount": "סכום", "w": "משקל %"})

    # ── Quality ───────────────────────────────────────────────────────────
    def _has_alloc(row) -> bool:
        return all(
            col in row.index and not (isinstance(row[col], float) and _nan(row[col]))
            for col in _ALLOC_COLS
        )
    def _has_any_alloc(row) -> bool:
        return any(
            col in row.index and not (isinstance(row[col], float) and _nan(row[col]))
            for col in _ALLOC_COLS
        )

    n_complete = int(active.apply(_has_alloc, axis=1).sum())
    n_partial  = int(active.apply(
        lambda r: _has_any_alloc(r) and not _has_alloc(r), axis=1
    ).sum())
    n_missing  = m.n_products - n_complete - n_partial

    alloc_src = active.get("allocation_source", pd.Series(["?"] * len(active)))
    n_manual   = int((alloc_src == "manual").sum())
    n_auto     = int((alloc_src == "auto_filled").sum())
    n_imported = int((alloc_src == "imported").sum())

    # % of total amount with complete alloc
    complete_mask = active.apply(_has_alloc, axis=1)
    pct_complete  = float(active[complete_mask]["amount"].sum() / total * 100) if total > 0 else 0.0
    pct_missing   = float(active[~complete_mask]["amount"].sum() / total * 100) if total > 0 else 0.0

    score = "מלא" if pct_complete >= 90 else "חלקי" if pct_complete >= 50 else "חסר"

    m.quality = QualityMetrics(
        n_total=m.n_products, n_complete=n_complete,
        n_partial=n_partial,  n_missing=n_missing,
        n_manual=n_manual,    n_auto=n_auto, n_imported=n_imported,
        pct_complete=round(pct_complete, 1),
        pct_missing =round(pct_missing, 1),
        overall_score=score,
    )

    # ── By product type ───────────────────────────────────────────────────
    if "product_type" in active.columns and total > 0:
        pt = active.groupby("product_type")["amount"].sum().reset_index()
        pt["w"] = pt["amount"] / total * 100
        pt["category"] = pt["product_type"].apply(
            lambda t: "קצבה" if t in _ANNUITY_TYPES
                      else "הון" if t in _CAPITAL_TYPES else "אחר"
        )
        m.by_type = pt.sort_values("amount", ascending=False).reset_index(drop=True)

    return m
