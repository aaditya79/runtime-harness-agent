"""
Step 6: ChromaDB Vector Store
Reads the CSVs from data/ (produced by steps 1-3) and loads them into
a ChromaDB vector database for similarity search.

The agent will query this store to find historically similar games.
For example: "Find games where a team was on a back-to-back, on the road,
after a loss, against a top-5 defensive team."

Usage:
    pip install chromadb pandas
    python nba_vector_store.py

Output:
    chroma_db/  - ChromaDB persistent storage directory

After running this, you can query the store like:
    from nba_vector_store import query_similar_games
    results = query_similar_games("team on back to back, road game, facing top defense")
"""

import os
import pandas as pd
import chromadb
from chromadb.config import Settings

DATA_DIR = "data"
CHROMA_DIR = "chroma_db"


def load_game_data():
    """Load and merge game logs with team stats for rich metadata."""
    print("Loading game data from CSVs...")

    # Load game logs (the main dataset)
    game_logs = pd.read_csv(f"{DATA_DIR}/game_logs.csv")
    print(f"  Game logs: {len(game_logs)} rows")

    # Load team stats for advanced metrics
    team_stats = None
    if os.path.exists(f"{DATA_DIR}/team_stats.csv"):
        team_stats = pd.read_csv(f"{DATA_DIR}/team_stats.csv")
        print(f"  Team stats: {len(team_stats)} rows")

    # Load standings
    standings = None
    if os.path.exists(f"{DATA_DIR}/standings.csv"):
        standings = pd.read_csv(f"{DATA_DIR}/standings.csv")
        print(f"  Standings: {len(standings)} rows")

    # Load H2H
    h2h = None
    if os.path.exists(f"{DATA_DIR}/head_to_head.csv"):
        h2h = pd.read_csv(f"{DATA_DIR}/head_to_head.csv")
        print(f"  H2H records: {len(h2h)} rows")

    return game_logs, team_stats, standings, h2h


def build_game_documents(game_logs):
    """
    Convert each game into a text document + metadata for ChromaDB.

    Each document is a natural language description of the game situation
    that the LLM agent can retrieve via semantic search.

    Metadata fields enable filtering (e.g., only back-to-back games,
    only road games, only specific teams).
    """
    print("Building game documents for vector store...")

    documents = []
    metadatas = []
    ids = []

    for idx, row in game_logs.iterrows():
        # Build a natural language description of this game
        home_away = "home" if row.get("HOME") == 1 else "away"
        win_loss = "won" if row.get("WIN") == 1 else "lost"
        b2b = "on a back-to-back" if row.get("BACK_TO_BACK") == 1 else "with rest"
        rest_days = row.get("REST_DAYS", "unknown")
        rolling_pct = row.get("ROLLING_WIN_PCT", 0)

        # Parse opponent from matchup string
        matchup = str(row.get("MATCHUP", ""))
        opponent = ""
        if "vs." in matchup:
            opponent = matchup.split("vs. ")[-1].strip()
        elif "@" in matchup:
            opponent = matchup.split("@ ")[-1].strip()

        team = row.get("TEAM_ABBREVIATION", "UNK")
        pts = row.get("PTS", 0)
        fg_pct = row.get("FG_PCT", 0)
        fg3_pct = row.get("FG3_PCT", 0)
        reb = row.get("REB", 0)
        ast = row.get("AST", 0)
        tov = row.get("TOV", 0)
        plus_minus = row.get("PLUS_MINUS", 0)
        season = row.get("SEASON", "")
        game_date = str(row.get("GAME_DATE", ""))[:10]

        # Create the document text (what gets embedded and searched)
        doc = (
            f"{team} played {home_away} against {opponent} on {game_date} ({season} season). "
            f"They were {b2b} ({rest_days} days rest). "
            f"Recent form: {rolling_pct:.1%} win rate over last 10 games. "
            f"Result: {team} {win_loss} {int(pts)} points. "
            f"Shooting: {fg_pct:.1%} FG, {fg3_pct:.1%} 3PT. "
            f"Stats: {int(reb)} rebounds, {int(ast)} assists, {int(tov)} turnovers. "
            f"Plus/minus: {plus_minus:+.0f}."
        )

        # Create metadata (for filtering, not for embedding)
        meta = {
            "team": team,
            "opponent": opponent,
            "season": season,
            "game_date": game_date,
            "home_away": home_away,
            "win_loss": win_loss,
            "back_to_back": int(row.get("BACK_TO_BACK", 0)),
            "rest_days": int(rest_days) if pd.notna(rest_days) and str(rest_days) != "unknown" else -1,
            "points": int(pts),
            "plus_minus": float(plus_minus),
            "rolling_win_pct": float(rolling_pct) if pd.notna(rolling_pct) else 0.0,
            "fg_pct": float(fg_pct) if pd.notna(fg_pct) else 0.0,
        }

        # Use game_id + team as unique ID
        game_id = str(row.get("GAME_ID", idx))
        doc_id = f"{game_id}_{team}"

        documents.append(doc)
        metadatas.append(meta)
        ids.append(doc_id)

    print(f"  Built {len(documents)} game documents")
    return documents, metadatas, ids


