import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

st.set_page_config(page_title="Portfolio & Vendor Metrics Dashboard", layout="wide", page_icon="📊")

# =================================================================
# THEME / STYLING  (palette matched to reference: FBFBFC / D5DEE7 / 3A414B / 1652A3 / 2F88F5)
# =================================================================
COLOR_BG = "#FBFBFC"
COLOR_MUTED = "#D5DEE7"
COLOR_DARK = "#3A414B"
COLOR_PRIMARY = "#1652A3"
COLOR_ACCENT = "#2F88F5"

COLOR_SPEND = COLOR_PRIMARY   # 1652A3
COLOR_SALES = COLOR_ACCENT    # 2F88F5
COLOR_ACOS = "#0EA5E9"        # sky blue — distinct line color, not near-black
COLOR_ROAS = "#226DCC"        # interpolated mid-blue between primary and accent

GROUP_COLORS = {
    "CBT": COLOR_MUTED,
    "Exclusive": COLOR_ACCENT,
    "Ageing": COLOR_PRIMARY,
    "FBA": "#0B3D91",         # navy blue — clearly blue, not near-black/grey
}

# Cycled blue palette for dynamic group counts (e.g. many brands) — kept clear of
# near-black tones so no bar/pie slice reads as "black".
BRAND_PALETTE = [
    "#2F88F5", "#1652A3", "#0EA5E9", "#226DCC", "#5B9BF7",
    "#0B3D91", "#6FA8F0", "#3D6FA8", "#89A9CF", "#1E6FBF",
    "#4C7FD1", "#38BDF8", "#7CB2F2", "#0369A1", "#60A5FA",
]

def brand_colors(n):
    return [BRAND_PALETTE[i % len(BRAND_PALETTE)] for i in range(n)]

def human_format(num, prefix="", decimals=1):
    """Abbreviate large numbers (1.2K, 3.9M, ...) so labels/axes stay readable."""
    if num is None or pd.isna(num):
        return "-"
    sign = "-" if num < 0 else ""
    num = abs(num)
    if num >= 1_000_000_000:
        val = f"{num / 1_000_000_000:.{decimals}f}B"
    elif num >= 1_000_000:
        val = f"{num / 1_000_000:.{decimals}f}M"
    elif num >= 1_000:
        val = f"{num / 1_000:.{decimals}f}K"
    else:
        val = f"{num:,.0f}"
    return f"{sign}{prefix}{val}"

