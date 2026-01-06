"""JSON API endpoints for sportsbetsinfo web UI."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from sportsbetsinfo.config.settings import get_settings
from sportsbetsinfo.db.connection import get_connection
from sportsbetsinfo.db.schema import get_table_counts

router = APIRouter()


class StatusResponse(BaseModel):
    """Response model for status endpoint."""

    snapshots: int
    analyses: int
    outcomes: int
    evaluations: int
    proposals: int
    last_updated: str


class CollectResponse(BaseModel):
    """Response model for collect endpoint."""

    status: str
    message: str
    snapshots_created: int = 0
    games: list[dict[str, Any]] = []


class EdgeItem(BaseModel):
    """Single edge opportunity."""

    game: str
    home_team: str
    away_team: str
    vegas_prob: float
    kalshi_prob: float | None
    delta: float | None
    delta_percent: float | None
    direction: str | None
    matched: bool
    game_status: str
    event_id: str


class EdgesResponse(BaseModel):
    """Response model for edges endpoint."""

    edges: list[EdgeItem]
    total_games: int
    matched_games: int
    significant_edges: int
    analysis_id: str | None = None
    analyzed_at: str | None = None


class EvaluateResponse(BaseModel):
    """Response model for evaluate endpoint."""

    status: str
    message: str
    evaluations_created: int = 0


class ReportResponse(BaseModel):
    """Response model for report endpoint."""

    total_evaluations: int
    avg_brier_score: float | None
    avg_log_loss: float | None
    avg_roi: float | None
    total_roi: float | None
    edge_bets_won: int
    edge_bets_lost: int
    edge_win_rate: float | None
    interpretation: str


@router.get("/status", response_model=StatusResponse)
def get_status() -> StatusResponse:
    """Get current database statistics."""
    settings = get_settings()

    if not settings.db_path.exists():
        return StatusResponse(
            snapshots=0,
            analyses=0,
            outcomes=0,
            evaluations=0,
            proposals=0,
            last_updated=datetime.now(timezone.utc).isoformat(),
        )

    with get_connection(settings.db_path) as conn:
        counts = get_table_counts(conn)

    return StatusResponse(
        snapshots=counts.get("info_snapshots", 0),
        analyses=counts.get("analyses", 0),
        outcomes=counts.get("outcomes", 0),
        evaluations=counts.get("evaluations", 0),
        proposals=counts.get("improvement_proposals", 0),
        last_updated=datetime.now(timezone.utc).isoformat(),
    )


@router.post("/collect", response_model=CollectResponse)
async def collect_today(sport: str = "basketball_nba") -> CollectResponse:
    """Collect snapshots for today's games."""
    from sportsbetsinfo.services.collector import DataCollector

    settings = get_settings()

    if not settings.odds_api_configured:
        raise HTTPException(
            status_code=400,
            detail="Odds API not configured. Set SPORTSBETS_ODDS_API_KEY.",
        )

    today = datetime.now(timezone.utc).date()

    async with DataCollector(settings) as collector:
        snapshots = await collector.collect_day_snapshots(
            target_date=today,
            sport=sport,
        )

    if not snapshots:
        return CollectResponse(
            status="success",
            message=f"No {sport} games found for today",
            snapshots_created=0,
        )

    # Extract game info from snapshots
    games = []
    for snapshot in snapshots:
        events = snapshot.normalized_fields.get("odds_api_events", [])
        if events:
            event = events[0]
            games.append({
                "home_team": event.get("home_team", "?"),
                "away_team": event.get("away_team", "?"),
                "game_status": event.get("game_status", "pre_game"),
                "snapshot_id": snapshot.snapshot_id[:8],
            })

    return CollectResponse(
        status="success",
        message=f"Collected {len(snapshots)} games for {today}",
        snapshots_created=len(snapshots),
        games=games,
    )


