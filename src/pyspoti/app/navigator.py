"""Interactive entity browser with back-navigation, pagination, and lazy fetching."""

from ..core.api import AlbumAPI, ArtistAPI, SearchAPI, TrackAPI
from ..core.client import SpotifyClient

from .display import (
    ENTITY_SECTIONS,
    LAZY_SECTIONS,
    _print_tracklist,
    console,
    display_header,
    display_section,
    display_section_page,
)


class _QuitSignal(Exception):
    """Raised to exit the entire interactive session."""


# Maps (entity_type, section_key) to a callable(api, entity) -> fetched_data
LAZY_FETCHERS = {
    ("artist", "top_tracks"): lambda api, e: api.get_top_tracks(e["id"]),
    ("artist", "albums"): lambda api, e: api.get_albums(e["id"]),
}

# Maps (entity_type, section_key) to a callable(entity) -> list of navigable items
# Each item must have "_type" and "id" to be navigable.
NAVIGABLE_SECTIONS = {
    ("artist", "albums"): lambda d: d.get("albums", []),
    ("artist", "top_tracks"): lambda d: d.get("top_tracks", []),
}


class Navigator:
    """Handles interactive browsing between Spotify entities."""

    def __init__(self, client: SpotifyClient):
        self.apis: dict = {
            "artist": ArtistAPI(client),
            "album": AlbumAPI(client),
            "track": TrackAPI(client),
            "search": SearchAPI(client),
        }
        self._history: list[dict] = []

    def fetch(self, entity_type: str, entity_id: str) -> dict | None:
        """Fetch a full entity by type and ID."""
        api = self.apis.get(entity_type)
        if not api or not hasattr(api, "get"):
            return None
        with console.status("Fetching details..."):
            return api.get(entity_id)

    def navigate(self, entity: dict) -> None:
        """Interactive display with navigation. Supports back navigation."""
        self._history.append(entity)
        try:
            self._interactive_loop(entity)
        finally:
            self._history.pop()

    def _interactive_loop(self, entity: dict) -> None:
        """Main interactive menu loop: display sections, handle user input."""
        display_header(entity)

        entity_type = entity["_type"]
        sections = ENTITY_SECTIONS.get(entity_type, [])

        # Albums: show tracklist inline, then offer track selection + header links
        if entity_type == "album" and entity.get("tracks"):
            _print_tracklist(entity["tracks"])
            self._album_loop(entity)
            return

        # Tracks: show header + navigation links
        if entity_type == "track":
            self._track_loop(entity)
            return

        if not sections:
            return

        lazy_keys = LAZY_SECTIONS.get(entity_type, set())

        # Collect header-level navigable links (e.g. track → artist, album → artist)
        header_links = self._get_header_links(entity)

        while True:
            console.print()
            for i, (key, label, _fn) in enumerate(sections, 1):
                has_data = bool(entity.get(key))
                is_lazy = key in lazy_keys
                is_nav = (entity_type, key) in NAVIGABLE_SECTIONS

                suffix = ""
                if is_nav:
                    suffix = " [dim]→[/dim]"

                if has_data or is_lazy:
                    console.print(f"  [bold cyan]\\[{i}][/bold cyan] {label}{suffix}")
                else:
                    console.print(f"  [dim]\\[{i}] {label} (empty)[/dim]")

            # Header links
            for j, (link_label, link_type, link_id) in enumerate(header_links):
                idx = len(sections) + 1 + j
                console.print(
                    f"  [bold cyan]\\[{idx}][/bold cyan] {link_label} [dim]→[/dim]"
                )

            console.print()
            exit_hints = []
            if len(self._history) > 1:
                exit_hints.append("[bold]0[/bold] to go back")
            exit_hints.append("Ctrl+C to quit")
            console.print(f"  [dim]{' | '.join(exit_hints)}[/dim]")

            try:
                raw = console.input("\n[bold]Choose:[/bold] ").strip()
            except (KeyboardInterrupt, EOFError):
                raise _QuitSignal()

            if not raw:
                continue

            try:
                choice = int(raw)
            except ValueError:
                continue

            if choice == 0 and len(self._history) > 1:
                break

            total_sections = len(sections)
            total_header_links = len(header_links)

            if 1 <= choice <= total_sections:
                key, label, _fn = sections[choice - 1]

                # Lazy fetch if needed (use sentinel to avoid re-fetching empty results)
                if key not in entity and (entity_type, key) in LAZY_FETCHERS:
                    api = self.apis[entity_type]
                    with console.status(f"Fetching {label}..."):
                        entity[key] = LAZY_FETCHERS[(entity_type, key)](api, entity)

                # If section is navigable, show numbered list instead of table
                nav_fn = NAVIGABLE_SECTIONS.get((entity_type, key))
                if nav_fn:
                    items = nav_fn(entity)
                    if items:
                        self._offer_navigation(items, title=label)
                    else:
                        display_section(entity, key)
                else:
                    display_section(entity, key)

            elif total_sections < choice <= total_sections + total_header_links:
                _, link_type, link_id = header_links[choice - total_sections - 1]
                target = self.fetch(link_type, link_id)
                if target:
                    self.navigate(target)
                    # Re-display header when coming back
                    display_header(entity)
                else:
                    console.print("[red]Could not fetch details.[/red]")
            else:
                console.print("[red]Invalid choice.[/red]")

    def _read_input(self) -> str:
        """Read user input, raising _QuitSignal on interrupt."""
        try:
            return console.input("\n[bold]>[/bold] ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            raise _QuitSignal()

    def _print_hints(self, hints: list[str]) -> None:
        """Print a dim hint line with back/quit options."""
        if len(self._history) > 1:
            hints.append("[bold]0[/bold] to go back")
        hints.append("Ctrl+C to quit")
        console.print(f"\n  [dim]{' | '.join(hints)}[/dim]")

    def _link_hints(self, header_links: list[tuple]) -> list[str]:
        """Build hint strings for letter-based header links."""
        return [
            f"[bold]{chr(ord('a') + j)}[/bold] {label}"
            for j, (label, _lt, _lid) in enumerate(header_links)
        ]

    def _try_link(self, raw: str, header_links: list[tuple]) -> bool:
        """Try to handle input as a header link letter. Returns True if handled."""
        if len(raw) == 1 and raw.isalpha():
            idx = ord(raw) - ord("a")
            if 0 <= idx < len(header_links):
                _, link_type, link_id = header_links[idx]
                target = self.fetch(link_type, link_id)
                if target:
                    self.navigate(target)
                return True
        return False

    def _track_loop(self, entity: dict) -> None:
        """Track-specific loop: just header links."""
        header_links = self._get_header_links(entity)
        if not header_links:
            return

        while True:
            self._print_hints(self._link_hints(header_links))
            raw = self._read_input()

            if not raw:
                continue
            if raw == "0" and len(self._history) > 1:
                return
            if self._try_link(raw, header_links):
                display_header(entity)

    def _offer_navigation(self, items: list[dict], title: str = "") -> None:
        """Paginated navigation through section items."""
        has_navigable = any(
            item.get("_type") and item.get("id") for item in items
        )
        if not has_navigable:
            return

        page_size = 25
        page = 0
        total = len(items)
        total_pages = (total + page_size - 1) // page_size

        # Display title and first page with numbers
        if title:
            console.print()
            console.rule(title, style="dim")
        display_section_page(items, start=0, count=page_size)

        while True:
            start = page * page_size
            end = min(start + page_size, total)

            console.print()
            if total_pages > 1:
                console.print(
                    f"[dim]Page {page + 1}/{total_pages} "
                    f"(items {start + 1}-{end} of {total})[/dim]"
                )

            hints = [f"[bold]1-{total}[/bold] to select"]
            if page > 0:
                hints.append("[bold]f[/bold]irst page")
                hints.append("[bold]p[/bold]rev page")
            if page < total_pages - 1:
                hints.append("[bold]n[/bold]ext page")
                hints.append("[bold]l[/bold]ast page")

            console.print(f"[dim]{' | '.join(hints)}[/dim]")
            console.print()
            console.print("[dim][bold]0[/bold] to go back | Ctrl+C to quit[/dim]")

            try:
                raw = console.input("[bold]>[/bold] ").strip()
            except (KeyboardInterrupt, EOFError):
                raise _QuitSignal()

            if not raw:
                continue

            raw = raw.lower()

            if raw == "0":
                return

            new_page = page
            if raw == "n" and page < total_pages - 1:
                new_page = page + 1
            elif raw == "p" and page > 0:
                new_page = page - 1
            elif raw == "f" and page > 0:
                new_page = 0
            elif raw == "l" and page < total_pages - 1:
                new_page = total_pages - 1

            if new_page != page:
                page = new_page
                display_section_page(items, start=page * page_size, count=page_size)
                continue

            try:
                idx = int(raw) - 1
            except ValueError:
                continue

            if 0 <= idx < total:
                item = items[idx]

                if not item.get("_type") or not item.get("id"):
                    console.print("[dim]This item is not navigable.[/dim]")
                    continue

                target = self.fetch(item["_type"], item["id"])
                if target:
                    self.navigate(target)
                    # Re-display current page after coming back
                    if title:
                        console.print()
                        console.rule(title, style="dim")
                    display_section_page(items, start=page * page_size, count=page_size)

    def _redisplay_album(self, entity: dict) -> None:
        """Re-display album header and tracklist after returning from navigation."""
        display_header(entity)
        _print_tracklist(entity["tracks"])

    def _album_loop(self, entity: dict) -> None:
        """Album-specific loop: track selection + header links."""
        tracks = entity.get("tracks", [])
        header_links = self._get_header_links(entity)

        while True:
            hints = [f"[bold]1-{len(tracks)}[/bold] to select a track"]
            hints.extend(self._link_hints(header_links))
            self._print_hints(hints)
            raw = self._read_input()

            if not raw:
                continue
            if raw == "0" and len(self._history) > 1:
                return
            if self._try_link(raw, header_links):
                self._redisplay_album(entity)
                continue

            try:
                choice = int(raw)
            except ValueError:
                continue

            if 1 <= choice <= len(tracks):
                track = tracks[choice - 1]
                if track.get("_type") and track.get("id"):
                    target = self.fetch(track["_type"], track["id"])
                    if target:
                        self.navigate(target)
                        self._redisplay_album(entity)

    def _get_header_links(self, entity: dict) -> list[tuple[str, str, str]]:
        """Return navigable links from the header: (display_label, entity_type, id)."""
        links = []
        entity_type = entity["_type"]

        if entity_type == "album":
            if entity.get("artist_id"):
                links.append(
                    (f"Artist: {entity.get('artist', 'Artist')}", "artist", entity["artist_id"])
                )

        elif entity_type == "track":
            if entity.get("artist_id"):
                links.append(
                    (f"Artist: {entity.get('artist', 'Artist')}", "artist", entity["artist_id"])
                )
            if entity.get("album_id"):
                links.append(
                    (f"Album: {entity.get('album', 'Album')}", "album", entity["album_id"])
                )

        return links
