import os
import sys
import json
import subprocess
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

st.set_page_config(page_title="Research Evaluation", page_icon="📊", layout="wide")

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

SUMMARY_PATH = "data/backtest_summary.csv"
PRED_PATH = "data/backtest_predictions.csv"
CAL_PATH = "data/backtest_calibration.csv"
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
            <strong>Research mode.</strong> This page is for backtesting, calibration, and model comparison rather than end-user matchup browsing.
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <div class="hero">
            <div class="hero-left">
                <h1>Research Evaluation</h1>
                <p>Comprehensive backtesting, calibration, and model comparison for MatchOdds AI.</p>
            </div>
            <div class="hero-pill">Evaluation Dashboard</div>
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


def get_available_metrics(summary_df):
    return [
        c for c in [
            "accuracy",
            "precision",
            "recall",
            "f1",
            "log_loss",
            "brier_score",
            "mae_prob",
            "avg_confidence",
            "avg_gap",
            "ece",
        ]
        if c in summary_df.columns
    ]


def metric_display_name(metric):
    return metric.replace("_", " ").title()


def metric_format(value, metric):
    if pd.isna(value):
        return "N/A"
    if metric in {"accuracy", "precision", "recall", "f1"}:
        return f"{float(value):.2%}"
    return f"{float(value):.4f}"


def metric_direction_subtitle(metric):
    if metric in {"accuracy", "precision", "recall", "f1"}:
        return "Higher is better"
    return "Lower is better"


def render_controls():
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Backtest Controls</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="subtle" style="margin-bottom:14px;">Choose how many historical games to evaluate, then run a fresh backtest from this page.</div>',
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns([2, 2, 1.5])
    with c1:
        n_games = st.slider("Number of Games", min_value=5, max_value=100, value=25, step=5)
    with c2:
        season = st.selectbox(
            "Season",
            ["2025-26", "2024-25", "2023-24", "2022-23", "All"],
            index=0,
            key="season_select",
        )
    with c3:
        min_hist = st.slider("Min Prior Games", min_value=5, max_value=20, value=10, step=1)

    run_now = st.button("Run / Refresh Backtest")
    st.markdown('</div>', unsafe_allow_html=True)
    return n_games, season, min_hist, run_now


def run_backtest_from_ui(n_games, season, min_hist):
    season_arg = season if season != "All" else ""
    cmd = [sys.executable, "nba_backtest.py", "--n-games", str(n_games), "--min-games-history", str(min_hist)]
    if season_arg:
        cmd.extend(["--season", season_arg])
    return subprocess.run(cmd, capture_output=True, text=True)


def render_run_health(meta):
    if not meta:
        return

    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Run Health</div>', unsafe_allow_html=True)

    requested = meta.get("n_games_requested", "N/A")
    selected = meta.get("candidate_games_selected", "N/A")
    skipped = meta.get("games_skipped", "N/A")
    rows = meta.get("prediction_rows", "N/A")
    methods = ", ".join([method_display_name(x) for x in meta.get("methods_present", [])]) or "N/A"

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_metric_card("Requested Games", str(requested), "Requested in this run", "blue")
    with c2:
        render_metric_card("Candidate Games", str(selected), "Selected for evaluation", "blue")
    with c3:
        skipped_color = "red" if isinstance(skipped, int) and skipped > 0 else "green"
        render_metric_card("Skipped Games", str(skipped), "Insufficient history or failed calls", skipped_color)
    with c4:
        render_metric_card("Prediction Rows", str(rows), f"Methods present: {methods}", "blue")

    if isinstance(skipped, int) and skipped > 0:
        st.warning(
            "This backtest run is incomplete. Some games were skipped, so the metrics below reflect only completed evaluations."
        )
    else:
        st.success("This backtest run completed without skipped games.")

    st.markdown('</div>', unsafe_allow_html=True)


