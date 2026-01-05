# CLAUDE.md

This file provides context for AI assistants working on this codebase.

## Project Purpose

Event-sourced sports betting research platform that builds an immutable timeline of "belief states" for NBA games, comparing Kalshi prediction markets against Vegas odds.

## Core Metaphor: Lab Notebook + Factory + Scoreboard

- **Lab notebook**: Every "what we knew at time T" is saved exactly as-is, forever
- **Factory**: Deterministic transforms turn raw info into comparable numbers
- **Scoreboard**: Attach actual outcomes and judge which transforms/ideas worked

This separation is what makes the system scalable and honest.

## Quick Start

```bash
# Install dependencies
pip install -e ".[dev]"

# Initialize database
sportsbetsinfo init-db

# Collect today's games
sportsbetsinfo collect-day --sport basketball_nba

# Run analysis (Kalshi vs Vegas comparison)
sportsbetsinfo analyze --all

# After games complete, ingest outcomes
sportsbetsinfo ingest-outcomes --sport basketball_nba --days 3

# Score analyses against outcomes
sportsbetsinfo evaluate --report
```

## Project Structure

```
src/sportsbetsinfo/
├── __init__.py              # Package version (0.1.0)
├── __main__.py              # CLI entry point
├── core/                    # Domain models & utilities
│   ├── models.py            # Frozen dataclasses (InfoSnapshot, Analysis, Outcome, Evaluation, ImprovementProposal)
│   ├── hashing.py           # SHA-256 content hashing
│   ├── exceptions.py        # Custom exception hierarchy
│   └── __init__.py
├── config/                  # Configuration management
│   ├── settings.py          # Pydantic BaseSettings (SPORTSBETS_ prefix)
│   └── __init__.py
├── db/                      # SQLite layer
│   ├── schema.py            # DDL + immutability triggers
│   ├── connection.py        # Connection management
│   ├── repositories/        # Append-only data access
│   │   ├── base.py          # ImmutableRepository ABC
│   │   ├── snapshot.py      # InfoSnapshot CRUD
│   │   ├── analysis.py      # Analysis DAG operations
│   │   ├── outcome.py       # Outcome records
│   │   ├── evaluation.py    # Evaluation scoring
│   │   ├── proposal.py      # ImprovementProposal (status-updatable)
│   │   └── __init__.py
│   └── __init__.py
├── clients/                 # External API clients
│   ├── base.py              # BaseAPIClient + RateLimiter
│   ├── kalshi.py            # Kalshi prediction market API (RSA auth)
│   ├── odds_api.py          # The Odds API client
│   └── __init__.py
├── services/                # Business logic layer
│   ├── collector.py         # Data collection → InfoSnapshots
│   ├── analyzer.py          # Kalshi vs Vegas comparison → Analyses
│   ├── outcomes.py          # Game result ingestion → Outcomes
│   ├── evaluator.py         # Analysis scoring → Evaluations
│   └── __init__.py
└── cli/                     # Click CLI commands
    ├── commands.py          # All CLI operations
    └── __init__.py
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `sportsbetsinfo init-db` | Create schema + immutability triggers |
| `sportsbetsinfo status` | Show table row counts |
| `sportsbetsinfo config` | Display current settings |
| `sportsbetsinfo collect <game_id>` | Snapshot for specific game |
| `sportsbetsinfo collect-day [date]` | Snapshot all games on date (defaults today) |
| `sportsbetsinfo timeline <game_id>` | Show all snapshots for game |
| `sportsbetsinfo analyze [game_id]` | Create Analysis for specific game |
| `sportsbetsinfo analyze --all` | Analyze all games with recent snapshots |
| `sportsbetsinfo ingest-outcomes` | Import final scores from completed games |
| `sportsbetsinfo evaluate` | Score analyses against outcomes |
| `sportsbetsinfo evaluate --report` | Generate aggregate performance report |
| `sportsbetsinfo lineage <analysis_id>` | Show DAG path root→analysis |
| `sportsbetsinfo verify` | Check all hashes match computed values |

## Core Data Models

All entities are frozen dataclasses with SHA-256 content hashing.

### InfoSnapshot - Market data at time T
```python
InfoSnapshot(
    snapshot_id: str,              # UUID v4
    game_id: str,                  # Event identifier
    collected_at: datetime,        # When collected
    schema_version: str,           # Data shape version (e.g., "1.0.0")
    source_versions: SourceVersions,  # API versions (kalshi_api, odds_api)
    raw_payloads: dict[str, Any],  # Original API responses (preserved exactly)
    normalized_fields: dict[str, Any],  # Standardized computed data
    hash: str                      # SHA-256 content hash
)
```

### Analysis - Derived comparison (DAG structure)
```python
Analysis(
    analysis_id: str,
    created_at: datetime,
    analysis_version: str,         # Analysis logic version
    code_version: str,             # Git commit hash
    model_version: str | None,     # Optional ML model ID
    parent_analysis_id: str | None,  # Links in DAG
    input_snapshot_ids: tuple[str, ...],  # Multiple snapshots
    derived_features: dict,        # No-vig probs, deltas, liquidity
    conclusions: dict,             # Analysis summary findings
    recommended_actions: list[dict],  # Suggested trades/bets
    hash: str
)
```

### Outcome - Ground truth result
```python
Outcome(
    outcome_id: str,
    game_id: str,                  # Matches InfoSnapshot.game_id
    occurred_at: datetime,         # When game ended
    final_score: FinalScore,       # (home: int, away: int)
    winner: str | None,            # Team name or "tie"
    stats_summary: dict,           # Game metadata
    source: str,                   # "odds_api"
    hash: str
)
```

### Evaluation - Scoring analysis vs outcome
```python
Evaluation(
    evaluation_id: str,
    analysis_id: str,              # Links to Analysis
    game_id: str,                  # Links to Outcome
    scored_at: datetime,
    metrics: EvaluationMetrics,    # (brier_score, log_loss, roi, edge_realized)
    notes: dict | None,
    hash: str
)
```

### ImprovementProposal - LLM-suggested improvements
```python
ImprovementProposal(
    proposal_id: str,
    created_at: datetime,
    based_on_evaluation_ids: tuple[str, ...],  # Evidence-grounded
    proposal_text: str,
    suggested_schema_additions: dict | None,
    suggested_modules: list[str] | None,
    expected_impact: dict | None,
    status: ProposalStatus,        # pending → accepted/rejected/implemented
    hash: str
)
```

## Database Schema

```
info_snapshots          # Market data captures (UNIQUE hash)
analyses                # Derived comparisons (FK parent_analysis_id self-reference)
analysis_snapshots      # Many-to-many (Analysis→Snapshot)
outcomes                # Final scores (UNIQUE game_id)
evaluations             # Performance metrics (FK analysis_id, game_id)
improvement_proposals   # LLM suggestions (status field updatable)
proposal_evaluations    # Many-to-many (Proposal→Evaluation)
```

**Immutability Enforcement:**
- SQLite triggers prevent UPDATE/DELETE on all tables (except proposal status)
- Hash verification on every read
- Repository layer exposes only insert + read methods

## Service Layer

### DataCollector (`services/collector.py`)
```python
async collect_snapshot(game_id, sport)      # Single game
async collect_bulk_snapshots(sport)         # All upcoming events
async collect_day_snapshots(date, sport)    # Games on specific date
compute_deltas(older, newer)                # What changed between snapshots
get_snapshot_timeline(game_id)              # Full history for game
```

### AnalysisService (`services/analyzer.py`)
```python
analyze_snapshot(snapshot, parent_id)       # Compare Kalshi vs Vegas
analyze_game(game_id, parent_id)            # Analyze latest snapshot for game
analyze_all_games(limit)                    # Batch analysis
```

**Comparison Logic:**
- Vegas: American odds → implied probability (with vig removal)
- Kalshi: Mid-point of orderbook (YES bid/ask)
- Delta = Kalshi prob - Vegas prob
- Edge threshold: 3% (configurable)

### OutcomeService (`services/outcomes.py`)
```python
async ingest_outcomes(sport, days_from)           # Batch ingest completed games
async ingest_outcome_for_game(game_id, sport)     # Single game
get_games_needing_outcomes()                       # Games with snapshots but no outcome
```

### EvaluationService (`services/evaluator.py`)
```python
evaluate_all_pending()                      # Score all analyses with outcomes
evaluate_analysis(analysis_id)              # Score single analysis
get_aggregate_report()                      # Performance summary
```

**Metrics:**
- Brier score: (predicted_prob - actual)^2
- Log loss: -(actual*log(p) + (1-actual)*log(1-p))
- ROI: Payout/Cost assuming bet on Vegas odds
- Edge realized: Directional edge success

## External API Clients

### KalshiClient (`clients/kalshi.py`)
- **Auth**: RSA-PSS with SHA256 signature
- **Rate limit**: 10 req/sec (configurable)
- Key methods: `get_markets()`, `get_odds()`, `normalize_market_data()`

### OddsAPIClient (`clients/odds_api.py`)
- **Auth**: API key header
- **Rate limit**: 1 req/sec (conservative for free tier)
- Key methods: `get_markets()`, `get_scores()`, `calculate_no_vig_probability()`

## Configuration

Environment variables (prefix: `SPORTSBETS_`):

```bash
SPORTSBETS_DB_PATH=data/sportsbets.db
SPORTSBETS_SCHEMA_VERSION=1.0.0
SPORTSBETS_KALSHI_API_KEY=your_key
SPORTSBETS_KALSHI_PRIVATE_KEY_PATH=/path/to/key.pem
SPORTSBETS_ODDS_API_KEY=your_key
SPORTSBETS_KALSHI_RATE_LIMIT=10
SPORTSBETS_ODDS_API_RATE_LIMIT=1
SPORTSBETS_LOG_LEVEL=INFO
```

## Exception Hierarchy

```python
SportsBetsInfoError (base)
├── IntegrityError
│   └── HashMismatchError(entity_type, entity_id, expected, actual)
├── ImmutabilityViolationError(operation, table)
├── EntityNotFoundError(entity_type, entity_id)
├── DuplicateEntityError(entity_type, hash_value)
├── APIError(client, message, status_code)
└── ConfigurationError
```

## The Conceptual Model: Immutable Timeline of Belief States

### Why Immutability?

**Key rule**: Snapshots are immutable. Never "update" one - when you re-fetch, create a new snapshot with a new timestamp.

Timeline example:
```
S0 @ 10:00 (morning injury report)
S1 @ 12:15 (line moved)
S2 @ 17:45 (final status update)
S3 @ 18:50 (10 min pre-tip)
```

You can always answer: "What did I know at 12:15?"

### Analysis DAG

Analysis forms a directed acyclic graph, like Git commits:
```
A0 uses S0
A1 uses S1 and parent=A0
A2 uses S2 and parent=A1
```

New analysis creates a new record pointing to newer snapshots and optionally the previous analysis as a parent.

### Full Data Loop

**Snapshot → Analysis → Outcome → Evaluation**

The system can say:
```
"At 12:15 I thought Team A was 54%.
At 17:45, with Injury X now OUT and line moved, updated to 61%.
Here's what changed and why (feature deltas)."
```

## What an "Edge" Actually Is

An edge is: "Given what was knowable at time T, my system predicted a probability/price that was systematically better than the market, after costs."

The system must answer:
- At T, what was Kalshi price? (YES cents)
- At T, what was Vegas no-vig probability? (from moneylines)
- At T, what was expected value given fees, spread, liquidity, slippage?
- Later, what happened?

If you see positive expected value AND realized value over time, you have an edge.

## Four Version Axes

1. **Schema version** (data shape): `schema_version = "1.0.0"`
2. **Data source version** (provenance): Which provider, endpoint versions
3. **Code version** (pipeline logic): Git commit hash
4. **Model version** (if LLM/ML): model_name + model_version

This prevents: "it used to work but now it doesn't and we don't know why."

## Architectural Rules

1. **Never overwrite** snapshots, analyses, or evaluations. Append only.
2. **Every record references its parents** (lineage).
3. **Deterministic transforms only** in derived features (math, not opinions).
4. **Human/LLM narrative** lives in analysis_output, never mixed into raw data.
5. **Every automated suggestion** must point to evidence (evaluation IDs).

## LLM Improvement System (Evidence-Based)

Don't ask the LLM "how do I improve?" in a vacuum. Ask with structured evidence from evaluations.

### Error Journal (automatic)
Each evaluation run produces an error record:
- Which features changed most between winning vs losing calls?
- Where did delta_prob look big but failed due to liquidity/spread?
- Where were injuries wrong/late?

### Improvement Proposals
The LLM becomes a research assistant writing testable hypotheses grounded in evaluation IDs, not a fortune teller.

## Development Workflow

### Adding New Features

1. **New data field**: Add to normalized_fields, bump schema_version minor
2. **New analysis type**: Create new service method, store in derived_features
3. **New data source**: Add client in `clients/`, integrate in DataCollector

### Testing

```bash
# Run all tests
pytest

