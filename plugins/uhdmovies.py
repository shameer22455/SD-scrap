"""
SDM Plugin: UHD Movies
========================
Scraper for UHDMovies.casa — 1080p/4K movie downloads.
Migrated from the broken Kotlin UHDmoviesProvider.kt.

Uses the SDM Python SDK exclusively (sdm_api).
"""

from sdm_api import (
    http, logger,
    search_response, home_page_list, home_page_response,
    movie_response, stream_link,
    extract_quality, clean_title, url_encode
)
import re

# ─── Plugin Metadata ──────────────────────────────────────────────────────────

PLUGIN_NAME = "UHD Movies"
MAIN_URL = "https://uhdmovies.casa"


# ─── Contract Functions ───────────────────────────────────────────────────────

def get_name() -> str:
    return PLUGIN_NAME


def get_supported_types() -> list:
    return ["movie"]


def get_main_page() -> dict:
    logger.info(f"{PLUGIN_NAME}: loading home page from {MAIN_URL}")
    try:
        soup = http.get_soup(MAIN_URL, cloudflare=True)
        items = _parse_article_list(soup)
        return home_page_response([
            home_page_list("Latest Movies", items)
        ])
    except Exception as e:
        logger.error(f"{PLUGIN_NAME}: get_main_page failed: {e}", exc_info=True)
        return home_page_response([])


def search(query: str) -> list:
    logger.info(f"{PLUGIN_NAME}: searching for '{query}'")
    try:
        search_url = f"{MAIN_URL}/?s={url_encode(query)}"
        soup = http.get_soup(search_url, cloudflare=True)
        return _parse_article_list(soup)
    except Exception as e:
        logger.error(f"{PLUGIN_NAME}: search failed: {e}", exc_info=True)
        return []


def load_details(url: str) -> dict:
    logger.info(f"{PLUGIN_NAME}: loading details for {url}")
    try:
        soup = http.get_soup(url, cloudflare=True)

        # Extract title
        title_tag = soup.select_one("h1.entry-title, h1.title, article h1")
        title = clean_title(title_tag.get_text(strip=True)) if title_tag else "Unknown"

        # Extract poster
        poster_tag = soup.select_one("div.post-thumbnail img, div.entry-image img, article img")
        poster = poster_tag.get("src") if poster_tag else None

        # Extract plot — first substantial paragraph
        plot_candidates = soup.select("div.entry-content p, div.post-content p")
        plot = None
        for p in plot_candidates:
            text = p.get_text(strip=True)
            if len(text) > 60:
                plot = text
                break

        # Extract year from title or page text
        year_match = re.search(r'\b(20\d{2})\b', soup.get_text())
        year = year_match.group(1) if year_match else None

        # Extract the download/fastserver link as the dataUrl
        # UHDMovies typically has gdrive or fastserver links behind buttons
        link_candidates = soup.select("a[href*='fastserver'], a[href*='gdtot'], a.maxbutton, a[href*='driveseed']")
        data_url = link_candidates[0].get("href") if link_candidates else url

        return movie_response(
            name=title,
            url=url,
            data_url=data_url,
            poster_url=poster,
            plot=plot,
            year=year
        )
    except Exception as e:
        logger.error(f"{PLUGIN_NAME}: load_details failed: {e}", exc_info=True)
        return movie_response(name="Error", url=url, data_url=url)


def load_links(data_url: str) -> list:
    """
    UHDMovies uses a token-gated download system (Driveseed/Fastserver).
    This function extracts the direct streamable/downloadable link.
    """
    logger.info(f"{PLUGIN_NAME}: extracting stream links from {data_url}")
    links = []

    try:
        resp = http.get(data_url, cloudflare=True)
        html = resp.text

        # Strategy 1: Driveseed token-based API extraction
        token_match = re.search(r"formData\.append\('token',\s*'([a-f0-9]+)'\)", html)
        dl_path_match = re.search(r"fetch\('(/download\?id=[a-zA-Z0-9/+=%]+)'", html)

        if token_match and dl_path_match:
            from urllib.parse import urlparse
            parsed = urlparse(data_url)
            domain = f"{parsed.scheme}://{parsed.netloc}"
            api_url = domain + dl_path_match.group(1)

            json_resp = http.post_json(
                api_url,
                data={"token": token_match.group(1)},
                headers={"X-Requested-With": "XMLHttpRequest", "Referer": data_url}
            )
            final_url = json_resp.get("url", "").replace("\\/", "/")
            if final_url:
                quality = extract_quality(final_url)
                links.append(stream_link(
                    url=final_url,
                    name=f"UHD Server {quality}p",
                    source=PLUGIN_NAME,
                    quality=quality,
                    referer=data_url
                ))

        # Strategy 2: Direct MP4/M3U8 regex scan
        if not links:
            for pattern, media_type in [
                (r'https?://[^\s"\']+\.m3u8(?:[^\s"\']*)', "HLS"),
                (r'https?://[^\s"\']+\.mp4(?:[^\s"\']*)', "MP4"),
            ]:
                for match in re.finditer(pattern, html, re.IGNORECASE):
                    url_found = match.group(0).rstrip("\"',;")
                    quality = extract_quality(url_found)
                    links.append(stream_link(
                        url=url_found,
                        name=f"{media_type} {quality}p",
                        source=PLUGIN_NAME,
                        quality=quality,
                        referer=data_url
                    ))

    except Exception as e:
        logger.error(f"{PLUGIN_NAME}: load_links failed: {e}", exc_info=True)

    return links


# ─── Internal Helpers ─────────────────────────────────────────────────────────

def _parse_article_list(soup) -> list:
    """Parse UHDMovies article grid into SdmSearchResponse list."""
    items = []
    for article in soup.select("article"):
        # Title — UHDMovies uses h1.sanket or h2 inside the article
        title_el = article.select_one("h1.sanket, h2.entry-title, h3")
        if not title_el:
            continue
        title = clean_title(title_el.get_text(strip=True))

        # URL — first anchor inside the article
        link_el = article.select_one("a[href]")
        url = link_el.get("href") if link_el else None
        if not url or not url.startswith("http"):
            continue

        # Poster image
        img_el = article.select_one("img[src]")
        poster = img_el.get("src") if img_el else None

        # Year from title text
        year_match = re.search(r'\b(20\d{2})\b', title)
        year = year_match.group(1) if year_match else None

        items.append(search_response(
            name=title,
            url=url,
            poster_url=poster,
            media_type="movie",
            year=year
        ))
    return items
