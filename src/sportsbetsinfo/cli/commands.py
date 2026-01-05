"""CLI commands for sportsbetsinfo.

Provides commands for database management, data collection,
analysis lineage, and integrity verification.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

console = Console()


@click.group()
@click.option(
    "--db",
    default="data/sportsbets.db",
    help="Path to SQLite database",
    type=click.Path(),
)
@click.pass_context
def cli(ctx: click.Context, db: str) -> None:
    """SportsBetsInfo - Event-sourced betting research platform.

    An immutable timeline of market data with full lineage tracking.
    """
    ctx.ensure_object(dict)
    ctx.obj["db_path"] = Path(db)


@cli.command()
@click.pass_context
def init_db(ctx: click.Context) -> None:
    """Initialize the database schema.

    Creates all tables and immutability triggers.
    """
    from sportsbetsinfo.db.connection import get_connection
    from sportsbetsinfo.db.schema import initialize_database

    db_path = ctx.obj["db_path"]
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with get_connection(db_path) as conn:
        initialize_database(conn)

    console.print(f"[green]Database initialized at {db_path}[/green]")


@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show database statistics."""
    from sportsbetsinfo.db.connection import get_connection
    from sportsbetsinfo.db.schema import get_table_counts

    db_path = ctx.obj["db_path"]

    if not db_path.exists():
        console.print(f"[red]Database not found at {db_path}[/red]")
        console.print("Run 'sportsbetsinfo init-db' first.")
        return

    with get_connection(db_path) as conn:
        counts = get_table_counts(conn)

        table = Table(title="Database Statistics")
        table.add_column("Entity", style="cyan")
        table.add_column("Count", justify="right", style="green")

        for entity, count in counts.items():
            table.add_row(entity, str(count))

        console.print(table)


@cli.command()
@click.argument("game_id")
@click.option("--sport", default="basketball_nba", help="Sport key for The Odds API")
@click.pass_context
def collect(ctx: click.Context, game_id: str, sport: str) -> None:
    """Collect market data snapshot for a game.

    Creates an immutable InfoSnapshot with data from all configured sources.
    """
    from sportsbetsinfo.config.settings import get_settings
    from sportsbetsinfo.services.collector import DataCollector

    settings = get_settings()

    if not settings.kalshi_configured and not settings.odds_api_configured:
        console.print("[red]No API keys configured![/red]")
        console.print("Set SPORTSBETS_KALSHI_API_KEY or SPORTSBETS_ODDS_API_KEY in .env")
        return

    async def _collect() -> None:
        async with DataCollector(settings) as collector:
            snapshot = await collector.collect_snapshot(game_id, sport=sport)
            console.print(f"[green]Created snapshot:[/green] {snapshot.snapshot_id}")
            console.print(f"  Game ID: {snapshot.game_id}")
            console.print(f"  Collected at: {snapshot.collected_at}")
            console.print(f"  Schema version: {snapshot.schema_version}")
            console.print(f"  Hash: {snapshot.hash[:16]}...")

    asyncio.run(_collect())


