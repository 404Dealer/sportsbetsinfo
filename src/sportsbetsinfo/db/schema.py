"""SQLite database schema with immutability enforcement.

All tables are append-only with triggers preventing UPDATE and DELETE.
This enforces the core principle: snapshots, analyses, and evaluations
are immutable once created.
"""

import sqlite3

# Schema DDL for all tables
SCHEMA_SQL = """
-- Enable foreign keys
PRAGMA foreign_keys = ON;

--------------------------------------------------------------------------------
-- INFO_SNAPSHOTS: Immutable market data snapshots
--------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS info_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    game_id TEXT NOT NULL,
    collected_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    source_versions TEXT NOT NULL,
    raw_payloads TEXT NOT NULL,
    normalized_fields TEXT NOT NULL,
    hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_snapshots_game_id ON info_snapshots(game_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_collected_at ON info_snapshots(collected_at);
CREATE INDEX IF NOT EXISTS idx_snapshots_hash ON info_snapshots(hash);

--------------------------------------------------------------------------------
-- ANALYSES: DAG of derived artifacts (like git commits)
--------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS analyses (
    analysis_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    analysis_version TEXT NOT NULL,
    code_version TEXT NOT NULL,
    model_version TEXT,
    parent_analysis_id TEXT,
    derived_features TEXT NOT NULL,
    conclusions TEXT NOT NULL,
    recommended_actions TEXT NOT NULL,
    hash TEXT NOT NULL UNIQUE,
    FOREIGN KEY (parent_analysis_id) REFERENCES analyses(analysis_id)
);

CREATE INDEX IF NOT EXISTS idx_analyses_parent ON analyses(parent_analysis_id);
CREATE INDEX IF NOT EXISTS idx_analyses_created_at ON analyses(created_at);
CREATE INDEX IF NOT EXISTS idx_analyses_hash ON analyses(hash);

--------------------------------------------------------------------------------
-- ANALYSIS_SNAPSHOTS: Junction table for Analysis -> Snapshot (many-to-many)
--------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS analysis_snapshots (
    analysis_id TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    PRIMARY KEY (analysis_id, snapshot_id),
    FOREIGN KEY (analysis_id) REFERENCES analyses(analysis_id),
    FOREIGN KEY (snapshot_id) REFERENCES info_snapshots(snapshot_id)
);

--------------------------------------------------------------------------------
-- OUTCOMES: Ground truth results
--------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS outcomes (
    outcome_id TEXT PRIMARY KEY,
    game_id TEXT NOT NULL UNIQUE,
    occurred_at TEXT NOT NULL,
    final_score TEXT NOT NULL,
    winner TEXT,
    stats_summary TEXT NOT NULL,
    source TEXT NOT NULL,
    hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_outcomes_game_id ON outcomes(game_id);
CREATE INDEX IF NOT EXISTS idx_outcomes_occurred_at ON outcomes(occurred_at);

--------------------------------------------------------------------------------
-- EVALUATIONS: Scoring analyses against outcomes
--------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS evaluations (
    evaluation_id TEXT PRIMARY KEY,
    analysis_id TEXT NOT NULL,
    game_id TEXT NOT NULL,
    scored_at TEXT NOT NULL,
    brier_score REAL,
    log_loss REAL,
    roi REAL,
    edge_realized REAL,
    notes TEXT,
    hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (analysis_id) REFERENCES analyses(analysis_id),
    FOREIGN KEY (game_id) REFERENCES outcomes(game_id)
);

CREATE INDEX IF NOT EXISTS idx_evaluations_analysis ON evaluations(analysis_id);
CREATE INDEX IF NOT EXISTS idx_evaluations_game ON evaluations(game_id);

--------------------------------------------------------------------------------
-- IMPROVEMENT_PROPOSALS: LLM-suggested improvements based on evidence
--------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS improvement_proposals (
    proposal_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    proposal_text TEXT NOT NULL,
    suggested_schema_additions TEXT,
    suggested_modules TEXT,
    expected_impact TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    hash TEXT NOT NULL UNIQUE,
    created_at_db TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_proposals_status ON improvement_proposals(status);
CREATE INDEX IF NOT EXISTS idx_proposals_created ON improvement_proposals(created_at);

--------------------------------------------------------------------------------
-- PROPOSAL_EVALUATIONS: Junction table for Proposal -> Evaluation
--------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS proposal_evaluations (
    proposal_id TEXT NOT NULL,
    evaluation_id TEXT NOT NULL,
    PRIMARY KEY (proposal_id, evaluation_id),
    FOREIGN KEY (proposal_id) REFERENCES improvement_proposals(proposal_id),
    FOREIGN KEY (evaluation_id) REFERENCES evaluations(evaluation_id)
);
"""

