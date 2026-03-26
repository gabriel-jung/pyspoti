"""HTTP client for the Spotify Web API with built-in auth, rate limiting, and retry."""

import time
from pathlib import Path

import requests
from loguru import logger
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

BASE_URL = "https://api.spotify.com/v1"
TOKEN_URL = "https://accounts.spotify.com/api/token"

REQUEST_TIMEOUT = 10  # seconds


class NotFoundError(Exception):
    """Raised when a Spotify resource returns HTTP 404."""


class SpotifyClient:
    """HTTP client for Spotify with OAuth token management and rate limiting."""

    def __init__(self, client_id: str, client_secret: str):
        self._client_id = client_id
        self._client_secret = client_secret
        self._token: str | None = None
        self._expires_at: float = 0
        self._rate_limit_seconds = 0.5
        self._last_request_time: float | None = None
        self._session = self._create_session()
        logger.debug("Spotify client initialized.")

    def _create_session(self) -> requests.Session:
        """Configure requests.Session with retry strategy for 5xx errors.

        429 (rate limit) is handled manually to respect the Retry-After header.
        """
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        return session

    def _fetch_token(self) -> None:
        """Request a fresh client_credentials token and update session headers."""
        auth = (self._client_id, self._client_secret)
        data = {"grant_type": "client_credentials"}

        logger.debug("Requesting new Spotify access token...")
        try:
            response = self._session.post(
                TOKEN_URL, auth=auth, data=data, timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            token_data = response.json()
            self._token = token_data["access_token"]
            self._expires_at = time.time() + token_data["expires_in"] - 60
            self._session.headers.update({"Authorization": f"Bearer {self._token}"})
            logger.debug("Obtained Spotify access token.")
        except Exception as e:
            logger.critical("Failed to authenticate with Spotify: {}", e)
            raise

    def _ensure_valid_token(self) -> None:
        """Refresh the token if it is missing or expired."""
        if self._token is None or time.time() > self._expires_at:
            self._fetch_token()

    def _enforce_rate_limit(self) -> None:
        """Enforce minimum delay between requests."""
        if self._last_request_time is not None:
            elapsed = time.time() - self._last_request_time
            if elapsed < self._rate_limit_seconds:
                time.sleep(self._rate_limit_seconds - elapsed)
        self._last_request_time = time.time()

    def get(self, endpoint: str, params: dict | None = None) -> dict | None:
        """GET a Spotify API endpoint and return parsed JSON.

        Handles 429 rate limits by respecting the ``Retry-After`` header,
        retrying up to 3 times before giving up.

        Args:
            endpoint: Path relative to the base URL (e.g. ``/artists/123``).
            params: Optional query parameters.

        Returns:
            Parsed JSON dict, or None on network error.

        Raises:
            NotFoundError: If the resource returns 404.
        """
        self._ensure_valid_token()

        url = f"{BASE_URL}{endpoint}" if endpoint.startswith("/") else f"{BASE_URL}/{endpoint}"

        for attempt in range(4):  # 1 initial + 3 retries
            self._enforce_rate_limit()
            try:
                response = self._session.get(url, params=params, timeout=REQUEST_TIMEOUT)

                if response.status_code == 404:
                    raise NotFoundError(f"404 Not Found: {url}")

                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 5))
                    logger.warning(
                        "Rate limited (429). Retry-After: {}s (attempt {}/3)",
                        retry_after, attempt + 1,
                    )
                    if retry_after > 60:
                        logger.error(
                            "Retry-After too long ({}s / {:.1f}h). Giving up.",
                            retry_after, retry_after / 3600,
                        )
                        return None
                    if attempt < 3:
                        time.sleep(retry_after)
                        continue
                    logger.error("Rate limited after 3 retries: {}", url)
                    return None

                response.raise_for_status()
                return response.json()

            except NotFoundError:
                raise
            except requests.exceptions.Timeout:
                logger.warning("Request timed out for {} (attempt {}/3)", url, attempt + 1)
                if attempt < 3:
                    continue
                logger.error("Timed out after 3 retries: {}", url)
                return None
            except Exception as e:
                logger.error("Request failed for {}: {}", url, e)
                return None

        return None

    def get_bytes(self, url: str) -> bytes | None:
        """GET a full URL and return raw bytes (for images)."""
        self._enforce_rate_limit()
        try:
            response = self._session.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return response.content
        except Exception as e:
            logger.debug("Failed to fetch bytes from {}: {}", url, e)
            return None

    def download_image(
        self, url: str, output_dir: str = "./images/",
    ) -> str | None:
        """Download an image to a local file.

        The filename is derived from the URL path. Parent directories are
        created automatically.

        Args:
            url: Full image URL.
            output_dir: Local directory to save images under.

        Returns:
            The path of the saved file as a string, or ``None`` if the
            download failed or *url* was empty.
        """
        if not url:
            return None

        try:
            # Spotify image URLs: https://i.scdn.co/image/ab67616d...
            filename = url.split("/")[-1].split("?")[0]
            if not filename:
                return None
            output_path = Path(output_dir) / filename
            output_path.parent.mkdir(parents=True, exist_ok=True)

            image_data = self.get_bytes(url)
            if not image_data:
                return None

            output_path.write_bytes(image_data)
            logger.debug("Downloaded {} -> {}", filename, output_path)
            return str(output_path)

        except Exception as e:
            logger.debug("Failed to download {}: {}", url, e)
            return None

    def close(self) -> None:
        """Close the underlying HTTP session."""
        self._session.close()
        logger.debug("Spotify client closed.")

    def __enter__(self) -> "SpotifyClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
