import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

st.set_page_config(page_title="Portfolio & Vendor Metrics Dashboard", layout="wide", page_icon="📊")

# =================================================================
# THEME / STYLING  (heat-wave palette: amber -> orange -> rose, bold type)
# =================================================================
COLOR_SPEND = "#F97316"   # orange-500
COLOR_SALES = "#FBBF24"   # amber-400
COLOR_ACOS = "#FB7185"    # rose-400 (warm accent, not maroon)
COLOR_ROAS = "#FDBA74"    # orange-300

GROUP_COLORS = {
    "CBT": "#FCD34D",       # amber-300
    "Exclusive": "#FB923C", # orange-400
    "Ageing": "#F97316",    # orange-500
    "FBA": "#FB7185",       # rose-400
}

# Cycled warm palette for dynamic group counts (e.g. many brands)
WARM_PALETTE = [
    "#FCD34D", "#FB923C", "#F97316", "#FB7185", "#F59E0B",
    "#FDBA74", "#EA580C", "#F87171", "#FDE68A", "#FB6F92",
    "#EF4444", "#FCA5A5", "#FDBA8C", "#F0ABFC", "#FDA4AF",
]

def warm_colors(n):
    return [WARM_PALETTE[i % len(WARM_PALETTE)] for i in range(n)]

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
    """
    <style>
    .stApp { background-color: #FFFBF5; }
    h1, h2, h3 {
        color: #1C1917;
        font-family: 'Google Sans', 'Segoe UI', sans-serif;
        font-weight: 800 !important;
    }
    p, li, label, .stMarkdown, .stCaption { font-weight: 500; }
    .stCaption, [data-testid="stCaptionContainer"] { font-weight: 600 !important; color: #57534E !important; }
    .kpi-card {
        background: #FFFFFF;
        border-radius: 12px;
        padding: 16px 18px 14px 18px;
        box-shadow: 0 1px 3px rgba(28,25,23,0.12), 0 1px 2px rgba(28,25,23,0.08);
        border-top: 5px solid var(--accent);
        text-align: left;
    }
    .kpi-label {
        font-size: 13px;
        color: #57534E;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        margin-bottom: 4px;
    }
    .kpi-value {
        font-size: 28px;
        font-weight: 800;
        color: #1C1917;
    }
    div[data-testid="stDataFrame"] { border-radius: 10px; overflow: hidden; }

    /* HTML metrics table (bold, high-contrast, heat-wave tones) */
    .metrics-table-wrap { overflow-x: auto; border-radius: 10px; box-shadow: 0 1px 3px rgba(28,25,23,0.12); }
    .metrics-table-wrap.scroll-y { max-height: 520px; overflow-y: auto; }
    table.metrics-table { border-collapse: collapse; width: 100%; font-size: 15px; background: #FFFFFF; }
    table.metrics-table th {
        background: #1C1917; color: #FFFFFF; font-weight: 800;
        text-align: right; padding: 10px 14px; white-space: nowrap;
        position: sticky; top: 0; z-index: 1;
    }
    table.metrics-table th:first-child { text-align: left; }
    table.metrics-table td {
        padding: 10px 14px; text-align: right; font-weight: 700; color: #1C1917;
        border-bottom: 1px solid #E7E5E4; white-space: nowrap;
    }
    table.metrics-table td:first-child { text-align: left; font-weight: 800; }
    table.metrics-table tr.total-row td { background: #F5F5F4; font-weight: 800; }
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
    for c in candidates:
        if c in df.columns:
            return c
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
    Non-FBA portfolios are excluded (returns None)."""
    if pd.isna(portfolio):
        return None
    p = str(portfolio).strip()
    pu = p.upper()
    if not pu.startswith("FBA"):
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

if base.empty:
    st.warning("No FBA-prefixed portfolio data found for the selected country/countries.")
    st.stop()

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

