# CLAUDE.md

This file provides context for AI assistants working on this codebase.

## Project Purpose

Event-sourced sports betting research platform that builds an immutable timeline of "belief states" for NBA games, comparing Kalshi prediction markets against Vegas odds.

## Core Metaphor: Lab Notebook + Factory + Scoreboard

- **Lab notebook**: Every "what we knew at time T" is saved exactly as-is, forever
- **Factory**: Deterministic transforms turn raw info into comparable numbers
- **Scoreboard**: Attach actual outcomes and judge which transforms/ideas worked

This separation is what makes the system scalable and honest.

## The Conceptual Model: Immutable Timeline of Belief States

### 1. InfoSnapshot - Your ingredients at a timestamp

The only thing that talks to outside reality (APIs).

```
InfoSnapshot(game_id, collected_at, schema_version, source_versions, raw_payloads, normalized_fields)
```

**Key rule**: Snapshots are immutable. Never "update" one - when you re-fetch, create a new snapshot with a new timestamp.

Timeline example:
```
S0 @ 10:00 (morning injury report)
S1 @ 12:15 (line moved)
S2 @ 17:45 (final status update)
S3 @ 18:50 (10 min pre-tip)
```

You can always answer: "What did I know at 12:15?"

### 2. Analysis - Derived artifacts, timestamped + versioned

Analysis is a saved object that references inputs, not "thoughts in your head."

```
Analysis(analysis_id, created_at, analysis_version, code_version, model_version, parent_analysis_id?, input_snapshot_ids[], derived_features, conclusions, recommended_actions)
```

**Key rule**: Analysis is also immutable. New analysis creates a new record that points to newer snapshots and optionally the previous analysis as a parent.

This forms a DAG (directed graph), like Git commits:
```
A0 uses S0
A1 uses S1 and parent=A0
A2 uses S2 and parent=A1
```

This is event sourcing + versioned inference.

### 3. Outcome - Ground truth attached later

```
Outcome(game_id, occurred_at, final_score, winner, stats_summary, source)
```

Now you can evaluate any analysis made earlier against the outcome.

### 4. Evaluation - Scoring analyses against outcomes

Computed metrics: brier score, log_loss, roi, edge_realized, etc.

## Why This Architecture Stays Honest

It separates four things people usually mash together:

1. **Observation** (snapshot, raw + normalized)
2. **Transformation** (derived features: no-vig implied prob, deltas, liquidity metrics)
3. **Decision rule** (your strategy / "edge detector")
4. **Truth** (outcome)

You can improve any layer without corrupting the others.

## What an "Edge" Actually Is

An edge is: "Given what was knowable at time T, my system predicted a probability/price that was systematically better than the market, after costs."

The system must answer:
- At T, what was Kalshi price? (YES cents)
- At T, what was Vegas no-vig probability? (from moneylines)
- At T, what was my model probability? (optional; could start as "Vegas baseline")
- At T, what was expected value given fees, spread, liquidity, slippage?
- Later, what happened?

If you see positive expected value AND realized value over time, you have an edge. If not, you have a well-instrumented machine that tells you you don't have an edge (also valuable).

## The Update Loop Mental Model

Each new snapshot = a new frame in a movie.

- Frame = InfoSnapshot
- Analysis = subtitles added to that frame
- New frame arrives = create new subtitle track, referencing the old one

The system can say:
```
"At 12:15 I thought Team A was 54%.
At 17:45, with Injury X now OUT and line moved, updated to 61%.
Here's what changed and why (feature deltas)."
```

The "what changed" part is where the tool becomes valuable beyond just another odds scraper.

## Four Version Axes

### A) Schema version (data shape)
```
schema_version = nba_mvp_v1
```
- Add fields without breaking old readers = bump minor
- Change meanings / remove fields = bump major

### B) Data source version (provenance)
Per snapshot:
- Which provider for odds/stats/injuries
- Endpoint versions if relevant
- `collected_at` always present

### C) Code version (pipeline logic)
Every analysis/run stores:
- Git commit hash (or semver tag)
- Config hash

### D) Model version (if LLM or ML is used)
- `model_name` + `model_version`
- Prompt template version
- Retrieval version (if using RAG)