# With coverage
pytest --cov=sportsbetsinfo

# Type checking
mypy src/

# Linting
ruff check src/
```

### Build & Dependencies

- **Build system**: Hatchling
- **Python**: >=3.11
- **Type checking**: MyPy (strict mode)
- **Linting**: Ruff

Core dependencies: pydantic, pydantic-settings, httpx, click, rich, cryptography

## Common Development Tasks

### Add a new CLI command

1. Add function in `cli/commands.py` with `@cli.command()` decorator
2. Use existing services/repositories
3. Output with `rich` console for formatting

### Add a new entity type

1. Create frozen dataclass in `core/models.py`
2. Add hash function in `core/hashing.py`
3. Create table in `db/schema.py` with immutability trigger
4. Create repository in `db/repositories/`
5. Add service methods as needed

### Add a new API client

1. Extend `BaseAPIClient` in `clients/`
2. Implement `get_markets()`, `get_odds()`, `normalize_*_data()`
3. Add rate limiting configuration
4. Integrate in `DataCollector.collect_snapshot()`

## Code Conventions

- **Immutability**: All domain models are frozen dataclasses
- **Async**: API clients use async/await with httpx
- **Type hints**: Full type annotations throughout
- **Repositories**: Only expose insert + read operations
- **Hashing**: Content-based SHA-256 for integrity verification
- **No side effects**: Pure functions for transformations
