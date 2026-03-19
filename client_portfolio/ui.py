# -*- coding: utf-8 -*-
"""
client_portfolio/ui.py  v2
───────────────────────────
Clean UI that uses:
  - state.py     as single source of truth
  - metrics_service.py  for all calculations (computed once per render)
  - charts.py    for visuals
  - theme.py     for styling constants
"""
from __future__ import annotations

import math
import pandas as pd
import streamlit as st

from client_portfolio import state as S
from client_portfolio.theme import fmt_ils, NAVY

# ── Small helpers ─────────────────────────────────────────────────────────────

def _nan(v) -> bool:
    try:
        return math.isnan(float(v))
    except Exception:
        return v is None

def _pct(v, dec=1) -> str:
    return f"{v:.{dec}f}%" if not _nan(v) else "—"

def _safe_plotly(fig, key: str) -> None:
    try:
        st.plotly_chart(fig, use_container_width=True, key=key)
    except TypeError:
        st.plotly_chart(fig)

def _csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")


# ── KPI strip ──────────────────────────────────────────────────────────────────

def _render_kpis(m) -> None:
    a, q = m.allocation, m.quality
    cols = st.columns(7)
    metrics = [
        ("סך נכסים",        fmt_ils(m.total_amount)),
        ("מוצרים",           str(m.n_products)),
        ("מנהלים",           str(m.n_managers)),
        ("מניות (משוקלל)",   _pct(a.equity_pct)),
        ('חו"ל (משוקלל)',    _pct(a.foreign_pct)),
        ('מט"ח (משוקלל)',    _pct(a.fx_pct)),
        ("לא-סחיר",          _pct(a.illiquid_pct)),
    ]
    for col, (label, val) in zip(cols, metrics):
        col.metric(label, val)


# ── Quality panel ──────────────────────────────────────────────────────────────

def _render_quality_panel(m, df_long) -> None:
    q = m.quality
    color = {"מלא": "#D1FAE5", "חלקי": "#FEF3C7", "חסר": "#FEE2E2"}[q.overall_score]
    icon  = {"מלא": "✅", "חלקי": "⚠️", "חסר": "🔴"}[q.overall_score]

    st.markdown(f"""
<div style='background:{color};border-radius:10px;padding:14px 20px;
direction:rtl;margin-bottom:12px'>
  <span style='font-weight:800;font-size:15px'>{icon} איכות נתונים: {q.overall_score}</span>
  &nbsp;·&nbsp;
  <span style='font-size:13px'>{q.n_complete} מלאים · {q.n_partial} חלקיים · 
  {q.n_missing} חסרים · {q.pct_complete:.0f}% מהשווי מכוסה</span>
</div>
""", unsafe_allow_html=True)

    if q.n_missing > 0:
        if st.button(f"🔄 מלא אוטומטית את {q.n_missing} המוצרים החסרים",
                     key="ui_autofill_all"):
            filled = S.autofill_all(st, df_long)
            st.toast(f"✅ {filled} מוצרים מולאו")
            st.rerun()


# ── Product table ──────────────────────────────────────────────────────────────

def _render_product_table(df: pd.DataFrame, m) -> None:
    active = df[~df["excluded"].astype(bool)]
    if active.empty:
        st.info("אין מוצרים להצגה.")
        return

    total = active["amount"].sum()
    disp  = active.copy()
    disp["משקל %"] = (disp["amount"] / total * 100).round(1) if total > 0 else 0

    rename = {
        "provider": "גוף", "product_name": "מוצר", "track": "מסלול",
        "product_type": "סוג", "amount": "סכום",
        "equity_pct": "מניות %", "foreign_pct": 'חו"ל %',
        "fx_pct": 'מט"ח %', "illiquid_pct": "לא-סחיר %",
        "sharpe": "שארפ", "annual_cost_pct": "דמי ניהול %",
        "allocation_source": "מקור",
    }
    show = [c for c in [
        "גוף","מוצר","מסלול","סוג","סכום","משקל %",
        "מניות %",'חו"ל %','מט"ח %',"לא-סחיר %",
        "שארפ","דמי ניהול %","מקור"
    ] if c in disp.rename(columns=rename).columns]

    st.dataframe(
        disp.rename(columns=rename)[show].reset_index(drop=True),
        use_container_width=True, hide_index=True,
    )


