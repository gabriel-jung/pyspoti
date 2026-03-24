"""Display functions for rendering Spotify entities in the terminal.

Each entity type (artist, album, track) has two display levels:
- **summary**: one-line format for search result lists
- **header**: info panel with key/value grid (and optional image)

Dispatch dicts (``SUMMARY``, ``HEADER``) map ``_type`` strings to the
corresponding display function.
"""

from collections.abc import Callable

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .images import show_image_beside

console = Console()


def _info_grid(rows: list[tuple[str, str]]) -> Table:
    """Build a borderless key/value grid for info sections."""
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold", justify="right")
    grid.add_column()
    for label, value in rows:
        if value:
            grid.add_row(label, value)
    return grid


def _popularity_bar(score: int, width: int = 20) -> str:
    """Render a popularity score as a colored bar."""
    filled = round(score / 100 * width)
    empty = width - filled
    if score >= 70:
        color = "green"
    elif score >= 40:
        color = "yellow"
    else:
        color = "red"
    return f"[{color}]{'█' * filled}[/{color}][dim]{'░' * empty}[/dim] {score}"


# ─── Artist ──────────────────────────────────────────────────────────────────


def display_artist_summary(d: dict) -> None:
    genres = ", ".join(d.get("genres", [])[:3]) or "Unknown"
    console.print(f"[dim]artist[/dim]  [bold]{d['name']}[/bold]  [dim]{genres}[/dim]")


def display_artist_header(d: dict) -> None:
    genres = ", ".join(d.get("genres", [])) or "Unknown"
    followers = f"{d.get('followers', 0):,}"
    popularity = d.get("popularity", 0)

    info = _info_grid(
        [
            ("Genres", genres),
            ("Popularity", _popularity_bar(popularity)),
            ("Followers", followers),
        ]
    )

    panel = Panel(info, title=f"[bold]{d['name']}[/bold]", border_style="cyan")
    show_image_beside(console, d.get("_art_data"), panel)



# ─── Album ───────────────────────────────────────────────────────────────────


def display_album_summary(d: dict) -> None:
    artist = d.get("artist", "Unknown")
    release = d.get("release_date", "")
    album_type = d.get("album_type", "")
    type_label = album_type or "album"
    console.print(f"[dim]{type_label}[/dim]  [bold]{d['name']}[/bold]  [dim]{artist}[/dim]  {release}")


def display_album_header(d: dict) -> None:
    info = _info_grid(
        [
            ("Artist", d.get("artist", "")),
            ("Released", d.get("release_date", "")),
            ("Type", d.get("album_type", "")),
            ("Tracks", str(d.get("total_tracks", ""))),
        ]
    )

    panel = Panel(info, title=f"[bold]{d['name']}[/bold]", border_style="green")
    show_image_beside(console, d.get("_art_data"), panel)



# ─── Track ───────────────────────────────────────────────────────────────────


def display_track_summary(d: dict) -> None:
    artist = d.get("artist", "Unknown")
    duration = d.get("duration", "")
    console.print(f"[dim]track[/dim]   [bold]{d['name']}[/bold]  [dim]{artist}[/dim]  {duration}")


def display_track_header(d: dict) -> None:
    info = _info_grid(
        [
            ("Artist", d.get("artist", "")),
            ("Album", d.get("album", "")),
            ("Duration", d.get("duration", "")),
            ("Track", str(d.get("track_number", ""))),
            ("Disc", str(d.get("disc_number", ""))),
        ]
    )

    panel = Panel(info, title=f"[bold]{d['name']}[/bold]", border_style="magenta")
    show_image_beside(console, d.get("_art_data"), panel)



# ─── Section helpers ─────────────────────────────────────────────────────────


def _print_tracklist(
    tracks: list[dict], title: str = "Tracklist", *, sequential: bool = False,
) -> None:
    if not tracks:
        console.print(f"\n[dim]No {title.lower()} available.[/dim]")
        return

    console.print()
    console.rule(title, style="dim")

    table = Table(border_style="dim", show_lines=False, show_header=True)
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Title")
    table.add_column("Artist", style="dim")
    table.add_column("Duration", style="dim", justify="right")

    total_ms = 0
    for i, t in enumerate(tracks, 1):
        track_num = str(i) if sequential else str(t.get("track_number", ""))
        table.add_row(
            track_num,
            t.get("name", ""),
            t.get("artist", ""),
            t.get("duration", ""),
        )
        total_ms += t.get("duration_ms", 0)

    # Total duration footer
    total_min = total_ms // 60000
    total_sec = (total_ms % 60000) // 1000
    table.add_section()
    table.add_row("", "", "[bold]Total[/bold]", f"[bold]{total_min}:{total_sec:02d}[/bold]")

    console.print(table)


