# pyspoti

An interactive terminal browser for [Spotify](https://open.spotify.com).

Search artists, albums, and tracks — then navigate between them with a
menu-driven UI. Album covers display inline on supported terminals.

## Install

Requires Python 3.12+.

```bash
uv tool install pyspoti
# or
pip install pyspoti
```

For local development:

```bash
git clone https://github.com/gabriel-jung/pyspoti.git
cd pyspoti
uv sync
```

Requires a Spotify application with Client Credentials. Add the following
to your `~/.zshrc` or `~/.bashrc`:

```bash
export SPOTIFY_CLIENT_ID="your_client_id"
export SPOTIFY_CLIENT_SECRET="your_client_secret"
```

Alternatively, place a `.env` file with the same variables in the directory
where you run the command.

## Usage

### Search

```bash
spotify Summoning                        # search all categories
spotify --artist Summoning               # artists only
spotify --album "Minas Morgul"           # albums only
spotify --track "Long Lost to Where"     # tracks only
```

### Filters

```bash
spotify --genre "black metal"            # search by genre
spotify --genre "black metal" --year 2024  # genre + year
spotify --album --label "Season of Mist"   # albums by label
spotify --new                            # albums from the last two weeks
spotify --new --hipster                  # recent low-popularity albums
```

### Interactive navigation

After selecting a result, you enter an interactive browser:

- **Artists** — view top tracks, browse discography, select an album to see
  its tracklist, select a track to see details and navigate to its artist or
  album.
- **Albums** — header with tracklist, select a track or navigate to the artist.
- **Tracks** — header with details, navigate to artist or album.

Press `0` to go back, `Ctrl+C` to quit.

### Output modes

```bash
spotify --artist Summoning --json   # output as JSON
spotify --artist Summoning --full   # all sections at once, no interaction
spotify -v ...                      # enable debug logging
```

### Terminal images

Album covers and artist images render inline on terminals that support the
iTerm2 or Kitty image protocol (iTerm2, Kitty, WezTerm, Mintty).

## Library

The `core` module has no terminal dependencies — use it in scripts,
pipelines, or other tools. All data is returned as plain dicts with a
`_type` discriminator key.

```python
from pyspoti.core import SpotifyClient, ArtistAPI, AlbumAPI, TrackAPI, SearchAPI

with SpotifyClient(client_id, client_secret) as client:
    # search
    artists = ArtistAPI(client).search("Summoning")
    albums = AlbumAPI(client).search("Minas Morgul")
    tracks = TrackAPI(client).search("Long Lost to Where")

    # cross-type search
    results = SearchAPI(client).search("Summoning")
    # → {"artists": [...], "albums": [...], "tracks": [...]}

    # fetch full details
    artist = ArtistAPI(client).get(artists[0]["id"])
    top_tracks = ArtistAPI(client).get_top_tracks(artist["id"])
    discography = ArtistAPI(client).get_albums(artist["id"])

    album = AlbumAPI(client).get(discography[0]["id"])
    track = TrackAPI(client).get(top_tracks[0]["id"])

    # download images
    client.download_image(artist["image_url"], output_dir="./images/")
```

## License

MIT