@router.get("/edges", response_model=EdgesResponse)
def get_edges() -> EdgesResponse:
    """Get current edge opportunities from latest analysis."""
    from sportsbetsinfo.db.repositories.analysis import AnalysisRepository

    settings = get_settings()

    if not settings.db_path.exists():
        return EdgesResponse(
            edges=[],
            total_games=0,
            matched_games=0,
            significant_edges=0,
        )

    with get_connection(settings.db_path) as conn:
        repo = AnalysisRepository(conn)
        analyses = repo.get_all(limit=1)

    if not analyses:
        return EdgesResponse(
            edges=[],
            total_games=0,
            matched_games=0,
            significant_edges=0,
        )

    analysis = analyses[0]
    comparisons = analysis.derived_features.get("comparisons", [])

    # Build edge items sorted by delta magnitude
    edges = []
    for comp in comparisons:
        edge = EdgeItem(
            game=f"{comp.get('away_team', '?')} @ {comp.get('home_team', '?')}",
            home_team=comp.get("home_team", "?"),
            away_team=comp.get("away_team", "?"),
            vegas_prob=comp.get("vegas_home_prob", 0),
            kalshi_prob=comp.get("kalshi_implied_prob"),
            delta=comp.get("delta_home"),
            delta_percent=comp.get("delta_home_percent"),
            direction=comp.get("edge_direction"),
            matched=comp.get("matched", False),
            game_status=comp.get("game_status", "pre_game"),
            event_id=comp.get("event_id", ""),
        )
        edges.append(edge)

    # Sort by absolute delta (largest first)
    edges.sort(key=lambda e: abs(e.delta or 0), reverse=True)

    matched = [e for e in edges if e.matched]
    significant = [e for e in edges if e.delta and abs(e.delta) > 0.03]

    return EdgesResponse(
        edges=edges,
        total_games=len(edges),
        matched_games=len(matched),
        significant_edges=len(significant),
        analysis_id=analysis.analysis_id[:8],
        analyzed_at=analysis.created_at.isoformat(),
    )


@router.post("/analyze")
async def run_analysis() -> dict[str, Any]:
    """Run analysis on all games with snapshots."""
    from sportsbetsinfo.services.analyzer import AnalysisService

    settings = get_settings()
    service = AnalysisService(settings)

    analyses = service.analyze_all_games()

    return {
        "status": "success",
        "message": f"Created {len(analyses)} analysis(es)",
        "analyses_created": len(analyses),
    }


@router.post("/evaluate", response_model=EvaluateResponse)
def run_evaluation() -> EvaluateResponse:
    """Evaluate analyses against outcomes."""
    from sportsbetsinfo.services.evaluator import EvaluationService

    settings = get_settings()
    service = EvaluationService(settings)

    evaluations = service.evaluate_all_pending()

    if not evaluations:
        return EvaluateResponse(
            status="success",
            message="No new evaluations (pending analyses or missing outcomes)",
            evaluations_created=0,
        )

    return EvaluateResponse(
        status="success",
        message=f"Created {len(evaluations)} evaluation(s)",
        evaluations_created=len(evaluations),
    )


@router.get("/report", response_model=ReportResponse)
def get_report() -> ReportResponse:
    """Get aggregate performance report."""
    from sportsbetsinfo.services.evaluator import EvaluationService

    settings = get_settings()
    service = EvaluationService(settings)

    report = service.get_aggregate_report()

    if "error" in report:
        return ReportResponse(
            total_evaluations=0,
            avg_brier_score=None,
            avg_log_loss=None,
            avg_roi=None,
            total_roi=None,
            edge_bets_won=0,
            edge_bets_lost=0,
            edge_win_rate=None,
            interpretation=report["error"],
        )

    return ReportResponse(
        total_evaluations=report.get("total_evaluations", 0),
        avg_brier_score=report.get("avg_brier_score"),
        avg_log_loss=report.get("avg_log_loss"),
        avg_roi=report.get("avg_roi"),
        total_roi=report.get("total_roi"),
        edge_bets_won=report.get("edge_bets_won", 0),
        edge_bets_lost=report.get("edge_bets_lost", 0),
        edge_win_rate=report.get("edge_win_rate"),
        interpretation=report.get("interpretation", ""),
    )


