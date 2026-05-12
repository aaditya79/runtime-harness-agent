import os
import io
import json
import html
import time
from dotenv import load_dotenv

load_dotenv()

# Streamlit Cloud stores secrets in st.secrets — pull them into os.environ
# so the rest of the app (which reads os.environ) finds them.
try:
    import streamlit as st
    for _key in ("ANTHROPIC_API_KEY", "ODDS_API_KEY", "YOUTUBE_API_KEY"):
        if _key not in os.environ and hasattr(st, "secrets") and _key in st.secrets:
            os.environ[_key] = st.secrets[_key]
except Exception:
    pass
import contextlib
import streamlit as st
import pandas as pd
from datetime import datetime

from nba_agent import (
    tool_get_team_stats,
    tool_get_head_to_head,
    tool_get_injuries,
    tool_get_odds,
    tool_search_similar_games,
    tool_get_team_sentiment,
    run_agent,
)
from nba_multi_agent import run_full_debate, AGENTS
from nba_cot_baseline import run_cot_analysis


TEAMS = {
    "Atlanta Hawks": "ATL", "Boston Celtics": "BOS", "Brooklyn Nets": "BKN",
    "Charlotte Hornets": "CHA", "Chicago Bulls": "CHI", "Cleveland Cavaliers": "CLE",
    "Dallas Mavericks": "DAL", "Denver Nuggets": "DEN", "Detroit Pistons": "DET",
    "Golden State Warriors": "GSW", "Houston Rockets": "HOU", "Indiana Pacers": "IND",
    "LA Clippers": "LAC", "Los Angeles Lakers": "LAL", "Memphis Grizzlies": "MEM",
    "Miami Heat": "MIA", "Milwaukee Bucks": "MIL", "Minnesota Timberwolves": "MIN",
    "New Orleans Pelicans": "NOP", "New York Knicks": "NYK", "Oklahoma City Thunder": "OKC",
    "Orlando Magic": "ORL", "Philadelphia 76ers": "PHI", "Phoenix Suns": "PHX",
    "Portland Trail Blazers": "POR", "Sacramento Kings": "SAC", "San Antonio Spurs": "SAS",
    "Toronto Raptors": "TOR", "Utah Jazz": "UTA", "Washington Wizards": "WAS",
}