def render_metrics_table(data: pd.DataFrame, first_col_label: str = "Group", scroll_y: bool = False) -> str:
    fmt = {
        "Impressions": lambda v: f"{v:,.0f}",
        "Clicks": lambda v: f"{v:,.0f}",
        "CTR %": lambda v: f"{v:.2f}%",
        "Spend": lambda v: f"${v:,.2f}",
        "Sales": lambda v: f"${v:,.2f}",
        "ACOS %": lambda v: f"{v:.2f}%",
        "ROAS": lambda v: f"{v:.2f}",
    }

    # Cool-toned, single-hue intensity shading (darker = higher value) — no rainbow gradients
    def shade(series: pd.Series, cmap_hex_stops):
        s = series.astype(float)
        lo, hi = s.min(), s.max()
        rng = (hi - lo) or 1.0
        norm = (s - lo) / rng
        c0 = np.array(cmap_hex_stops[0])
        c1 = np.array(cmap_hex_stops[1])
        colors = []
        for n in norm:
            rgb = (c0 + (c1 - c0) * n).astype(int)
            colors.append(f"rgb({rgb[0]},{rgb[1]},{rgb[2]})")
        return colors

    acos_colors = shade(data["ACOS %"], ([255, 247, 191], [251, 113, 133]))  # pale yellow -> rose-400
    roas_colors = shade(data["ROAS"], ([255, 247, 191], [249, 115, 22]))     # pale yellow -> orange-500

    headers = [first_col_label, "Impressions", "Clicks", "CTR %", "Spend", "Sales", "ACOS %", "ROAS"]
    rows_html = []
    for i, (idx, row) in enumerate(data.iterrows()):
        is_total = idx == "TOTAL"
        cells = [f"<td>{idx}</td>"]
        for col in ["Impressions", "Clicks", "CTR %", "Spend", "Sales"]:
            cells.append(f"<td>{fmt[col](row[col])}</td>")
        acos_bg = "" if is_total else f' style="background:{acos_colors[i]};"'
        roas_bg = "" if is_total else f' style="background:{roas_colors[i]};"'
        cells.append(f"<td{acos_bg}>{fmt['ACOS %'](row['ACOS %'])}</td>")
        cells.append(f"<td{roas_bg}>{fmt['ROAS'](row['ROAS'])}</td>")
        row_class = ' class="total-row"' if is_total else ""
        rows_html.append(f"<tr{row_class}>{''.join(cells)}</tr>")

    header_html = "".join(f"<th>{h}</th>" for h in headers)
    wrap_class = "metrics-table-wrap scroll-y" if scroll_y else "metrics-table-wrap"
    return (
        f'<div class="{wrap_class}"><table class="metrics-table">'
        f"<thead><tr>{header_html}</tr></thead><tbody>{''.join(rows_html)}</tbody></table></div>"
    )

def bar_chart(labels, values, colors, y_title, value_fmt):
    fig = go.Figure(go.Bar(
        x=labels, y=values,
        marker_color=colors,
        text=[value_fmt(v) for v in values],
        textposition="outside",
        textfont=dict(size=13, color="#1C1917"),
    ))
    fig.update_layout(
        template="plotly_white", height=360,
        margin=dict(l=10, r=10, t=10, b=10),
        yaxis_title=y_title,
        font=dict(size=13, color="#1C1917", family="Segoe UI, sans-serif"),
        yaxis=dict(title_font=dict(size=13, color="#1C1917"), tickformat="~s"),
        xaxis=dict(tickangle=-35),
    )
    return fig

def contribution_pie(labels, values, colors, title, value_prefix=""):
    fig = go.Figure(go.Pie(
        labels=labels, values=values,
        marker=dict(colors=colors, line=dict(color="#FFFFFF", width=2)),
        hole=0.4,
        textinfo="label+percent",
        textfont=dict(size=12, color="#1C1917"),
        hovertemplate="%{label}: " + value_prefix + "%{value:,.2f} (%{percent})<extra></extra>",
    ))
    fig.update_layout(
        template="plotly_white", height=380,
        title=dict(text=f"<b>{title}</b>", font=dict(size=14, color="#1C1917")),
        margin=dict(l=10, r=10, t=45, b=10),
        showlegend=False,
        font=dict(size=12, color="#1C1917", family="Segoe UI, sans-serif"),
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
        title=dict(text=f"<b>{title}</b>", font=dict(size=16, color="#1C1917")),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=12, color="#1C1917")),
        margin=dict(l=10, r=10, t=60, b=10),
        hovermode="x unified",
        font=dict(size=13, color="#1C1917", family="Segoe UI, sans-serif"),
    )
    fig.update_xaxes(title_text=f"<b>{x_title}</b>", type=x_type)
    if rangeslider:
        fig.update_xaxes(rangeslider=dict(visible=True, thickness=0.08, bgcolor="#FEF3C7"))
    fig.update_yaxes(title_text="<b>Amount ($)</b>", secondary_y=False, tickformat="~s")
    fig.update_yaxes(title_text="<b>ACOS (%)</b>", secondary_y=True, showgrid=False)
    return fig

