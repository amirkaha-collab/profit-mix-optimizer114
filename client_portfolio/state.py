# -*- coding: utf-8 -*-
"""
client_portfolio/state.py
──────────────────────────
Single source of truth for portfolio state.

All session-state keys are prefixed "cps_" (client portfolio state).
No other module should read/write portfolio state directly.

Public API
──────────
    get_df(st)                   -> pd.DataFrame  (canonical holdings)
    set_df(st, df)               -> None
    get_metrics(st)              -> PortfolioMetrics (cached)
    invalidate(st)               -> None           (force metrics recompute)
    merge_from_clearinghouse(st, raw_list, df_long, product_type) -> int
    update_cost(st, uid, value)  -> None
    update_holding(st, uid, patch_dict) -> None
    delete_holding(st, uid)      -> None
    clear_all(st)                -> None
    add_holding(st, holding)     -> None
"""
from __future__ import annotations

import uuid
from typing import Any

import numpy as np
import pandas as pd

_KEY_DF      = "cps_df"        # pd.DataFrame
_KEY_METRICS = "cps_metrics"   # PortfolioMetrics | None

# ── Schema ─────────────────────────────────────────────────────────────────────
# Every holding row must have these columns.
REQUIRED_COLS = [
    "uid", "provider", "product_name", "track", "product_type",
    "amount",
    "equity_pct", "foreign_pct", "fx_pct", "illiquid_pct", "sharpe",
    "annual_cost_pct",
    "notes",
    "source_type",       # "imported" | "manual"
    "allocation_source", # "imported" | "auto_filled" | "manual" | "missing"
    "locked", "excluded",
]

NUMERIC_COLS = ["amount", "equity_pct", "foreign_pct", "fx_pct",
                "illiquid_pct", "sharpe", "annual_cost_pct"]

ALLOC_COLS = ["equity_pct", "foreign_pct", "fx_pct", "illiquid_pct"]


def _new_uid() -> str:
    return uuid.uuid4().hex[:12]