@cli.command("collect-day")
@click.argument("target_date", required=False)
@click.option("--sport", default="basketball_nba", help="Sport key for The Odds API")
@click.pass_context
def collect_day(ctx: click.Context, target_date: str | None, sport: str) -> None:
    """Collect market data for all games on a date.

    Fetches all games for TARGET_DATE (YYYY-MM-DD format, defaults to today UTC)
    and creates an immutable InfoSnapshot for each game.
    """
    from sportsbetsinfo.config.settings import get_settings
    from sportsbetsinfo.services.collector import DataCollector

    settings = get_settings()

    if not settings.odds_api_configured:
        console.print("[red]Odds API key not configured![/red]")
        console.print("Set SPORTSBETS_ODDS_API_KEY in .env")
        return

    # Parse date or use today (UTC)
    if target_date:
        try:
            parsed_date = datetime.strptime(target_date, "%Y-%m-%d").date()
        except ValueError:
            console.print(f"[red]Invalid date format: {target_date}[/red]")
            console.print("Use YYYY-MM-DD format (e.g., 2025-01-05)")
            return
    else:
        parsed_date = datetime.now(timezone.utc).date()

    console.print(f"Collecting {sport} games for [cyan]{parsed_date}[/cyan] (UTC)...")

    async def _collect_day() -> None:
        async with DataCollector(settings) as collector:
            snapshots = await collector.collect_day_snapshots(
                target_date=parsed_date,
                sport=sport,
            )

            if not snapshots:
                console.print(f"[yellow]No {sport} games found for {parsed_date}[/yellow]")
                return

            table = Table(title=f"Games Collected: {parsed_date}")
            table.add_column("Status", style="bold")
            table.add_column("Teams", style="cyan")
            table.add_column("Score", justify="center")
            table.add_column("Time (UTC)", style="green")
            table.add_column("Snapshot", style="dim")

            for snapshot in snapshots:
                # Extract game info from normalized fields
                events = snapshot.normalized_fields.get("odds_api_events", [])
                if events:
                    event = events[0]
                    away = event.get("away_team", "?")
                    home = event.get("home_team", "?")
                    teams = f"{away} @ {home}"

                    # Game status
                    game_status = event.get("game_status", "pre_game")
                    if game_status == "completed":
                        status = "[green]FINAL[/green]"
                    elif game_status == "in_progress":
                        status = "[yellow]LIVE[/yellow]"
                    else:
                        status = "[dim]PRE[/dim]"

                    # Score
                    home_score = event.get("home_score")
                    away_score = event.get("away_score")
                    if home_score is not None and away_score is not None:
                        score = f"{away_score}-{home_score}"
                    else:
                        score = "-"

                    # Time
                    start_time = event.get("commence_time", "?")
                    if start_time and start_time != "?":
                        try:
                            dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                            start_time = dt.strftime("%H:%M")
                        except (ValueError, AttributeError):
                            pass
                else:
                    status = "[dim]?[/dim]"
                    teams = "Unknown"
                    score = "-"
                    start_time = "?"

                table.add_row(
                    status,
                    teams,
                    score,
                    start_time,
                    snapshot.snapshot_id[:8] + "...",
                )

            console.print(table)
            console.print(f"\n[green]Created {len(snapshots)} snapshot(s)[/green]")

            # Show API quota if available
            if collector._odds_api and collector._odds_api.requests_remaining is not None:
                console.print(
                    f"[dim]Odds API requests remaining: "
                    f"{collector._odds_api.requests_remaining}[/dim]"
                )

    asyncio.run(_collect_day())


@cli.command()
@click.argument("game_id")
@click.pass_context
def timeline(ctx: click.Context, game_id: str) -> None:
    """Show snapshot timeline for a game.

    Displays all snapshots in chronological order - the "what we knew at time T"
    history for a specific game.
    """
    from sportsbetsinfo.db.connection import get_connection
    from sportsbetsinfo.db.repositories.snapshot import SnapshotRepository

    db_path = ctx.obj["db_path"]

    with get_connection(db_path) as conn:
        repo = SnapshotRepository(conn)
        snapshots = repo.get_by_game_id(game_id)

        if not snapshots:
            console.print(f"[yellow]No snapshots found for game {game_id}[/yellow]")
            return

        table = Table(title=f"Snapshot Timeline: {game_id}")
        table.add_column("Time", style="cyan")
        table.add_column("Snapshot ID", style="dim")
        table.add_column("Sources", style="green")
        table.add_column("Hash", style="dim")

        for snapshot in snapshots:
            sources = []
            if snapshot.source_versions.kalshi:
                sources.append("Kalshi")
            if snapshot.source_versions.odds_api:
                sources.append("OddsAPI")

            table.add_row(
                snapshot.collected_at.strftime("%Y-%m-%d %H:%M:%S"),
                snapshot.snapshot_id[:8] + "...",
                ", ".join(sources) or "None",
                snapshot.hash[:12] + "...",
            )

        console.print(table)


@cli.command()
@click.argument("analysis_id")
@click.pass_context
def lineage(ctx: click.Context, analysis_id: str) -> None:
    """Show lineage (DAG path) for an analysis.

    Traces the parent chain from root to the specified analysis,
    showing the evolution of understanding.
    """
    from sportsbetsinfo.db.connection import get_connection
    from sportsbetsinfo.db.repositories.analysis import AnalysisRepository

    db_path = ctx.obj["db_path"]

    with get_connection(db_path) as conn:
        repo = AnalysisRepository(conn)
        path = repo.get_lineage(analysis_id)

        if not path:
            console.print(f"[red]Analysis not found: {analysis_id}[/red]")
            return

        console.print(f"[bold]Lineage for {analysis_id[:8]}...[/bold]")
        console.print()

        for i, analysis in enumerate(path):
            indent = "  " * i
            arrow = "->" if i > 0 else "  "
            console.print(
                f"{indent}{arrow} [cyan]{analysis.analysis_id[:8]}...[/cyan] "
                f"(v{analysis.analysis_version})"
            )
            console.print(
                f"{indent}   Created: {analysis.created_at.strftime('%Y-%m-%d %H:%M')}"
            )
            console.print(
                f"{indent}   Code: {analysis.code_version[:8]}..."
            )
            console.print(
                f"{indent}   Snapshots: {len(analysis.input_snapshot_ids)}"
            )