def render_summary_section(summary_df):
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Backtest Summary</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="subtle" style="margin-bottom:12px;">These are the headline evaluation metrics. Higher accuracy, precision, recall, and F1 are better. Lower log loss, Brier score, MAE, and ECE are better.</div>',
        unsafe_allow_html=True,
    )
    st.dataframe(summary_df, use_container_width=True, hide_index=True)
    st.caption(
        """
Accuracy: % correct picks  
Precision: of predicted home wins, how many were correct  
Recall: of actual home wins, how many were caught  
F1: balance between precision and recall  
Log Loss: penalizes wrong confidence more strongly  
Brier Score: squared error of predicted probabilities  
MAE Prob: average absolute probability error  
Avg Confidence: average of the larger predicted side probability  
Avg Gap: average separation between home and away win probabilities  
ECE: calibration error, or how aligned probabilities are with reality
"""
    )

    available_metrics = get_available_metrics(summary_df)
    if not available_metrics:
        st.markdown('</div>', unsafe_allow_html=True)
        return

    selected_metric = st.selectbox(
        "Select evaluation metric",
        available_metrics,
        index=0,
        key="metric_select_main",
    )

    higher_is_better = selected_metric in {"accuracy", "precision", "recall", "f1"}
    best_row = summary_df.sort_values(selected_metric, ascending=not higher_is_better).iloc[0]

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_metric_card(
            f"Best {metric_display_name(selected_metric)}",
            metric_format(best_row[selected_metric], selected_metric),
            method_display_name(best_row["method"]),
            "green" if higher_is_better else "blue",
        )
    with c2:
        if "accuracy" in summary_df.columns:
            row = summary_df.sort_values("accuracy", ascending=False).iloc[0]
            render_metric_card("Best Accuracy", f"{row['accuracy']:.2%}", method_display_name(row["method"]), "green")
    with c3:
        if "log_loss" in summary_df.columns:
            row = summary_df.sort_values("log_loss", ascending=True).iloc[0]
            render_metric_card("Best Log Loss", f"{row['log_loss']:.4f}", method_display_name(row["method"]), "blue")
    with c4:
        if "ece" in summary_df.columns:
            row = summary_df.sort_values("ece", ascending=True).iloc[0]
            render_metric_card("Best Calibration", f"{row['ece']:.4f}", method_display_name(row["method"]), "blue")

    st.caption(f"Top card follows the selected metric above. {metric_direction_subtitle(selected_metric)}.")
    st.markdown('</div>', unsafe_allow_html=True)


def render_metric_comparison_charts(summary_df):
    available_metrics = get_available_metrics(summary_df)
    if not available_metrics:
        return

    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Metric Comparison</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="subtle" style="margin-bottom:12px;">Use the selector to compare one metric at a time across models. Higher is better for accuracy, precision, recall, and F1. Lower is better for log loss, Brier score, MAE, and ECE.</div>',
        unsafe_allow_html=True,
    )

    metric = st.selectbox(
        "Select chart metric",
        available_metrics,
        index=0,
        key="metric_select_chart",
    )

    plot_df = summary_df.copy()
    plot_df["method_label"] = plot_df["method"].apply(method_display_name)

    fig, ax = plt.subplots(figsize=(8, 4.6))
    ax.bar(plot_df["method_label"], plot_df[metric])

    fig.patch.set_facecolor("#1e1e1e")
    ax.set_facecolor("#1e1e1e")
    ax.tick_params(colors="white")
    ax.title.set_color("white")
    ax.yaxis.label.set_color("white")
    ax.xaxis.label.set_color("white")
    for spine in ax.spines.values():
        spine.set_color("white")

    ax.set_title(f"Model Comparison: {metric_display_name(metric)}")
    ax.set_ylabel(metric_display_name(metric))
    ax.set_xlabel("Model")
    plt.setp(ax.get_xticklabels(), rotation=12, color="white")

    st.pyplot(fig, use_container_width=True)
    plt.close(fig)

    st.caption("This chart updates when you change the chart metric selector above.")
    st.markdown('</div>', unsafe_allow_html=True)