# ── Per-product edit controls ─────────────────────────────────────────────────

def _render_edit_controls(df: pd.DataFrame, df_long) -> None:
    if df.empty:
        return

    for _, row in df.iterrows():
        uid      = row["uid"]
        is_excl  = bool(row.get("excluded", False))
        is_lock  = bool(row.get("locked",   False))
        alloc_src = row.get("allocation_source", "missing")
        is_miss  = (alloc_src == "missing")
        name_label = f"{row.get('provider','')} | {row.get('product_name','')} | {row.get('track','')}"

        prefix = ""
        if is_excl:  prefix += "🚫 "
        if is_lock:  prefix += "🔒 "
        if is_miss:  prefix += "🔴 "

        with st.expander(f"{prefix}{name_label}", expanded=False):
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                new_lock = st.checkbox("🔒 נעול (what-if)", value=is_lock, key=f"lck_{uid}")
                if new_lock != is_lock:
                    S.update_holding(st, uid, {"locked": new_lock}); st.rerun()
            with c2:
                new_excl = st.checkbox("🚫 החרג", value=is_excl, key=f"excl_{uid}")
                if new_excl != is_excl:
                    S.update_holding(st, uid, {"excluded": new_excl}); st.rerun()
            with c3:
                if st.button("🔄 מלא אוטו׳", key=f"auto_{uid}"):
                    if S.autofill_one(st, uid, df_long):
                        st.toast("✅ מולא!"); st.rerun()
                    else:
                        st.toast("לא נמצא נתון להשלמה")
            with c4:
                if st.button("🗑️ מחק", key=f"del_{uid}"):
                    S.delete_holding(st, uid); st.rerun()

            # Allocation edit
            if is_miss or st.session_state.get(f"edit_{uid}", False):
                st.markdown("**השלם תמהיל:**")
                a1, a2, a3, a4 = st.columns(4)
                eq  = a1.number_input("מניות %",    0.0, 100.0, float(row.get("equity_pct")   or 0), key=f"eq_{uid}")
                fo  = a2.number_input('חו"ל %',     0.0, 100.0, float(row.get("foreign_pct")  or 0), key=f"fo_{uid}")
                fx_ = a3.number_input('מט"ח %',     0.0, 100.0, float(row.get("fx_pct")       or 0), key=f"fx_{uid}")
                ill = a4.number_input("לא-סחיר %",  0.0, 100.0, float(row.get("illiquid_pct") or 0), key=f"ill_{uid}")
                if st.button("💾 שמור", key=f"save_{uid}"):
                    S.update_holding(st, uid, {
                        "equity_pct": eq, "foreign_pct": fo,
                        "fx_pct": fx_, "illiquid_pct": ill,
                        "allocation_source": "manual",
                    })
                    st.session_state[f"edit_{uid}"] = False; st.rerun()
            elif alloc_src != "missing":
                if st.button("✏️ ערוך תמהיל", key=f"edbtn_{uid}"):
                    st.session_state[f"edit_{uid}"] = True; st.rerun()

            # Cost input
            cost_val = row.get("annual_cost_pct")
            cost_cur = 0.0 if _nan(cost_val) else float(cost_val)
            new_cost = st.number_input("דמי ניהול שנתיים (%)", 0.0, 5.0, cost_cur,
                                        step=0.01, format="%.2f", key=f"cost_{uid}")
            if abs(new_cost - cost_cur) > 0.001:
                S.update_cost(st, uid, new_cost); st.rerun()


# ── Add product form ──────────────────────────────────────────────────────────

PRODUCT_TYPES = ["קרנות השתלמות","פוליסות חיסכון","קרנות פנסיה",
                  "קופות גמל","גמל להשקעה","אחר"]

