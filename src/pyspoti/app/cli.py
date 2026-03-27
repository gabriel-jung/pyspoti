"""CLI entry point for spotify -- an interactive Spotify browser.

Run ``spotify --help`` for usage examples.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from importlib.metadata import version

__version__ = version("pyspoti")

from rich_metadata import (
    BaseNavigator,
    DisplayEngine,
    EntityDef,
    HeaderField,
    HeaderLink,
    QuitSignal,
    SectionDef,
    SummaryField,
    TableColumn,
    configure_logging,
    resolve_entity_type,
    strip_internal_keys,
)

from ..core.api import AlbumAPI, ArtistAPI, SearchAPI, TrackAPI
from ..core.client import SpotifyClient
from ..core.transforms import album_url, artist_url, track_url

# ─── Display transforms ──────────────────────────────────────────────────────

ENTITY_TYPES = ["artist", "album", "track"]


def _popularity_bar(score: int, width: int = 20) -> str:
    """Render a popularity score as a colored bar."""
    if not score:
        return ""
    filled = round(score / 100 * width)
    empty = width - filled
    if score >= 70:
        color = "green"
    elif score >= 40:
        color = "yellow"
    else:
        color = "red"
    return f"[{color}]{'█' * filled}[/{color}][dim]{'░' * empty}[/dim] {score}"


def _join_genres(genres) -> str:
    """Join a list of genre strings with commas."""
    return ", ".join(genres) if genres else ""


def _short_genres(genres) -> str:
    """Join up to 3 genres for summary display."""
    return ", ".join(genres[:3]) if genres else "Unknown"


def _format_followers(count) -> str:
    """Format followers count with commas."""
    return f"{count:,}" if count else ""


def _artist_link(entity: dict) -> str:
    """Build a clickable artist URL."""
    url = artist_url(entity["id"])
    return f"[link={url}]{url}[/link]"


def _album_link(entity: dict) -> str:
    """Build a clickable album URL."""
    url = album_url(entity["id"])
    return f"[link={url}]{url}[/link]"


def _track_link(entity: dict) -> str:
    """Build a clickable track URL."""
    url = track_url(entity["id"])
    return f"[link={url}]{url}[/link]"


def _disc_number(entity: dict) -> str:
    """Show disc number only if > 1."""
    disc = entity.get("disc_number", 1)
    return str(disc) if disc and disc > 1 else ""


# ─── Entity definitions ──────────────────────────────────────────────────────

_TRACK_COLUMNS = [
    TableColumn("Title", "name", style="bold"),
    TableColumn("Artist", "artist", style="dim"),
    TableColumn("Duration", "duration", justify="right"),
]

artist_def = EntityDef(
    type_name="artist",
    summary=[
        SummaryField(key="name", style="bold"),
        SummaryField(key="genres", style="dim", transform=_short_genres, fallback="Unknown"),
    ],
    header_fields=[
        HeaderField("Genres", key="genres", transform=_join_genres),
        HeaderField("Popularity", key="popularity", transform=_popularity_bar),
        HeaderField("Followers", key="followers", transform=_format_followers),
        HeaderField("Link", transform=_artist_link),
    ],
    header_image_key="_art_data",
    panel_border_style="cyan",
    sections=[
        SectionDef(
            "top_tracks", label="Top Tracks", lazy=True, navigable=True,
            numbered=False, duration_key="duration",
            columns=[
                TableColumn("#", "track_number", style="dim", width=4, justify="right"),
                *_TRACK_COLUMNS,
            ],
        ),
        SectionDef(
            "albums", lazy=True, navigable=True,
            columns=[
                TableColumn("Title", "name", style="bold"),
                TableColumn("Type", "album_type", style="dim"),
                TableColumn("Released", "release_date", style="dim"),
                TableColumn("Tracks", "total_tracks", style="dim", justify="right"),
            ],
        ),
    ],
)

album_def = EntityDef(
    type_name="album",
    summary=[
        SummaryField(key="album_type", style="dim", fallback="album"),
        SummaryField(key="name", style="bold"),
        SummaryField(key="artist", style="dim", fallback="Unknown"),
        SummaryField(key="release_date"),
    ],
    header_fields=[
        HeaderField("Artist", key="artist"),
        HeaderField("Released", key="release_date"),
        HeaderField("Type", key="album_type"),
        HeaderField("Label", key="label"),
        HeaderField("Tracks", key="total_tracks", transform=lambda v: str(v) if v else ""),
        HeaderField("Popularity", key="popularity", transform=_popularity_bar),
        HeaderField("Link", transform=_album_link),
    ],
    header_image_key="_art_data",
    panel_border_style="green",
    sections=[
        SectionDef(
            "tracks", navigable=True, numbered=False, duration_key="duration",
            columns=[
                TableColumn("#", "track_number", style="dim", width=4, justify="right"),
                *_TRACK_COLUMNS,
            ],
        ),
    ],
    header_links=[
        HeaderLink("Artist: {artist}", "artist", ref_key="artist_id"),
    ],
)

track_def = EntityDef(
    type_name="track",
    summary=[
        SummaryField(key="name", style="bold"),
        SummaryField(key="artist", style="dim", fallback="Unknown"),
        SummaryField(key="duration"),
    ],
    header_fields=[
        HeaderField("Artist", key="artist"),
        HeaderField("Album", key="album"),
        HeaderField("Duration", key="duration"),
        HeaderField("Track", key="track_number", transform=lambda v: str(v) if v else ""),
        HeaderField("Disc", transform=_disc_number),
        HeaderField("Popularity", key="popularity", transform=_popularity_bar),
        HeaderField("Link", transform=_track_link),
    ],
    header_image_key="_art_data",
    panel_border_style="magenta",
    header_links=[
        HeaderLink("Artist: {artist}", "artist", ref_key="artist_id"),
        HeaderLink("Album: {album}", "album", ref_key="album_id"),
    ],
)

# ─── Engine & navigator setup ────────────────────────────────────────────────

engine = DisplayEngine()
engine.register(artist_def, album_def, track_def)
console = engine.console

LAZY_FETCHERS = {
    ("artist", "top_tracks"): lambda api, entity: api.get_top_tracks(entity["id"]),
    ("artist", "albums"): lambda api, entity: api.get_albums(entity["id"]),
}


# ─── Parser ──────────────────────────────────────────────────────────────────


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

    entity_group = parser.add_mutually_exclusive_group()
    for entity in ENTITY_TYPES:
        entity_group.add_argument(
            f"--{entity}", nargs="?", const=True, default=None,
            metavar="NAME", help=f"Search {entity}s (optionally by name)",
        )

    parser.add_argument("--genre", type=str, metavar="GENRE", help='Filter by genre')
    parser.add_argument("--year", type=str, metavar="YEAR", help="Filter by year or range")
    parser.add_argument("--label", type=str, metavar="LABEL", help="Filter albums by label")
    parser.add_argument("--new", action="store_true", help="Show albums released in the last two weeks")
    parser.add_argument("--hipster", action="store_true", help="Show low-popularity albums")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--full", action="store_true", help="Non-interactive: show header and all sections, then exit")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show debug logs")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    return parser


# ─── Credentials ─────────────────────────────────────────────────────────────


def _get_credentials() -> tuple[str, str]:
    """Read Spotify credentials from environment variables."""
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


# ─── Search ──────────────────────────────────────────────────────────────────


def _run_search(navigator, query, entity_type, args):
    """Execute a search and handle results."""
    if entity_type:
        api = navigator.apis[entity_type]
        with console.status(f"Searching {entity_type}s..."):
            results = api.search(query)
    else:
        search_api = navigator.apis["search"]
        with console.status("Searching..."):
            all_results = search_api.search(query)
        results = all_results["artists"] + all_results["albums"] + all_results["tracks"]

    if not results:
        console.print("[dim]No results found.[/dim]")
        return

    if args.json:
        print(json.dumps(strip_internal_keys(results), indent=2))
        return

    if args.full:
        selected = results[0]
    else:
        selected = engine.select_from_list(results, title=f'Search: "{query}"')
    if not selected:
        return

    entity = navigator.fetch_entity(selected["_type"], selected["id"])
    if not entity:
        console.print("[red]Could not fetch details.[/red]")
        return

    navigator.display_or_navigate(entity, json_output=args.json, full=args.full)


# ─── Main ────────────────────────────────────────────────────────────────────


def main():
    """Parse arguments, configure logging, and run the interactive session."""
    parser = _build_parser()
    args = parser.parse_args()

    configure_logging(args.verbose)
    entity_type, name_query = resolve_entity_type(args, ENTITY_TYPES)

    query = name_query or args.query or ""

    # Build Spotify query modifiers
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
        navigator = _make_navigator(client)
        try:
            _run_search(navigator, query, entity_type, args)
        except (QuitSignal, KeyboardInterrupt):
            pass


def _make_navigator(client: SpotifyClient) -> BaseNavigator:
    """Create a navigator wired to all Spotify APIs."""
    apis = {
        "artist": ArtistAPI(client),
        "album": AlbumAPI(client),
        "track": TrackAPI(client),
        "search": SearchAPI(client),
    }
    return BaseNavigator(engine, apis=apis, entity_ref_key="id", lazy_fetchers=LAZY_FETCHERS)