def render_calibration_section(cal_df):
    if cal_df.empty:
        return

    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Calibration Analysis</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="subtle" style="margin-bottom:12px;">Calibration checks whether predicted probabilities match actual outcomes. The dashed diagonal is perfect calibration. Curves below the line are overconfident; curves above it are underconfident.</div>',
        unsafe_allow_html=True,
    )
    st.dataframe(cal_df, use_container_width=True, hide_index=True)
    st.caption(
        """
Points above diagonal → underconfident  
Points below diagonal → overconfident  
Closer to diagonal → better calibration
"""
    )

    fig, ax = plt.subplots(figsize=(7.8, 5.2))

    for method in cal_df["method"].dropna().unique():
        m = cal_df[cal_df["method"] == method].copy().sort_values("avg_pred_home_win_prob")
        ax.plot(
            m["avg_pred_home_win_prob"],
            m["actual_home_win_rate"],
            marker="o",
            linewidth=2.5,
            label=method_display_name(method),
        )

    ax.plot([0, 1], [0, 1], linestyle="--", linewidth=2)

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

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("Average Predicted Home Win Probability")
    ax.set_ylabel("Actual Home Win Rate")
    ax.set_title("Calibration Plot")

    st.pyplot(fig, use_container_width=True)
    plt.close(fig)

    st.markdown('</div>', unsafe_allow_html=True)


def render_prediction_table(pred_df):
    if pred_df.empty:
        return

    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Prediction-Level Inspection</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="subtle" style="margin-bottom:12px;">This table lets you inspect individual predictions. Use the filters to isolate one method or only incorrect picks.</div>',
        unsafe_allow_html=True,
    )

    show_df = pred_df.copy()
    show_df["method_label"] = show_df["method"].apply(method_display_name)
    method_options = ["All"] + sorted(show_df["method_label"].dropna().unique().tolist())

    c1, c2 = st.columns([2, 1])
    with c1:
        method_filter = st.selectbox(
            "Method Filter",
            method_options,
            index=0,
            key="method_filter",
        )
    with c2:
        correctness_filter = st.selectbox(
            "Correctness Filter",
            ["All", "Correct Only", "Incorrect Only"],
            index=0,
            key="correctness_filter",
        )

    if method_filter != "All":
        show_df = show_df[show_df["method_label"] == method_filter].copy()

    if correctness_filter == "Correct Only":
        show_df = show_df[show_df["correct"] == 1].copy()
    elif correctness_filter == "Incorrect Only":
        show_df = show_df[show_df["correct"] == 0].copy()

    cols = [
        "date",
        "away_team",
        "home_team",
        "method_label",
        "home_win_prob",
        "away_win_prob",
        "actual_home_win",
        "correct",
        "confidence",
    ]
    cols = [c for c in cols if c in show_df.columns]
    st.dataframe(show_df[cols].head(100), use_container_width=True, hide_index=True)

    st.markdown('</div>', unsafe_allow_html=True)


def render_disagreement_section(pred_df):
    if pred_df.empty:
        return

    grouped = []
    for (date, away_team, home_team), g in pred_df.groupby(["date", "away_team", "home_team"]):
        if g["method"].nunique() < 2:
            continue
        grouped.append({
            "date": date,
            "away_team": away_team,
            "home_team": home_team,
            "min_home_prob": g["home_win_prob"].min(),
            "max_home_prob": g["home_win_prob"].max(),
            "spread": g["home_win_prob"].max() - g["home_win_prob"].min(),
            "actual_home_win": g["actual_home_win"].iloc[0],
        })

    if not grouped:
        return

    dis_df = pd.DataFrame(grouped).sort_values("spread", ascending=False).head(15)

    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Model Disagreement</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="subtle" style="margin-bottom:12px;">These are the games where the three reasoning modes differed the most. This is useful for qualitative case studies and deeper error analysis.</div>',
        unsafe_allow_html=True,
    )
    st.dataframe(dis_df, use_container_width=True, hide_index=True)
    st.markdown('</div>', unsafe_allow_html=True)


