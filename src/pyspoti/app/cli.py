"""CLI entry point for spotify -- an interactive Spotify browser.

Usage::

    spotify Summoning              # search all categories
    spotify --artist Summoning     # search artists only
    spotify --album "Minas Morgul" # search albums only
    spotify --track "Black Years"  # search tracks only
    spotify --artist Summoning --json  # output as JSON
    spotify --artist Summoning --full  # non-interactive full output
    spotify --genre "black metal"      # search artists by genre
    spotify --genre "black metal" --year 2024  # genre + year filter
    spotify --new                      # albums from the last two weeks
"""

import argparse
import json
import os
import sys

from loguru import logger

from .. import __version__

from ..core.client import SpotifyClient
from .display import ENTITY_SECTIONS, _print_tracklist, console, display_header, display_section, select_from_list
from .navigator import LAZY_FETCHERS, Navigator, _QuitSignal

ENTITY_TYPES = ["artist", "album", "track"]


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="spotify",
        description="An interactive CLI for Spotify.",
        epilog=(
            "examples:\n"
            "  spotify Summoning              search all categories\n"
            "  spotify --artist Summoning     search artists only\n"
            '  spotify --album "Minas Morgul" search albums only\n'
            '  spotify --track "Black Years"  search tracks only\n'
            "  spotify --artist Summoning --json  output as JSON\n"
            "  spotify --artist Summoning --full  non-interactive full output\n"
            '  spotify --genre "black metal"      search artists by genre\n'
            '  spotify --genre "black metal" --year 2024  genre + year\n'
            "  spotify --new                      recent albums\n"
            "  spotify --new --hipster            recent low-popularity albums\n"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )

    parser.add_argument("query", nargs="?", type=str, help="Search all categories")

    # Entity type selectors -- mutually exclusive with each other
    entity_group = parser.add_mutually_exclusive_group()
    for entity in ENTITY_TYPES:
        entity_group.add_argument(
            f"--{entity}",
            nargs="?",
            const=True,
            default=None,
            metavar="NAME",
            help=f"Search {entity}s (optionally by name)",
        )

    # Search modifiers
    parser.add_argument(
        "--genre", type=str, metavar="GENRE",
        help='Filter by genre (e.g. --genre "black metal")',
    )
    parser.add_argument(
        "--year", type=str, metavar="YEAR",
        help="Filter by year or range (e.g. --year 2026 or --year 2020-2026)",
    )
    parser.add_argument(
        "--label", type=str, metavar="LABEL",
        help='Filter albums by label (e.g. --label "Season of Mist")',
    )
    parser.add_argument(
        "--new", action="store_true",
        help="Show albums released in the last two weeks",
    )
    parser.add_argument(
        "--hipster", action="store_true",
        help="Show low-popularity albums",
    )

    # Output options
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument(
        "--full", action="store_true",
        help="Non-interactive: show header and all sections, then exit",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Show debug logs")
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )

    return parser


def _get_credentials() -> tuple[str, str]:
    """Read Spotify credentials from environment variables."""
    # Try python-dotenv if available
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    client_id = os.environ.get("SPOTIFY_CLIENT_ID", "")
    client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        console.print(
            "[red]Missing credentials. Set SPOTIFY_CLIENT_ID and "
            "SPOTIFY_CLIENT_SECRET environment variables.[/red]"
        )
        sys.exit(1)

    return client_id, client_secret


def _display_full(navigator: Navigator, entity: dict) -> None:
    """Non-interactive display: header + all sections, then exit."""
    display_header(entity)

    entity_type = entity["_type"]
    sections = ENTITY_SECTIONS.get(entity_type, [])

    for key, label, _fn in sections:
        # Lazy fetch if needed
        if key not in entity and (entity_type, key) in LAZY_FETCHERS:
            api = navigator.apis[entity_type]
            with console.status(f"Fetching {label}..."):
                entity[key] = LAZY_FETCHERS[(entity_type, key)](api, entity)
        display_section(entity, key)

    # Albums: show tracklist inline
    if entity_type == "album" and entity.get("tracks"):
        _print_tracklist(entity["tracks"])


def _run_search(
    navigator: Navigator,
    query: str,
    entity_type: str | None,
    args: argparse.Namespace,
) -> None:
    """Execute a search and handle results."""
    if entity_type:
        api = navigator.apis[entity_type]
        with console.status(f"Searching {entity_type}s..."):
            results = api.search(query)
    else:
        # Search all types
        search_api = navigator.apis["search"]
        with console.status("Searching..."):
            all_results = search_api.search(query)
        # Merge results, artists first
        results = all_results["artists"] + all_results["albums"] + all_results["tracks"]

    if not results:
        console.print("[dim]No results found.[/dim]")
        return

    if args.json:
        # Strip binary art data for JSON output
        clean = [{k: v for k, v in r.items() if k != "_art_data"} for r in results]
        console.print_json(json.dumps(clean, indent=2))
        return

    if args.full:
        # Non-interactive: show first result's header + all sections
        selected = results[0]
    else:
        selected = select_from_list(results, title=f'Search: "{query}"')
    if not selected:
        return

    # Fetch full details
    full = navigator.fetch(selected["_type"], selected["id"])
    if not full:
        console.print("[red]Could not fetch details.[/red]")
        return

    if args.full:
        _display_full(navigator, full)
    else:
        navigator.navigate(full)


def main():
    """Parse arguments, configure logging, and run the interactive session."""
    parser = _build_parser()
    args = parser.parse_args()

    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="DEBUG" if args.verbose else "WARNING",
    )

    # Determine entity type and query
    entity_type = None
    name_query = None
    for t in ENTITY_TYPES:
        value = getattr(args, t, None)
        if value is not None:
            entity_type = t
            if value is not True:
                name_query = value
            break

    query = name_query or args.query or ""

    # Build query modifiers
    parts = []
    if args.genre:
        parts.append(f'genre:"{args.genre}"')
    if args.year:
        parts.append(f"year:{args.year}")
    if args.label:
        parts.append(f'label:"{args.label}"')
        if not entity_type:
            entity_type = "album"
    if args.new:
        parts.append("tag:new")
        if not entity_type:
            entity_type = "album"
    if args.hipster:
        parts.append("tag:hipster")
        if not entity_type:
            entity_type = "album"

    if parts:
        query = " ".join([*parts, query]).strip()

    if not query:
        parser.error("Provide a search query or use --artist/--album/--track NAME.")

    client_id, client_secret = _get_credentials()

    with SpotifyClient(client_id, client_secret) as client:
        navigator = Navigator(client)
        try:
            _run_search(navigator, query, entity_type, args)
        except _QuitSignal:
            console.print("[dim]Goodbye.[/dim]")
        except KeyboardInterrupt:
            console.print("\n[dim]Goodbye.[/dim]")