@router.post("/ingest-outcomes")
async def ingest_outcomes(
    sport: str = "basketball_nba",
    days: int = 3,
) -> dict[str, Any]:
    """Ingest outcomes for completed games."""
    from sportsbetsinfo.services.outcomes import OutcomeService

    settings = get_settings()

    if not settings.odds_api_configured:
        raise HTTPException(
            status_code=400,
            detail="Odds API not configured. Set SPORTSBETS_ODDS_API_KEY.",
        )

    async with OutcomeService(settings) as service:
        outcomes = await service.ingest_outcomes(sport=sport, days_from=days)

    return {
        "status": "success",
        "message": f"Ingested {len(outcomes)} outcome(s)",
        "outcomes_created": len(outcomes),
    }


@router.get("/games/{game_id}/timeline")
def get_game_timeline(game_id: str) -> dict[str, Any]:
    """Get belief drift timeline for a specific game."""
    from sportsbetsinfo.db.repositories.snapshot import SnapshotRepository

    settings = get_settings()

    if not settings.db_path.exists():
        raise HTTPException(status_code=404, detail="Database not found")

    with get_connection(settings.db_path) as conn:
        repo = SnapshotRepository(conn)
        snapshots = repo.get_by_game_id(game_id)

    if not snapshots:
        raise HTTPException(status_code=404, detail=f"No snapshots for game {game_id}")

    timeline = []
    for snapshot in snapshots:
        events = snapshot.normalized_fields.get("odds_api_events", [])
        kalshi_markets = snapshot.normalized_fields.get("kalshi_markets", [])

        point = {
            "collected_at": snapshot.collected_at.isoformat(),
            "snapshot_id": snapshot.snapshot_id[:8],
        }

        if events:
            event = events[0]
            point["vegas_home_prob"] = event.get("home_no_vig_prob")
            point["vegas_away_prob"] = event.get("away_no_vig_prob")
            point["home_team"] = event.get("home_team")
            point["away_team"] = event.get("away_team")

        if kalshi_markets:
            # Find matching market
            market = kalshi_markets[0] if kalshi_markets else None
            if market:
                point["kalshi_prob"] = market.get("implied_probability")

        timeline.append(point)

    return {
        "game_id": game_id,
        "timeline": timeline,
        "snapshot_count": len(timeline),
    }


@router.get("/games")
def get_games() -> dict[str, Any]:
    """Get list of all games with snapshots."""
    from sportsbetsinfo.db.repositories.outcome import OutcomeRepository
    from sportsbetsinfo.db.repositories.snapshot import SnapshotRepository

    settings = get_settings()

    if not settings.db_path.exists():
        return {"games": [], "total": 0}

    with get_connection(settings.db_path) as conn:
        snapshot_repo = SnapshotRepository(conn)
        outcome_repo = OutcomeRepository(conn)

        snapshots = snapshot_repo.get_all(limit=500)
        outcomes = outcome_repo.get_all(limit=500)

    # Group snapshots by game_id
    games_map: dict[str, dict[str, Any]] = {}
    outcomes_map = {o.game_id: o for o in outcomes}

    for snapshot in snapshots:
        game_id = snapshot.game_id
        events = snapshot.normalized_fields.get("odds_api_events", [])

        if game_id not in games_map:
            games_map[game_id] = {
                "game_id": game_id,
                "snapshot_count": 0,
                "first_snapshot": snapshot.collected_at.isoformat(),
                "last_snapshot": snapshot.collected_at.isoformat(),
                "home_team": None,
                "away_team": None,
                "has_outcome": game_id in outcomes_map,
                "winner": None,
                "final_score": None,
            }

            if events:
                event = events[0]
                games_map[game_id]["home_team"] = event.get("home_team")
                games_map[game_id]["away_team"] = event.get("away_team")

            if game_id in outcomes_map:
                outcome = outcomes_map[game_id]
                games_map[game_id]["winner"] = outcome.winner
                games_map[game_id]["final_score"] = (
                    f"{outcome.final_score.away}-{outcome.final_score.home}"
                )

        games_map[game_id]["snapshot_count"] += 1
        if snapshot.collected_at.isoformat() > games_map[game_id]["last_snapshot"]:
            games_map[game_id]["last_snapshot"] = snapshot.collected_at.isoformat()

    games = sorted(games_map.values(), key=lambda g: g["last_snapshot"], reverse=True)

    return {"games": games, "total": len(games)}


