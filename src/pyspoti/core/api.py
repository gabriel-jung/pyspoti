"""API classes for Spotify entities: artists, albums, tracks, and search."""

from loguru import logger

from .client import SpotifyClient
from .transforms import transform_album, transform_artist, transform_track

_SEARCH_TYPES = {
    "artist": ("artists", transform_artist),
    "album": ("albums", transform_album),
    "track": ("tracks", transform_track),
}


class BaseAPI:
    """Base class providing shared fetch helpers for all Spotify entity APIs."""

    def __init__(self, client: SpotifyClient):
        self._client = client

    def _get(self, endpoint: str, params: dict | None = None) -> dict | None:
        """Fetch a Spotify API endpoint and return raw JSON."""
        return self._client.get(endpoint, params=params)

    def _get_image(self, image_url: str | None) -> bytes | None:
        """Fetch image bytes from a URL."""
        if not image_url:
            return None
        return self._client.get_bytes(image_url)

    def _attach_image(self, entity: dict) -> None:
        """Fetch and attach image data to an entity dict."""
        entity["_art_data"] = self._get_image(entity.get("image_url"))

    def _search(self, query: str, entity_type: str, limit: int = 50) -> list[dict]:
        """Search for entities of a given type, paginating to reach *limit*."""
        response_key, transform = _SEARCH_TYPES[entity_type]
        results: list[dict] = []
        page_size = min(limit, 10)
        offset = 0

        while len(results) < limit:
            data = self._get(
                "/search",
                params={"q": query, "type": entity_type, "limit": page_size, "offset": offset},
            )
            if not data:
                break
            items = data.get(response_key, {}).get("items", [])
            if not items:
                break
            results.extend(transform(item) for item in items)
            offset += len(items)
            # Stop if Spotify returned fewer than requested (no more results)
            if len(items) < page_size:
                break

        return results[:limit]


class ArtistAPI(BaseAPI):
    """Search and fetch Spotify artists."""

    def get(self, artist_id: str) -> dict | None:
        """Fetch a full artist by ID, including image data."""
        data = self._get(f"/artists/{artist_id}")
        if not data:
            return None
        artist = transform_artist(data)
        self._attach_image(artist)
        return artist

    def get_albums(self, artist_id: str, limit: int = 50) -> list[dict]:
        """Fetch an artist's albums and singles (paginated)."""
        results: list[dict] = []
        params = {"include_groups": "album,single", "limit": min(limit, 50), "offset": 0}

        while True:
            data = self._get(f"/artists/{artist_id}/albums", params=params)
            if not data:
                break
            results.extend(transform_album(item) for item in data.get("items", []))
            if not data.get("next") or len(results) >= limit:
                break
            params["offset"] = len(results)

        return results[:limit]

    def get_top_tracks(self, artist_id: str) -> list[dict]:
        """Fetch an artist's top tracks."""
        data = self._get(f"/artists/{artist_id}/top-tracks")
        if not data:
            return []
        return [transform_track(item) for item in data.get("tracks", [])]

    def search(self, query: str, limit: int = 50) -> list[dict]:
        """Search for artists by name."""
        return self._search(query, "artist", limit)


class AlbumAPI(BaseAPI):
    """Search and fetch Spotify albums."""

    def get(self, album_id: str) -> dict | None:
        """Fetch a full album by ID, including image data and embedded tracks."""
        data = self._get(f"/albums/{album_id}")
        if not data:
            return None
        album = transform_album(data)
        self._attach_image(album)
        return album

    def search(self, query: str, limit: int = 50) -> list[dict]:
        """Search for albums by name."""
        return self._search(query, "album", limit)


class TrackAPI(BaseAPI):
    """Search and fetch Spotify tracks."""

    def get(self, track_id: str) -> dict | None:
        """Fetch a full track by ID, including album art."""
        data = self._get(f"/tracks/{track_id}")
        if not data:
            return None
        track = transform_track(data)
        self._attach_image(track)
        return track

    def search(self, query: str, limit: int = 50) -> list[dict]:
        """Search for tracks by name."""
        return self._search(query, "track", limit)


class SearchAPI(BaseAPI):
    """Cross-type search across artists, albums, and tracks."""

    def search(
        self,
        query: str,
        types: list[str] | None = None,
        limit: int = 20,
    ) -> dict:
        """Search Spotify across multiple entity types.

        Returns:
            Dict with keys ``artists``, ``albums``, ``tracks`` — each a list of
            transformed dicts.
        """
        if types is None:
            types = ["artist", "album", "track"]

        data = self._get(
            "/search",
            params={"q": query, "type": ",".join(types), "limit": limit},
        )
        if not data:
            return {"artists": [], "albums": [], "tracks": []}

        result = {}
        for type_key, (response_key, transform) in _SEARCH_TYPES.items():
            if type_key in types and response_key in data:
                result[response_key] = [
                    transform(item) for item in data[response_key].get("items", [])
                ]
            else:
                result[response_key] = []

        logger.debug(
            "Search '{}': {} artists, {} albums, {} tracks",
            query, len(result["artists"]), len(result["albums"]), len(result["tracks"]),
        )
        return result