def create_vector_store(documents, metadatas, ids):
    """
    Create a ChromaDB collection and add all documents.
    Uses ChromaDB's default embedding function (all-MiniLM-L6-v2).
    """
    print("Creating ChromaDB vector store...")
    print(f"  Storage directory: {CHROMA_DIR}/")

    # Initialize ChromaDB with persistent storage
    client = chromadb.PersistentClient(path=CHROMA_DIR)

    # Delete existing collection if it exists (for clean rebuilds)
    try:
        client.delete_collection("nba_games")
        print("  Deleted existing collection.")
    except Exception:
        pass

    # Create collection
    collection = client.create_collection(
        name="nba_games",
        metadata={"description": "NBA game data for similarity search"},
    )

    # Add documents in batches (ChromaDB has batch size limits)
    batch_size = 500
    total = len(documents)
    for i in range(0, total, batch_size):
        end = min(i + batch_size, total)
        collection.add(
            documents=documents[i:end],
            metadatas=metadatas[i:end],
            ids=ids[i:end],
        )
        print(f"  Added batch {i//batch_size + 1}: documents {i+1} to {end}")

    print(f"  Total documents in collection: {collection.count()}")
    return client, collection


def query_similar_games(query_text, n_results=5, where_filter=None):
    """
    Query the vector store for games similar to the description.

    Args:
        query_text: Natural language description of the game situation
                   e.g. "Lakers on a back-to-back, road game, after a loss"
        n_results: Number of similar games to return
        where_filter: Optional metadata filter dict
                     e.g. {"team": "LAL"} or {"back_to_back": 1}

    Returns:
        dict with documents, metadatas, and distances
    """
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.get_collection("nba_games")

    query_params = {
        "query_texts": [query_text],
        "n_results": n_results,
    }
    if where_filter:
        query_params["where"] = where_filter

    results = collection.query(**query_params)
    return results


def test_queries(collection):
    """Run a few test queries to verify the vector store works."""
    print()
    print("=" * 60)
    print("TEST QUERIES")
    print("=" * 60)

    test_cases = [
        {
            "query": "team on a back-to-back, playing away, recent losing streak",
            "description": "Tired road team",
        },
        {
            "query": "home game, well rested, high win rate, strong shooting",
            "description": "Dominant home team",
        },
        {
            "query": "Lakers playing against Celtics, high stakes rivalry game",
            "description": "LAL vs BOS",
        },
    ]

    for tc in test_cases:
        print(f"\nQuery: \"{tc['description']}\"")
        print(f"  Search text: \"{tc['query'][:80]}...\"")

        results = collection.query(
            query_texts=[tc["query"]],
            n_results=3,
        )

        for i, (doc, meta) in enumerate(zip(results["documents"][0], results["metadatas"][0])):
            print(f"  Result {i+1}: {meta['team']} vs {meta['opponent']} ({meta['game_date']}) "
                  f"- {meta['win_loss']}, {meta['home_away']}, B2B={meta['back_to_back']}")


def main():
    print("=" * 60)
    print("NBA Vector Store - Step 6")
    print("=" * 60)

    # 1. Load data
    game_logs, team_stats, standings, h2h = load_game_data()

    # 2. Build documents
    documents, metadatas, ids = build_game_documents(game_logs)

    # 3. Create vector store
    client, collection = create_vector_store(documents, metadatas, ids)

    # 4. Test it
    test_queries(collection)

    # Summary
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Documents indexed: {collection.count()}")
    print(f"Storage location: {CHROMA_DIR}/")
    print(f"Collection name: nba_games")
    print()
    print("To query from other scripts:")
    print("  from nba_vector_store import query_similar_games")
    print('  results = query_similar_games("team on back to back, road game")')
    print()
    print("Next: Step 7 (agent loop)")


if __name__ == "__main__":
    main()