@cli.command()
@click.pass_context
def verify(ctx: click.Context) -> None:
    """Verify hash integrity of all records.

    Checks that stored hashes match computed hashes for all entities.
    Reports any integrity violations.
    """
    from sportsbetsinfo.core.exceptions import HashMismatchError
    from sportsbetsinfo.db.connection import get_connection
    from sportsbetsinfo.db.repositories.analysis import AnalysisRepository
    from sportsbetsinfo.db.repositories.evaluation import EvaluationRepository
    from sportsbetsinfo.db.repositories.outcome import OutcomeRepository
    from sportsbetsinfo.db.repositories.proposal import ProposalRepository
    from sportsbetsinfo.db.repositories.snapshot import SnapshotRepository

    db_path = ctx.obj["db_path"]
    errors: list[str] = []
    verified = 0

    with get_connection(db_path) as conn:
        # Verify snapshots
        console.print("Verifying snapshots...", end=" ")
        snapshot_repo = SnapshotRepository(conn)
        try:
            snapshots = snapshot_repo.get_all(limit=10000)
            verified += len(snapshots)
            console.print(f"[green]{len(snapshots)} OK[/green]")
        except HashMismatchError as e:
            errors.append(str(e))
            console.print(f"[red]ERROR: {e}[/red]")

        # Verify analyses
        console.print("Verifying analyses...", end=" ")
        analysis_repo = AnalysisRepository(conn)
        try:
            analyses = analysis_repo.get_all(limit=10000)
            verified += len(analyses)
            console.print(f"[green]{len(analyses)} OK[/green]")
        except HashMismatchError as e:
            errors.append(str(e))
            console.print(f"[red]ERROR: {e}[/red]")

        # Verify outcomes
        console.print("Verifying outcomes...", end=" ")
        outcome_repo = OutcomeRepository(conn)
        try:
            outcomes = outcome_repo.get_all(limit=10000)
            verified += len(outcomes)
            console.print(f"[green]{len(outcomes)} OK[/green]")
        except HashMismatchError as e:
            errors.append(str(e))
            console.print(f"[red]ERROR: {e}[/red]")

        # Verify evaluations
        console.print("Verifying evaluations...", end=" ")
        eval_repo = EvaluationRepository(conn)
        try:
            evaluations = eval_repo.get_all(limit=10000)
            verified += len(evaluations)
            console.print(f"[green]{len(evaluations)} OK[/green]")
        except HashMismatchError as e:
            errors.append(str(e))
            console.print(f"[red]ERROR: {e}[/red]")

        # Verify proposals
        console.print("Verifying proposals...", end=" ")
        proposal_repo = ProposalRepository(conn)
        try:
            proposals = proposal_repo.get_all(limit=10000)
            verified += len(proposals)
            console.print(f"[green]{len(proposals)} OK[/green]")
        except HashMismatchError as e:
            errors.append(str(e))
            console.print(f"[red]ERROR: {e}[/red]")

    console.print()
    if errors:
        console.print(f"[red]Found {len(errors)} integrity error(s)![/red]")
        for err in errors[:10]:
            console.print(f"  - {err}")
    else:
        console.print(f"[green]All {verified} records verified successfully[/green]")


@cli.command()
@click.argument("game_id", required=False)
@click.option("--all", "analyze_all", is_flag=True, help="Analyze all games with snapshots")
@click.pass_context
def analyze(ctx: click.Context, game_id: str | None, analyze_all: bool) -> None:
    """Analyze snapshots comparing Kalshi vs Vegas (with vig).

    Creates Analysis objects with edge calculations.
    Use --all to analyze all games, or provide a specific GAME_ID.
    """
    from sportsbetsinfo.config.settings import get_settings
    from sportsbetsinfo.services.analyzer import AnalysisService

    if not game_id and not analyze_all:
        console.print("[red]Provide a GAME_ID or use --all[/red]")
        return

    settings = get_settings()
    service = AnalysisService(settings)

    if analyze_all:
        console.print("Analyzing all games with snapshots...")
        analyses = service.analyze_all_games()

        if not analyses:
            console.print("[yellow]No analyses created (no matching data)[/yellow]")
            return

        table = Table(title="Analyses Created")
        table.add_column("Analysis ID", style="dim")
        table.add_column("Games", justify="right")
        table.add_column("Matched", justify="right")
        table.add_column("Edges", justify="right", style="yellow")
        table.add_column("Avg Delta", justify="right")

        for analysis in analyses:
            derived = analysis.derived_features
            conclusions = analysis.conclusions
            table.add_row(
                analysis.analysis_id[:8] + "...",
                str(derived.get("game_count", 0)),
                str(derived.get("matched_count", 0)),
                str(derived.get("edges_above_threshold", 0)),
                f"{conclusions.get('avg_delta_percent', 0):+.1f}%",
            )

        console.print(table)
        console.print(f"\n[green]Created {len(analyses)} analysis(es)[/green]")

    else:
        console.print(f"Analyzing game [cyan]{game_id}[/cyan]...")
        analysis = service.analyze_game(game_id)

        if not analysis:
            console.print(f"[yellow]No snapshot found for game {game_id}[/yellow]")
            return

        _display_analysis(analysis)


