"""Public API surface for the pyspoti core library."""

from .api import AlbumAPI, ArtistAPI, SearchAPI, TrackAPI
from .client import NotFoundError, SpotifyClient

__all__ = [
    "AlbumAPI",
    "ArtistAPI",
    "NotFoundError",
    "SearchAPI",
    "SpotifyClient",
    "TrackAPI",
]