@router.get("/charts/calibration")
def get_calibration_data() -> dict[str, Any]:
    """Get calibration plot data (predicted vs actual outcomes).

    Buckets predictions into probability ranges and calculates
    actual win rates for each bucket.
    """
    from sportsbetsinfo.db.repositories.evaluation import EvaluationRepository

    settings = get_settings()

    if not settings.db_path.exists():
        return {"buckets": [], "total_evaluations": 0}

    with get_connection(settings.db_path) as conn:
        repo = EvaluationRepository(conn)
        evaluations = repo.get_all(limit=10000)

    if not evaluations:
        return {"buckets": [], "total_evaluations": 0}

    # Define buckets: 0-20%, 20-40%, 40-60%, 60-80%, 80-100%
    bucket_ranges = [
        (0.0, 0.2, "0-20%"),
        (0.2, 0.4, "20-40%"),
        (0.4, 0.6, "40-60%"),
        (0.6, 0.8, "60-80%"),
        (0.8, 1.0, "80-100%"),
    ]

    buckets: dict[str, dict[str, Any]] = {
        label: {"label": label, "min": min_p, "max": max_p, "predictions": [], "outcomes": []}
        for min_p, max_p, label in bucket_ranges
    }

    for evaluation in evaluations:
        notes = evaluation.notes or {}
        vegas_prob = notes.get("vegas_home_prob")
        home_won = notes.get("home_won")

        if vegas_prob is None or home_won is None:
            continue

        # Find the bucket
        for min_p, max_p, label in bucket_ranges:
            if min_p <= vegas_prob < max_p or (max_p == 1.0 and vegas_prob == 1.0):
                buckets[label]["predictions"].append(vegas_prob)
                buckets[label]["outcomes"].append(1.0 if home_won else 0.0)
                break

    # Calculate actual win rates
    result_buckets = []
    for label, data in buckets.items():
        n = len(data["outcomes"])
        if n > 0:
            avg_predicted = sum(data["predictions"]) / n
            actual_rate = sum(data["outcomes"]) / n
        else:
            avg_predicted = (data["min"] + data["max"]) / 2
            actual_rate = None

        result_buckets.append({
            "label": label,
            "avg_predicted": round(avg_predicted, 4),
            "actual_rate": round(actual_rate, 4) if actual_rate is not None else None,
            "count": n,
            "midpoint": (data["min"] + data["max"]) / 2,
        })

    return {
        "buckets": result_buckets,
        "total_evaluations": len(evaluations),
    }


@router.get("/charts/roi-waterfall")
def get_roi_waterfall() -> dict[str, Any]:
    """Get cumulative ROI waterfall data.

    Returns chronological sequence of bets with running P&L.
    """
    from sportsbetsinfo.db.repositories.evaluation import EvaluationRepository

    settings = get_settings()

    if not settings.db_path.exists():
        return {"bets": [], "total_roi": 0}

    with get_connection(settings.db_path) as conn:
        repo = EvaluationRepository(conn)
        evaluations = repo.get_all(limit=10000)

    if not evaluations:
        return {"bets": [], "total_roi": 0}

    # Sort by scored_at
    sorted_evals = sorted(evaluations, key=lambda e: e.scored_at)

    bets = []
    cumulative = 0.0

    for evaluation in sorted_evals:
        roi = evaluation.metrics.roi
        if roi is None:
            continue

        cumulative += roi
        notes = evaluation.notes or {}

        bets.append({
            "date": evaluation.scored_at.isoformat(),
            "game": f"{notes.get('away_team', '?')} @ {notes.get('home_team', '?')}",
            "roi": round(roi, 4),
            "cumulative": round(cumulative, 4),
            "won": roi > 0,
        })

    return {
        "bets": bets,
        "total_roi": round(cumulative, 4),
        "total_bets": len(bets),
    }


