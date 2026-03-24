"""Transform raw Spotify API JSON into clean, normalized dicts with ``_type`` keys."""


def _best_image(images: list[dict]) -> str | None:
    """Pick the best image URL from Spotify's images array (largest first)."""
    if not images:
        return None
    # Spotify returns images sorted largest-first, pick the first
    return images[0].get("url")


def _format_duration(ms: int | None) -> str:
    """Convert milliseconds to ``m:ss`` string."""
    if ms is None:
        return ""
    total_seconds = ms // 1000
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes}:{seconds:02d}"


def transform_artist(raw: dict) -> dict:
    """Normalize a Spotify artist object."""
    return {
        "_type": "artist",
        "id": raw.get("id", ""),
        "name": raw.get("name", ""),
        "genres": raw.get("genres", []),
        "popularity": raw.get("popularity", 0),
        "followers": raw.get("followers", {}).get("total", 0),
        "image_url": _best_image(raw.get("images", [])),
        "url": raw.get("external_urls", {}).get("spotify", ""),
    }


def transform_album(raw: dict) -> dict:
    """Normalize a Spotify album object."""
    artists = raw.get("artists", [])
    first_artist = artists[0] if artists else {}

    album = {
        "_type": "album",
        "id": raw.get("id", ""),
        "name": raw.get("name", ""),
        "artist": first_artist.get("name", ""),
        "artist_id": first_artist.get("id", ""),
        "release_date": raw.get("release_date", ""),
        "total_tracks": raw.get("total_tracks", 0),
        "album_type": raw.get("album_type", ""),
        "image_url": _best_image(raw.get("images", [])),
        "url": raw.get("external_urls", {}).get("spotify", ""),
    }

    # Include tracks if present in the response (full album object)
    tracks_data = raw.get("tracks", {})
    if tracks_data and tracks_data.get("items"):
        album["tracks"] = [transform_track(t) for t in tracks_data["items"]]

    return album


def transform_track(raw: dict) -> dict:
    """Normalize a Spotify track object.

    Works for both full tracks (with album info) and album tracklist items
    (where album info is absent in the response).
    """
    artists = raw.get("artists", [])
    first_artist = artists[0] if artists else {}
    album = raw.get("album", {})

    return {
        "_type": "track",
        "id": raw.get("id", ""),
        "name": raw.get("name", ""),
        "duration_ms": raw.get("duration_ms", 0),
        "duration": _format_duration(raw.get("duration_ms")),
        "track_number": raw.get("track_number", 0),
        "disc_number": raw.get("disc_number", 1),
        "artist": first_artist.get("name", ""),
        "artist_id": first_artist.get("id", ""),
        "album": album.get("name", ""),
        "album_id": album.get("id", ""),
        "image_url": _best_image(album.get("images", [])),
        "preview_url": raw.get("preview_url"),
        "url": raw.get("external_urls", {}).get("spotify", ""),
    }
