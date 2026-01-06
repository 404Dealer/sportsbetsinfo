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