def render_info_density_section(pred_df):
    if pred_df.empty:
        return

    density_cols = [c for c in [
        "info_density_context_tokens",
        "info_density_vector_hits",
        "info_density_youtube_comments",
        "info_density_news_articles",
    ] if c in pred_df.columns]

    if not density_cols or "brier_score" not in pred_df.columns:
        return

    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Information Density vs Prediction Quality (RQ1)</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="subtle" style="margin-bottom:12px;">'
        'Does having more pre-game information improve prediction quality? '
        'Each point is one game-method prediction. Lower Brier score = better. '
        'A positive correlation means more info → worse predictions (harder games). '
        'A negative correlation means more info → better predictions.'
        '</div>',
        unsafe_allow_html=True,
    )

    signal_labels = {
        "info_density_context_tokens": "Context Tokens (total input size)",
        "info_density_vector_hits": "Vector Store Hits (similar past games)",
        "info_density_youtube_comments": "YouTube Comments",
        "info_density_news_articles": "News Articles",
    }

    x_col = st.selectbox(
        "Info density signal",
        density_cols,
        format_func=lambda c: signal_labels.get(c, c),
        key="density_x_col",
    )

    plot_df = pred_df[["method", x_col, "brier_score"]].dropna().copy()
    if plot_df.empty or plot_df[x_col].nunique() < 3:
        st.info("Not enough variation in this signal to plot.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    colors = {"chain_of_thought": "#39d98a", "single_agent": "#8bc1ff", "multi_agent_debate": "#ffd166"}
    fig, ax = plt.subplots(figsize=(9, 5))
    fig.patch.set_facecolor("#1e1e1e")
    ax.set_facecolor("#1e1e1e")

    for method, g in plot_df.groupby("method"):
        ax.scatter(
            g[x_col], g["brier_score"],
            alpha=0.55, s=28,
            color=colors.get(method, "#aaa"),
            label=method_display_name(method),
        )

    # Pearson r annotation
    import numpy as np
    xv = plot_df[x_col].values.astype(float)
    yv = plot_df["brier_score"].values.astype(float)
    if xv.std() > 0 and yv.std() > 0:
        r = float(np.corrcoef(xv, yv)[0, 1])
        ax.annotate(
            f"Pearson r = {r:+.3f}",
            xy=(0.97, 0.05), xycoords="axes fraction",
            ha="right", fontsize=10, color="white",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#1e1e1e", edgecolor="white", alpha=0.7),
        )

    ax.tick_params(colors="white")
    ax.title.set_color("white")
    ax.yaxis.label.set_color("white")
    ax.xaxis.label.set_color("white")
    for spine in ax.spines.values():
        spine.set_color("#555")
    legend = ax.legend()
    plt.setp(legend.get_texts(), color="white")
    legend.get_frame().set_facecolor("#1e1e1e")
    legend.get_frame().set_edgecolor("#555")

    ax.set_xlabel(signal_labels.get(x_col, x_col))
    ax.set_ylabel("Brier Score (lower = better)")
    ax.set_title("Info Density vs Prediction Quality")

    st.pyplot(fig, use_container_width=True)
    plt.close(fig)

    # High vs low info quartile summary
    q25 = plot_df[x_col].quantile(0.25)
    q75 = plot_df[x_col].quantile(0.75)
    hi_brier = plot_df[plot_df[x_col] >= q75]["brier_score"].mean()
    lo_brier = plot_df[plot_df[x_col] <= q25]["brier_score"].mean()
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Low-info Brier (≤25th pct)", f"{lo_brier:.4f}")
    with c2:
        st.metric("High-info Brier (≥75th pct)", f"{hi_brier:.4f}")
    with c3:
        delta = hi_brier - lo_brier
        st.metric("Delta (high − low)", f"{delta:+.4f}", help="Positive = high-info games are harder to predict")

    st.markdown('</div>', unsafe_allow_html=True)


def render_ablation_section():
    import glob
    ablation_files = glob.glob("data/backtest_ablation_*_summary.csv")
    if not ablation_files:
        return

    baseline_df = load_csv_if_exists("data/backtest_summary.csv")
    if baseline_df.empty:
        return

    baseline_cot = baseline_df[baseline_df["method"] == "chain_of_thought"]
    if baseline_cot.empty:
        return
    baseline_brier = float(baseline_cot["brier_score"].iloc[0])

    rows = []
    for fpath in sorted(ablation_files):
        source = os.path.basename(fpath).replace("backtest_ablation_", "").replace("_summary.csv", "")
        df = load_csv_if_exists(fpath)
        if df.empty:
            continue
        cot_row = df[df["method"] == "chain_of_thought"]
        if cot_row.empty:
            continue
        ablation_brier = float(cot_row["brier_score"].iloc[0])
        rows.append({
            "source": source,
            "ablation_brier": round(ablation_brier, 4),
            "brier_delta": round(ablation_brier - baseline_brier, 4),
            "n_games": int(cot_row["n_games"].iloc[0]),
        })

    if not rows:
        return

    abl_df = pd.DataFrame(rows).sort_values("brier_delta", ascending=False)

    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Ablation Study — Per-Source Impact (RQ3)</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="subtle" style="margin-bottom:12px;">'
        f'CoT baseline Brier = <strong>{baseline_brier:.4f}</strong>. '
        f'Each bar shows how much Brier score increases (gets worse) when that data source is removed. '
        f'Larger positive delta = that source matters more.'
        f'</div>',
        unsafe_allow_html=True,
    )

    st.dataframe(abl_df, use_container_width=True, hide_index=True)

    fig, ax = plt.subplots(figsize=(9, 4.5))
    fig.patch.set_facecolor("#1e1e1e")
    ax.set_facecolor("#1e1e1e")

    bar_colors = ["#ff6b6b" if d > 0 else "#39d98a" for d in abl_df["brier_delta"]]
    bars = ax.bar(abl_df["source"], abl_df["brier_delta"], color=bar_colors, edgecolor="#555")

    ax.axhline(0, color="white", linewidth=1, linestyle="--", alpha=0.5)
    ax.tick_params(colors="white")
    ax.title.set_color("white")
    ax.yaxis.label.set_color("white")
    ax.xaxis.label.set_color("white")
    for spine in ax.spines.values():
        spine.set_color("#555")

    for bar, val in zip(bars, abl_df["brier_delta"]):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.001 if val >= 0 else bar.get_height() - 0.003,
            f"{val:+.4f}", ha="center", va="bottom" if val >= 0 else "top",
            color="white", fontsize=9,
        )

    ax.set_xlabel("Disabled Source")
    ax.set_ylabel("Brier Delta vs Baseline (↑ = worse)")
    ax.set_title("Ablation: Which Sources Matter Most?")
    plt.setp(ax.get_xticklabels(), color="white")

    st.pyplot(fig, use_container_width=True)
    plt.close(fig)

    most_impactful = abl_df.iloc[0]["source"]
    st.caption(
        f"Most impactful source removed: **{most_impactful}** "
        f"(Δ Brier = {abl_df.iloc[0]['brier_delta']:+.4f}). "
        f"Sources with near-zero delta had no historical data available in backtest context."
    )
    st.markdown('</div>', unsafe_allow_html=True)


def main():
    render_header()

    n_games, season, min_hist, run_now = render_controls()

    if run_now:
        with st.spinner("Running backtest. This can take a while because each game runs three reasoning modes..."):
            completed = run_backtest_from_ui(n_games, season, min_hist)
            if completed.returncode != 0:
                st.error("Backtest failed.")
                st.code(completed.stderr if completed.stderr else completed.stdout, language="text")
                st.stop()
            st.success("Backtest completed.")
            st.code(completed.stdout[-4000:], language="text")
            load_csv_if_exists.clear()
            load_json_if_exists.clear()

    summary_df = load_csv_if_exists(SUMMARY_PATH)
    pred_df = load_csv_if_exists(PRED_PATH)
    cal_df = load_csv_if_exists(CAL_PATH)
    meta = load_json_if_exists(META_PATH)

    if summary_df.empty:
        st.warning("No backtest results found yet. Run a backtest from the controls above.")
        st.stop()

    render_run_health(meta)
    render_summary_section(summary_df)
    render_metric_comparison_charts(summary_df)
    render_calibration_section(cal_df)
    render_info_density_section(pred_df)
    render_ablation_section()
    render_prediction_table(pred_df)
    render_disagreement_section(pred_df)


if __name__ == "__main__":
    main()