def _render_add_form(df_long) -> None:
    with st.expander("➕ הוסף מוצר ידנית", expanded=False):
        r1c1, r1c2, r1c3 = st.columns(3)
        ptype = r1c1.selectbox("סוג מוצר", PRODUCT_TYPES, key="add_type")
        prov  = r1c2.text_input("גוף מנהל", key="add_prov", placeholder="הראל, מגדל...")
        name  = r1c3.text_input("שם מוצר",  key="add_name", placeholder="שם הקרן...")
        r2c1, r2c2, r2c3 = st.columns(3)
        track  = r2c1.text_input("מסלול", key="add_track")
        amount = r2c2.number_input("סכום (₪)", 0.0, step=1000.0, key="add_amount")
        notes  = r2c3.text_input("הערות", key="add_notes")

        # Smart auto-fill preview
        if prov or name:
            tmp = {
                "uid": "preview", "provider": prov, "product_name": name or prov,
                "track": track, "product_type": ptype, "amount": float(amount),
                "equity_pct": float("nan"), "foreign_pct": float("nan"),
                "fx_pct": float("nan"), "illiquid_pct": float("nan"),
                "sharpe": float("nan"), "annual_cost_pct": float("nan"),
                "notes": notes, "source_type": "manual",
                "allocation_source": "missing", "locked": False, "excluded": False,
            }
            from client_portfolio.state import _autofill
            COL_MAP = {"equity_pct":"stocks","foreign_pct":"foreign","fx_pct":"fx","illiquid_pct":"illiquid"}
            filled = _autofill(tmp, df_long, COL_MAP)
            if filled.get("allocation_source") == "auto_filled":
                st.success(
                    f"💡 נמצאו נתונים אוטומטיים: "
                    f"מניות {_pct(filled.get('equity_pct'))} | "
                    f'חו"ל {_pct(filled.get("foreign_pct"))} | '
                    f'מט"ח {_pct(filled.get("fx_pct"))} | '
                    f"לא-סחיר {_pct(filled.get('illiquid_pct'))}"
                )

        st.markdown("**תמהיל (אם לא מולא אוטומטית):**")
        ac1, ac2, ac3, ac4, ac5 = st.columns(5)
        eq  = ac1.number_input("מניות %",    0.0, 100.0, 0.0, key="add_eq")
        fo  = ac2.number_input('חו"ל %',     0.0, 100.0, 0.0, key="add_fo")
        fx_ = ac3.number_input('מט"ח %',     0.0, 100.0, 0.0, key="add_fx")
        ill = ac4.number_input("לא-סחיר %",  0.0, 100.0, 0.0, key="add_ill")
        sh  = ac5.number_input("שארפ",        0.0,  5.0,  0.0, step=0.01, key="add_sh")

        if st.button("➕ הוסף לפורטפוליו", key="add_submit", type="primary"):
            if not prov and not name:
                st.error("יש למלא שם גוף או מוצר."); return
            if amount <= 0:
                st.error("יש להזין סכום חיובי."); return

            from client_portfolio.state import _new_uid, _autofill
            h = {
                "uid": _new_uid(), "provider": prov, "product_name": name or prov,
                "track": track, "product_type": ptype, "amount": float(amount),
                "equity_pct": eq or float("nan"), "foreign_pct": fo or float("nan"),
                "fx_pct": fx_ or float("nan"), "illiquid_pct": ill or float("nan"),
                "sharpe": sh or float("nan"), "annual_cost_pct": float("nan"),
                "notes": notes, "source_type": "manual",
                "allocation_source": "manual" if any([eq, fo, fx_, ill]) else "missing",
                "locked": False, "excluded": False,
            }
            COL_MAP = {"equity_pct":"stocks","foreign_pct":"foreign","fx_pct":"fx","illiquid_pct":"illiquid"}
            h = _autofill(h, df_long, COL_MAP)
            S.add_holding(st, h)
            st.success(f"✅ {h['product_name']} נוסף"); st.rerun()


# ── What-If ───────────────────────────────────────────────────────────────────