TEAM_LOGOS = {
    "ATL": "https://a.espncdn.com/i/teamlogos/nba/500/atl.png",
    "BOS": "https://a.espncdn.com/i/teamlogos/nba/500/bos.png",
    "BKN": "https://a.espncdn.com/i/teamlogos/nba/500/bkn.png",
    "CHA": "https://a.espncdn.com/i/teamlogos/nba/500/cha.png",
    "CHI": "https://a.espncdn.com/i/teamlogos/nba/500/chi.png",
    "CLE": "https://a.espncdn.com/i/teamlogos/nba/500/cle.png",
    "DAL": "https://a.espncdn.com/i/teamlogos/nba/500/dal.png",
    "DEN": "https://a.espncdn.com/i/teamlogos/nba/500/den.png",
    "DET": "https://a.espncdn.com/i/teamlogos/nba/500/det.png",
    "GSW": "https://a.espncdn.com/i/teamlogos/nba/500/gsw.png",
    "HOU": "https://a.espncdn.com/i/teamlogos/nba/500/hou.png",
    "IND": "https://a.espncdn.com/i/teamlogos/nba/500/ind.png",
    "LAC": "https://a.espncdn.com/i/teamlogos/nba/500/lac.png",
    "LAL": "https://a.espncdn.com/i/teamlogos/nba/500/lal.png",
    "MEM": "https://a.espncdn.com/i/teamlogos/nba/500/mem.png",
    "MIA": "https://a.espncdn.com/i/teamlogos/nba/500/mia.png",
    "MIL": "https://a.espncdn.com/i/teamlogos/nba/500/mil.png",
    "MIN": "https://a.espncdn.com/i/teamlogos/nba/500/min.png",
    "NOP": "https://a.espncdn.com/i/teamlogos/nba/500/no.png",
    "NYK": "https://a.espncdn.com/i/teamlogos/nba/500/ny.png",
    "OKC": "https://a.espncdn.com/i/teamlogos/nba/500/okc.png",
    "ORL": "https://a.espncdn.com/i/teamlogos/nba/500/orl.png",
    "PHI": "https://a.espncdn.com/i/teamlogos/nba/500/phi.png",
    "PHX": "https://a.espncdn.com/i/teamlogos/nba/500/phx.png",
    "POR": "https://a.espncdn.com/i/teamlogos/nba/500/por.png",
    "SAC": "https://a.espncdn.com/i/teamlogos/nba/500/sac.png",
    "SAS": "https://a.espncdn.com/i/teamlogos/nba/500/sas.png",
    "TOR": "https://a.espncdn.com/i/teamlogos/nba/500/tor.png",
    "UTA": "https://a.espncdn.com/i/teamlogos/nba/500/uta.png",
    "WAS": "https://a.espncdn.com/i/teamlogos/nba/500/wsh.png",
}


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
        --yellow: #ffd166;
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
        max-width: 1280px;
        padding-top: 1.5rem;
        padding-bottom: 2.5rem;
    }

    #MainMenu, header, footer {
        visibility: hidden;
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

    .glass-card {
        background: rgba(20, 45, 66, 0.18);
        border: 1px solid rgba(255,255,255,0.14);
        border-radius: 22px;
        padding: 18px 18px 16px 18px;
        box-shadow: var(--shadow);
        backdrop-filter: blur(12px);
        margin-bottom: 16px;
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

    .method-card {
        background: rgba(255,255,255,0.08);
        border: 1px solid rgba(255,255,255,0.12);
        border-radius: 18px;
        padding: 14px;
        height: 100%;
    }

    .method-title {
        font-weight: 700;
        margin-bottom: 6px;
        color: var(--text);
    }

    .method-copy {
        color: var(--muted);
        font-size: 0.88rem;
        line-height: 1.55;
    }

    .score-card {
        background: rgba(255,255,255,0.08);
        border: 1px solid rgba(255,255,255,0.12);
        border-radius: 20px;
        padding: 16px;
        text-align: center;
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

    .metric-chip {
        background: rgba(255,255,255,0.08);
        border: 1px solid rgba(255,255,255,0.12);
        border-radius: 16px;
        padding: 12px 14px;
        margin-bottom: 10px;
    }

    .metric-chip .k {
        color: var(--soft);
        font-size: 0.76rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        font-weight: 700;
        margin-bottom: 4px;
    }

    .metric-chip .v {
        color: var(--text);
        font-size: 1.12rem;
        font-weight: 700;
    }

    .team-block {
        display: flex;
        align-items: center;
        gap: 12px;
    }

    .team-name {
        font-size: 1.15rem;
        font-weight: 700;
        color: var(--text);
    }

    .team-abbr {
        font-size: 0.86rem;
        color: var(--muted);
        font-weight: 600;
    }

    .vs-text {
        color: var(--soft);
        font-size: 1.1rem;
        font-weight: 800;
    }

    .ring-card {
        flex: 1;
        min-width: 220px;
        background: rgba(255,255,255,0.07);
        border: 1px solid rgba(255,255,255,0.11);
        border-radius: 20px;
        padding: 18px;
        text-align: center;
    }

    .ring {
        width: 130px;
        height: 130px;
        border-radius: 50%;
        margin: 0 auto 10px auto;
        display: flex;
        align-items: center;
        justify-content: center;
        position: relative;
    }

    .ring::before {
        content: "";
        width: 92px;
        height: 92px;
        background: rgba(36, 64, 88, 0.98);
        border-radius: 50%;
        position: absolute;
    }

    .ring-inner {
        position: relative;
        z-index: 1;
        text-align: center;
    }

    .ring-pct {
        font-size: 1.9rem;
        font-weight: 800;
        line-height: 1;
    }

    .ring-team {
        font-size: 0.82rem;
        color: var(--muted);
        margin-top: 6px;
        font-weight: 600;
    }

    .factor-box {
        background: rgba(255,255,255,0.07);
        border: 1px solid rgba(255,255,255,0.11);
        border-radius: 18px;
        padding: 14px;
        height: 100%;
    }

    .factor-top {
        display: flex;
        justify-content: space-between;
        gap: 8px;
        margin-bottom: 8px;
        align-items: center;
    }

    .factor-badge {
        border-radius: 999px;
        padding: 4px 10px;
        font-size: 0.72rem;
        font-weight: 700;
    }

    .factor-home { background: rgba(57,217,138,0.18); color: #98f0be; }
    .factor-away { background: rgba(255,107,107,0.18); color: #ffb1b1; }
    .factor-neutral { background: rgba(139,193,255,0.18); color: #cbe3ff; }

    .factor-importance {
        color: var(--soft);
        font-size: 0.75rem;
        text-transform: uppercase;
        font-weight: 700;
    }

    .factor-text {
        color: var(--text);
        font-size: 0.94rem;
        line-height: 1.55;
    }

    .bar-wrap {
        margin-top: 10px;
    }

    .bar-label {
        display: flex;
        justify-content: space-between;
        color: var(--muted);
        font-size: 0.84rem;
        margin-bottom: 6px;
    }

    .bar {
        width: 100%;
        height: 10px;
        border-radius: 999px;
        background: rgba(255,255,255,0.10);
        overflow: hidden;
    }

    .bar-fill-green {
        height: 100%;
        border-radius: 999px;
        background: linear-gradient(90deg, #39d98a, #9cf1c0);
    }

    .bar-fill-red {
        height: 100%;
        border-radius: 999px;
        background: linear-gradient(90deg, #ff8e8e, #ff6b6b);
    }

    .text-panel {
        background: rgba(255,255,255,0.07);
        border: 1px solid rgba(255,255,255,0.11);
        border-radius: 18px;
        padding: 16px;
        color: var(--text);
        line-height: 1.7;
        font-size: 0.95rem;
    }

    .verdict-card {
        background: linear-gradient(135deg, rgba(57,217,138,0.15), rgba(139,193,255,0.11));
        border: 1px solid rgba(255,255,255,0.15);
        border-radius: 22px;
        padding: 18px;
        box-shadow: var(--shadow);
    }

    .verdict-title {
        font-size: 0.82rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--soft);
        font-weight: 800;
        margin-bottom: 8px;
    }

    .verdict-main {
        font-size: 1.45rem;
        font-weight: 800;
        color: var(--text);
        line-height: 1.25;
        margin-bottom: 8px;
    }

    .verdict-sub {
        color: var(--muted);
        font-size: 0.95rem;
        line-height: 1.6;
    }

    .footer-note {
        color: rgba(247,251,255,0.65);
        text-align: center;
        font-size: 0.82rem;
        margin-top: 24px;
    }

    .live-trace-card {
        background: rgba(20, 45, 66, 0.24);
        border: 1px solid rgba(255,255,255,0.16);
        border-radius: 22px;
        padding: 18px;
        box-shadow: var(--shadow);
        backdrop-filter: blur(12px);
        margin-bottom: 16px;
    }

    .live-trace-top {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 16px;
        margin-bottom: 12px;
    }

    .live-trace-label {
        font-size: 1rem;
        font-weight: 700;
        color: var(--text);
    }

    .live-trace-pill {
        border-radius: 999px;
        padding: 6px 12px;
        background: rgba(139,193,255,0.18);
        border: 1px solid rgba(139,193,255,0.22);
        color: #d7ebff;
        font-size: 0.78rem;
        font-weight: 700;
        white-space: nowrap;
    }

    .live-trace-box {
        background: rgba(255,255,255,0.06);
        border: 1px solid rgba(255,255,255,0.10);
        border-radius: 16px;
        padding: 14px;
        max-height: 320px;
        overflow-y: auto;
    }

    .live-trace-box pre {
        margin: 0;
        white-space: pre-wrap;
        font-size: 0.88rem;
        line-height: 1.6;
        color: var(--text);
        font-family: 'Inter', sans-serif;
    }

    .trace-help {
        color: var(--muted);
        font-size: 0.88rem;
        margin-bottom: 10px;
    }

    .legend-grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 10px;
        margin-bottom: 12px;
    }

    .legend-chip {
        background: rgba(255,255,255,0.06);
        border: 1px solid rgba(255,255,255,0.10);
        border-radius: 16px;
        padding: 10px 12px;
        font-size: 0.84rem;
        color: var(--muted);
        line-height: 1.45;
    }

    .stButton > button {
        border-radius: 14px;
        border: 0;
        background: linear-gradient(135deg, #9ec8ff, #71afff);
        color: #0b2337;
        font-weight: 800;
        padding: 0.72rem 1.25rem;
        box-shadow: var(--shadow);
    }

    .stDownloadButton > button {
        border-radius: 14px;
        border: 1px solid rgba(255,255,255,0.14);
        background: rgba(255,255,255,0.12);
        color: white;
        font-weight: 700;
    }

    .stRadio > div {
        background: transparent;
        padding: 0;
        border: none;
    }

    div[data-baseweb="select"] > div {
        background: rgba(255,255,255,0.12) !important;
        border: 1px solid rgba(255,255,255,0.16) !important;
        border-radius: 14px !important;
        color: white !important;
    }

    .stDateInput > div > div {
        background: rgba(255,255,255,0.12) !important;
        border: 1px solid rgba(255,255,255,0.16) !important;
        border-radius: 14px !important;
    }

    .stDateInput input {
        color: white !important;
        background: transparent !important;
    }

    .stTextInput input,
    input {
        color: white !important;
    }

    label, .stDateInput label, .stSelectbox label {
        color: var(--muted) !important;
        font-weight: 600 !important;
    }

    hr {
        display: none !important;
    }
</style>
"""


class StreamlitTraceWriter:
    def __init__(self, container, mode):
        self.container = container
        self.mode = mode
        self.buffer = ""
        self.last_render = 0.0

    def write(self, text):
        if not text:
            return 0

        if isinstance(text, bytes):
            text = text.decode("utf-8", errors="ignore")

        self.buffer += text
        now = time.time()
        if "\n" in text or (now - self.last_render) > 0.20:
            self.render()
        return len(text)

    def flush(self):
        try:
            self.render(final=True)

        except Exception:
            pass

    def render(self, final=False):
        lines = [line.rstrip() for line in self.buffer.splitlines() if line.strip()]
        status_label = extract_live_status(lines, self.mode, final=final)
        recent_lines = "\n".join(lines[-14:]) if lines else "Starting analysis..."
        safe_recent = html.escape(recent_lines)
        safe_status = html.escape(status_label)

        self.container.markdown(
            f"""
            <div class="live-trace-card">
                <div class="live-trace-top">
                    <div class="live-trace-label">Live Analysis Progress</div>
                    <div class="live-trace-pill">{safe_status}</div>
                </div>
                <div class="trace-help">
                    This updates as the model gathers evidence, calls tools, and builds its final view.
                </div>
                <div class="live-trace-box">
                    <pre>{safe_recent}</pre>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        self.last_render = time.time()


def extract_live_status(lines, mode, final=False):
    if final:
        return "Analysis complete"

    if not lines:
        return "Starting analysis..."

    for line in reversed(lines):
        s = line.strip()
        if not s:
            continue

        if "MODERATOR SYNTHESIS" in s:
            return "Synthesizing final report"
        if "DEBATE ROUND" in s:
            return s.title()
        if "PHASE 1: INDEPENDENT ANALYSIS" in s:
            return "Running independent agent analysis"
        if s in [cfg["name"] for cfg in AGENTS.values()]:
            return f"Working on {s}"
        if s.startswith("Step "):
            return s if len(s) < 90 else s[:87] + "..."
        if s.startswith("Getting "):
            return s
        if "Running chain-of-thought analysis" in s:
            return "Running one-pass reasoning"
        if "FINAL REPORT" in s:
            return "Preparing final answer"

    return f"Running {mode}..."


def run_with_live_trace(fn, live_container, mode, *args, **kwargs):
    writer = StreamlitTraceWriter(live_container, mode)
    with contextlib.redirect_stdout(writer):
        result = fn(*args, **kwargs)
    writer.flush()
    return result, writer.buffer


def render_header(llm_name):
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    st.markdown(
        """
        <div class="top-banner">
            <strong>Research purposes only.</strong> MatchOdds AI is an experimental game analysis interface for studying matchup edges, team context, injuries, and pricing signals. It is <strong>not financial advice</strong>.
        </div>
        """,
        unsafe_allow_html=True
    )
    st.markdown(
        f"""
        <div class="hero">
            <div class="hero-left">
                <h1>MatchOdds AI</h1>
                <p>NBA matchup analysis with cleaner reasoning, clearer metrics, and side-by-side model views.</p>
            </div>
            <div class="hero-pill">Model Engine: {llm_name}</div>
        </div>
        """,
        unsafe_allow_html=True
    )


def render_method_guide():
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Analysis Types</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(
            """
            <div class="method-card">
                <div class="method-title">Multi-Agent Debate</div>
                <div class="method-copy">
                    Best for deeper analysis. Multiple specialized agents challenge each other before a final synthesis. More robust, slower, and usually the most complete.
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
    with c2:
        st.markdown(
            """
            <div class="method-card">
                <div class="method-title">Single Agent</div>
                <div class="method-copy">
                    One analyst pulls evidence and produces a direct recommendation. Faster and simpler, with less cross-checking than the debate mode.
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
    with c3:
        st.markdown(
            """
            <div class="method-card">
                <div class="method-title">Chain-of-Thought</div>
                <div class="method-copy">
                    Most transparent linear reasoning path. Good when you want to inspect the logic step by step without multiple agent disagreement layers.
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
    st.markdown('</div>', unsafe_allow_html=True)


def render_matchup_header(home_team, away_team, home_abbr, away_abbr, game_date):
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Matchup</div>', unsafe_allow_html=True)

    c1, c2, c3 = st.columns([3, 1, 3])
    with c1:
        st.markdown(
            f"""
            <div class="team-block">
                <img src="{TEAM_LOGOS.get(away_abbr, '')}" width="52">
                <div>
                    <div class="team-name">{away_team}</div>
                    <div class="team-abbr">Away · {away_abbr}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
    with c2:
        st.markdown('<div style="text-align:center; padding-top:12px;" class="vs-text">@</div>', unsafe_allow_html=True)
    with c3:
        st.markdown(
            f"""
            <div class="team-block" style="justify-content:flex-end;">
                <div style="text-align:right;">
                    <div class="team-name">{home_team}</div>
                    <div class="team-abbr">Home · {home_abbr}</div>
                </div>
                <img src="{TEAM_LOGOS.get(home_abbr, '')}" width="52">
            </div>
            """,
            unsafe_allow_html=True
        )

    st.markdown(
        f"""
        <div style="margin-top:14px;" class="subtle">
            Game date: <strong>{game_date.strftime('%A, %B %d, %Y')}</strong>
        </div>
        """,
        unsafe_allow_html=True
    )
    st.markdown('</div>', unsafe_allow_html=True)

def safe_load_json(raw, default=None):
    try:
        return json.loads(raw)
    except Exception:
        return default if default is not None else {}

def render_team_snapshot(home_team, away_team, home_abbr, away_abbr):
    home_stats = safe_load_json(tool_get_team_stats(home_abbr), {})
    away_stats = safe_load_json(tool_get_team_stats(away_abbr), {})

    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Team Snapshot</div>', unsafe_allow_html=True)

    col1, col2 = st.columns(2)

    def render_metric(label, value):
        st.markdown(
            f"""
            <div class="metric-chip">
                <div class="k">{label}</div>
                <div class="v">{value}</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    # LEFT = AWAY TEAM
    with col1:
        st.markdown(f"#### {away_team}")

        pm = away_stats.get("avg_plus_minus_last_10", "N/A")
        fg = away_stats.get("avg_fg_pct_last_10", None)

        pm_text = f"{pm:+.1f}" if isinstance(pm, (int, float)) else str(pm)
        fg_text = f"{fg:.1%}" if isinstance(fg, (int, float)) else "N/A"

        render_metric("Season Record", away_stats.get("season_record", "N/A"))
        render_metric("Last 10", away_stats.get("last_10_record", "N/A"))
        render_metric("Avg Pts Last 10", away_stats.get("avg_points_last_10", "N/A"))
        render_metric("Avg +/- Last 10", pm_text)
        render_metric("FG% Last 10", fg_text)

    # RIGHT = HOME TEAM
    with col2:
        st.markdown(f"#### {home_team}")

        pm = home_stats.get("avg_plus_minus_last_10", "N/A")
        fg = home_stats.get("avg_fg_pct_last_10", None)

        pm_text = f"{pm:+.1f}" if isinstance(pm, (int, float)) else str(pm)
        fg_text = f"{fg:.1%}" if isinstance(fg, (int, float)) else "N/A"

        render_metric("Season Record", home_stats.get("season_record", "N/A"))
        render_metric("Last 10", home_stats.get("last_10_record", "N/A"))
        render_metric("Avg Pts Last 10", home_stats.get("avg_points_last_10", "N/A"))
        render_metric("Avg +/- Last 10", pm_text)
        render_metric("FG% Last 10", fg_text)

    st.markdown('</div>', unsafe_allow_html=True)


def render_injury_summary(home_team, away_team):

    home_inj = safe_load_json(tool_get_injuries(home_team), [])

    away_inj = safe_load_json(tool_get_injuries(away_team), [])

    st.markdown('<div class="glass-card">', unsafe_allow_html=True)

    st.markdown('<div class="section-title">Injury & Availability</div>', unsafe_allow_html=True)

    c1, c2 = st.columns(2)

    def team_inj(col, team_name, injuries):

        with col:

            st.markdown(f"#### {team_name}")

            if not injuries:

                st.markdown('<div class="text-panel">No reported injuries.</div>', unsafe_allow_html=True)

                return

            rows = []

            for inj in injuries[:8]:
                player = inj.get("player", "")
                status = inj.get("status", "")
                pos = inj.get("position", "")
                comment = inj.get("comment", "")

                # Skip rows where key fields are NaN/empty
                import math
                def _is_blank(v):
                    if v is None: return True
                    if isinstance(v, float) and math.isnan(v): return True
                    return str(v).strip().lower() in ("", "nan", "none")

                if _is_blank(player) and _is_blank(status):
                    continue

                player = "Unknown" if _is_blank(player) else str(player)
                status = "" if _is_blank(status) else str(status)
                pos = "" if _is_blank(pos) else str(pos)
                comment = "" if _is_blank(comment) else str(comment)[:110]

                color = "#ff6b6b" if status.lower() == "out" else "#ffd166"

                rows.append(
                    f"<div style='margin-bottom:10px;'><strong style='color:{color};'>{status}</strong> · {player}"
                    f"<span style='color:rgba(247,251,255,0.7);'>{' (' + pos + ')' if pos else ''}</span>"
                    f"{'<br><span style=\"color:rgba(247,251,255,0.72); font-size:0.88rem;\">' + comment + '</span>' if comment else ''}</div>"
                )

            if rows:
                st.markdown(f"<div class='text-panel'>{''.join(rows)}</div>", unsafe_allow_html=True)
            else:
                st.markdown('<div class="text-panel">No reported injuries.</div>', unsafe_allow_html=True)

    # LEFT = AWAY, RIGHT = HOME

    team_inj(c1, away_team, away_inj)

    team_inj(c2, home_team, home_inj)

    st.markdown('</div>', unsafe_allow_html=True)

def load_team_sentiment(team_abbr):
    raw = tool_get_team_sentiment(team_abbr)
    return safe_load_json(raw, {})

def sentiment_color(value):
    if not isinstance(value, (int, float)):
        return "blue"
    if value > 0.05:
        return "green"
    if value < -0.05:
        return "red"
    return "blue"

def render_sentiment_summary(home_team, away_team, home_abbr, away_abbr):
    home_sent = load_team_sentiment(home_abbr)
    away_sent = load_team_sentiment(away_abbr)

    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Media Sentiment & Coverage</div>', unsafe_allow_html=True)

    c1, c2 = st.columns(2)

    def render_metric_card(label, value):
        st.markdown(
            f"""
            <div class="metric-chip">
                <div class="k">{label}</div>
                <div class="v">{value}</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    def render_team_sentiment(col, team_name, sent):
        avg_sent = sent.get("avg_sentiment", 0.0)
        article_count = sent.get("article_count", 0)
        pos_count = sent.get("positive_article_count", 0)
        neg_count = sent.get("negative_article_count", 0)
        label = sent.get("sentiment_label", "neutral").capitalize()

        color_class = sentiment_color(avg_sent)
        avg_sent_text = f"{avg_sent:+.3f}" if isinstance(avg_sent, (int, float)) else "N/A"

        with col:
            st.markdown(f"#### {team_name}")

            st.markdown(
                f"""
                <div class="score-card" style="margin-bottom:12px;">
                    <div class="score-label">Average Sentiment</div>
                    <div class="score-value {color_class}">{avg_sent_text}</div>
                    <div class="subtle" style="margin-top:8px;">{label} coverage</div>
                </div>
                """,
                unsafe_allow_html=True
            )

            render_metric_card("Article Count", article_count)
            render_metric_card("Positive Articles", pos_count)
            render_metric_card("Negative Articles", neg_count)

    # LEFT = AWAY, RIGHT = HOME
    render_team_sentiment(c1, away_team, away_sent)
    render_team_sentiment(c2, home_team, home_sent)

    st.markdown(
        """
        <div class="subtle" style="margin-top:10px;">
            Sentiment is derived from recent NBA news headlines and summaries. It is a secondary contextual signal, not a replacement for stats, injuries, or odds.
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown('</div>', unsafe_allow_html=True)

def get_prediction_block(report_json):

    pred = (
        report_json.get("prediction")
        or report_json.get("synthesized_prediction")
        or report_json.get("agent_prediction", {})
    )

    home_prob = pred.get("home_win_prob", 0.5)
    away_prob = pred.get("away_win_prob", 0.5)
    confidence = pred.get("confidence", "Medium")
    return pred, home_prob, away_prob, confidence

def render_market_divergence(report_json, home_team, away_team):
    """Show bookmaker consensus odds and flag divergence vs agent probability."""
    try:
        odds_df = pd.read_csv("data/odds_live.csv")
        odds_df = odds_df[odds_df["MARKET"] == "h2h"].copy()
    except Exception:
        return

    home_rows = odds_df[odds_df["HOME_TEAM"].str.lower().str.contains(home_team.split()[-1].lower(), na=False)]
    if home_rows.empty:
        return

    # Compute market consensus: average implied home/away probability across books
    def american_to_prob(odds_val):
        try:
            o = float(odds_val)
            return 100 / (o + 100) if o > 0 else abs(o) / (abs(o) + 100)
        except Exception:
            return None

    home_probs, away_probs = [], []
    for _, row in home_rows.iterrows():
        try:
            h = american_to_prob(row.get("HOME_ODDS") or row.get("PRICE"))
            a = american_to_prob(row.get("AWAY_ODDS"))
            if h and a:
                total = h + a
                home_probs.append(h / total)
                away_probs.append(a / total)
        except Exception:
            continue

    if not home_probs:
        return

    market_home = sum(home_probs) / len(home_probs)
    market_away = sum(away_probs) / len(away_probs)

    _, agent_home, agent_away, _ = get_prediction_block(report_json)
    if not isinstance(agent_home, (int, float)):
        return

    divergence = abs(agent_home - market_home)

    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Market Odds Comparison</div>', unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric(f"{home_team} — Agent", f"{agent_home:.0%}")
    with c2:
        st.metric(f"{home_team} — Market consensus", f"{market_home:.0%}",
                  delta=f"{agent_home - market_home:+.0%} vs market")
    with c3:
        st.metric("Bookmakers sampled", str(len(home_probs)))

    if divergence >= 0.05:
        direction = "higher" if agent_home > market_home else "lower"
        st.warning(
            f"⚡ **Divergence detected ({divergence:.0%}):** The agent's home win probability is "
            f"{divergence:.0%} {direction} than the market consensus. "
            f"This may indicate an edge or a model blind spot worth investigating."
        )
    else:
        st.success(f"Agent and market are aligned (divergence {divergence:.0%} < 5% threshold).")

    st.markdown('</div>', unsafe_allow_html=True)


def render_similar_games(home_abbr, away_abbr, home_team, away_team):
    """Surface top similar historical matchups from the vector store."""
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Similar Past Matchups</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="subtle" style="margin-bottom:12px;">'
        'Historical games retrieved from ChromaDB based on semantic similarity to this matchup context. '
        'Used by the agent to ground predictions in real precedent.'
        '</div>',
        unsafe_allow_html=True,
    )

    try:
        raw_home = tool_search_similar_games(
            query_text=f"{home_abbr} home game recent form matchup",
            team=home_abbr, n_results=3,
        )
        raw_away = tool_search_similar_games(
            query_text=f"{away_abbr} away game recent form matchup",
            team=away_abbr, n_results=2,
        )
        hits = []
        for raw in [raw_home, raw_away]:
            if isinstance(raw, str):
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, list):
                        hits.extend(parsed)
                except Exception:
                    pass
            elif isinstance(raw, list):
                hits.extend(raw)

        if not hits:
            st.info("No similar games found in the vector store.")
            st.markdown('</div>', unsafe_allow_html=True)
            return

        seen = set()
        unique_hits = []
        for h in hits:
            key = h.get("game_description", "")[:60]
            if key not in seen:
                seen.add(key)
                unique_hits.append(h)

        for hit in unique_hits[:5]:
            desc = hit.get("game_description", "Unknown game")
            outcome = hit.get("outcome", "")
            similarity = hit.get("similarity_score") or hit.get("distance")
            outcome_emoji = "✅" if str(outcome).lower() in ("w", "win", "1") else "❌" if str(outcome).lower() in ("l", "loss", "0") else "—"
            sim_str = f" · similarity {float(similarity):.3f}" if similarity is not None else ""
            st.markdown(
                f'<div style="padding:8px 12px;margin-bottom:8px;background:rgba(255,255,255,0.07);'
                f'border-radius:10px;border-left:3px solid rgba(139,193,255,0.6);">'
                f'<span style="font-size:0.88rem;color:#f7fbff;">{outcome_emoji} {desc}</span>'
                f'<span style="font-size:0.78rem;color:rgba(247,251,255,0.55);">{sim_str}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

    except Exception as e:
        st.caption(f"Similar games unavailable: {e}")

    st.markdown('</div>', unsafe_allow_html=True)


def render_prediction_visuals(report_json, home_team, away_team):
    _, home_prob, away_prob, confidence = get_prediction_block(report_json)
    home_pct = int(round((home_prob if isinstance(home_prob, (int, float)) else 0.5) * 100))
    away_pct = int(round((away_prob if isinstance(away_prob, (int, float)) else 0.5) * 100))

    conf_map = {"low": 36, "medium": 62, "high": 82}
    conf_score = conf_map.get(str(confidence).lower(), 62)

    gap_pp = abs(home_pct - away_pct)

    if gap_pp >= 30:
        gap_explainer = "Large separation between the two teams. The model sees one side as a clear favorite."
    elif gap_pp >= 15:
        gap_explainer = "Moderate edge for one team. There is a real lean, but it is not overwhelming."
    else:
        gap_explainer = "Close matchup. The model does not see much separation between the two teams."

    confidence_explainer = {
        "low": "The model sees meaningful uncertainty or conflicting signals.",
        "medium": "The model sees a real edge, but not a decisive one.",
        "high": "The model sees a strong edge supported by multiple signals.",
    }.get(str(confidence).lower(), "The model sees a moderate level of certainty.")

    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Win Probability</div>', unsafe_allow_html=True)

    c1, c2, c3 = st.columns([2, 2, 1.8])

    with c1:
        st.markdown(
            f"""
            <div class="ring-card">
                <div class="score-label">{home_team} Win</div>
                <div class="ring" style="background: conic-gradient(#35d07f 0% {home_pct}%, rgba(255,255,255,0.10) {home_pct}% 100%);">
                    <div class="ring-inner">
                        <div class="ring-pct" style="color:#87f2b5;">{home_pct}%</div>
                        <div class="ring-team">Home</div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c2:
        st.markdown(
            f"""
            <div class="ring-card">
                <div class="score-label">{away_team} Win</div>
                <div class="ring" style="background: conic-gradient(#ff6b6b 0% {away_pct}%, rgba(255,255,255,0.10) {away_pct}% 100%);">
                    <div class="ring-inner">
                        <div class="ring-pct" style="color:#ffb3b3;">{away_pct}%</div>
                        <div class="ring-team">Away</div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c3:
        conf_label = str(confidence).capitalize()

        st.markdown(
            f"""
            <div class="score-card">
                <div class="score-label">Confidence</div>
                <div class="score-value blue">{conf_label}</div>
                <div class="subtle" style="margin-top:8px; margin-bottom:14px;">
                    {confidence_explainer}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            f"""
            <div class="subtle" style="margin-top:12px; margin-bottom:6px;">
                <strong>Confidence Score:</strong> {conf_score}/100
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.progress(conf_score / 100.0)

        st.markdown(
            f"""
            <div class="subtle" style="margin-top:16px; margin-bottom:6px;">
                <strong>Win Probability Gap:</strong> {gap_pp} percentage points
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.progress(min(gap_pp, 100) / 100.0)

        st.markdown(
            f"""
            <div class="subtle" style="margin-top:12px;">
                {gap_explainer}
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown('</div>', unsafe_allow_html=True)


def render_key_factors(factors):
    if not factors:
        return

    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Key Factors</div>', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="subtle" style="margin-bottom:12px;">
            These are the main drivers behind the prediction.
        </div>
        <div class="legend-grid">
            <div class="legend-chip"><strong>Favors Home Team</strong><br>Pushes the model toward the home team.</div>
            <div class="legend-chip"><strong>Favors Away Team</strong><br>Pushes the model toward the away team.</div>
            <div class="legend-chip"><strong>Mixed / Neutral</strong><br>Provides context but does not clearly favor one side.</div>
            <div class="legend-chip"><strong>High Importance</strong><br>A major driver of the prediction.</div>
            <div class="legend-chip"><strong>Medium Importance</strong><br>Meaningful, but not decisive by itself.</div>
            <div class="legend-chip"><strong>Low Importance</strong><br>A minor supporting signal.</div>
        </div>
        """,
        unsafe_allow_html=True
    )

    cols = st.columns(2)
    for i, f in enumerate(factors):
        impact = str(f.get("impact", "neutral")).lower()
        importance_raw = str(f.get("importance", "medium")).lower()
        text = f.get("factor", "")

        if "home" in impact or "favors home" in impact:
            badge_class = "factor-home"
            badge_text = "Favors Home Team"
        elif "away" in impact or "favors away" in impact:
            badge_class = "factor-away"
            badge_text = "Favors Away Team"
        else:
            badge_class = "factor-neutral"
            badge_text = "Mixed / Neutral"

        importance_map = {
            "high": "High Importance",
            "medium": "Medium Importance",
            "low": "Low Importance",
        }
        importance_text = importance_map.get(importance_raw, "Medium Importance")

        with cols[i % 2]:
            st.markdown(
                f"""
                <div class="factor-box">
                    <div class="factor-top">
                        <span class="factor-badge {badge_class}">{badge_text}</span>
                        <span class="factor-importance">{importance_text}</span>
                    </div>
                    <div class="factor-text">{text}</div>
                </div>
                """,
                unsafe_allow_html=True
            )

    st.markdown('</div>', unsafe_allow_html=True)


def render_reasoning_value(report_json):
    reasoning = report_json.get("reasoning", "")
    value = report_json.get("value_assessment", "")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div class="glass-card"><div class="section-title">Reasoning</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="text-panel">{reasoning if reasoning else "No reasoning provided."}</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with c2:
        st.markdown('<div class="glass-card"><div class="section-title">Value Assessment</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="text-panel">{value if value else "No value commentary provided."}</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

def pct_str(x):

    if isinstance(x, (int, float)):
        return f"{x:.0%}"
    return str(x)

def render_agent_breakdown(agent_analyses):
    if not agent_analyses:
        return

    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Agent Breakdown</div>', unsafe_allow_html=True)

    cols = st.columns(len(agent_analyses))
    for i, (agent_key, analysis) in enumerate(agent_analyses.items()):
        name = AGENTS[agent_key]["name"].replace(" Agent", "")
        pred = analysis.get("prediction", {})
        home = pred.get("home_win_prob", 0.5)
        away = pred.get("away_win_prob", 0.5)
        conf = analysis.get("confidence", "Medium")

        with cols[i]:
            st.markdown(
                f"""
                <div class="score-card">
                    <div class="score-label">{name}</div>
                    <div class="subtle" style="margin-bottom:10px;">Home {pct_str(home)} · Away {pct_str(away)}</div>
                    <div class="bar-wrap">
                        <div class="bar-label"><span>Home lean</span><span>{pct_str(home)}</span></div>
                        <div class="bar"><div class="bar-fill-green" style="width:{int((home if isinstance(home,(int,float)) else 0.5)*100)}%;"></div></div>
                    </div>
                    <div class="bar-wrap">
                        <div class="bar-label"><span>Confidence</span><span>{conf}</span></div>
                        <div class="bar"><div class="bar-fill-red" style="width:{82 if str(conf).lower()=='high' else 62 if str(conf).lower()=='medium' else 38}%;"></div></div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )
    st.markdown('</div>', unsafe_allow_html=True)


def render_agreement(report_json):
    agree = report_json.get("areas_of_agreement", [])
    disagree = report_json.get("areas_of_disagreement", [])

    if not agree and not disagree:
        return

    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div class="glass-card"><div class="section-title">Areas of Agreement</div>', unsafe_allow_html=True)
        if agree:
            st.markdown(
                "<div class='text-panel'>" + "".join([f"• {x}<br>" for x in agree]) + "</div>",
                unsafe_allow_html=True
            )
        else:
            st.markdown("<div class='text-panel'>No clear agreement items.</div>", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with c2:
        st.markdown('<div class="glass-card"><div class="section-title">Areas of Disagreement</div>', unsafe_allow_html=True)
        if disagree:
            st.markdown(
                "<div class='text-panel'>" + "".join([f"• {x}<br>" for x in disagree]) + "</div>",
                unsafe_allow_html=True
            )
        else:
            st.markdown("<div class='text-panel'>No major disagreement items.</div>", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)


def render_final_prediction(report_json, home_team, away_team):
    _, home_prob, away_prob, confidence = get_prediction_block(report_json)

    winner = home_team if home_prob >= away_prob else away_team
    edge = abs(home_prob - away_prob) if isinstance(home_prob, (int, float)) and isinstance(away_prob, (int, float)) else 0

    summary = report_json.get("value_assessment") or report_json.get("reasoning") or ""
    if len(summary) > 240:
        summary = summary[:240].rsplit(" ", 1)[0] + "..."

    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="verdict-card">
            <div class="verdict-title">Final Prediction</div>
            <div class="verdict-main">{winner} projected to win</div>
            <div class="verdict-sub">
                Estimated confidence: <strong>{str(confidence).capitalize()}</strong> ·
                win probability gap: <strong>{edge:.1%}</strong><br><br>
                {summary}
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )
    st.markdown('</div>', unsafe_allow_html=True)


def render_trace_event_box(title, body, tone="neutral"):
    tone_map = {
        "neutral": "factor-neutral",
        "home": "factor-home",
        "away": "factor-away",
    }
    badge_class = tone_map.get(tone, "factor-neutral")

    st.markdown(
        f"""
        <div class="factor-box" style="margin-bottom:10px;">
            <div class="factor-top">
                <span class="factor-badge {badge_class}">{title}</span>
            </div>
            <div class="factor-text"><pre style="white-space:pre-wrap; margin:0; color:inherit; font-family:Inter, sans-serif;">{body}</pre></div>
        </div>
        """,
        unsafe_allow_html=True
    )

def render_trace_step_card(title, subtitle="", body="", tone="neutral"):
    tone_map = {
        "neutral": "factor-neutral",
        "home": "factor-home",
        "away": "factor-away",
    }
    badge_class = tone_map.get(tone, "factor-neutral")

    subtitle_html = f"<div class='subtle' style='margin-top:6px;'>{subtitle}</div>" if subtitle else ""
    body_html = f"<div class='factor-text' style='margin-top:10px;'>{body}</div>" if body else ""

    st.markdown(
        f"""
        <div class="factor-box" style="margin-bottom:12px;">
            <div class="factor-top">
                <span class="factor-badge {badge_class}">{title}</span>
            </div>
            {subtitle_html}
            {body_html}
        </div>
        """,
        unsafe_allow_html=True
    )
    
def clean_trace_line(line):
    line = line.strip()

    for junk in ["============================================================", "############################################################"]:
        line = line.replace(junk, "")

    while "====" in line:
        line = line.replace("====", "")
    while "####" in line:
        line = line.replace("####", "")

    return line.strip(" -:")

def render_analysis_trace(trace_text, mode):
    if not trace_text or not trace_text.strip():
        return

    with st.expander("View Analysis Trace", expanded=False):
        st.caption("Step-by-step workflow: data gathering, tool calls, debate rounds, and final synthesis.")
        st.code(trace_text.strip(), language=None)
        return

    # Legacy rendering below (unreachable, kept for reference)
    lines = [clean_trace_line(line) for line in trace_text.splitlines()]
    lines = [line for line in lines if line]

    if mode == "Multi-Agent Debate":
        current_agent = None

        for line in lines:
            if "PHASE 1: INDEPENDENT ANALYSIS" in line:
                st.markdown("### Phase 1: Independent Analysis")
                continue

            if "DEBATE ROUND 1" in line:
                st.markdown("### Debate Round 1")
                current_agent = None
                continue

            if "DEBATE ROUND 2" in line:
                st.markdown("### Debate Round 2")
                current_agent = None
                continue

            if "MODERATOR SYNTHESIS" in line:
                st.markdown("### Moderator Synthesis")
                current_agent = None
                continue

            if line in [cfg["name"] for cfg in AGENTS.values()]:
                current_agent = line
                render_trace_step_card(
                    title=current_agent,
                    subtitle="Agent is gathering evidence and updating its view."
                )
                continue

            if line.startswith("Step "):
                parts = line.split(":", 1)
                title = parts[0].strip()
                body = parts[1].strip() if len(parts) > 1 else ""
                render_trace_step_card(title=title, body=body)
                continue

            if "Tool call:" in line:
                render_trace_step_card(
                    title="Debate tool call",
                    body=line.replace("Tool call:", "").strip()
                )
                continue

            if "Updated prediction:" in line or "Prediction:" in line:
                render_trace_step_card(
                    title="Prediction update",
                    body=line
                )
                continue

            if "Kept previous position (parse failed)" in line:
                render_trace_step_card(
                    title="No update",
                    body="The agent kept its previous position because the follow-up response could not be parsed cleanly."
                )
                continue

            if "FINAL SYNTHESIZED REPORT" in line or "FINAL REPORT" in line:
                render_trace_step_card(
                    title="Final report ready",
                    body="The reasoning pipeline completed and produced the final structured report."
                )
                continue

            if current_agent:
                render_trace_step_card(
                    title=current_agent,
                    body=line
                )
            else:
                render_trace_step_card(
                    title="Trace",
                    body=line
                )

    else:
        for line in lines:
            if line.startswith("Gathering all evidence"):
                render_trace_step_card(title="Evidence gathering", body=line)
            elif line.startswith("Getting "):
                render_trace_step_card(title="Data fetch", body=line)
            elif line.startswith("Step "):
                render_trace_step_card(title="Agent step", body=line)
            elif "Running chain-of-thought analysis" in line:
                render_trace_step_card(title="Reasoning pass", body=line)
            elif "FINAL REPORT" in line:
                render_trace_step_card(title="Final report ready", body=line)
            else:
                render_trace_step_card(title="Trace", body=line)

    with st.expander("View raw terminal trace"):
        st.code(trace_text, language="text")

    st.markdown('</div>', unsafe_allow_html=True)


def build_download_payload(mode, game_description, result, report_json):
    payload = {
        "product": "MatchOdds AI",
        "mode": mode,
        "game": game_description,
        "generated_at": datetime.utcnow().isoformat(),
        "summary_report": report_json,
        "full_result": result,
    }
    return json.dumps(payload, indent=2)

def _resolve_key(name):
    """Get an API key from env, .env file, or st.secrets — whichever has it."""
    # 1. environment variable (set via export or load_dotenv)
    val = os.environ.get(name, "").strip()
    if val:
        return val
    # 2. direct .env file read (handles cases where load_dotenv path differs)
    try:
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith(f"{name}="):
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if val:
                        os.environ[name] = val
                        return val
    except Exception:
        pass
    # 3. Streamlit Cloud secrets
    try:
        val = st.secrets.get(name, "").strip()
        if val:
            os.environ[name] = val
            return val
    except Exception:
        pass
    return ""


def get_llm_fn():
    anthropic_key = _resolve_key("ANTHROPIC_API_KEY")
    if anthropic_key:
        def call_anthropic(messages):
            import anthropic
            client = anthropic.Anthropic(api_key=anthropic_key)
            system_msg = ""
            conv_messages = []
            for msg in messages:
                if msg["role"] == "system":
                    system_msg = msg["content"]
                else:
                    conv_messages.append(msg)

            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=4096,
                system=system_msg if system_msg else "You are an NBA betting analyst.",
                messages=conv_messages,
            )
            return response.content[0].text

        return call_anthropic, "Claude"

    openai_key = _resolve_key("OPENAI_API_KEY")
    if openai_key:
        def call_openai(messages):
            from openai import OpenAI
            client = OpenAI(api_key=openai_key)
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                max_tokens=4096,
            )
            return response.choices[0].message.content

        return call_openai, "GPT-4o"

    return None, None

def parse_report(report_text):
    if "FINAL REPORT:" in report_text:
        json_str = report_text.split("FINAL REPORT:")[-1].strip()
    else:
        json_str = report_text.strip()

    try:
        start = json_str.find("{")
        end = json_str.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(json_str[start:end])
    except json.JSONDecodeError:
        pass

    return None

def load_upcoming_games():
    try:
        df = pd.read_csv("data/odds_live.csv")

        if df.empty:
            return []

        df = df[df["MARKET"] == "h2h"].copy()

        # Parse UTC timestamps from The Odds API
        df["COMMENCE_TIME"] = pd.to_datetime(df["COMMENCE_TIME"], utc=True, errors="coerce")
        df = df.dropna(subset=["COMMENCE_TIME"])

        # Convert to your local timezone for display/filtering
        df["LOCAL_COMMENCE_TIME"] = df["COMMENCE_TIME"].dt.tz_convert("America/New_York")
        latest_time = df["LOCAL_COMMENCE_TIME"].max()
        print(f"Latest game in odds file: {latest_time}")
        
        # Keep only games today or later
        now_local = pd.Timestamp.now(tz="America/New_York")
        grace_period_hours = 3
        df = df[df["LOCAL_COMMENCE_TIME"] >= (now_local - pd.Timedelta(hours=grace_period_hours))].copy()

        if df.empty:
            return []

        games = (
            df[["GAME_ID", "HOME_TEAM", "AWAY_TEAM", "LOCAL_COMMENCE_TIME"]]
            .drop_duplicates()
            .sort_values("LOCAL_COMMENCE_TIME")
        )

        game_list = []
        for _, row in games.iterrows():
            label = (
                f"{row['AWAY_TEAM']} @ {row['HOME_TEAM']} "
                f"({row['LOCAL_COMMENCE_TIME'].strftime('%b %d %I:%M %p ET')})"
            )
            game_list.append({
                "label": label,
                "home_team": row["HOME_TEAM"],
                "away_team": row["AWAY_TEAM"],
                "date": row["LOCAL_COMMENCE_TIME"].to_pydatetime(),
            })

        return game_list

    except Exception as e:
        print(f"Error loading upcoming games: {e}")
        return []

def build_compare_row(label, report_json):
    pred = (
        report_json.get("prediction")
        or report_json.get("synthesized_prediction")
        or report_json.get("agent_prediction", {})
    )

    home_prob = pred.get("home_win_prob", None)
    away_prob = pred.get("away_win_prob", None)
    confidence = pred.get("confidence", "N/A")

    if isinstance(home_prob, (int, float)) and isinstance(away_prob, (int, float)):
        winner_side = "Home" if home_prob >= away_prob else "Away"
        winner_prob = max(home_prob, away_prob)
        gap = abs(home_prob - away_prob)
        home_pct = f"{home_prob:.0%}"
        away_pct = f"{away_prob:.0%}"
        winner_pct = f"{winner_prob:.0%}"
        gap_pct = f"{gap:.0%}"
    else:
        winner_side = "N/A"
        home_pct = "N/A"
        away_pct = "N/A"
        winner_pct = "N/A"
        gap_pct = "N/A"

    return {
        "Method": label,
        "Home Win %": home_pct,
        "Away Win %": away_pct,
        "Predicted Side": winner_side,
        "Top Probability": winner_pct,
        "Confidence": str(confidence).capitalize(),
        "Gap": gap_pct,
    }
    
def render_compare_all_summary(compare_rows):
    if not compare_rows:
        return

    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Model Comparison</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="subtle" style="margin-bottom:12px;">All three reasoning modes are run on the same matchup so you can compare probabilities, confidence, and agreement.</div>',
        unsafe_allow_html=True
    )

    df = pd.DataFrame(compare_rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown('</div>', unsafe_allow_html=True)
    
def render_compare_all_report_block(title, result, report_json, mode_label, home_team, away_team, trace_text=""):
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown(f'<div class="section-title">{title}</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    render_prediction_visuals(report_json, home_team, away_team)
    render_key_factors(report_json.get("key_factors", []))

    if mode_label == "Multi-Agent Debate":
        render_agent_breakdown(result.get("agent_analyses", {}))
        render_agreement(report_json)

    render_reasoning_value(report_json)
    render_final_prediction(report_json, home_team, away_team)

    if trace_text:
        render_analysis_trace(trace_text, mode_label)
        
def render_compare_all_cards(compare_rows):
    if not compare_rows:
        return

    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Model Comparison</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="subtle" style="margin-bottom:12px;">All three reasoning modes are run on the same matchup so you can compare probabilities, confidence, and agreement.</div>',
        unsafe_allow_html=True
    )

    cols = st.columns(len(compare_rows))

    for i, row in enumerate(compare_rows):
        method = row.get("Method", "N/A")
        home_win = row.get("Home Win %", "N/A")
        away_win = row.get("Away Win %", "N/A")
        predicted_side = row.get("Predicted Side", "N/A")
        top_probability = row.get("Top Probability", "N/A")
        confidence = row.get("Confidence", "N/A")
        gap = row.get("Gap", "N/A")

        conf_width = 82 if str(confidence).lower() == "high" else 62 if str(confidence).lower() == "medium" else 38

        home_width = home_win if home_win != "N/A" else "0%"
        away_width = away_win if away_win != "N/A" else "0%"

        with cols[i]:
            st.markdown(
                f"""
                <div class="score-card">
                    <div class="score-label">{method}</div>
                    <div class="score-value blue" style="font-size:1.35rem;">{top_probability}</div>
                    <div class="subtle" style="margin-top:6px; margin-bottom:12px;">
                        Predicted side: <strong>{predicted_side}</strong>
                    </div>

                    <div class="bar-wrap">
                        <div class="bar-label"><span>Home Win %</span><span>{home_win}</span></div>
                        <div class="bar">
                            <div class="bar-fill-green" style="width:{home_width};"></div>
                        </div>
                    </div>

                    <div class="bar-wrap">
                        <div class="bar-label"><span>Away Win %</span><span>{away_win}</span></div>
                        <div class="bar">
                            <div class="bar-fill-red" style="width:{away_width};"></div>
                        </div>
                    </div>

                    <div class="bar-wrap">
                        <div class="bar-label"><span>Confidence</span><span>{confidence}</span></div>
                        <div class="bar">
                            <div class="bar-fill-green" style="width:{conf_width}%;"></div>
                        </div>
                    </div>

                    <div class="subtle" style="margin-top:10px;">
                        Gap: <strong>{gap}</strong>
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )

    st.markdown('</div>', unsafe_allow_html=True)

def main():
    st.set_page_config(page_title="MatchOdds AI", page_icon="🏀", layout="wide")

    llm_fn, llm_name = get_llm_fn()
    if not llm_fn:
        st.error("No API key found. Set ANTHROPIC_API_KEY or OPENAI_API_KEY before running.")
        st.stop()

    render_header(llm_name)
    render_method_guide()

    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Select Game</div>', unsafe_allow_html=True)

    c1, c2, c3 = st.columns([3, 3, 2])
    games = load_upcoming_games()
    
    if games:
        st.markdown(
            f"<div class='subtle'>Odds last available game: {games[-1]['date'].strftime('%b %d %I:%M %p ET')}</div>",
            unsafe_allow_html=True
        )

    if not games:
        st.warning("No current or future games found in live odds. Re-run the odds pipeline to refresh today's matchups.")
        st.stop()

    game_labels = [g["label"] for g in games]

    selected_label = st.selectbox("Select Upcoming Game", game_labels)

    selected_game = next(g for g in games if g["label"] == selected_label)

    away_team = selected_game["away_team"]
    home_team = selected_game["home_team"]
    game_date = selected_game["date"]
    try:
        game_date = selected_game["date"]
    except ValueError:
        st.error("Please enter the date as YYYY-MM-DD.")
        st.stop()

    mode = st.radio(
    "Analysis Mode",
    ["Multi-Agent Debate", "Single Agent", "Chain-of-Thought", "Compare All"],
    horizontal=True,
)

    st.markdown('</div>', unsafe_allow_html=True)

    if home_team == away_team:
        st.warning("Select two different teams.")
        st.stop()

    def map_to_abbr(team_name):
        for full, abbr in TEAMS.items():
            if team_name.lower() in full.lower() or full.lower() in team_name.lower():
                return abbr
        return None

    home_abbr = map_to_abbr(home_team)
    away_abbr = map_to_abbr(away_team)

    if not home_abbr or not away_abbr:
        st.error(f"Could not map teams to abbreviations: {home_team}, {away_team}")
        st.stop()
    
    game_description = f"{away_team} vs {home_team}, {game_date.strftime('%B %d, %Y')}"

    render_matchup_header(home_team, away_team, home_abbr, away_abbr, game_date)
    render_team_snapshot(home_team, away_team, home_abbr, away_abbr)
    render_injury_summary(home_team, away_team)
    render_sentiment_summary(home_team, away_team, home_abbr, away_abbr)

    live_trace_placeholder = st.empty()

    if st.button("Run Analysis"):
        result = None
        report_json = None
        trace_text = ""

        if mode == "Single Agent":
            result, trace_text = run_with_live_trace(
                run_agent,
                live_trace_placeholder,
                mode,
                game_description,
                llm_fn,
            )
            report_json = parse_report(result["final_response"])

            if report_json:
                live_trace_placeholder.empty()
                render_prediction_visuals(report_json, home_team, away_team)
                render_market_divergence(report_json, home_team, away_team)
                render_key_factors(report_json.get("key_factors", []))
                render_similar_games(home_abbr, away_abbr, home_team, away_team)
                render_reasoning_value(report_json)
                render_final_prediction(report_json, home_team, away_team)
                render_analysis_trace(trace_text, mode)

                download_text = build_download_payload(mode, game_description, result, report_json)
                st.download_button(
                    label="Download Full Report",
                    data=download_text,
                    file_name=f"matchodds_report_{away_abbr}_at_{home_abbr}_{game_date.strftime('%Y%m%d')}.json",
                    mime="application/json"
                )

                with st.expander("View Full Structured Output"):
                    st.json(report_json)

                with st.expander("View Full Raw Analysis"):
                    st.json(result)
            else:
                st.error("Could not parse a structured report from the model output.")
                if trace_text:
                    st.code(trace_text, language="text")
                st.write(result)

        elif mode == "Chain-of-Thought":
            result, trace_text = run_with_live_trace(
                run_cot_analysis,
                live_trace_placeholder,
                mode,
                home_abbr,
                away_abbr,
                home_team,
                away_team,
                game_description,
                llm_fn,
            )
            report_json = parse_report(result["response"])

            if report_json:
                live_trace_placeholder.empty()
                render_prediction_visuals(report_json, home_team, away_team)
                render_market_divergence(report_json, home_team, away_team)
                render_key_factors(report_json.get("key_factors", []))
                render_similar_games(home_abbr, away_abbr, home_team, away_team)
                render_reasoning_value(report_json)
                render_final_prediction(report_json, home_team, away_team)
                render_analysis_trace(trace_text, mode)

                download_text = build_download_payload(mode, game_description, result, report_json)
                st.download_button(
                    label="Download Full Report",
                    data=download_text,
                    file_name=f"matchodds_report_{away_abbr}_at_{home_abbr}_{game_date.strftime('%Y%m%d')}.json",
                    mime="application/json"
                )

                with st.expander("View Full Structured Output"):
                    st.json(report_json)

                with st.expander("View Full Raw Analysis"):
                    st.json(result)
            else:
                st.error("Could not parse a structured report from the model output.")
                if trace_text:
                    st.code(trace_text, language="text")
                st.write(result)

        elif mode == "Multi-Agent Debate":
            result, trace_text = run_with_live_trace(
                run_full_debate,
                live_trace_placeholder,
                mode,
                game_description,
                llm_fn,
                num_debate_rounds=2,
            )
            report_json = parse_report(result["final_report"])

            if report_json:
                live_trace_placeholder.empty()
                render_prediction_visuals(report_json, home_team, away_team)
                render_market_divergence(report_json, home_team, away_team)
                render_key_factors(report_json.get("key_factors", []))
                render_similar_games(home_abbr, away_abbr, home_team, away_team)
                render_agent_breakdown(result.get("agent_analyses", {}))
                render_agreement(report_json)
                render_reasoning_value(report_json)
                render_final_prediction(report_json, home_team, away_team)
                render_analysis_trace(trace_text, mode)

                download_text = build_download_payload(mode, game_description, result, report_json)
                st.download_button(
                    label="Download Full Report",
                    data=download_text,
                    file_name=f"matchodds_report_{away_abbr}_at_{home_abbr}_{game_date.strftime('%Y%m%d')}.json",
                    mime="application/json"
                )

                with st.expander("View Full Structured Output"):
                    st.json(report_json)

                with st.expander("View Full Raw Analysis"):
                    st.json(result)
            else:
                st.error("Could not parse a structured report from the model output.")
                if trace_text:
                    st.code(trace_text, language="text")
                st.write(result)

        elif mode == "Compare All":
            compare_rows = []

            compare_live = st.empty()

            compare_live.markdown(
                """
                <div class="live-trace-card">
                    <div class="live-trace-top">
                        <div class="live-trace-label">Running comparison</div>
                        <div class="live-trace-pill">Step 1 of 3</div>
                    </div>
                    <div class="trace-help">
                        Running Multi-Agent Debate, Single Agent, and Chain-of-Thought on the same matchup.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            multi_result, multi_trace = run_with_live_trace(
                run_full_debate,
                compare_live,
                "Multi-Agent Debate",
                game_description,
                llm_fn,
                num_debate_rounds=2,
            )
            multi_report = parse_report(multi_result["final_report"])

            compare_live.markdown(
                """
                <div class="live-trace-card">
                    <div class="live-trace-top">
                        <div class="live-trace-label">Running comparison</div>
                        <div class="live-trace-pill">Step 2 of 3</div>
                    </div>
                    <div class="trace-help">
                        Multi-Agent complete. Running Single Agent.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            single_result, single_trace = run_with_live_trace(
                run_agent,
                compare_live,
                "Single Agent",
                game_description,
                llm_fn,
            )
            single_report = parse_report(single_result["final_response"])

            compare_live.markdown(
                """
                <div class="live-trace-card">
                    <div class="live-trace-top">
                        <div class="live-trace-label">Running comparison</div>
                        <div class="live-trace-pill">Step 3 of 3</div>
                    </div>
                    <div class="trace-help">
                        Single Agent complete. Running Chain-of-Thought.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            cot_result, cot_trace = run_with_live_trace(
                run_cot_analysis,
                compare_live,
                "Chain-of-Thought",
                home_abbr,
                away_abbr,
                home_team,
                away_team,
                game_description,
                llm_fn,
            )
            cot_report = parse_report(cot_result["response"])

            compare_live.empty()

            if multi_report:
                compare_rows.append(build_compare_row("Multi-Agent Debate", multi_report))
            if single_report:
                compare_rows.append(build_compare_row("Single Agent", single_report))
            if cot_report:
                compare_rows.append(build_compare_row("Chain-of-Thought", cot_report))

            render_compare_all_cards(compare_rows)

            if multi_report:
                render_compare_all_report_block(
                    "Multi-Agent Debate",
                    multi_result,
                    multi_report,
                    "Multi-Agent Debate",
                    home_team,
                    away_team,
                    multi_trace,
                )

            if single_report:
                render_compare_all_report_block(
                    "Single Agent",
                    single_result,
                    single_report,
                    "Single Agent",
                    home_team,
                    away_team,
                    single_trace,
                )

            if cot_report:
                render_compare_all_report_block(
                    "Chain-of-Thought",
                    cot_result,
                    cot_report,
                    "Chain-of-Thought",
                    home_team,
                    away_team,
                    cot_trace,
                )

            compare_payload = {
                "mode": "Compare All",
                "game": game_description,
                "generated_at": datetime.utcnow().isoformat(),
                "multi_agent": {
                    "result": multi_result,
                    "report": multi_report,
                },
                "single_agent": {
                    "result": single_result,
                    "report": single_report,
                },
                "cot": {
                    "result": cot_result,
                    "report": cot_report,
                },
                "comparison_rows": compare_rows,
            }

            st.download_button(
                label="Download Full Comparison",
                data=json.dumps(compare_payload, indent=2),
                file_name=f"matchodds_compare_{away_abbr}_at_{home_abbr}_{game_date.strftime('%Y%m%d')}.json",
                mime="application/json"
            )

    st.markdown(
        """
        <div class="footer-note">
            MatchOdds AI · Research interface only · Not financial advice
        </div>
        """,
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()