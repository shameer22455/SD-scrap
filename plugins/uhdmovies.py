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
    movie_response, tv_response, episode, stream_link,
    extract_quality, clean_title, url_encode
)
import re
from bs4 import BeautifulSoup

# ─── Plugin Metadata ──────────────────────────────────────────────────────────

PLUGIN_NAME = "UHD Movies"
MAIN_URL = "https://uhdmovies.casa"


# ─── Contract Functions ───────────────────────────────────────────────────────

def get_name() -> str:
    return PLUGIN_NAME


def get_supported_types() -> list:
    return ["movie", "tv"]


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

        # Check if TV Series
        is_tv = False
        title_lower = title_raw.lower()
        if "season" in title_lower or "s0" in title_lower or "complete" in title_lower or "episodes" in title_lower or "tv-shows" in url or "series" in url:
            is_tv = True

        # Fetch Cinemeta Metadata (Real overview description, episode names, thumbs, air dates)
        cinemeta_desc = None
        cinemeta_videos = []
        try:
            clean_search_name = _clean_search_title(title)
            cat = "series" if is_tv else "movie"
            search_url = f"https://v3-cinemeta.strem.io/catalog/{cat}/top/search={url_encode(clean_search_name)}.json"
            search_resp = http.get_json(search_url)
            metas = search_resp.get("metas", [])
            if metas:
                imdb_id = metas[0].get("imdb_id")
                if imdb_id:
                    meta_url = f"https://v3-cinemeta.strem.io/meta/{cat}/{imdb_id}.json"
                    meta_resp = http.get_json(meta_url)
                    meta_data = meta_resp.get("meta", {})
                    cinemeta_desc = meta_data.get("description")
                    cinemeta_videos = meta_data.get("videos", [])
                    if meta_data.get("poster"):
                        poster = meta_data.get("poster")
        except Exception as meta_err:
            logger.warning(f"Failed to load Cinemeta metadata for {title}: {meta_err}")

        # Extract plot fallback
        plot = cinemeta_desc
        if not plot:
            plot_candidates = soup.select("div.entry-content p")
            for p in plot_candidates:
                text = p.get_text(strip=True)
                if len(text) > 60:
                    plot = text
                    break

        # Parse episodes if TV Series
        episodes_list = []
        content = soup.select_one("div.entry-content")
        link_candidates = soup.select("a.maxbutton, a[href*='fastserver'], a[href*='gdtot'], a[href*='driveseed'], a[href*='techmny'], a[href*='howard']")

        if is_tv and content:
            current_season = 1
            # Walk through paragraph text/headings to capture season, and links for episodes
            for child in content.descendants:
                if child.name in ["h1", "h2", "h3", "h4", "p", "span"]:
                    text = child.get_text()
                    season_match = re.search(r'(?i)(?:season\s+|s)(\d+)', text)
                    if season_match:
                        current_season = int(season_match.group(1))
                elif child.name == "a" and child.get("href"):
                    href = child.get("href")
                    text = child.get_text(strip=True)
                    if any(x in href for x in ["fastserver", "driveseed", "gdtot", "techmny", "howard"]) or "maxbutton" in child.get("class", []):
                        ep_match = re.search(r'(?i)(?:episode\s+|ep\s+|e|ep)(\d+)', text)
                        if ep_match:
                            ep_num = int(ep_match.group(1))
                            
                            # Match episode with Cinemeta videos to fetch clean names/thumbnails/plots
                            ep_name = f"Episode {ep_num}"
                            ep_plot = ""
                            ep_thumb = None
                            for video in cinemeta_videos:
                                if video.get("season") == current_season and (video.get("number") == ep_num or video.get("episode") == ep_num):
                                    ep_name = video.get("name", ep_name)
                                    ep_plot = video.get("description") or video.get("overview", "")
                                    ep_thumb = video.get("thumbnail")
                                    break
                            
                            episodes_list.append(episode(
                                name=ep_name,
                                data=href,
                                episode_num=ep_num,
                                season=current_season,
                                poster_url=ep_thumb,
                                description=ep_plot
                            ))
                        elif any(p in text.lower() for p in ["pack", "complete", "zip"]):
                            quality_match = re.search(r'(2160p|1080p|720p|480p)', text, re.IGNORECASE)
                            q_suffix = f" ({quality_match.group(1)})" if quality_match else ""
                            episodes_list.append(episode(
                                name=f"Season {current_season} Complete Pack{q_suffix}",
                                data=href,
                                episode_num=100 + len(episodes_list),
                                season=current_season
                            ))

        if not is_tv or not episodes_list:
            data_url = link_candidates[0].get("href") if link_candidates else url
            return movie_response(
                name=title,
                url=url,
                data_url=data_url,
                poster_url=poster,
                plot=plot,
                year=year
            )
        else:
            return tv_response(
                name=title,
                url=url,
                data_url=url,
                episodes=episodes_list,
                poster_url=poster,
                plot=plot,
                year=year
            )
    except Exception as e:
        logger.error(f"{PLUGIN_NAME}: load_details failed: {e}", exc_info=True)
        return movie_response(name="Error", url=url, data_url=url)


