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
    logger.info(f"{PLUGIN_NAME}: loading home page categories")
    lists = []
    
    # 1. Trending / Latest (Home)
    try:
        soup = http.get_soup(MAIN_URL, cloudflare=True)
        items = _parse_article_list(soup)
        if items:
            lists.append(home_page_list("Trending & Latest", items))
    except Exception as e:
        logger.error(f"{PLUGIN_NAME}: failed to load Trending category: {e}")

    # 2. Hollywood Movies Collection
    try:
        soup = http.get_soup(f"{MAIN_URL}/movies/collection-movies/", cloudflare=True)
        items = _parse_article_list(soup)
        if items:
            lists.append(home_page_list("Hollywood Movies", items))
    except Exception as e:
        logger.error(f"{PLUGIN_NAME}: failed to load Hollywood category: {e}")

    # 3. Netflix Series
    try:
        soup = http.get_soup(f"{MAIN_URL}/tv-shows/netflix/", cloudflare=True)
        items = _parse_article_list(soup)
        if items:
            lists.append(home_page_list("Netflix Collection", items))
    except Exception as e:
        logger.error(f"{PLUGIN_NAME}: failed to load Netflix category: {e}")

    # 4. 4K Ultra HD
    try:
        soup = http.get_soup(f"{MAIN_URL}/4k-hdr/", cloudflare=True)
        items = _parse_article_list(soup)
        if items:
            lists.append(home_page_list("4K Ultra HD", items))
    except Exception as e:
        logger.error(f"{PLUGIN_NAME}: failed to load 4K HDR category: {e}")

    return home_page_response(lists)


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

        # Extract title exactly like Cloudstream's load()
        title_tag = soup.select_one("div.gridlove-content div.entry-header h1.entry-title")
        title_raw = title_tag.get_text(strip=True) if title_tag else "Unknown"
        if title_raw.startswith("Download "):
            title_raw = title_raw[9:].strip()

        title_match = re.search(r"(^.*\)\d*)", title_raw)
        title = title_match.group(1).strip() if title_match else title_raw

        # Extract poster from entry-content > p img
        poster_tag = soup.select_one("div.entry-content > p img")
        poster = poster_tag.get("src") if poster_tag else None
        if poster:
            poster = re.sub(r'-\d+x\d+(\.[a-zA-Z]+)$', r'\1', poster)

        # Extract year
        year_match = re.search(r'(?<=\()[\d(\]]+(?!\))', title_raw)
        if not year_match:
             year_match = re.search(r'\b(20\d{2})\b', title_raw)
        year = year_match.group(0) if year_match else None

        # Extract plot
        plot_candidates = soup.select("div.entry-content p")
        plot = None
        for p in plot_candidates:
            text = p.get_text(strip=True)
            if len(text) > 60:
                plot = text
                break

        # Extract the fastserver/driveseed links correctly 
        link_candidates = soup.select("a.maxbutton, a[href*='fastserver'], a[href*='gdtot'], a[href*='driveseed']")
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
    logger.info(f"{PLUGIN_NAME}: extracting stream links from {data_url}")
    links = []

    try:
        resp = http.get(data_url, cloudflare=True)
        html = resp.text

        # Driveseed / Fastserver token API bypass
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

        # Direct MP4/M3U8 regex scan fallback
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
    """Parse UHDMovies article grid exactly like Cloudstream toSearchResult()."""
    items = []
    
    # Fallback to general article if gridlove-post is missing
    articles = soup.select("article.gridlove-post")
    if not articles:
        articles = soup.select("article")
        
    for article in articles:
        title_el = article.select_one("h1.sanket, h2.entry-title, h2, h3")
        if not title_el:
            continue
        
        title_raw = title_el.get_text(strip=True)
        if title_raw.startswith("Download "):
            title_raw = title_raw[9:].strip()
            
        title_match = re.search(r"(^.*\)\d*)", title_raw)
        title = title_match.group(1).strip() if title_match else title_raw

        link_el = article.select_one("div.entry-image > a, a[href]")
        url = link_el.get("href") if link_el else None
        if not url:
            continue

        img_el = article.select_one("div.entry-image > a > img, img[src]")
        poster = None
        if img_el:
            poster = img_el.get("data-src")
            if not poster:
                poster = img_el.get("src")
        
        if poster:
            # Clean WP resize suffix (e.g. -370x290.jpg -> .jpg) to get high-resolution original image
            poster = re.sub(r'-\d+x\d+(\.[a-zA-Z]+)$', r'\1', poster)

        year_match = re.search(r'\b(20\d{2})\b', title_raw)
        year = year_match.group(1) if year_match else None

        items.append(search_response(
            name=title,
            url=url,
            poster_url=poster,
            media_type="movie",
            year=year
        ))
        
    if not items:
        # Debugging: Log why it failed
        page_title = soup.title.string if soup.title else "No Title"
        logger.warning(f"UHDMovies _parse_article_list found 0 items! Page title: {page_title}. Articles found: {len(articles)}")
        
    return items

