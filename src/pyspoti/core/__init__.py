"""Public API surface for the pyspoti core library."""

from .api import AlbumAPI, ArtistAPI, SearchAPI, TrackAPI
from .client import NotFoundError, SpotifyClient
from .transforms import album_url, artist_url, track_url

__all__ = [
    "AlbumAPI",
    "ArtistAPI",
    "NotFoundError",
    "SearchAPI",
    "SpotifyClient",
    "TrackAPI",
    "album_url",
    "artist_url",
    "track_url",
]