# Triggers to enforce immutability
IMMUTABILITY_TRIGGERS_SQL = """
--------------------------------------------------------------------------------
-- IMMUTABILITY TRIGGERS: Prevent UPDATE and DELETE on all tables
--------------------------------------------------------------------------------

-- info_snapshots
CREATE TRIGGER IF NOT EXISTS prevent_snapshot_update
BEFORE UPDATE ON info_snapshots
BEGIN
    SELECT RAISE(ABORT, 'Updates not allowed on immutable table info_snapshots');
END;

CREATE TRIGGER IF NOT EXISTS prevent_snapshot_delete
BEFORE DELETE ON info_snapshots
BEGIN
    SELECT RAISE(ABORT, 'Deletes not allowed on immutable table info_snapshots');
END;

-- analyses
CREATE TRIGGER IF NOT EXISTS prevent_analysis_update
BEFORE UPDATE ON analyses
BEGIN
    SELECT RAISE(ABORT, 'Updates not allowed on immutable table analyses');
END;

CREATE TRIGGER IF NOT EXISTS prevent_analysis_delete
BEFORE DELETE ON analyses
BEGIN
    SELECT RAISE(ABORT, 'Deletes not allowed on immutable table analyses');
END;

-- analysis_snapshots
CREATE TRIGGER IF NOT EXISTS prevent_analysis_snapshots_update
BEFORE UPDATE ON analysis_snapshots
BEGIN
    SELECT RAISE(ABORT, 'Updates not allowed on immutable table analysis_snapshots');
END;

CREATE TRIGGER IF NOT EXISTS prevent_analysis_snapshots_delete
BEFORE DELETE ON analysis_snapshots
BEGIN
    SELECT RAISE(ABORT, 'Deletes not allowed on immutable table analysis_snapshots');
END;

-- outcomes
CREATE TRIGGER IF NOT EXISTS prevent_outcome_update
BEFORE UPDATE ON outcomes
BEGIN
    SELECT RAISE(ABORT, 'Updates not allowed on immutable table outcomes');
END;

CREATE TRIGGER IF NOT EXISTS prevent_outcome_delete
BEFORE DELETE ON outcomes
BEGIN
    SELECT RAISE(ABORT, 'Deletes not allowed on immutable table outcomes');
END;

-- evaluations
CREATE TRIGGER IF NOT EXISTS prevent_evaluation_update
BEFORE UPDATE ON evaluations
BEGIN
    SELECT RAISE(ABORT, 'Updates not allowed on immutable table evaluations');
END;

CREATE TRIGGER IF NOT EXISTS prevent_evaluation_delete
BEFORE DELETE ON evaluations
BEGIN
    SELECT RAISE(ABORT, 'Deletes not allowed on immutable table evaluations');
END;

-- improvement_proposals (status is special - can be updated)
-- We allow status updates but nothing else
CREATE TRIGGER IF NOT EXISTS prevent_proposal_delete
BEFORE DELETE ON improvement_proposals
BEGIN
    SELECT RAISE(ABORT, 'Deletes not allowed on immutable table improvement_proposals');
END;

-- proposal_evaluations
CREATE TRIGGER IF NOT EXISTS prevent_proposal_evaluations_update
BEFORE UPDATE ON proposal_evaluations
BEGIN
    SELECT RAISE(ABORT, 'Updates not allowed on immutable table proposal_evaluations');
END;

CREATE TRIGGER IF NOT EXISTS prevent_proposal_evaluations_delete
BEFORE DELETE ON proposal_evaluations
BEGIN
    SELECT RAISE(ABORT, 'Deletes not allowed on immutable table proposal_evaluations');
END;
"""


def create_all_tables(conn: sqlite3.Connection) -> None:
    """Create all tables and indexes.

    Args:
        conn: SQLite connection
    """
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def create_immutability_triggers(conn: sqlite3.Connection) -> None:
    """Create triggers that enforce append-only behavior.

    Args:
        conn: SQLite connection
    """
    conn.executescript(IMMUTABILITY_TRIGGERS_SQL)
    conn.commit()


def initialize_database(conn: sqlite3.Connection) -> None:
    """Initialize database with schema and immutability triggers.

    Args:
        conn: SQLite connection
    """
    create_all_tables(conn)
    create_immutability_triggers(conn)


def get_table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Get row counts for all tables.

    Args:
        conn: SQLite connection

    Returns:
        Dictionary mapping table name to row count
    """
    tables = [
        "info_snapshots",
        "analyses",
        "analysis_snapshots",
        "outcomes",
        "evaluations",
        "improvement_proposals",
        "proposal_evaluations",
    ]
    counts = {}
    cursor = conn.cursor()
    for table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")  # noqa: S608
        counts[table] = cursor.fetchone()[0]
    return counts
