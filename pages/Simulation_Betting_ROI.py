import os
import json
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

st.set_page_config(page_title="Simulation Betting (ROI)", page_icon="💸", layout="wide")

CUSTOM_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    :root {
        --bg: #336b95;
        --panel: rgba(255,255,255,0.12);
        --panel-strong: rgba(255,255,255,0.16);
        --card: rgba(255,255,255,0.10);
        --card-2: rgba(255,255,255,0.14);
        --border: rgba(255,255,255,0.16);
        --text: #f7fbff;
        --muted: rgba(247,251,255,0.76);
        --soft: rgba(247,251,255,0.56);
        --green: #39d98a;
        --red: #ff6b6b;
        --blue: #8bc1ff;
        --yellow: #ffd166;
        --shadow: 0 10px 30px rgba(10, 28, 45, 0.22);
    }

    .stApp {
        background:
            radial-gradient(circle at top left, rgba(255,255,255,0.07), transparent 24%),
            radial-gradient(circle at top right, rgba(255,255,255,0.05), transparent 20%),
            linear-gradient(180deg, #3f79a7 0%, #336b95 48%, #2d628b 100%);
        font-family: 'Inter', sans-serif;
        color: var(--text);
    }

    .block-container {
        max-width: 1320px;
        padding-top: 1.5rem;
        padding-bottom: 2.5rem;
    }

    #MainMenu, header, footer {
        visibility: hidden;
    }

    .glass-card {
        background: rgba(20, 45, 66, 0.18);
        border: 1px solid rgba(255,255,255,0.14);
        border-radius: 22px;
        padding: 18px 18px 16px 18px;
        box-shadow: var(--shadow);
        backdrop-filter: blur(12px);
        margin-bottom: 16px;
    }

    .top-banner {
        background: rgba(255,255,255,0.10);
        border: 1px solid rgba(255,255,255,0.14);
        color: var(--text);
        border-radius: 18px;
        padding: 12px 16px;
        margin-bottom: 18px;
        font-size: 0.92rem;
        box-shadow: var(--shadow);
        backdrop-filter: blur(10px);
    }

    .hero {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 18px;
        margin-bottom: 20px;
    }

    .hero-left h1 {
        margin: 0;
        font-size: 2.3rem;
        line-height: 1.05;
        font-weight: 800;
        color: var(--text);
        letter-spacing: -0.03em;
    }

    .hero-left p {
        margin: 8px 0 0 0;
        color: var(--muted);
        font-size: 1rem;
    }

    .hero-pill {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        border-radius: 999px;
        padding: 10px 14px;
        background: rgba(255,255,255,0.12);
        border: 1px solid rgba(255,255,255,0.14);
        color: var(--text);
        font-size: 0.86rem;
        font-weight: 600;
        white-space: nowrap;
        box-shadow: var(--shadow);
    }

    .section-title {
        font-size: 1.02rem;
        font-weight: 700;
        color: var(--text);
        margin-bottom: 12px;
    }

    .subtle {
        color: var(--muted);
        font-size: 0.92rem;
    }

    .score-card {
        background: rgba(255,255,255,0.08);
        border: 1px solid rgba(255,255,255,0.12);
        border-radius: 20px;
        padding: 16px;
        text-align: center;
        height: 100%;
    }

    .score-label {
        color: var(--soft);
        text-transform: uppercase;
        font-size: 0.74rem;
        letter-spacing: 0.08em;
        margin-bottom: 8px;
        font-weight: 700;
    }

    .score-value {
        color: var(--text);
        font-size: 1.9rem;
        font-weight: 800;
        letter-spacing: -0.03em;
    }

    .score-value.green { color: var(--green); }
    .score-value.red { color: var(--red); }
    .score-value.blue { color: var(--blue); }
    .score-value.yellow { color: var(--yellow); }

    .stButton > button {
        border-radius: 14px;
        border: 0;
        background: linear-gradient(135deg, #9ec8ff, #71afff);
        color: #0b2337;
        font-weight: 800;
        padding: 0.72rem 1.25rem;
        box-shadow: var(--shadow);
    }

    .stDataFrame, .stTable {
        border-radius: 16px !important;
        overflow: hidden !important;
    }
</style>
"""

PRED_PATH = "data/backtest_predictions.csv"
META_PATH = "data/backtest_run_metadata.json"


@st.cache_data(show_spinner=False)
def load_csv_if_exists(path):
    if os.path.exists(path):
        return pd.read_csv(path)
    return pd.DataFrame()


@st.cache_data(show_spinner=False)
def load_json_if_exists(path):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {}


def render_header():
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    st.markdown(
        """
        <div class="top-banner">
            <strong>Research extension.</strong> This page runs a simple flat-stake betting simulation using backtest predictions and market implied probabilities. It is a rough research tool, not a production betting engine.
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <div class="hero">
            <div class="hero-left">
                <h1>Simulation Betting (ROI)</h1>
                <p>Evaluate whether model probability edges would have produced positive simulated returns against market-implied prices.</p>
            </div>
            <div class="hero-pill">Flat Stake ROI Simulation</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_metric_card(label, value, subtitle="", color_class="blue"):
    st.markdown(
        f"""
        <div class="score-card">
            <div class="score-label">{label}</div>
            <div class="score-value {color_class}">{value}</div>
            <div class="subtle" style="margin-top:8px;">{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def method_display_name(method):
    mapping = {
        "single_agent": "Single Agent",
        "chain_of_thought": "Chain-of-Thought",
        "multi_agent_debate": "Multi-Agent Debate",
    }
    return mapping.get(method, method)


def safe_prob(x):
    try:
        x = float(x)
        return min(max(x, 1e-6), 1 - 1e-6)
    except Exception:
        return np.nan


def available_market_columns(df):
    return "market_home_implied_prob" in df.columns and "market_away_implied_prob" in df.columns


def render_run_health(meta):
    if not meta:
        return

    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Backtest Run Context</div>', unsafe_allow_html=True)

    requested = meta.get("n_games_requested", "N/A")
    selected = meta.get("candidate_games_selected", "N/A")
    skipped = meta.get("games_skipped", "N/A")
    methods = ", ".join([method_display_name(x) for x in meta.get("methods_present", [])]) or "N/A"

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_metric_card("Requested Games", str(requested), "Requested in latest run", "blue")
    with c2:
        render_metric_card("Candidate Games", str(selected), "Selected for historical evaluation", "blue")
    with c3:
        color = "red" if isinstance(skipped, int) and skipped > 0 else "green"
        render_metric_card("Skipped Games", str(skipped), "May affect simulation coverage", color)
    with c4:
        render_metric_card("Methods", str(len(meta.get("methods_present", []))), methods, "blue")

    st.markdown('</div>', unsafe_allow_html=True)


def render_controls(pred_df):
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Simulation Controls</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="subtle" style="margin-bottom:14px;">A bet is placed only when the model probability exceeds the market implied probability by at least the chosen edge threshold. Each bet uses a flat stake of 1 unit.</div>',
        unsafe_allow_html=True,
    )

    methods_available = sorted(pred_df["method"].dropna().unique().tolist()) if "method" in pred_df.columns else []
    method_options = ["All"] + methods_available

    c1, c2, c3, c4 = st.columns([1.4, 1.2, 1.2, 1.2])
    with c1:
        method_filter = st.selectbox(
            "Method",
            method_options,
            index=0,
            format_func=lambda x: "All Methods" if x == "All" else method_display_name(x),
            key="roi_method_filter",
        )
    with c2:
        edge_threshold = st.slider("Edge Threshold", min_value=0.00, max_value=0.20, value=0.05, step=0.01)
    with c3:
        side_filter = st.selectbox(
            "Allowed Side",
            ["Both", "Home Only", "Away Only"],
            index=0,
            key="roi_side_filter",
        )
    with c4:
        min_confidence = st.slider("Min Model Confidence", min_value=0.50, max_value=0.95, value=0.50, step=0.01)

    st.markdown('</div>', unsafe_allow_html=True)
    return method_filter, edge_threshold, side_filter, min_confidence


def simulate_roi(pred_df, method_filter="All", edge_threshold=0.05, side_filter="Both", min_confidence=0.50):
    if pred_df.empty or not available_market_columns(pred_df):
        return pd.DataFrame(), pd.DataFrame()

    df = pred_df.copy()

    if method_filter != "All":
        df = df[df["method"] == method_filter].copy()

    if df.empty:
        return pd.DataFrame(), pd.DataFrame()

    sim_rows = []

    for _, row in df.iterrows():
        home_prob = safe_prob(row.get("home_win_prob"))
        away_prob = safe_prob(row.get("away_win_prob"))
        market_home = safe_prob(row.get("market_home_implied_prob"))
        market_away = safe_prob(row.get("market_away_implied_prob"))

        if any(pd.isna(x) for x in [home_prob, away_prob, market_home, market_away]):
            continue

        model_confidence = max(home_prob, away_prob)
        if model_confidence < min_confidence:
            continue

        home_edge = home_prob - market_home
        away_edge = away_prob - market_away

        chosen_side = None
        chosen_edge = None
        chosen_market_prob = None
        won = None

        if side_filter in ["Both", "Home Only"] and home_edge >= edge_threshold:
            chosen_side = "Home"
            chosen_edge = home_edge
            chosen_market_prob = market_home
            won = int(row["actual_home_win"]) == 1

        if side_filter in ["Both", "Away Only"] and away_edge >= edge_threshold:
            if chosen_side is None or away_edge > chosen_edge:
                chosen_side = "Away"
                chosen_edge = away_edge
                chosen_market_prob = market_away
                won = int(row["actual_home_win"]) == 0

        if chosen_side is None:
            continue

        decimal_odds = 1.0 / chosen_market_prob
        units = (decimal_odds - 1.0) if won else -1.0

        sim_rows.append({
            "date": row["date"],
            "season": row.get("season", ""),
            "game_id": row.get("game_id", ""),
            "away_team": row["away_team"],
            "home_team": row["home_team"],
            "method": row["method"],
            "side_bet": chosen_side,
            "edge": round(float(chosen_edge), 4),
            "model_home_prob": round(float(home_prob), 4),
            "model_away_prob": round(float(away_prob), 4),
            "market_home_implied_prob": round(float(market_home), 4),
            "market_away_implied_prob": round(float(market_away), 4),
            "model_confidence": round(float(model_confidence), 4),
            "won": int(won),
            "units": round(float(units), 4),
            "correct": int(row["correct"]),
        })

    bets_df = pd.DataFrame(sim_rows)
    if bets_df.empty:
        return bets_df, pd.DataFrame()

    bets_df["date"] = pd.to_datetime(bets_df["date"], errors="coerce")
    bets_df = bets_df.sort_values(["method", "date", "game_id"]).reset_index(drop=True)
    bets_df["cum_units"] = bets_df.groupby("method")["units"].cumsum()

    summary = (
        bets_df.groupby("method")
        .agg(
            n_bets=("units", "count"),
            win_rate=("won", "mean"),
            total_units=("units", "sum"),
            avg_units_per_bet=("units", "mean"),
            avg_edge=("edge", "mean"),
            avg_model_confidence=("model_confidence", "mean"),
        )
        .reset_index()
    )

    summary["roi"] = summary["total_units"] / summary["n_bets"]
    return bets_df, summary


def render_overview(summary_df, bets_df):
    if summary_df.empty:
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.warning("No qualifying simulated bets under the current filters.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    best_roi = summary_df.sort_values("roi", ascending=False).iloc[0]
    best_units = summary_df.sort_values("total_units", ascending=False).iloc[0]
    most_bets = summary_df.sort_values("n_bets", ascending=False).iloc[0]
    best_win_rate = summary_df.sort_values("win_rate", ascending=False).iloc[0]

    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Simulation Overview</div>', unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_metric_card(
            "Best ROI",
            f"{best_roi['roi']:.2%}",
            method_display_name(best_roi["method"]),
            "green" if best_roi["roi"] > 0 else "red",
        )
    with c2:
        render_metric_card(
            "Most Units Won",
            f"{best_units['total_units']:.2f}",
            method_display_name(best_units["method"]),
            "green" if best_units["total_units"] > 0 else "red",
        )
    with c3:
        render_metric_card(
            "Most Bets",
            f"{int(most_bets['n_bets'])}",
            method_display_name(most_bets["method"]),
            "blue",
        )
    with c4:
        render_metric_card(
            "Best Win Rate",
            f"{best_win_rate['win_rate']:.2%}",
            method_display_name(best_win_rate["method"]),
            "yellow",
        )

    st.caption(
        "ROI here means average units returned per bet under a flat 1-unit staking rule. This is a simple research simulation, not a production betting strategy."
    )
    st.markdown('</div>', unsafe_allow_html=True)


def render_summary_table(summary_df):
    if summary_df.empty:
        return

    pretty = summary_df.copy()
    pretty["method"] = pretty["method"].apply(method_display_name)
    pretty = pretty.sort_values("roi", ascending=False).reset_index(drop=True)

    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Method-Level ROI Summary</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="subtle" style="margin-bottom:12px;">This table summarizes the simulated performance of each reasoning method under the current filters.</div>',
        unsafe_allow_html=True,
    )
    st.dataframe(pretty, use_container_width=True, hide_index=True)
    st.markdown('</div>', unsafe_allow_html=True)


def render_cumulative_units_chart(bets_df):
    if bets_df.empty:
        return

    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Cumulative Units Over Time</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="subtle" style="margin-bottom:12px;">This chart shows how the simulated bankroll changes over time for each method under flat 1-unit staking.</div>',
        unsafe_allow_html=True,
    )

    fig, ax = plt.subplots(figsize=(9, 5.2))

    for method in bets_df["method"].dropna().unique():
        g = bets_df[bets_df["method"] == method].copy().sort_values("date")
        ax.plot(g["date"], g["cum_units"], linewidth=2.5, label=method_display_name(method))

    fig.patch.set_facecolor("#1e1e1e")
    ax.set_facecolor("#1e1e1e")
    ax.tick_params(colors="white")
    ax.title.set_color("white")
    ax.yaxis.label.set_color("white")
    ax.xaxis.label.set_color("white")
    for spine in ax.spines.values():
        spine.set_color("white")

    legend = ax.legend()
    plt.setp(legend.get_texts(), color="white")
    legend.get_frame().set_facecolor("#1e1e1e")
    legend.get_frame().set_edgecolor("white")

    ax.set_title("Cumulative Units")
    ax.set_xlabel("Date")
    ax.set_ylabel("Units")

    st.pyplot(fig, use_container_width=True)
    plt.close(fig)

    st.markdown('</div>', unsafe_allow_html=True)


def render_roi_bar_chart(summary_df):
    if summary_df.empty:
        return

    plot_df = summary_df.copy()
    plot_df["method_label"] = plot_df["method"].apply(method_display_name)

    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">ROI by Method</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="subtle" style="margin-bottom:12px;">Higher is better. Positive ROI means the method won units on average under this simple betting rule.</div>',
        unsafe_allow_html=True,
    )

    fig, ax = plt.subplots(figsize=(8, 4.8))
    ax.bar(plot_df["method_label"], plot_df["roi"])

    fig.patch.set_facecolor("#1e1e1e")
    ax.set_facecolor("#1e1e1e")
    ax.tick_params(colors="white")
    ax.title.set_color("white")
    ax.yaxis.label.set_color("white")
    ax.xaxis.label.set_color("white")
    for spine in ax.spines.values():
        spine.set_color("white")

    ax.axhline(0, linewidth=1.5)
    ax.set_title("ROI by Method")
    ax.set_xlabel("Method")
    ax.set_ylabel("ROI")
    plt.setp(ax.get_xticklabels(), rotation=10, color="white")

    st.pyplot(fig, use_container_width=True)
    plt.close(fig)

    st.markdown('</div>', unsafe_allow_html=True)


def render_bets_table(bets_df):
    if bets_df.empty:
        return

    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Simulated Bets</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="subtle" style="margin-bottom:12px;">These are the individual bets that passed the edge and confidence filters. Use this to inspect where the simulated returns came from.</div>',
        unsafe_allow_html=True,
    )

    show_df = bets_df.copy()
    show_df["method"] = show_df["method"].apply(method_display_name)
    cols = [
        "date",
        "away_team",
        "home_team",
        "method",
        "side_bet",
        "edge",
        "model_confidence",
        "market_home_implied_prob",
        "market_away_implied_prob",
        "won",
        "units",
        "cum_units",
    ]
    cols = [c for c in cols if c in show_df.columns]
    st.dataframe(show_df[cols].head(200), use_container_width=True, hide_index=True)

    st.markdown('</div>', unsafe_allow_html=True)


def main():
    render_header()

    pred_df = load_csv_if_exists(PRED_PATH)
    meta = load_json_if_exists(META_PATH)

    if pred_df.empty:
        st.warning("No backtest predictions found yet. Run a backtest first from the Research Evaluation page.")
        st.stop()

    if not available_market_columns(pred_df):
        st.warning(
            "This backtest file does not contain market implied probabilities yet. Re-run your backtest after using the updated `nba_backtest.py` so the simulation page has market columns to work with."
        )
        st.stop()

    render_run_health(meta)

    method_filter, edge_threshold, side_filter, min_confidence = render_controls(pred_df)
    bets_df, summary_df = simulate_roi(
        pred_df,
        method_filter=method_filter,
        edge_threshold=edge_threshold,
        side_filter=side_filter,
        min_confidence=min_confidence,
    )

    render_overview(summary_df, bets_df)
    render_summary_table(summary_df)
    render_roi_bar_chart(summary_df)
    render_cumulative_units_chart(bets_df)
    render_bets_table(bets_df)


if __name__ == "__main__":
    main()