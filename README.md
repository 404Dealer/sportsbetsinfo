# SportsBetsInfo

Event-sourced sports betting research platform with immutable timeline tracking.

## Concept

**Lab notebook + Factory + Scoreboard:**

- **Lab notebook**: Every "what we knew at time T" is saved exactly as-is, forever
- **Factory**: Deterministic transforms turn raw info into comparable numbers
- **Scoreboard**: Attach actual outcomes and judge which transforms/ideas worked

## Architecture

### Core Entities

1. **InfoSnapshot** - Immutable market data at a timestamp
   - Raw API payloads preserved exactly
   - Normalized fields for comparison
   - Content-addressable hash for integrity

2. **Analysis** - Derived artifacts forming a DAG (like git commits)
   - References parent analysis and input snapshots
   - Full lineage tracking

3. **Outcome** - Ground truth results
   - Attached after games complete

4. **Evaluation** - Scoring analyses against outcomes
   - Brier score, log loss, ROI, edge realized

5. **ImprovementProposal** - LLM-suggested improvements based on evidence

### Immutability Guarantees

- Python: Frozen dataclasses prevent mutation
- SQLite: Triggers reject UPDATE/DELETE operations
- Repository: Only insert + read methods exposed
- Content hashing: SHA-256 verification on read

### Four Version Axes

1. `schema_version` - Data structure version
2. `source_versions` - Per-API versions
3. `code_version` - Git commit hash
4. `model_version` - ML model identifier

## Installation

```bash
# Clone the repository
git clone https://github.com/404Dealer/sportsbetsinfo.git
cd sportsbetsinfo

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install in development mode
pip install -e ".[dev]"

# Copy and configure environment
cp .env.example .env
# Edit .env with your API keys
```

## Configuration

Set environment variables (or add to `.env`):

```bash
# Database
SPORTSBETS_DB_PATH=data/sportsbets.db

# Kalshi API (https://kalshi.com)
SPORTSBETS_KALSHI_API_KEY=your_email
SPORTSBETS_KALSHI_API_SECRET=your_password

# The Odds API (https://the-odds-api.com)
SPORTSBETS_ODDS_API_KEY=your_key
```

## Usage

### Initialize Database

```bash
sportsbetsinfo init-db
```

### Check Status

```bash
sportsbetsinfo status
```

### Collect Market Data

```bash
# Collect snapshot for a specific game
sportsbetsinfo collect game-12345 --sport basketball_nba
```

### View Timeline

```bash
# See all snapshots for a game (what we knew at each time T)
sportsbetsinfo timeline game-12345
```

### View Analysis Lineage

```bash
# Trace the DAG path for an analysis
sportsbetsinfo lineage analysis-uuid
```

### Verify Integrity

```bash
# Check all hashes match
sportsbetsinfo verify
```

### Show Configuration

```bash
sportsbetsinfo config
```

## Project Structure

```
sportsbetsinfo/
├── src/sportsbetsinfo/
│   ├── core/           # Domain models, hashing, exceptions
│   ├── config/         # Pydantic settings
│   ├── db/             # SQLite schema, connection, repositories
│   ├── clients/        # Kalshi, The Odds API clients
│   ├── services/       # Data collection, analysis
│   └── cli/            # Click commands
├── data/               # SQLite database (gitignored)
└── tests/              # Test suite
```

## Data Sources

- **Kalshi**: Prediction market prices (YES/NO cents)
- **The Odds API**: Vegas odds from multiple bookmakers

## Key Features

- **Timeline queries**: "What did I know at 12:15?"
- **Delta computation**: "What changed between snapshot A and B?"
- **No-vig probabilities**: Fair odds with bookmaker edge removed
- **DAG analysis**: Trace how conclusions evolved with new data
- **Hash verification**: Detect any data corruption

## The "Edge" Formula

An edge exists when:

```
At time T:
- What was Kalshi price? (YES cents)
- What was Vegas no-vig probability?
- What was expected value given fees/spread/liquidity?
Later:
- What actually happened?
```

If your system consistently predicts better than the market after costs, you have an edge.

## License

MIT