@router.get("/charts/edge-accuracy")
def get_edge_accuracy() -> dict[str, Any]:
    """Get rolling edge accuracy data.

    Shows win rate on edge bets (>3% delta) over time.
    """
    from sportsbetsinfo.db.repositories.evaluation import EvaluationRepository

    settings = get_settings()

    if not settings.db_path.exists():
        return {"points": [], "overall_win_rate": None}

    with get_connection(settings.db_path) as conn:
        repo = EvaluationRepository(conn)
        evaluations = repo.get_all(limit=10000)

    if not evaluations:
        return {"points": [], "overall_win_rate": None}

    # Filter to edge bets only (where edge_realized is not None)
    edge_evals = [e for e in evaluations if e.metrics.edge_realized is not None]

    if not edge_evals:
        return {"points": [], "overall_win_rate": None}

    # Sort by scored_at
    sorted_evals = sorted(edge_evals, key=lambda e: e.scored_at)

    # Calculate rolling win rate (window of 10)
    window_size = min(10, len(sorted_evals))
    points = []
    wins = 0
    total = 0

    for i, evaluation in enumerate(sorted_evals):
        won = evaluation.metrics.edge_realized > 0
        wins += 1 if won else 0
        total += 1

        # Rolling window
        if i >= window_size:
            old_eval = sorted_evals[i - window_size]
            old_won = old_eval.metrics.edge_realized > 0
            wins -= 1 if old_won else 0

        current_window = min(total, window_size)
        win_rate = wins / current_window if current_window > 0 else 0

        notes = evaluation.notes or {}
        points.append({
            "date": evaluation.scored_at.isoformat(),
            "game": f"{notes.get('away_team', '?')} @ {notes.get('home_team', '?')}",
            "win_rate": round(win_rate, 4),
            "won": won,
            "cumulative_wins": sum(
                1 for e in sorted_evals[: i + 1] if e.metrics.edge_realized > 0
            ),
            "cumulative_total": i + 1,
        })

    # Overall win rate
    total_wins = sum(1 for e in sorted_evals if e.metrics.edge_realized > 0)
    overall = total_wins / len(sorted_evals) if sorted_evals else None

    return {
        "points": points,
        "overall_win_rate": round(overall, 4) if overall else None,
        "total_edge_bets": len(sorted_evals),
        "window_size": window_size,
    }


@router.get("/charts/heatmap")
def get_heatmap_data() -> dict[str, Any]:
    """Get market disagreement heatmap data.

    Returns all games with their Kalshi/Vegas delta for visualization.
    """
    from sportsbetsinfo.db.repositories.analysis import AnalysisRepository

    settings = get_settings()

    if not settings.db_path.exists():
        return {"games": [], "analyzed_at": None}

    with get_connection(settings.db_path) as conn:
        repo = AnalysisRepository(conn)
        analyses = repo.get_all(limit=1)

    if not analyses:
        return {"games": [], "analyzed_at": None}

    analysis = analyses[0]
    comparisons = analysis.derived_features.get("comparisons", [])

    games = []
    for comp in comparisons:
        if not comp.get("matched"):
            continue

        games.append({
            "game": f"{comp.get('away_team', '?')} @ {comp.get('home_team', '?')}",
            "home_team": comp.get("home_team", "?"),
            "delta": comp.get("delta_home", 0),
            "delta_percent": comp.get("delta_home_percent", 0),
            "vegas_prob": comp.get("vegas_home_prob", 0),
            "kalshi_prob": comp.get("kalshi_implied_prob", 0),
            "direction": comp.get("edge_direction"),
        })

    # Sort by delta (most negative to most positive for visual flow)
    games.sort(key=lambda g: g["delta"])

    return {
        "games": games,
        "analyzed_at": analysis.created_at.isoformat(),
        "total_matched": len(games),
    }