# =================================================================
# Tabs: Portfolio Group  |  Vendor / Brand
# =================================================================
tab_group, tab_brand = st.tabs(["📁 Portfolio Group", "🏷️ Vendor / Brand"])

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
    st.markdown(render_metrics_table(full_table, first_col_label="Group"), unsafe_allow_html=True)

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
        "Grouping rule: only portfolios whose name starts with 'FBA' are included. "
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
            wk_headers = "".join(f"<th>{h}</th>" for h in ["Week", "Spend", "Sales", "ACOS %"])
            wk_rows = []
            for _, r in weekly.iterrows():
                wk_rows.append(
                    f"<tr><td>{r['Week']}</td><td>${r['Spend']:,.2f}</td>"
                    f"<td>${r['Sales']:,.2f}</td><td>{r['ACOS %']:.2f}%</td></tr>"
                )
            wk_table_html = (
                '<div class="metrics-table-wrap"><table class="metrics-table">'
                f"<thead><tr>{wk_headers}</tr></thead><tbody>{''.join(wk_rows)}</tbody></table></div>"
            )
            st.markdown(wk_table_html, unsafe_allow_html=True)

        st.caption(
            "Week bucketing: Day 1 = earliest date in the current selection. "
            "Week 1 = Day 1–7, Week 2 = Day 8–14, Week 3 = Day 15–21, Week 4 = Day 22–28, "
            "Week 5 = Day 29 onward (all remaining days)."
        )