def _display_analysis(analysis: "Analysis") -> None:
    """Display a single analysis in detail."""
    from sportsbetsinfo.core.models import Analysis

    derived = analysis.derived_features
    conclusions = analysis.conclusions

    console.print(f"\n[bold]Analysis: {analysis.analysis_id[:8]}...[/bold]")
    console.print(f"  Version: {analysis.analysis_version}")
    console.print(f"  Created: {analysis.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
    console.print(f"  Code: {analysis.code_version[:8]}...")

    console.print(f"\n[bold]Summary:[/bold]")
    console.print(f"  {conclusions.get('summary', 'No summary')}")

    console.print(f"\n[bold]Stats:[/bold]")
    console.print(f"  Games analyzed: {conclusions.get('total_games', 0)}")
    console.print(f"  Matched with Kalshi: {conclusions.get('matched_with_kalshi', 0)}")
    console.print(f"  Avg Vegas vig: {conclusions.get('avg_vegas_vig_percent', 0):.1f}%")
    console.print(f"  Avg delta: {conclusions.get('avg_delta_percent', 0):+.1f}%")
    console.print(f"  Significant edges (>3%): {conclusions.get('significant_edges', 0)}")

    # Show comparisons table
    comparisons = derived.get("comparisons", [])
    if comparisons:
        console.print(f"\n[bold]Comparisons:[/bold]")
        comp_table = Table()
        comp_table.add_column("Game", style="cyan")
        comp_table.add_column("Vegas", justify="right")
        comp_table.add_column("Kalshi", justify="right")
        comp_table.add_column("Delta", justify="right")
        comp_table.add_column("Status")

        for comp in comparisons[:10]:  # Show top 10
            game = f"{comp.get('away_team', '?')[:10]} @ {comp.get('home_team', '?')[:10]}"
            vegas = f"{comp.get('vegas_home_prob', 0):.1%}"
            if comp.get("matched"):
                kalshi = f"{comp.get('kalshi_implied_prob', 0):.1%}"
                delta = comp.get("delta_home_percent", 0)
                delta_str = f"{delta:+.1f}%"
                if abs(delta) > 3:
                    delta_str = f"[yellow]{delta_str}[/yellow]"
            else:
                kalshi = "-"
                delta_str = "-"
            status = comp.get("game_status", "?")
            comp_table.add_row(game, vegas, kalshi, delta_str, status)

        console.print(comp_table)

    # Show recommendations
    recommendations = analysis.recommended_actions
    if recommendations:
        console.print(f"\n[bold]Recommendations:[/bold]")
        for i, rec in enumerate(recommendations[:3], 1):
            console.print(f"  {i}. [yellow]{rec.get('signal', '')}[/yellow]")
            console.print(f"     {rec.get('interpretation', '')}")


@cli.command()
@click.pass_context
def config(ctx: click.Context) -> None:
    """Show current configuration."""
    from sportsbetsinfo.config.settings import get_settings

    settings = get_settings()

    table = Table(title="Configuration")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Database Path", str(settings.db_path))
    table.add_row("Schema Version", settings.schema_version)
    table.add_row("Log Level", settings.log_level)
    table.add_row(
        "Kalshi API",
        "[green]Configured[/green]" if settings.kalshi_configured else "[red]Not set[/red]",
    )
    table.add_row(
        "Odds API",
        "[green]Configured[/green]" if settings.odds_api_configured else "[red]Not set[/red]",
    )
    table.add_row("Kalshi Rate Limit", f"{settings.kalshi_rate_limit}/sec")
    table.add_row("Odds API Rate Limit", f"{settings.odds_api_rate_limit}/sec")

    console.print(table)