def _render_whatif(df: pd.DataFrame, m) -> None:
    active  = df[~df["excluded"].astype(bool)]
    locked  = active[active["locked"].astype(bool)]
    free    = active[~active["locked"].astype(bool)]

    st.markdown(f"**{len(active)} מוצרים פעילים — {len(locked)} נעולים · {len(free)} פנויים לאופטימיזציה**")
    if not locked.empty:
        st.caption("מוצרים נעולים לא ישתנו באופטימיזציה:")
        st.dataframe(locked[["provider","product_name","track","amount"]].rename(columns={
            "provider":"גוף","product_name":"מוצר","track":"מסלול","amount":"סכום"
        }), use_container_width=True, hide_index=True)

    if st.button("🚀 שלח כבסיס לאופטימיזציה", key="whatif_send", type="primary"):
        a = m.allocation
        baseline = {
            "stocks":   a.equity_pct   or 0,
            "foreign":  a.foreign_pct  or 0,
            "fx":       a.fx_pct       or 0,
            "illiquid": a.illiquid_pct or 0,
            "sharpe":   a.sharpe       or 0,
            "service":  0,
        }
        st.session_state["portfolio_baseline"] = baseline
        st.session_state["portfolio_total"]    = m.total_amount
        st.session_state["portfolio_managers"] = df["provider"].unique().tolist()
        if "targets" in st.session_state:
            if baseline["stocks"]:   st.session_state["targets"]["stocks"]   = round(baseline["stocks"], 1)
            if baseline["foreign"]:  st.session_state["targets"]["foreign"]  = round(baseline["foreign"], 1)
            if baseline["fx"]:       st.session_state["targets"]["fx"]       = round(baseline["fx"], 1)
            if baseline["illiquid"]: st.session_state["targets"]["illiquid"] = round(baseline["illiquid"], 1)
        st.success("✅ הבסיס נשמר. גלול למעלה לאופטימיזציה.")


# ── Export ────────────────────────────────────────────────────────────────────

def _render_exports(df: pd.DataFrame, m, client_name: str) -> None:
    from client_portfolio.report_builder import (
        build_html_report, build_notebook, build_notebooklm_package
    )
    totals_dict = {
        "total": m.total_amount, "n_products": m.n_products, "n_managers": m.n_managers,
        "equity":   m.allocation.equity_pct,   "foreign": m.allocation.foreign_pct,
        "fx":       m.allocation.fx_pct,       "illiquid": m.allocation.illiquid_pct,
        "cost":     m.allocation.cost_pct,
    }

    # Generate once
    html_b = build_html_report(df, client_name, totals_dict)
    nb_b   = build_notebook(df, client_name, totals_dict)
    nlm_b  = build_notebooklm_package(df, client_name, totals_dict)
    csv_b  = _csv_bytes(df)
    fname  = client_name or "client"

    dc1, dc2, dc3, dc4 = st.columns(4)
    with dc1:
        st.markdown("**📄 דוח HTML**")
        st.caption("מעוצב, מוכן להדפסה")
        st.download_button("📄 הורד", html_b, f"portfolio_{fname}.html",
                           "text/html", key="dl_html",
                           use_container_width=True, type="primary")
    with dc2:
        st.markdown("**📓 Jupyter Notebook**")
        st.caption("Run All ב-Colab → מצגת")
        st.download_button("📓 הורד", nb_b, f"portfolio_{fname}.ipynb",
                           "application/json", key="dl_nb",
                           use_container_width=True, type="primary")
    with dc3:
        st.markdown("**🔬 NotebookLM**")
        st.caption("נתונים + פרומפט מצגת")
        st.download_button("🔬 הורד", nlm_b, f"notebooklm_{fname}.md",
                           "text/markdown", key="dl_nlm",
                           use_container_width=True, type="primary")
    with dc4:
        st.markdown("**⬇️ CSV גולמי**")
        st.caption("לעיבוד עצמאי")
        st.download_button("⬇️ הורד", csv_b, "portfolio.csv",
                           "text/csv", key="dl_csv", use_container_width=True)

    st.markdown("""
---
**🔬 NotebookLM:** העלה קובץ `.md` → `Add source` → שאל כל שאלה על התיק  
**📓 Colab:** `File → Upload notebook` → `Runtime → Run all`
""")


# ── Main page ─────────────────────────────────────────────────────────────────