def _coerce_df(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure all required columns exist and numeric cols are numeric."""
    df = df.copy()
    for col in REQUIRED_COLS:
        if col not in df.columns:
            if col in NUMERIC_COLS:
                df[col] = float("nan")
            elif col in ("locked", "excluded"):
                df[col] = False
            else:
                df[col] = ""
    for col in NUMERIC_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


# ── Init ───────────────────────────────────────────────────────────────────────

def _init(st) -> None:
    if _KEY_DF not in st.session_state:
        st.session_state[_KEY_DF] = pd.DataFrame(columns=REQUIRED_COLS)
    if _KEY_METRICS not in st.session_state:
        st.session_state[_KEY_METRICS] = None


# ── Public getters ─────────────────────────────────────────────────────────────

def get_df(st) -> pd.DataFrame:
    _init(st)
    return st.session_state[_KEY_DF]


def get_metrics(st):
    """Return cached PortfolioMetrics, computing on first call or after invalidation."""
    _init(st)
    if st.session_state[_KEY_METRICS] is None:
        from client_portfolio.metrics_service import compute_all
        st.session_state[_KEY_METRICS] = compute_all(st.session_state[_KEY_DF])
    return st.session_state[_KEY_METRICS]


def invalidate(st) -> None:
    """Force metrics recompute on next get_metrics() call."""
    _init(st)
    st.session_state[_KEY_METRICS] = None


# ── Public setters ─────────────────────────────────────────────────────────────

def set_df(st, df: pd.DataFrame) -> None:
    st.session_state[_KEY_DF] = _coerce_df(df)
    invalidate(st)


def add_holding(st, holding: dict) -> None:
    _init(st)
    if "uid" not in holding or not holding["uid"]:
        holding["uid"] = _new_uid()
    row = pd.DataFrame([holding])
    existing = st.session_state[_KEY_DF]
    merged = pd.concat([existing, row], ignore_index=True)
    set_df(st, merged)


def update_holding(st, uid: str, patch: dict) -> None:
    df = get_df(st).copy()
    mask = df["uid"] == uid
    if not mask.any():
        return
    for col, val in patch.items():
        df.loc[mask, col] = val
    set_df(st, df)


def delete_holding(st, uid: str) -> None:
    df = get_df(st)
    set_df(st, df[df["uid"] != uid].reset_index(drop=True))


def update_cost(st, uid: str, value: float) -> None:
    update_holding(st, uid, {"annual_cost_pct": value})


def clear_all(st) -> None:
    st.session_state[_KEY_DF] = pd.DataFrame(columns=REQUIRED_COLS)
    invalidate(st)


# ── Import from clearinghouse ──────────────────────────────────────────────────

def merge_from_clearinghouse(
    st,
    raw_list: list[dict],
    df_long: pd.DataFrame,
    product_type: str = "קרנות השתלמות",
) -> int:
    """
    Merge raw clearinghouse records into the canonical state DataFrame.
    Auto-fills allocation from df_long where possible.
    Returns number of new records added.
    """
    _init(st)
    existing = get_df(st)
    existing_keys = set(
        zip(existing["provider"].str.lower(), existing["product_name"].str.lower())
    )

    COL_MAP = {
        "equity_pct":   "stocks",
        "foreign_pct":  "foreign",
        "fx_pct":       "fx",
        "illiquid_pct": "illiquid",
    }

    new_rows = []
    for r in raw_list:
        prov = str(r.get("manager", "")).strip()
        name = str(r.get("fund", "")).strip()
        key  = (prov.lower(), name.lower())
        if key in existing_keys:
            continue

        h = {
            "uid":               _new_uid(),
            "provider":          prov,
            "product_name":      name,
            "track":             str(r.get("track", "")),
            "product_type":      product_type,
            "amount":            float(r.get("amount", 0)),
            "equity_pct":        float("nan"),
            "foreign_pct":       float("nan"),
            "fx_pct":            float("nan"),
            "illiquid_pct":      float("nan"),
            "sharpe":            float("nan"),
            "annual_cost_pct":   float("nan"),
            "notes":             "",
            "source_type":       "imported",
            "allocation_source": "missing",
            "locked":            False,
            "excluded":          False,
        }

        # Auto-fill from df_long
        h = _autofill(h, df_long, COL_MAP)
        new_rows.append(h)
        existing_keys.add(key)

    if not new_rows:
        return 0

    merged = pd.concat([existing, pd.DataFrame(new_rows)], ignore_index=True)
    set_df(st, merged)
    return len(new_rows)


def autofill_one(st, uid: str, df_long: pd.DataFrame) -> bool:
    """Try to auto-fill allocation for one holding. Returns True if filled."""
    df = get_df(st)
    row = df[df["uid"] == uid]
    if row.empty:
        return False
    h = row.iloc[0].to_dict()
    COL_MAP = {"equity_pct": "stocks", "foreign_pct": "foreign",
               "fx_pct": "fx", "illiquid_pct": "illiquid"}
    filled = _autofill(h, df_long, COL_MAP)
    changed = filled.get("allocation_source") != h.get("allocation_source")
    if changed:
        update_holding(st, uid, filled)
    return changed


def autofill_all(st, df_long: pd.DataFrame) -> int:
    """Auto-fill all holdings with allocation_source == 'missing'. Returns count filled."""
    df = get_df(st)
    missing = df[df["allocation_source"] == "missing"]["uid"].tolist()
    count = 0
    for uid in missing:
        if autofill_one(st, uid, df_long):
            count += 1
    return count


# ── Internal ───────────────────────────────────────────────────────────────────

def _autofill(h: dict, df_long: pd.DataFrame, col_map: dict) -> dict:
    if df_long is None or df_long.empty:
        return h
    h = dict(h)
    prov = h.get("provider", "").lower().strip()
    name = h.get("product_name", "").lower().strip()
    track = h.get("track", "").lower().strip()

    match = pd.DataFrame()
    # Strategy 1: exact fund name
    if name and "fund" in df_long.columns:
        m = df_long[df_long["fund"].str.lower().str.strip() == name]
        if not m.empty:
            match = m.head(1)
    # Strategy 2: manager + track
    if match.empty and prov and "manager" in df_long.columns:
        m = df_long[df_long["manager"].str.lower().str.strip() == prov]
        if not m.empty and track:
            mt = m[m["track"].str.lower().str.strip() == track]
            match = mt.head(1) if not mt.empty else m.head(1)
        elif not m.empty:
            match = m.head(1)
    # Strategy 3: fuzzy manager
    if match.empty and prov and "manager" in df_long.columns:
        for word in prov.split():
            if len(word) > 2:
                m = df_long[df_long["manager"].str.lower().str.contains(word, na=False)]
                if not m.empty:
                    match = m.head(1)
                    break

    if match.empty:
        return h

    row = match.iloc[0]
    filled = False
    for pf_col, app_col in col_map.items():
        if app_col in row.index:
            val = row[app_col]
            if not (isinstance(val, float) and np.isnan(val)):
                h[pf_col] = float(val)
                filled = True

    if filled:
        h["allocation_source"] = "auto_filled"

    if "sharpe" in row.index and (isinstance(h.get("sharpe"), float) and np.isnan(h["sharpe"])):
        sv = row["sharpe"]
        if not (isinstance(sv, float) and np.isnan(sv)):
            h["sharpe"] = float(sv)

    return h
