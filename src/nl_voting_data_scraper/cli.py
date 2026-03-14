"""CLI interface for nl-voting-data-scraper."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from nl_voting_data_scraper.config import KNOWN_ELECTIONS
from nl_voting_data_scraper.output import write_all
from nl_voting_data_scraper.scraper import StemwijzerScraper

console = Console()


def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s %(message)s",
        handlers=[logging.StreamHandler()],
    )


@click.group()
@click.version_option()
def cli():
    """nl-voting-data-scraper: Scrape Dutch voting advice (StemWijzer) data."""


@cli.command()
@click.argument("election")
@click.option("-m", "--municipality", multiple=True, help="Specific GM codes (e.g. GM0014)")
@click.option("-l", "--language", multiple=True, default=["nl"], help="Languages to scrape")
@click.option("-o", "--output", "output_dir", default="./output", help="Output directory")
@click.option("--combined", is_flag=True, help="Also write a combined.json file")
@click.option("--rate-limit", type=float, default=2.0, help="Requests per second")
@click.option("--no-cache", is_flag=True, help="Disable caching")
@click.option("--resume", is_flag=True, help="Resume interrupted scrape from cache")
@click.option("--browser-only", is_flag=True, help="Only use browser scraping")
@click.option("--api-only", is_flag=True, help="Only use API scraping")
@click.option("-v", "--verbose", is_flag=True, help="Verbose output")
def scrape(
    election: str,
    municipality: tuple[str, ...],
    language: tuple[str, ...],
    output_dir: str,
    combined: bool,
    rate_limit: float,
    no_cache: bool,
    resume: bool,
    browser_only: bool,
    api_only: bool,
    verbose: bool,
):
    """Scrape StemWijzer data for an election.

    ELECTION is the election slug (e.g. gr2026, tk2025, eu2024).
    Use 'list-elections' to see available elections.
    """
    setup_logging(verbose)
    municipalities = list(municipality) if municipality else None
    cache_dir = None if no_cache else Path(".cache") / "nl-voting-data-scraper"

    async def _run():
        scraper = StemwijzerScraper(
            election=election,
            rate_limit=rate_limit,
            cache_dir=cache_dir,
            use_browser=not api_only,
            use_api=not browser_only,
        )
        async with scraper:
            with console.status(f"Scraping {election}..."):
                results = await scraper.scrape(municipalities=municipalities)

        if not results:
            console.print("[red]No data scraped.[/red]")
            return

        out = Path(output_dir)
        paths = write_all(results, out, write_combined=combined)

        console.print(f"\n[green]Scraped {len(results)} entries to {out}/[/green]")
        for name, path in paths.items():
            console.print(f"  {name}: {path}")

    asyncio.run(_run())


@cli.command("list-elections")
def list_elections():
    """List known elections."""
    table = Table(title="Known Elections")
    table.add_column("Slug", style="cyan")
    table.add_column("Type", style="green")
    table.add_column("Year")
    table.add_column("Description")
    table.add_column("Data URL", style="dim")

    for slug, config in sorted(KNOWN_ELECTIONS.items(), key=lambda x: x[1].year, reverse=True):
        table.add_row(
            slug,
            config.election_type,
            str(config.year),
            config.description,
            config.data_url,
        )

    console.print(table)


@cli.command("list-municipalities")
@click.argument("election")
@click.option("-v", "--verbose", is_flag=True)
def list_municipalities(election: str, verbose: bool):
    """List available municipalities for an election."""
    setup_logging(verbose)

    async def _run():
        async with StemwijzerScraper(election) as scraper:
            with console.status("Fetching index..."):
                index = await scraper.fetch_index()

        table = Table(title=f"Municipalities for {election}")
        table.add_column("#", style="dim")
        table.add_column("Name", style="cyan")
        table.add_column("GM Code", style="green")
        table.add_column("Source")
        table.add_column("Language")

        for i, entry in enumerate(index, 1):
            table.add_row(
                str(i), entry.name, entry.remoteId, entry.source, entry.language
            )

        console.print(table)
        console.print(f"\nTotal: {len(index)} entries")

    asyncio.run(_run())


@cli.command()
@click.argument("election")
@click.option("-v", "--verbose", is_flag=True)
def discover(election: str, verbose: bool):
    """Discover API endpoints for an election."""
    setup_logging(verbose)

    async def _run():
        async with StemwijzerScraper(election) as scraper:
            with console.status("Discovering endpoints..."):
                info = await scraper.discover_endpoints()

        console.print("\n[bold]Discovery Results[/bold]")
        for key, value in info.items():
            console.print(f"  [cyan]{key}[/cyan]: {value}")

    asyncio.run(_run())


if __name__ == "__main__":
    cli()