def _clean_search_title(title: str) -> str:
    # Clean titles like "House Of The Dragon (Season 1 – 3) (2022)" to "House Of The Dragon"
    t = re.sub(r'\(.*?\)', '', title)
    t = re.sub(r'\[.*?\]', '', t)
    t = re.sub(r'(?i)\bseason\s*\d+\b', '', t)
    t = re.sub(r'(?i)\bs\d+\b', '', t)
    t = re.sub(r'\s*–\s*\d+', '', t)
    return t.strip()


def load_links(data_url: str) -> list:
    logger.info(f"{PLUGIN_NAME}: extracting stream links from {data_url}")
    links = []

    try:
        final_data_url = bypass_shortener(data_url)
        logger.info(f"{PLUGIN_NAME}: bypassed URL is {final_data_url}")

        resp = http.get(final_data_url, cloudflare=True)
        html = resp.text

        # Driveseed / Fastserver token API bypass
        token_match = re.search(r"formData\.append\('token',\s*'([a-f0-9]+)'\)", html)
        dl_path_match = re.search(r"fetch\('(/download\?id=[a-zA-Z0-9/+=%]+)'", html)

        if token_match and dl_path_match:
            from urllib.parse import urlparse
            parsed = urlparse(final_data_url)
            domain = f"{parsed.scheme}://{parsed.netloc}"
            api_url = domain + dl_path_match.group(1)

            json_resp = http.post_json(
                api_url,
                data={"token": token_match.group(1)},
                headers={"X-Requested-With": "XMLHttpRequest", "Referer": final_data_url}
            )
            final_url = json_resp.get("url", "").replace("\\/", "/")
            if final_url:
                quality = extract_quality(final_url)
                links.append(stream_link(
                    url=final_url,
                    name=f"UHD Server {quality}p",
                    source=PLUGIN_NAME,
                    quality=quality,
                    referer=final_data_url
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
                        referer=final_data_url
                    ))

    except Exception as e:
        logger.error(f"{PLUGIN_NAME}: load_links failed: {e}", exc_info=True)

    return links


# ─── Internal Helpers ─────────────────────────────────────────────────────────

def bypass_shortener(url: str) -> str:
    if not url:
        return ""
    if any(x in url for x in ["fastserver", "driveseed", "vcloud", "gdtot", "gdflix"]):
        return url
    try:
        logger.info(f"{PLUGIN_NAME}: bypassing shortener for {url}")
        soup = http.get_soup(url, cloudflare=True)
        form = soup.select_one("form#landing")
        if not form:
            return url
        action = form.get("action")
        inputs = {inp.get("name"): inp.get("value", "") for inp in form.select("input") if inp.get("name")}
        resp = http.post(action, data=inputs, headers={"Referer": url})
        soup = BeautifulSoup(resp.text, "html.parser")
        form = soup.select_one("form#landing")
        if not form:
            return url
        action = form.get("action")
        inputs = {inp.get("name"): inp.get("value", "") for inp in form.select("input") if inp.get("name")}
        resp = http.post(action, data=inputs, headers={"Referer": action})
        soup = BeautifulSoup(resp.text, "html.parser")
        script = soup.find("script", text=re.compile(r"\?go="))
        if not script:
            refresh = soup.select_one("meta[http-equiv=refresh]")
            if refresh:
                content = refresh.get("content", "")
                m = re.search(r"url=(https?://\S+)", content, re.IGNORECASE)
                if m:
                    return m.group(1)
            return url
        script_text = script.string
        m = re.search(r"\?go=([a-zA-Z0-9/+=%_-]+)", script_text)
        if not m:
            return url
        token = m.group(1)
        redirect_url = f"{action.rstrip('/')}?go={token}"
        resp = http.get(redirect_url, headers={"Referer": action})
        m = re.search(r"replace\(\"([^\"]+)\"\)", resp.text)
        if m:
            path = m.group(1)
            if path == "/404":
                return url
            from urllib.parse import urljoin
            return urljoin(redirect_url, path)
        soup = BeautifulSoup(resp.text, "html.parser")
        refresh = soup.select_one("meta[http-equiv=refresh]")
        if refresh:
            content = refresh.get("content", "")
            m = re.search(r"url=(https?://\S+)", content, re.IGNORECASE)
            if m:
                return m.group(1)
        return url
    except Exception as e:
        logger.error(f"Error bypassing shortener: {e}")
        return url


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

        is_tv = False
        title_lower = title_raw.lower()
        if "season" in title_lower or "s0" in title_lower or "complete" in title_lower or "episodes" in title_lower:
            is_tv = True

        items.append(search_response(
            name=title,
            url=url,
            poster_url=poster,
            media_type="tv" if is_tv else "movie",
            year=year
        ))
        
    if not items:
        # Debugging: Log why it failed
        page_title = soup.title.string if soup.title else "No Title"
        logger.warning(f"UHDMovies _parse_article_list found 0 items! Page title: {page_title}. Articles found: {len(articles)}")
        
    return items