This prevents: "it used to work but now it doesn't and we don't know why."

## Database Tables

```
info_snapshots
├── snapshot_id
├── game_id
├── collected_at
├── schema_version
├── source_map (json)
├── raw_payloads (json or storage pointer)
├── normalized_schema (jsonb)
└── hash

analyses
├── analysis_id
├── created_at
├── analysis_version
├── parent_analysis_id (nullable)
├── input_snapshot_ids (array)
├── code_version
├── model_version
├── analysis_output (jsonb)
├── recommended_actions (jsonb)
└── hash

outcomes
├── game_id
├── finalized_at
└── result_payload (jsonb)

evaluations
├── evaluation_id
├── analysis_id
├── game_id
├── scored_at
├── metrics: brier, log_loss, roi, edge_realized, etc.
└── notes
```

Full loop: **Snapshot -> Analysis -> Outcome -> Evaluation**

## LLM Improvement System (Evidence-Based)

Don't ask the LLM "how do I improve?" in a vacuum. Ask with structured evidence from evaluations.

### Error Journal (automatic)
Each evaluation run produces an error record:
- Which features changed most between winning vs losing calls?
- Where did delta_prob look big but failed due to liquidity/spread?
- Where were injuries wrong/late?
- Which sources were missing?
- Did we overreact to line movement?

### Improvement Proposals (versioned)
```
improvement_proposals
├── proposal_id
├── created_at
├── based_on_evaluation_ids
├── proposal_text
├── suggested_schema_additions (json)
├── suggested_modules (list)
├── expected_impact (hypothesis)
└── status (proposed / accepted / rejected)
```

The LLM becomes a research assistant writing testable hypotheses, not a fortune teller.

## What Makes This Different

Most bettors:
- Scrape stuff
- Eyeball it
- Forget what they knew when
- Cannot reproduce decisions
- Cannot measure improvements

This system:
- Event-sourced market + info history
- Lineage graph of analyses
- Evaluation loop
- Proposal + experiment tracking

It's a mini "quant research platform" scoped to NBA + Kalshi.

## Architectural Rules

1. **Never overwrite** snapshots, analyses, or evaluations. Append only.
2. **Every record references its parents** (lineage).
3. **Deterministic transforms only** in derived (math, not opinions).
4. **Human/LLM narrative** lives in analysis_output, never mixed into raw data.
5. **Every automated suggestion** must point to evidence (evaluation IDs).

## Immutability Enforcement

- **Python**: Frozen dataclasses prevent mutation
- **SQLite**: Triggers reject UPDATE/DELETE operations
- **Repository**: Only insert + read methods exposed
- **Content hashing**: SHA-256 verification on read

## Build Commands

```bash
# Install dependencies
pip install -e ".[dev]"

# Initialize database
sportsbetsinfo init-db

# Check status
sportsbetsinfo status

# Collect snapshot for today's games
sportsbetsinfo collect-day --sport basketball_nba

# Collect for specific game
sportsbetsinfo collect <game_id> --sport basketball_nba

# View timeline
sportsbetsinfo timeline <game_id>

# Verify integrity
sportsbetsinfo verify
```

## Data Sources

- **Kalshi**: Prediction market prices (YES/NO cents) - uses RSA key authentication
- **The Odds API**: Vegas odds from multiple bookmakers

## Project Structure

```
src/sportsbetsinfo/
├── core/           # Domain models (frozen dataclasses), hashing, exceptions
├── config/         # Pydantic settings from environment
├── db/             # SQLite schema, connection, repositories (insert + read only)
├── clients/        # Kalshi (RSA auth), The Odds API clients
├── services/       # Data collection, analysis services
└── cli/            # Click commands
```

## The Minimal Loop (Build This First)

1. **Snapshot ingestion**: Pull today's games + Kalshi prices + Vegas odds -> store info_snapshots
2. **Derived comparison**: Compute no-vig implied prob and delta vs Kalshi -> store analysis object
3. **Outcome + evaluation**: After games finish, attach results -> compute scoring metrics

Once that loop exists, the tool is "alive." Everything else is upgrades.