def render_client_portfolio_page(df_long: pd.DataFrame) -> None:
    """Full-page client portfolio — called when product_type == 'תיק לקוח'."""

    st.markdown(f"""
<div style='background:linear-gradient(135deg,#1F3A5F 0%,#3A7AFE 100%);
border-radius:14px;padding:20px 28px;margin-bottom:18px;color:#fff'>
  <div style='font-size:22px;font-weight:900'>📊 ניתוח תיק לקוח</div>
  <div style='font-size:13px;opacity:0.8;margin-top:4px'>
    העלה דוח מסלקה · השלם נתונים · קבל ניתוח · הפק דוח מקצועי
  </div>
</div>
""", unsafe_allow_html=True)

    df = S.get_df(st)

    # ── Step 1: Import ────────────────────────────────────────────────────
    n = len(df)
    with st.expander(f"{'✅' if n>0 else '📂'} שלב 1 — ייבוא פורטפוליו ({n} מוצרים)",
                     expanded=n == 0):

        # File upload with inline parser
        uploaded = st.file_uploader("העלה דוח מסלקה (XLSX/XLS)", type=["xlsx","xls"],
                                    key="page_upload", label_visibility="visible")
        if uploaded:
            raw_bytes = uploaded.read()
            try:
                import io, math as _math, numpy as _np
                import pandas as _pd
                AMOUNT_A  = ["יתרה","ערך","סכום","balance","amount","שווי"]
                FUND_A    = ["שם הקרן","קרן","שם מוצר","fund","product","שם הקופה"]
                MANAGER_A = ["מנהל","גוף מנהל","manager","provider"]
                TRACK_A   = ["מסלול","track","שם מסלול"]
                def _tof(v):
                    try: return float(str(v).replace(",","").replace("₪","").strip())
                    except: return float("nan")
                xls = _pd.ExcelFile(io.BytesIO(raw_bytes))
                recs = []
                for sheet in xls.sheet_names:
                    try: dfs = _pd.read_excel(xls, sheet_name=sheet, header=None)
                    except: continue
                    if dfs.empty or dfs.shape[0] < 2: continue
                    hidx = None
                    for i in range(min(10, len(dfs))):
                        rv = [str(v).strip().lower() for v in dfs.iloc[i].tolist()]
                        if sum(1 for v in rv if any(a.lower() in v for a in AMOUNT_A+FUND_A+MANAGER_A)) >= 2:
                            hidx = i; break
                    if hidx is None: continue
                    dc = dfs.iloc[hidx:].copy().reset_index(drop=True)
                    dc.columns = [str(c).strip() for c in dc.iloc[0].tolist()]
                    dc = dc.iloc[1:].reset_index(drop=True)
                    def _fc(aliases):
                        for c in dc.columns:
                            if any(a.lower() in c.lower() for a in aliases): return c
                        return None
                    fc = _fc(FUND_A); mc = _fc(MANAGER_A); ac = _fc(AMOUNT_A); tc = _fc(TRACK_A)
                    if not (fc or mc) or not ac: continue
                    for _, row in dc.iterrows():
                        fn = str(row.get(fc,"") or "").strip() if fc else ""
                        mn = str(row.get(mc,"") or "").strip() if mc else ""
                        tn = str(row.get(tc,"") or "").strip() if tc else ""
                        av = _tof(row.get(ac, _np.nan))
                        if not fn and not mn: continue
                        if _math.isnan(av) or av <= 0: continue
                        recs.append({"manager": mn or fn, "fund": fn or mn,
                                     "track": tn, "amount": av})
                if recs:
                    # Store in old key too for backwards compat
                    st.session_state["portfolio_holdings"] = recs
                    st.success(f"✅ {len(recs)} קרנות זוהו בקובץ — מייבא...")
                    added = S.merge_from_clearinghouse(st, recs, df_long, "קרנות השתלמות")
                    if added:
                        st.success(f"✅ {added} מוצרים נוספו לתיק")
                        st.rerun()
                else:
                    st.error("לא נמצאו נתונים תקינים בקובץ.")
            except Exception as _e:
                st.error(f"שגיאה: {_e}")

        # Manual add
        _render_add_form(df_long)

    if df.empty:
        st.info("💡 העלה דוח מסלקה או הוסף מוצרים ידנית.")
        return

    # ── Compute metrics ONCE ──────────────────────────────────────────────
    m = S.get_metrics(st)

    # ── Client name ───────────────────────────────────────────────────────
    col_name, _ = st.columns([2, 5])
    with col_name:
        cname = st.text_input("שם הלקוח", key="cps_client_name",
                              value=st.session_state.get("cp_client_name",""),
                              placeholder="ישראל ישראלי")
        st.session_state["cp_client_name"] = cname

    # ── KPI strip ─────────────────────────────────────────────────────────
    _render_kpis(m)
    _render_quality_panel(m, df_long)

    st.markdown("---")

    # ── Export banner — always prominent ──────────────────────────────────
    st.markdown("""
<div style='background:linear-gradient(135deg,#EFF6FF,#DBEAFE);border:1.5px solid #3A7AFE;
border-radius:12px;padding:14px 20px;margin-bottom:14px;direction:rtl'>
  <span style='font-weight:800;color:#1F3A5F;font-size:15px'>📥 הפקת דוחות</span>
  &nbsp;·&nbsp;
  <span style='font-size:12px;color:#3A7AFE'>דוח HTML · Jupyter Notebook · NotebookLM · CSV</span>
</div>
""", unsafe_allow_html=True)
    _render_exports(df, m, cname)

    st.markdown("---")

    # ── Analysis tabs ─────────────────────────────────────────────────────
    t1, t2, t3, t4 = st.tabs(["📈 גרפים", "📋 טבלה", "✏️ עריכה", "🔀 What-If"])

    with t1:
        from client_portfolio.charts import (
            chart_executive_summary, chart_by_manager, chart_stocks_bonds,
            chart_foreign_domestic, chart_fx_ils, chart_asset_breakdown,
            chart_annuity_capital, chart_costs, chart_concentration,
            chart_sharpe, chart_radar,
        )

        # Executive summary — 4 mini donuts
        st.markdown("#### סיכום מהיר")
        _safe_plotly(chart_executive_summary(m), "exec_sum")

        # Manager + stocks/bonds side by side
        c1, c2 = st.columns(2)
        with c1:
            _safe_plotly(chart_by_manager(m), "by_mgr")
        with c2:
            _safe_plotly(chart_stocks_bonds(m), "stk_bond")

        # Foreign/domestic + FX/ILS side by side
        c3, c4 = st.columns(2)
        with c3:
            _safe_plotly(chart_foreign_domestic(m), "fo_dom")
        with c4:
            _safe_plotly(chart_fx_ils(m), "fx_ils")

        # Annuity vs capital + radar side by side
        c5, c6 = st.columns(2)
        with c5:
            _safe_plotly(chart_annuity_capital(m), "ann_cap")
        with c6:
            _safe_plotly(chart_radar(m), "radar")

        # Full-width: asset breakdown per product
        st.markdown("---")
        _safe_plotly(chart_asset_breakdown(df), "asset_bk")

        # Concentration + sharpe side by side
        c7, c8 = st.columns(2)
        with c7:
            _safe_plotly(chart_concentration(m), "conc")
        with c8:
            fig_sh = chart_sharpe(df)
            if fig_sh.data:
                _safe_plotly(fig_sh, "sharpe_cmp")

        # Costs (if data entered)
        fig_cost = chart_costs(df)
        if fig_cost.data:
            st.markdown("---")
            _safe_plotly(fig_cost, "costs")

    with t2:
        _render_product_table(df, m)
        st.download_button("⬇️ CSV", data=_csv_bytes(df),
                           file_name="portfolio.csv", mime="text/csv",
                           key="tbl_dl")

    with t3:
        _render_edit_controls(df, df_long)
        st.markdown("---")
        if st.button("🗑️ נקה תיק כולו", key="clear_all"):
            S.clear_all(st); st.rerun()

    with t4:
        _render_whatif(df, m)


# ── Legacy expander mode (kept for backwards compat) ──────────────────────────

def render_client_portfolio(df_long: pd.DataFrame, product_type: str) -> None:
    """Legacy expander — used when portfolio_analysis module calls this."""
    with st.expander("📊 ניתוח תיק לקוח", expanded=False):
        holdings = st.session_state.get("pf_holdings", [])
        if not holdings:
            st.info("עבור לטאב 📊 ניתוח תיק לקוח להזנת נתונים.")
            return
        # Sync pf_holdings → cps_df if cps_df is empty
        if S.get_df(st).empty and holdings:
            import pandas as _pd
            S.set_df(st, _pd.DataFrame(holdings))
        render_client_portfolio_page(df_long)