# =================================================================
# TAB 2 — Vendor / Brand  (ASIN -> Brand mapping, VLOOKUP-style join)
# =================================================================
with tab_brand:
    st.subheader(f"Overview — {', '.join(selected_countries)}")
    st.caption(
        "Scoped to the same FBA-prefixed portfolios as the Portfolio Group tab. "
        "Upload an ASIN → Brand mapping file to break these metrics out by brand."
    )

    ASIN_CANDIDATES = ["ASIN", "Advertised ASIN"]
    BRAND_CANDIDATES = ["Brand", "Prefix", "Brand Prefix"]

    mapping_file = st.file_uploader(
        "Upload ASIN → Brand mapping (.csv or .xlsx, columns: Prefix/Brand + ASIN)",
        type=["csv", "xlsx"],
        key="brand_mapping_uploader",
    )

    if mapping_file is None:
        st.info("👆 Upload the ASIN → Brand mapping file to see vendor-wise metrics.")
    elif "Advertised ASIN" not in base.columns:
        st.error("The report is missing an 'Advertised ASIN' column, so ASINs can't be matched to brands.")
    else:
        @st.cache_data
        def load_mapping(file) -> pd.DataFrame:
            name = getattr(file, "name", "")
            if name.lower().endswith(".csv"):
                m = pd.read_csv(file)
            else:
                m = pd.read_excel(file)
            m.columns = [str(c).strip() for c in m.columns]

            asin_col = resolve_column(m, ASIN_CANDIDATES, "ASIN")
            brand_col = resolve_column(m, BRAND_CANDIDATES, "Brand/Prefix")

            m = m[[brand_col, asin_col]].rename(columns={brand_col: "Brand", asin_col: "ASIN"})
            m["ASIN"] = m["ASIN"].astype(str).str.strip()
            m["Brand"] = m["Brand"].astype(str).str.strip()
            m = m[(m["ASIN"] != "") & (m["Brand"] != "")]
            return m

        try:
            raw_map = load_mapping(mapping_file)
        except Exception as e:
            st.error(f"Could not read mapping file: {e}")
            st.stop()

        # ---- Deduplicate: one Brand per ASIN. Flag genuine conflicts. ----
        per_asin_brands = raw_map.groupby("ASIN")["Brand"].unique()
        conflict_asins = per_asin_brands[per_asin_brands.apply(len) > 1]
        clean_map = raw_map.drop_duplicates(subset="ASIN", keep="first")
        if len(conflict_asins) > 0:
            clean_map = clean_map[~clean_map["ASIN"].isin(conflict_asins.index)]

        asin_to_brand = dict(zip(clean_map["ASIN"], clean_map["Brand"]))

        st.caption(
            f"Mapping loaded: {len(raw_map):,} rows → {len(clean_map):,} unique ASINs mapped "
            f"({len(conflict_asins):,} ASIN(s) excluded due to conflicting brands — see below)."
        )

        if len(conflict_asins) > 0:
            with st.expander(f"⚠️ {len(conflict_asins)} ASIN(s) with conflicting brand mappings (excluded)"):
                conflict_df = conflict_asins.reset_index()
                conflict_df.columns = ["ASIN", "Conflicting Brands"]
                conflict_df["Conflicting Brands"] = conflict_df["Conflicting Brands"].apply(lambda x: ", ".join(x))
                st.dataframe(conflict_df, use_container_width=True, hide_index=True)

        # ---- VLOOKUP: tag every report row with its Brand ----
        vendor_df = base.copy()
        vendor_df["Advertised ASIN"] = vendor_df["Advertised ASIN"].astype(str).str.strip()
        vendor_df["Brand"] = vendor_df["Advertised ASIN"].map(asin_to_brand)

        matched = vendor_df[vendor_df["Brand"].notna()]
        unmatched = vendor_df[vendor_df["Brand"].isna()]

        n_unmatched_asins = unmatched["Advertised ASIN"].nunique()
        if n_unmatched_asins > 0:
            with st.expander(f"⚠️ {n_unmatched_asins} ASIN(s) in the report have no brand mapping"):
                unmapped_list = sorted(unmatched["Advertised ASIN"].dropna().unique())
                st.write(", ".join(unmapped_list[:500]))
                if len(unmapped_list) > 500:
                    st.caption(f"...and {len(unmapped_list) - 500} more.")

        if matched.empty:
            st.warning("No ASINs in the current selection matched the uploaded brand mapping.")
        else:
            brand_order = (
                matched.groupby("Brand")["Spend - converted"].sum().sort_values(ascending=False).index.tolist()
            )
            brand_table = build_metrics_table(matched, "Brand", order=brand_order)
            brand_totals = build_totals_row(brand_table)
            brand_full_table = pd.concat([brand_table, brand_totals])

            bt = brand_totals.iloc[0]
            kpis = [
                ("BRANDS MATCHED", f"{len(brand_table):,}", f"{len(brand_table):,}", COLOR_SPEND),
                ("SPEND", human_format(bt['Spend'], prefix="$"), f"${bt['Spend']:,.2f}", COLOR_SPEND),
                ("SALES", human_format(bt['Sales'], prefix="$"), f"${bt['Sales']:,.2f}", COLOR_SALES),
                ("ACOS", f"{bt['ACOS %']:.2f}%", f"{bt['ACOS %']:.2f}%", COLOR_ACOS),
                ("ROAS", f"{bt['ROAS']:.2f}", f"{bt['ROAS']:.2f}", COLOR_ROAS),
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
            st.subheader(f"Metrics by Brand ({len(brand_table)} brands, sorted by Spend)")
            st.markdown(
                render_metrics_table(brand_full_table, first_col_label="Brand", scroll_y=len(brand_table) > 12),
                unsafe_allow_html=True,
            )

            TOP_N = 15
            top_brands = brand_table.head(TOP_N)
            top_colors = warm_colors(len(top_brands))

            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"<b style='font-size:16px;'>Top {len(top_brands)} Brands by Spend</b>", unsafe_allow_html=True)
                fig = bar_chart(
                    top_brands.index, top_brands["Spend"], top_colors,
                    "Spend ($)", lambda v: human_format(v, prefix="$"),
                )
                st.plotly_chart(fig, use_container_width=True)
            with col2:
                st.markdown(f"<b style='font-size:16px;'>Top {len(top_brands)} Brands by ROAS</b>", unsafe_allow_html=True)
                roas_sorted = brand_table.sort_values("ROAS", ascending=False).head(TOP_N)
                fig = bar_chart(
                    roas_sorted.index, roas_sorted["ROAS"], warm_colors(len(roas_sorted)),
                    "ROAS", lambda v: f"{v:.2f}",
                )
                st.plotly_chart(fig, use_container_width=True)

            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown(f"<b style='font-size:18px;'>Contribution by Brand (Top {TOP_N} + Other)</b>", unsafe_allow_html=True)

            def top_plus_other(series):
                top = series.head(TOP_N)
                other_val = series.iloc[TOP_N:].sum()
                if other_val > 0:
                    top = pd.concat([top, pd.Series({"Other": other_val})])
                return top

            spend_pie_data = top_plus_other(brand_table["Spend"])
            sales_pie_data = top_plus_other(brand_table.sort_values("Sales", ascending=False)["Sales"])
            pie_colors_spend = warm_colors(len(spend_pie_data))
            pie_colors_sales = warm_colors(len(sales_pie_data))

            pcol1, pcol2 = st.columns(2)
            with pcol1:
                st.plotly_chart(
                    contribution_pie(spend_pie_data.index, spend_pie_data, pie_colors_spend, "Spend Contribution", "$"),
                    use_container_width=True,
                )
            with pcol2:
                st.plotly_chart(
                    contribution_pie(sales_pie_data.index, sales_pie_data, pie_colors_sales, "Sales Contribution", "$"),
                    use_container_width=True,
                )

            st.caption(
                "TOTAL row reflects only ASINs successfully matched to a brand. "
                "Unmatched ASINs (listed above, if any) are excluded from this tab's metrics."
            )
