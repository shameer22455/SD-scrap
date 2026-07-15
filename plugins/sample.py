"""
SDM Plugin: Sample / Template
==============================
This is the minimal template for writing an SDM plugin.
Copy this file, rename it, and replace the implementation.

Rules:
  1. You MUST import ONLY from sdm_api — never import requests, bs4, etc. directly.
  2. You MUST implement all 5 contract functions below.
  3. All return values must match the sdm_api response dict format.
"""

from sdm_api import (
    http, logger,
    search_response, home_page_list, home_page_response,
    movie_response, stream_link
)

# ─── Plugin Metadata ──────────────────────────────────────────────────────────

PLUGIN_NAME = "SDM Sample"
MAIN_URL = "https://example.com"


# ─── Contract Functions (ALL required) ───────────────────────────────────────

def get_name() -> str:
    """Return the display name of this plugin."""
    return PLUGIN_NAME


def get_supported_types() -> list:
    """Return list of supported media types: 'movie', 'tv', 'anime'."""
    return ["movie", "tv", "anime"]


def get_main_page() -> dict:
    """
    Return the home page content for this plugin.
    :return: SdmHomePageResponse format dict
    """
    logger.info(f"{PLUGIN_NAME}: loading home page")
    # Return dummy data as an example
    items = [
        search_response("Sample Movie 1", f"{MAIN_URL}/movie1", media_type="movie", year="2024"),
        search_response("Sample Movie 2", f"{MAIN_URL}/movie2", media_type="movie", year="2023"),
    ]
    return home_page_response([
        home_page_list("Trending Now", items)
    ])


def search(query: str) -> list:
    """
    Search for content matching the query string.
    :param query: Search query from the user
    :return: List of SdmSearchResponse dicts
    """
    logger.info(f"{PLUGIN_NAME}: searching for '{query}'")
    # Replace with real scraping logic:
    # soup = http.get_soup(f"{MAIN_URL}/search?q={query}")
    return [
        search_response(f"Result for {query}", f"{MAIN_URL}/result", media_type="movie")
    ]


def load_details(url: str) -> dict:
    """
    Load detailed info about a specific media item.
    :param url: The URL from the search_response
    :return: SdmMovieLoadResponse or SdmTvSeriesLoadResponse dict
    """
    logger.info(f"{PLUGIN_NAME}: loading details for {url}")
    # Replace with real scraping logic:
    # soup = http.get_soup(url)
    return movie_response(
        name="Sample Movie",
        url=url,
        data_url=url,
        plot="This is a sample plot description.",
        year="2024"
    )


def load_links(data_url: str) -> list:
    """
    Resolve stream links from a dataUrl.
    :param data_url: The dataUrl from the load_details response
    :return: List of SdmStreamLink dicts
    """
    logger.info(f"{PLUGIN_NAME}: resolving streams for {data_url}")
    # Replace with real stream extraction:
    return [
        stream_link(
            url="https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4",
            name="Sample 1080p",
            source=PLUGIN_NAME,
            quality=1080
        )
    ]