st.markdown(
    f"""
    <style>
    .stApp {{ background-color: {COLOR_BG}; }}
    h1, h2, h3 {{
        color: {COLOR_DARK};
        font-family: 'Google Sans', 'Segoe UI', sans-serif;
        font-weight: 800 !important;
    }}
    p, li, label, .stMarkdown, .stCaption {{ font-weight: 500; }}
    .stCaption, [data-testid="stCaptionContainer"] {{ font-weight: 600 !important; color: {COLOR_DARK} !important; }}
    .kpi-card {{
        background: #FFFFFF;
        border-radius: 12px;
        padding: 16px 18px 14px 18px;
        box-shadow: 0 1px 3px rgba(58,65,75,0.12), 0 1px 2px rgba(58,65,75,0.08);
        border-top: 5px solid var(--accent);
        text-align: left;
    }}
    .kpi-label {{
        font-size: 13px;
        color: {COLOR_DARK};
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        margin-bottom: 4px;
    }}
    .kpi-value {{
        font-size: 28px;
        font-weight: 800;
        color: {COLOR_DARK};
    }}
    div[data-testid="stDataFrame"] {{ border-radius: 10px; overflow: hidden; border: 1px solid {COLOR_MUTED}; }}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("📊 Portfolio & Vendor PPC Metrics Dashboard")
st.caption("Sponsored Products Advertised Product Report — by Portfolio type and by Brand")

# =================================================================
# Data load (main report)
# =================================================================
# Different Amazon report exports use slightly different column names/
# suffixes (e.g. "Spend" vs "Spend - converted"). These are the accepted
# variants, in priority order, for each canonical field we need.
BASE_REQUIRED_COLS = ["Date", "Portfolio name", "Country", "Impressions", "Clicks"]
SPEND_CANDIDATES = ["Spend - converted", "Spend"]
SALES_CANDIDATES = ["7 Day Total Sales - converted", "7 Day Total Sales"]

def resolve_column(df: pd.DataFrame, candidates: list[str], label: str) -> str:
    lookup = {str(c).strip().lower(): c for c in df.columns}
    for cand in candidates:
        key = cand.strip().lower()
        if key in lookup:
            return lookup[key]
    raise ValueError(f"Missing expected column for {label}: tried {candidates}")

@st.cache_data
def load_data(file) -> pd.DataFrame:
    df = pd.read_excel(file)
    # Normalize column names (some exports have trailing/leading whitespace,
    # e.g. "7 Day Total Sales ")
    df.columns = [str(c).strip() for c in df.columns]

    missing_base = [c for c in BASE_REQUIRED_COLS if c not in df.columns]
    if missing_base:
        raise ValueError(f"Missing expected column(s): {missing_base}")

    spend_col = resolve_column(df, SPEND_CANDIDATES, "Spend")
    sales_col = resolve_column(df, SALES_CANDIDATES, "7 Day Total Sales")

    # Standardize to canonical names used throughout the rest of the app
    df = df.rename(columns={spend_col: "Spend - converted", sales_col: "7 Day Total Sales - converted"})

    df["Date"] = pd.to_datetime(df["Date"])
    return df

uploaded = st.sidebar.file_uploader(
    "Upload Sponsored Products Advertised Product Report (.xlsx)",
    type=["xlsx"],
)

if uploaded is None:
    st.info("👈 Upload the Sponsored Products Advertised Product Report to get started.")
    st.stop()

try:
    df = load_data(uploaded)
except Exception as e:
    st.error(f"Could not read file: {e}")
    st.stop()

# =================================================================
# Portfolio grouping logic
# =================================================================
def classify_portfolio(portfolio):
    """Bucket FBA-prefixed portfolios into CBT / Exclusive / Ageing / FBA (remaining).
    Non-FBA portfolios are excluded (returns None). Vizari portfolios are excluded
    even if FBA-prefixed, per standing business rule."""
    if pd.isna(portfolio):
        return None
    p = str(portfolio).strip()
    pu = p.upper()
    if not pu.startswith("FBA"):
        return None
    if "VIZARI" in pu:
        return None
    if "CBT" in pu:
        return "CBT"
    if "EXCLUSIVE" in pu:
        return "Exclusive"
    if "LTSF" in pu or "AGEING" in pu or "AGING" in pu:
        return "Ageing"
    return "FBA"

df["Group"] = df["Portfolio name"].apply(classify_portfolio)

GROUP_ORDER = ["CBT", "Exclusive", "Ageing", "FBA"]

# =================================================================
# Sidebar controls (shared across tabs)
# =================================================================
countries_available = sorted(df["Country"].dropna().unique().tolist())
default_countries = [c for c in countries_available if c == "United States"] or countries_available

selected_countries = st.sidebar.multiselect(
    "Marketplace / Country",
    options=countries_available,
    default=default_countries,
)

if not selected_countries:
    st.warning("Select at least one country from the sidebar.")
    st.stop()

# =================================================================
# Base filtered dataset (FBA-classified rows, selected countries)
# =================================================================
base = df[df["Country"].isin(selected_countries)].copy()
base = base[base["Group"].notna()]

# Portfolio-name-based Vizari exclusion (above) only catches portfolios literally
# named "Vizari" — but Vizari-branded SKUs can run under ANY FBA portfolio
# (e.g. a generic "FBA_Prime Day" portfolio). So also exclude by SKU brand code
# (VIZA) directly, applied once here so every tab inherits the same clean scope.
VIZARI_SKU_PREFIXES = {"VIZA"}
try:
    _sku_col_check = resolve_column(base, ["Advertised SKU", "SKU"], "Advertised SKU")
    _sku_prefix_check = base[_sku_col_check].astype(str).str.strip().str.upper().str[:4]
    _n_before = len(base)
    base = base[~_sku_prefix_check.isin(VIZARI_SKU_PREFIXES)]
    _n_vizari_dropped = _n_before - len(base)
except ValueError:
    _n_vizari_dropped = 0  # No SKU column in this report; portfolio-name exclusion still applies.

if base.empty:
    st.warning("No FBA-prefixed portfolio data found for the selected country/countries.")
    st.stop()

if _n_vizari_dropped > 0:
    st.sidebar.caption(f"🚫 Excluded {_n_vizari_dropped:,} Vizari-branded (VIZA) SKU row(s) from all tabs.")

# =================================================================
# Generic, reusable metrics-table builder (works for Group or Brand)
# =================================================================
def build_metrics_table(data: pd.DataFrame, group_col: str, order=None) -> pd.DataFrame:
    agg = data.groupby(group_col).agg(
        Impressions=("Impressions", "sum"),
        Clicks=("Clicks", "sum"),
        Spend=("Spend - converted", "sum"),
        Sales=("7 Day Total Sales - converted", "sum"),
    )
    if order is not None:
        agg = agg.reindex(order).fillna(0)

    agg["ACOS %"] = (agg["Spend"] / agg["Sales"].replace(0, np.nan) * 100).round(2)
    agg["ROAS"] = (agg["Sales"] / agg["Spend"].replace(0, np.nan)).round(2)
    agg["CTR %"] = (agg["Clicks"] / agg["Impressions"].replace(0, np.nan) * 100).round(2)
    agg["Spend"] = agg["Spend"].round(2)
    agg["Sales"] = agg["Sales"].round(2)

    return agg[["Impressions", "Clicks", "CTR %", "Spend", "Sales", "ACOS %", "ROAS"]]

def build_totals_row(table: pd.DataFrame) -> pd.DataFrame:
    totals = pd.DataFrame({
        "Impressions": [table["Impressions"].sum()],
        "Clicks": [table["Clicks"].sum()],
        "Spend": [table["Spend"].sum()],
        "Sales": [table["Sales"].sum()],
    }, index=["TOTAL"])
    totals["ACOS %"] = (totals["Spend"] / totals["Sales"] * 100).round(2)
    totals["ROAS"] = (totals["Sales"] / totals["Spend"]).round(2)
    totals["CTR %"] = (totals["Clicks"] / totals["Impressions"] * 100).round(2)
    return totals[["Impressions", "Clicks", "CTR %", "Spend", "Sales", "ACOS %", "ROAS"]]

def show_metrics_table(data: pd.DataFrame, first_col_label: str = "Group", height=None):
    """Interactive, sortable (click any column header) table. Optionally
    height-constrained for a scrollable view when there are many rows."""
    d = data.copy()
    d.index.name = "__key__"
    d = d.reset_index().rename(columns={"__key__": first_col_label})

    fmt = {
        "Impressions": "{:,.0f}",
        "Clicks": "{:,.0f}",
        "CTR %": "{:.2f}%",
        "Spend": "${:,.2f}",
        "Sales": "${:,.2f}",
        "ACOS %": "{:.2f}%",
        "ROAS": "{:.2f}",
    }

    is_total = d[first_col_label] == "TOTAL"
    non_total_idx = d.index[~is_total]

    def highlight_total(row):
        return [f"font-weight:700; background-color:{COLOR_MUTED}" if row[first_col_label] == "TOTAL" else "" for _ in row]

    styled = (
        d.style
        .format(fmt)
        .background_gradient(subset=pd.IndexSlice[non_total_idx, ["ACOS %"]], cmap="Blues", low=0.0, high=0.55)
        .background_gradient(subset=pd.IndexSlice[non_total_idx, ["ROAS"]], cmap="Blues", low=0.0, high=0.55)
        .apply(highlight_total, axis=1)
    )
    kwargs = dict(use_container_width=True, hide_index=True)
    if height is not None:
        kwargs["height"] = height
    st.dataframe(styled, **kwargs)

def bar_chart(labels, values, colors, y_title, value_fmt):
    fig = go.Figure(go.Bar(
        x=labels, y=values,
        marker_color=colors,
        text=[value_fmt(v) for v in values],
        textposition="outside",
        textfont=dict(size=13, color=COLOR_DARK),
    ))
    fig.update_layout(
        template="plotly_white", height=360,
        paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
        margin=dict(l=10, r=10, t=10, b=10),
        yaxis_title=y_title,
        font=dict(size=13, color=COLOR_DARK, family="Segoe UI, sans-serif"),
        yaxis=dict(title_font=dict(size=13, color=COLOR_DARK), tickformat="~s"),
        xaxis=dict(tickangle=-35),
    )
    return fig

def contribution_pie(labels, values, colors, title, value_prefix=""):
    fig = go.Figure(go.Pie(
        labels=labels, values=values,
        marker=dict(colors=colors, line=dict(color="#FFFFFF", width=2)),
        hole=0.4,
        textinfo="label+percent",
        textfont=dict(size=12, color="#FFFFFF"),
        hovertemplate="%{label}: " + value_prefix + "%{value:,.2f} (%{percent})<extra></extra>",
    ))
    fig.update_layout(
        template="plotly_white", height=380,
        paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
        title=dict(text=f"<b>{title}</b>", font=dict(size=14, color=COLOR_DARK)),
        margin=dict(l=10, r=10, t=45, b=10),
        showlegend=False,
        font=dict(size=12, color=COLOR_DARK, family="Segoe UI, sans-serif"),
    )
    return fig

def combo_chart(x, spend, sales, acos, title, x_title, x_type="category", rangeslider=False):
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(x=x, y=spend, name="Spend", marker_color=COLOR_SPEND, opacity=0.9),
        secondary_y=False,
    )
    fig.add_trace(
        go.Bar(x=x, y=sales, name="Sales", marker_color=COLOR_SALES, opacity=0.9),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=x, y=acos, name="ACOS %", mode="lines+markers",
            line=dict(color=COLOR_ACOS, width=3),
            marker=dict(size=6),
        ),
        secondary_y=True,
    )

    fig.update_layout(
        template="plotly_white",
        barmode="group",
        height=460 if rangeslider else 420,
        paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
        title=dict(text=f"<b>{title}</b>", font=dict(size=16, color=COLOR_DARK)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=12, color=COLOR_DARK)),
        margin=dict(l=10, r=10, t=60, b=10),
        hovermode="x unified",
        font=dict(size=13, color=COLOR_DARK, family="Segoe UI, sans-serif"),
    )
    fig.update_xaxes(title_text=f"<b>{x_title}</b>", type=x_type)
    if rangeslider:
        fig.update_xaxes(rangeslider=dict(visible=True, thickness=0.08, bgcolor=COLOR_MUTED))
    fig.update_yaxes(title_text="<b>Amount ($)</b>", secondary_y=False, tickformat="~s")
    fig.update_yaxes(title_text="<b>ACOS (%)</b>", secondary_y=True, showgrid=False)
    return fig

# =================================================================
# Tabs: Portfolio Group  |  Vendor / Brand
# =================================================================
tab_group, tab_brand, tab_campaign = st.tabs(["📁 Portfolio Group", "🏷️ Vendor / Brand", "📣 Campaign Overview"])

# =================================================================
# TAB 1 — Portfolio Group (existing behaviour)
# =================================================================
with tab_group:
    table = build_metrics_table(base, "Group", order=GROUP_ORDER)
    totals = build_totals_row(table)
    full_table = pd.concat([table, totals])

    st.subheader(f"Overview — {', '.join(selected_countries)}")

    t = totals.iloc[0]
    kpis = [
        ("IMPRESSIONS", human_format(t['Impressions']), f"{t['Impressions']:,.0f}", COLOR_SPEND),
        ("CLICKS", human_format(t['Clicks']), f"{t['Clicks']:,.0f}", COLOR_SPEND),
        ("SPEND", human_format(t['Spend'], prefix="$"), f"${t['Spend']:,.2f}", COLOR_SPEND),
        ("SALES", human_format(t['Sales'], prefix="$"), f"${t['Sales']:,.2f}", COLOR_SALES),
        ("ACOS", f"{t['ACOS %']:.2f}%", f"{t['ACOS %']:.2f}%", COLOR_ACOS),
        ("ROAS", f"{t['ROAS']:.2f}", f"{t['ROAS']:.2f}", COLOR_ROAS),
    ]
    cols = st.columns(len(kpis))
    for c, (label, value, exact, color) in zip(cols, kpis):
        c.markdown(
            f"""
            <div class="kpi-card" style="--accent:{color};" title="{exact}">
                <div class="kpi-label">{label}</div>
                <div class="kpi-value">{value}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.write("")
    st.subheader("Metrics by Portfolio Group")
    st.caption("Click any column header to sort ascending/descending.")
    show_metrics_table(full_table, first_col_label="Group")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("<b style='font-size:16px;'>Spend by Group</b>", unsafe_allow_html=True)
        fig = bar_chart(
            table.index, table["Spend"], [GROUP_COLORS[g] for g in table.index],
            "Spend ($)", lambda v: human_format(v, prefix="$"),
        )
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        st.markdown("<b style='font-size:16px;'>ROAS by Group</b>", unsafe_allow_html=True)
        fig = bar_chart(
            table.index, table["ROAS"], [GROUP_COLORS[g] for g in table.index],
            "ROAS", lambda v: f"{v:.2f}",
        )
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("<b style='font-size:18px;'>Contribution by Portfolio Group</b>", unsafe_allow_html=True)

    pcol1, pcol2, pcol3 = st.columns(3)
    with pcol1:
        st.plotly_chart(
            contribution_pie(table.index, table["Spend"], [GROUP_COLORS[g] for g in table.index], "Spend Contribution", "$"),
            use_container_width=True,
        )
    with pcol2:
        st.plotly_chart(
            contribution_pie(table.index, table["Sales"], [GROUP_COLORS[g] for g in table.index], "Sales Contribution", "$"),
            use_container_width=True,
        )
    with pcol3:
        st.plotly_chart(
            contribution_pie(table.index, table["ACOS %"], [GROUP_COLORS[g] for g in table.index], "ACOS Share (relative)", ""),
            use_container_width=True,
        )

    st.caption(
        "Spend and Sales pies show each group's true share of the total. "
        "The ACOS pie shows relative magnitude across groups only — ACOS is a ratio, "
        "not an additive amount, so its slices don't represent a literal 'share of total ACOS'."
    )

    with st.expander("Which portfolios fall into each group?"):
        for g in GROUP_ORDER:
            names = sorted(base[base["Group"] == g]["Portfolio name"].unique())
            st.markdown(f"**{g}** ({len(names)}): {', '.join(names) if names else '—'}")

    st.caption(
        "Grouping rule: only portfolios whose name starts with 'FBA' are included, excluding any 'Vizari' portfolios. "
        "Names containing 'CBT' → CBT, 'Exclusive' → Exclusive, 'LTSF'/'Ageing' → Ageing, "
        "all remaining FBA-prefixed portfolios → FBA."
    )

    st.divider()
    st.header("📈 Spend vs Sales vs ACOS Trend")

    trend_group = st.selectbox(
        "Portfolio group for trend view",
        options=["All groups (combined)"] + GROUP_ORDER,
        index=0,
    )

    if trend_group == "All groups (combined)":
        trend_df = base.copy()
    else:
        trend_df = base[base["Group"] == trend_group].copy()

    if trend_df.empty:
        st.info("No data available for this selection.")
    else:
        st.subheader("Day-wise Trend")
        st.caption("Drag the mini range-slider below the chart to scroll/zoom sideways as the date range extends →")

        daily = (
            trend_df.groupby(trend_df["Date"].dt.date)
            .agg(Spend=("Spend - converted", "sum"), Sales=("7 Day Total Sales - converted", "sum"))
            .reset_index()
            .rename(columns={"Date": "Day"})
            .sort_values("Day")
        )
        daily["ACOS %"] = (daily["Spend"] / daily["Sales"].replace(0, np.nan) * 100).round(2)
        daily["Day"] = pd.to_datetime(daily["Day"])

        fig_daily = combo_chart(
            x=daily["Day"], spend=daily["Spend"], sales=daily["Sales"], acos=daily["ACOS %"],
            title="Daily Spend vs Sales vs ACOS", x_title="Date", x_type="date", rangeslider=True,
        )
        st.plotly_chart(fig_daily, use_container_width=True)

        st.subheader("Week-wise Trend")

        wk = trend_df.copy()
        min_date = wk["Date"].min().normalize()
        wk["Day_Number"] = (wk["Date"].dt.normalize() - min_date).dt.days + 1
        wk["Week"] = np.minimum(((wk["Day_Number"] - 1) // 7) + 1, 5)
        wk["Week"] = "Week " + wk["Week"].astype(int).astype(str)

        weekly = (
            wk.groupby("Week")
            .agg(Spend=("Spend - converted", "sum"), Sales=("7 Day Total Sales - converted", "sum"))
            .reset_index()
        )
        weekly["order"] = weekly["Week"].str.extract(r"(\d+)").astype(int)
        weekly = weekly.sort_values("order").drop(columns="order").reset_index(drop=True)
        weekly["ACOS %"] = (weekly["Spend"] / weekly["Sales"].replace(0, np.nan) * 100).round(2)

        fig_weekly = combo_chart(
            x=weekly["Week"], spend=weekly["Spend"], sales=weekly["Sales"], acos=weekly["ACOS %"],
            title="Weekly Spend vs Sales vs ACOS (Week 1–4 = 7-day blocks, Week 5 = Day 29+)",
            x_title="Week",
        )
        st.plotly_chart(fig_weekly, use_container_width=True)

        with st.expander("Weekly breakdown (table)"):
            weekly_display = weekly.copy()
            styled_weekly = (
                weekly_display.style
                .format({"Spend": "${:,.2f}", "Sales": "${:,.2f}", "ACOS %": "{:.2f}%"})
                .background_gradient(subset=["ACOS %"], cmap="Blues", low=0.0, high=0.55)
            )
            st.dataframe(styled_weekly, use_container_width=True, hide_index=True)

        st.caption(
            "Week bucketing: Day 1 = earliest date in the current selection. "
            "Week 1 = Day 1–7, Week 2 = Day 8–14, Week 3 = Day 15–21, Week 4 = Day 22–28, "
            "Week 5 = Day 29 onward (all remaining days)."
        )

# =================================================================
# TAB 2 — Vendor / Brand  (Brand = first 4 letters of Advertised SKU)
# =================================================================
with tab_brand:
    SKU_CANDIDATES = ["Advertised SKU", "SKU"]

    try:
        sku_col = resolve_column(base, SKU_CANDIDATES, "Advertised SKU")
    except ValueError:
        sku_col = None

    if sku_col is None:
        st.error("The report is missing an 'Advertised SKU' column, so brand can't be derived.")
    else:
        vendor_df = base.copy()
        vendor_df["Brand"] = vendor_df[sku_col].astype(str).str.strip().str[:4].str.upper()
        vendor_df.loc[vendor_df[sku_col].isna() | (vendor_df[sku_col].astype(str).str.strip() == ""), "Brand"] = np.nan

        matched = vendor_df[vendor_df["Brand"].notna()]
        unmatched = vendor_df[vendor_df["Brand"].isna()]

        # ---- Single overall overview (all brands combined) ----
        st.subheader(f"Overall Overview — {', '.join(selected_countries)}")
        st.caption("Brand is derived from the first 4 characters of the Advertised SKU (e.g. 'VIZA-FBA-93344-11.5' → VIZA).")

        overall_table = build_metrics_table(matched, "Brand").sort_values("Sales", ascending=False)
        overall_totals = build_totals_row(overall_table)
        ot = overall_totals.iloc[0]

        kpis = [
            ("BRANDS", f"{len(overall_table):,}", f"{len(overall_table):,}", COLOR_SPEND),
            ("IMPRESSIONS", human_format(ot['Impressions']), f"{ot['Impressions']:,.0f}", COLOR_SPEND),
            ("CLICKS", human_format(ot['Clicks']), f"{ot['Clicks']:,.0f}", COLOR_SPEND),
            ("SPEND", human_format(ot['Spend'], prefix="$"), f"${ot['Spend']:,.2f}", COLOR_SPEND),
            ("SALES", human_format(ot['Sales'], prefix="$"), f"${ot['Sales']:,.2f}", COLOR_SALES),
            ("ACOS", f"{ot['ACOS %']:.2f}%", f"{ot['ACOS %']:.2f}%", COLOR_ACOS),
            ("ROAS", f"{ot['ROAS']:.2f}", f"{ot['ROAS']:.2f}", COLOR_ROAS),
        ]
        cols = st.columns(len(kpis))
        for c, (label, value, exact, color) in zip(cols, kpis):
            c.markdown(
                f"""
                <div class="kpi-card" style="--accent:{color};" title="{exact}">
                    <div class="kpi-label">{label}</div>
                    <div class="kpi-value">{value}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        if len(unmatched) > 0:
            st.caption(f"{len(unmatched):,} row(s) had a blank/missing SKU and are excluded from brand-level metrics.")

        st.divider()

        # ---- Single sortable, scrollable brand table (replaces separate Top-10 + full-table views) ----
        st.subheader(f"Metrics by Brand ({len(overall_table)} brands)")

        brand_search = st.text_input(
            "🔍 Search brand",
            placeholder="Type a brand, e.g. VIZA",
            key="brand_search_box",
        ).strip()

        if brand_search:
            filtered_table = overall_table[overall_table.index.str.contains(brand_search, case=False, na=False)]
        else:
            filtered_table = overall_table

        if filtered_table.empty:
            st.info(f"No brands match '{brand_search}'.")
        else:
            st.caption(
                f"Showing {len(filtered_table)} of {len(overall_table)} brands. "
                "Click any column header to sort ascending/descending; scroll within the table to see more."
            )
            filtered_totals = build_totals_row(filtered_table)
            brand_full_table = pd.concat([filtered_table, filtered_totals])
            show_metrics_table(brand_full_table, first_col_label="Brand", height=520)

        # ---- Charts: Top 10 by Sales (visual only, not a duplicate table) ----
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("<b style='font-size:18px;'>Top 10 Brands by Sales — Charts</b>", unsafe_allow_html=True)

        top10_table = overall_table.head(10)
        top10_colors = brand_colors(len(top10_table))

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("<b style='font-size:16px;'>Sales</b>", unsafe_allow_html=True)
            fig = bar_chart(
                top10_table.index, top10_table["Sales"], top10_colors,
                "Sales ($)", lambda v: human_format(v, prefix="$"),
            )
            st.plotly_chart(fig, use_container_width=True)
        with col2:
            st.markdown("<b style='font-size:16px;'>Spend</b>", unsafe_allow_html=True)
            fig = bar_chart(
                top10_table.index, top10_table["Spend"], top10_colors,
                "Spend ($)", lambda v: human_format(v, prefix="$"),
            )
            st.plotly_chart(fig, use_container_width=True)

        col3, col4 = st.columns(2)
        with col3:
            st.markdown("<b style='font-size:16px;'>ACOS</b>", unsafe_allow_html=True)
            fig = bar_chart(
                top10_table.index, top10_table["ACOS %"], top10_colors,
                "ACOS (%)", lambda v: f"{v:.2f}%",
            )
            st.plotly_chart(fig, use_container_width=True)
        with col4:
            st.markdown("<b style='font-size:16px;'>ROAS</b>", unsafe_allow_html=True)
            fig = bar_chart(
                top10_table.index, top10_table["ROAS"], top10_colors,
                "ROAS", lambda v: f"{v:.2f}",
            )
            st.plotly_chart(fig, use_container_width=True)

        st.plotly_chart(
            contribution_pie(top10_table.index, top10_table["Sales"], top10_colors, "Sales Contribution (Top 10)", "$"),
            use_container_width=True,
        )

        st.caption(
            "Brand grouping rule: first 4 characters of the Advertised SKU, uppercased. "
            "Scoped to the same FBA-prefixed portfolios as the Portfolio Group tab, excluding any 'Vizari' portfolios."
        )

# =================================================================
# TAB 3 — Campaign Overview  (same FBA-prefixed, non-Vizari scope)
# =================================================================
with tab_campaign:
    CAMPAIGN_CANDIDATES = ["Campaign Name", "Campaign"]

    try:
        campaign_col = resolve_column(base, CAMPAIGN_CANDIDATES, "Campaign Name")
    except ValueError:
        campaign_col = None

    if campaign_col is None:
        st.error("The report is missing a 'Campaign Name' column, so campaign-level metrics can't be built.")
    else:
        campaign_df = base.copy()
        campaign_df["Campaign"] = campaign_df[campaign_col].astype(str).str.strip()

        st.subheader(f"Campaign Overview — {', '.join(selected_countries)}")
        st.caption(
            "Scoped to the same FBA-prefixed portfolios as the Portfolio Group tab, excluding any 'Vizari' portfolios."
        )

        campaign_table = build_metrics_table(campaign_df, "Campaign").sort_values("Sales", ascending=False)
        campaign_totals = build_totals_row(campaign_table)
        ct = campaign_totals.iloc[0]

        kpis = [
            ("CAMPAIGNS", f"{len(campaign_table):,}", f"{len(campaign_table):,}", COLOR_SPEND),
            ("IMPRESSIONS", human_format(ct['Impressions']), f"{ct['Impressions']:,.0f}", COLOR_SPEND),
            ("CLICKS", human_format(ct['Clicks']), f"{ct['Clicks']:,.0f}", COLOR_SPEND),
            ("SPEND", human_format(ct['Spend'], prefix="$"), f"${ct['Spend']:,.2f}", COLOR_SPEND),
            ("SALES", human_format(ct['Sales'], prefix="$"), f"${ct['Sales']:,.2f}", COLOR_SALES),
            ("ACOS", f"{ct['ACOS %']:.2f}%", f"{ct['ACOS %']:.2f}%", COLOR_ACOS),
            ("ROAS", f"{ct['ROAS']:.2f}", f"{ct['ROAS']:.2f}", COLOR_ROAS),
        ]
        cols = st.columns(len(kpis))
        for c, (label, value, exact, color) in zip(cols, kpis):
            c.markdown(
                f"""
                <div class="kpi-card" style="--accent:{color};" title="{exact}">
                    <div class="kpi-label">{label}</div>
                    <div class="kpi-value">{value}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.divider()
        st.subheader(f"Metrics by Campaign ({len(campaign_table)} campaigns)")

        campaign_search = st.text_input(
            "🔍 Search campaign",
            placeholder="Type part of a campaign name, e.g. FBA_SANG",
            key="campaign_search_box",
        ).strip()

        if campaign_search:
            filtered_campaigns = campaign_table[campaign_table.index.str.contains(campaign_search, case=False, na=False)]
        else:
            filtered_campaigns = campaign_table

        if filtered_campaigns.empty:
            st.info(f"No campaigns match '{campaign_search}'.")
        else:
            st.caption(
                f"Showing {len(filtered_campaigns)} of {len(campaign_table)} campaigns. "
                "Click any column header to sort ascending/descending; scroll within the table to see more."
            )
            filtered_campaign_totals = build_totals_row(filtered_campaigns)
            campaign_full_table = pd.concat([filtered_campaigns, filtered_campaign_totals])
            show_metrics_table(campaign_full_table, first_col_label="Campaign", height=520)

        st.caption(
            "Campaign grouping rule: exact Campaign Name from the report. "
            "Scoped to FBA-prefixed portfolios, excluding any 'Vizari' portfolios."
        )