def _print_album_list(albums: list[dict]) -> None:
    if not albums:
        return

    table = Table(title="Albums", border_style="dim", show_lines=False)
    table.add_column("Title")
    table.add_column("Type", style="dim")
    table.add_column("Released", style="dim")
    table.add_column("Tracks", style="dim", justify="right")

    for a in albums:
        table.add_row(
            a.get("name", ""),
            a.get("album_type", ""),
            a.get("release_date", ""),
            str(a.get("total_tracks", "")),
        )

    console.print()
    console.print(table)


# ─── Dispatch dicts ──────────────────────────────────────────────────────────


SUMMARY: dict[str, Callable[[dict], None]] = {
    "artist": display_artist_summary,
    "album": display_album_summary,
    "track": display_track_summary,
}

HEADER: dict[str, Callable[[dict], None]] = {
    "artist": display_artist_header,
    "album": display_album_header,
    "track": display_track_header,
}

# Sections: (key, label, display_fn taking entity dict)
ENTITY_SECTIONS: dict[str, list[tuple[str, str, Callable[[dict], None]]]] = {
    "artist": [
        ("top_tracks", "Top Tracks", lambda d: _print_tracklist(d.get("top_tracks", []), "Top Tracks", sequential=True)),
        ("albums", "Albums", lambda d: _print_album_list(d.get("albums", []))),
    ],
}

# Sections that are lazily fetched (not included in the initial request)
LAZY_SECTIONS: dict[str, set[str]] = {
    "artist": {"top_tracks", "albums"},
}


def display_header(entity: dict) -> None:
    """Display the header for any entity type."""
    fn = HEADER.get(entity["_type"])
    if fn:
        fn(entity)



def display_section(entity: dict, section_key: str) -> None:
    """Display a specific section of an entity."""
    sections = ENTITY_SECTIONS.get(entity["_type"], [])
    for key, _label, display_fn in sections:
        if key == section_key:
            display_fn(entity)
            return


def display_section_page(items: list[dict], start: int = 0, count: int = 25) -> None:
    """Display a page of items using their summary format."""
    end = min(start + count, len(items))
    console.print()
    for i in range(start, end):
        item = items[i]
        fn = SUMMARY.get(item.get("_type", ""))
        if fn:
            console.print(f"  [bold cyan]\\[{i + 1}][/bold cyan] ", end="")
            fn(item)


def select_from_list(
    items: list[dict],
    *,
    title: str = "",
    label: str = "results",
    page_size: int = 10,
) -> dict | None:
    """Display a paginated numbered list and prompt for selection."""
    if not items:
        console.print(f"[dim]No {label} found.[/dim]")
        return None

    if len(items) == 1:
        return items[0]

    total = len(items)
    total_pages = (total + page_size - 1) // page_size
    page = 0

    while True:
        start = page * page_size
        end = min(start + page_size, total)

        if title:
            console.print(f"\n[bold]{title}[/bold]")
        if total_pages > 1:
            console.print(
                f"[dim]Page {page + 1}/{total_pages} — {total} {label}[/dim]\n"
            )
        else:
            console.print(f"[dim]{total} {label}[/dim]\n")

        for i in range(start, end):
            fn = SUMMARY.get(items[i].get("_type", ""))
            if fn:
                console.print(f"  [bold cyan]\\[{i + 1}][/bold cyan] ", end="")
                fn(items[i])

        console.print()
        hints = []
        if page > 0:
            hints.append("[bold]p[/bold]rev page")
        if page < total_pages - 1:
            hints.append("[bold]n[/bold]ext page")
        hints.append("[bold]0[/bold] to cancel")
        console.print(f"[dim]{' | '.join(hints)}[/dim]")

        try:
            raw = console.input("\n[bold]>[/bold] ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            return None

        if not raw:
            continue

        if raw == "n" and page < total_pages - 1:
            page += 1
            continue
        if raw == "p" and page > 0:
            page -= 1
            continue
        if raw == "0":
            return None

        try:
            choice = int(raw)
        except ValueError:
            continue

        if 1 <= choice <= total:
            return items[choice - 1]
