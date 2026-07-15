"""
SDM Plugin: UHD Movies
========================
Scraper for UHDMovies -- 1080p/4K movie downloads.
Ported faithfully from the decompiled Kotlin UHDmoviesProvider.kt + Driveseed.kt.

Link extraction flow (matches CloudStream exactly):
  1. load() scrapes movie page -> extracts UHDLinks JSON array
     (each entry: {sourceName: "4K HDR...", sourceLink: "https://cloud.unblockedgames.world/..."})
  2. load_links() receives that JSON -> for each sourceLink:
     a. If "unblockedgames" in URL -> bypass shortener -> get driveseed.org/r? redirect URL
     b. Follow redirect to driveseed.org/file/{id}
     c. Extract PHPSESSID cookie + token + download-id from page HTML
     d. POST to driveseed.org/download?id={id} with token in form body
     e. Parse JSON response {"url": "https://..."} for direct link
     f. Use Driveseed "Resume Cloud" (/zfile/ path) as fallback
"""

from sdm_api import (
    http, logger,
    search_response, home_page_list, home_page_response,
    movie_response, stream_link,
    extract_quality, clean_title, url_encode
)
import re
import json

# ---- Plugin Metadata --------------------------------------------------------

PLUGIN_NAME = "UHD Movies"
MAIN_URL = "https://uhdmovies.casa"
DRIVESEED_BASE = "https://driveseed.org"


# ---- Contract Functions -----------------------------------------------------

def get_name():
    return PLUGIN_NAME


def get_supported_types():
    return ["movie", "tvshow"]


def get_main_page():
    logger.info(f"{PLUGIN_NAME}: loading home page from {MAIN_URL}")
    try:
        soup = http.get_soup(MAIN_URL, cloudflare=True)
        items = _parse_article_list(soup)
        return home_page_response([home_page_list("Latest Movies", items)])
    except Exception as e:
        logger.error(f"{PLUGIN_NAME}: get_main_page failed: {e}", exc_info=True)
        return home_page_response([])


def search(query):
    logger.info(f"{PLUGIN_NAME}: searching for '{query}'")
    try:
        search_url = f"{MAIN_URL}/?s={url_encode(query)} "
        soup = http.get_soup(search_url, cloudflare=True)
        return _parse_article_list(soup)
    except Exception as e:
        logger.error(f"{PLUGIN_NAME}: search failed: {e}", exc_info=True)
        return []


def load_details(url):
    """
    Load movie/TV details. The data_url returned is a JSON array of UHDLinks
    objects matching Kotlin UHDmoviesProvider$load$data$2:
      {"sourceName": "<quality label>", "sourceLink": "<unblockedgames URL>"}
    """
    logger.info(f"{PLUGIN_NAME}: loading details for {url}")
    try:
        soup = http.get_soup(url, cloudflare=True)

        # Title (matches Kotlin: removePrefix "Download ", then regex (^.*\)\d*) )
        title_raw_el = soup.select_one("div.gridlove-content div.entry-header h1.entry-title")
        title_raw = title_raw_el.get_text(strip=True) if title_raw_el else ""
        title_raw = re.sub(r"^Download\s+", "", title_raw)
        title_match = re.search(r"^(.*?)\s*\(", title_raw)
        title = title_match.group(1).strip() if title_match else title_raw

        # Poster: first <img> inside entry-content > p
        img_el = soup.select_one("div.entry-content > p img")
        poster = img_el.get("src") if img_el else None
        if not poster:
            og = soup.select_one("meta[property='og:image']")
            poster = og.get("content") if og else None

        # Year
        year_match = re.search(r"\((\d{4})\)", title_raw)
        year = year_match.group(1) if year_match else None

        # Tags
        tags = [el.get_text(strip=True) for el in soup.select("div.entry-category > a.gridlove-cat")]

        # Plot
        plot = None
        for p in soup.select("div.entry-content p"):
            text = p.get_text(strip=True)
            if len(text) > 60 and not text.lower().startswith("download"):
                plot = text
                break

        # Detect TV
        title_full_el = soup.select_one("h1.entry-title")
        title_full = title_full_el.get_text(strip=True) if title_full_el else ""
        is_tv = "season" in title_full.lower() or bool(re.search(r"\bS0\d\b", title_full))

        # Build UHDLinks JSON (matches Kotlin UHDmoviesProvider$load$data$2)
        # Each <p><strong>...Download...</strong></p> is followed by a sibling
        # containing <a class="maxbutton-1"> pointing to unblockedgames
        uhd_links = []
        for h_tag in soup.select("div.entry-content p strong, div.entry-content h4, div.entry-content h3"):
            label_text = h_tag.get_text(strip=True)
            if not label_text:
                continue
            parent = h_tag.parent if h_tag.parent else h_tag
            next_sib = parent.find_next_sibling()
            if next_sib:
                btns = next_sib.select("a.maxbutton-1, a[href*='unblockedgames'], a[href*='driveseed']")
                for btn in btns:
                    href = btn.get("href", "")
                    if href.startswith("http"):
                        src_name = label_text.split("Download")[0].strip()
                        uhd_links.append({"sourceName": src_name, "sourceLink": href})

        # Fallback: scan all maxbutton links
        if not uhd_links:
            for btn in soup.select("a.maxbutton-1, a.maxbutton"):
                href = btn.get("href", "")
                if href.startswith("http"):
                    label = ""
                    for prev in btn.parents:
                        heading = prev.find_previous(["strong", "h3", "h4", "p"])
                        if heading:
                            label = heading.get_text(strip=True).split("Download")[0].strip()
                            break
                    uhd_links.append({"sourceName": label or "Stream", "sourceLink": href})

        data_url = json.dumps(uhd_links) if uhd_links else url

        return movie_response(
            name=title,
            url=url,
            data_url=data_url,
            poster_url=poster,
            plot=plot,
            year=year,
            genres=tags
        )

    except Exception as e:
        logger.error(f"{PLUGIN_NAME}: load_details failed: {e}", exc_info=True)
        return movie_response(name="Error", url=url, data_url=url)


def load_links(data_url):
    """
    Mirrors CloudStream UHDmoviesProvider.loadLinks + Driveseed.getUrl.

    data_url is either:
      - JSON array: [{"sourceName": "...", "sourceLink": "https://..."}]
      - Plain HTTPS URL (single direct link)
    """
    logger.info(f"{PLUGIN_NAME}: extracting stream links from {data_url}")
    links = []

    if data_url.startswith("https://"):
        sources = [{"sourceName": "Stream", "sourceLink": data_url}]
    else:
        try:
            sources = json.loads(data_url)
        except Exception:
            sources = [{"sourceName": "Stream", "sourceLink": data_url}]

    # Deduplicate by sourceLink — same URL = same driveseed file, no need to resolve twice
    seen_links = set()
    deduped = []
    for source in sources:
        link = source.get("sourceLink", "")
        if link and link not in seen_links:
            seen_links.add(link)
            deduped.append(source)

    logger.info(f"{PLUGIN_NAME}: {len(sources)} sources -> {len(deduped)} unique after dedup")

    for source in deduped:
        source_name = source.get("sourceName", "")
        source_link = source.get("sourceLink", "")
        if not source_link:
            continue
        try:
            final_url = _resolve_source_link(source_link, source_name)
            if final_url:
                quality = extract_quality(source_name + " " + final_url)
                name = (source_name + f" [{quality}p]").strip("[] ") if source_name else f"UHD [{quality}p]"
                links.append(stream_link(
                    url=final_url,
                    name=name,
                    source=PLUGIN_NAME,
                    quality=quality,
                    referer=DRIVESEED_BASE
                ))
        except Exception as e:
            logger.warning(f"{PLUGIN_NAME}: failed resolving {source_link}: {e}")

    return links


# ---- Link Resolution (mirrors Driveseed.kt exactly) -------------------------

def _resolve_source_link(url, label=""):
    """
    Full resolution chain:
    1. unblockedgames -> bypass shortener -> driveseed.org/r? URL
    2. /r? redirect -> /file/{id}
    3. resumeBot: GET /file/{id} -> PHPSESSID + token + dl_id -> POST -> direct URL
    4. Fallback: Resume Cloud, instant download
    """
    logger.info(f"{PLUGIN_NAME}: bypassing shortener for {url}")
    final_link = url

    # Step 1: Bypass unblockedgames shortener
    if "unblockedgames" in url:
        bypassed = _bypass_unblockedgames(url)
        if bypassed:
            final_link = bypassed
            logger.info(f"{PLUGIN_NAME}: bypassed URL is {final_link}")
        else:
            logger.warning(f"{PLUGIN_NAME}: bypass returned nothing for {url}")
            return None

    # Step 2: Follow driveseed /r? redirect
    if "driveseed.org/r" in final_link:
        final_link = _follow_driveseed_redirect(final_link)
        if not final_link:
            return None

    # Step 3: Driveseed resumeBot
    if "driveseed.org/file/" in final_link:
        return _driveseed_resume_bot(final_link)

    # Fallback: direct media URL
    if final_link.endswith(".mp4") or final_link.endswith(".m3u8") or "cdn." in final_link:
        return final_link

    logger.warning(f"{PLUGIN_NAME}: could not resolve final URL from {url}")
    return None


def _bypass_unblockedgames(url):
    """
    Bypass cloud.unblockedgames.world shortener.

    Exact port of Moviesmod Utils.kt bypass() function:
      1. GET ?sid=... -> form#landing with _wp_http
      2. POST -> second form#landing with _wp_http2
      3. POST -> page with <script> containing ?go=pepe-xxx token
      4. GET /?go=pepe-xxx with cookie (pepe-xxx = _wp_http2 value)
         -> <meta http-equiv=refresh> pointing to driveseed.org/r?...
      5. GET driveseed /r?... -> JS replace('/file/xxx')
    """
    import requests as req_lib
    session = req_lib.Session()
    ua = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    from urllib.parse import urlparse

    def get_base(u):
        p = urlparse(u)
        return f"{p.scheme}://{p.netloc}"

    def get_form(html):
        """Extract (action, {name: value}) from form#landing."""
        soup = _quick_soup(html)
        form = soup.select_one("form#landing")
        if not form:
            return None, {}
        action = form.get("action", "")
        data = {i.get("name"): i.get("value", "") for i in form.find_all("input") if i.get("name")}
        return action, data

    try:
        host = get_base(url)
        logger.info(f"{PLUGIN_NAME}: bypass step 1 GET {url[:60]}")

        # Step 1: GET initial page -> first form
        r1 = session.get(url, headers=headers, timeout=20, allow_redirects=True)
        form_url1, form_data1 = get_form(r1.text)
        if not form_url1 or not form_data1:
            logger.warning(f"{PLUGIN_NAME}: bypass: no form#landing on step 1")
            return None
        logger.debug(f"{PLUGIN_NAME}: bypass step 1 form: action={form_url1}, keys={list(form_data1.keys())}")

        # Step 2: POST first form -> second form
        logger.info(f"{PLUGIN_NAME}: bypass step 2 POST {form_url1}")
        r2 = session.post(form_url1, data=form_data1,
                          headers={**headers, "Referer": url}, timeout=20, allow_redirects=True)
        form_url2, form_data2 = get_form(r2.text)
        if not form_url2 or not form_data2:
            logger.warning(f"{PLUGIN_NAME}: bypass: no second form#landing on step 2")
            return None
        logger.debug(f"{PLUGIN_NAME}: bypass step 2 form: action={form_url2}, keys={list(form_data2.keys())}")

        # Step 3: POST second form -> page with <script> containing ?go=pepe-xxx
        logger.info(f"{PLUGIN_NAME}: bypass step 3 POST {form_url2}")
        r3 = session.post(form_url2, data=form_data2,
                          headers={**headers, "Referer": form_url1}, timeout=20, allow_redirects=True)
        html3 = r3.text

        # Extract skToken from: <script>...window.location.replace("?go=pepe-6a576xxx")...</script>
        # Kotlin: res.selectFirst("script:containsData(?go=)")?.data()
        #         ?.substringAfter("?go=")?.substringBefore('"')
        sk_token_match = re.search(r'[?&]go=(pepe-[a-zA-Z0-9]+)', html3)
        if not sk_token_match:
            # Try alternate: href or location with ?go=
            sk_token_match = re.search(r'\?go=(pepe-[a-zA-Z0-9]+)', html3)
        if not sk_token_match:
            logger.warning(f"{PLUGIN_NAME}: bypass: no ?go=pepe-xxx token in step 3 response")
            logger.debug(f"{PLUGIN_NAME}: bypass step3 html snippet: {html3[:500]}")
            return None

        sk_token = sk_token_match.group(1)
        wp_http2_val = form_data2.get("_wp_http2", "")
        logger.info(f"{PLUGIN_NAME}: bypass step 4: skToken={sk_token}, cookie_val={wp_http2_val[:20]}...")

        # Step 4: GET /?go=pepe-xxx with cookie skToken=_wp_http2_value
        # Kotlin: app.get("$host?go=$skToken", cookies = mapOf(skToken to "${formData["_wp_http2"]}"))
        go_url = f"{host}?go={sk_token}"
        go_cookies = {sk_token: wp_http2_val}
        session.cookies.update(go_cookies)

        r4 = session.get(go_url,
                         headers={**headers, "Referer": form_url2},
                         timeout=20, allow_redirects=False)
        logger.debug(f"{PLUGIN_NAME}: bypass step 4 status={r4.status_code}")
        logger.debug(f"{PLUGIN_NAME}: bypass step 4 Set-Cookie={r4.headers.get('Set-Cookie', 'none')}")
        logger.debug(f"{PLUGIN_NAME}: bypass step 4 Location={r4.headers.get('Location', 'none')}")

        # If we get a redirect (Location header) -> driveseed URL
        if r4.status_code in (301, 302, 303, 307, 308):
            loc = r4.headers.get("Location", "")
            if loc:
                logger.info(f"{PLUGIN_NAME}: bypass got redirect to: {loc}")
                return loc

        # Kotlin: .document.selectFirst("meta[http-equiv=refresh]")?.attr("content")?.substringAfter("url=")
        meta_m = re.search(r'<meta[^>]+http-equiv=["\']refresh["\'][^>]+content=["\'][^;]+;\s*url=([^"\'>\s]+)',
                            r4.text, re.IGNORECASE)
        if not meta_m:
            # Also try content="0; url=..." format
            meta_m = re.search(r'content=["\'][^;]*;\s*url=([^"\'>\s]+)', r4.text, re.IGNORECASE)

        if meta_m:
            drive_url = meta_m.group(1).strip()
            logger.info(f"{PLUGIN_NAME}: bypass meta refresh URL: {drive_url}")

            # Step 5: GET driveseed /r?... -> JS replace('/file/xxx')
            # Kotlin: val path = app.get(driveUrl).text.substringAfter("replace(\"").substringBefore("\")")
            r5 = session.get(drive_url, headers={**headers, "Referer": go_url}, timeout=20)
            path_m = re.search(r'replace\(["\']([^"\']+)["\']', r5.text)
            if path_m:
                path = path_m.group(1)
                if path == "/404":
                    logger.warning(f"{PLUGIN_NAME}: bypass got /404")
                    return None
                if not path.startswith("http"):
                    path = get_base(drive_url) + path
                logger.info(f"{PLUGIN_NAME}: bypass final path: {path}")
                return path

            # If already landed at driveseed /file/...
            if "driveseed.org/file/" in r5.url:
                return r5.url

            # Fallback: any driveseed URL in response
            ds = re.search(r"(https://driveseed\.org/[^\s\"'<>]+)", r5.text)
            if ds:
                return ds.group(1)

        # Last resort: check if any response contained driveseed
        for html in [html3, r4.text]:
            ds = re.search(r"(https://driveseed\.org/[^\s\"'<>]+)", html)
            if ds:
                return ds.group(1)

    except Exception as e:
        logger.error(f"{PLUGIN_NAME}: _bypass_unblockedgames error: {e}", exc_info=True)
    return None


def _follow_driveseed_redirect(url):
    """
    GET driveseed.org/r?... and follow JS window.location.replace to /file/{id}.
    """
    try:
        resp = http.get(url)
        html = resp.text
        m = re.search(r"window\.location\.replace\([\"']([^\"']+)[\"']\)", html)
        if m:
            path = m.group(1)
            if not path.startswith("http"):
                path = DRIVESEED_BASE + path
            return path
        if hasattr(resp, "url") and resp.url != url:
            return resp.url
    except Exception as e:
        logger.error(f"{PLUGIN_NAME}: _follow_driveseed_redirect error: {e}")
    return None


def _driveseed_resume_bot(file_url):
    """
    Faithfully mirrors Driveseed.resumeBot() from decompiled Kotlin:
      1. GET /file/{id} -- extract PHPSESSID cookie, token, dl_id
      2. POST /download?id={dl_id} with token + Accept/*,Origin,Sec-Fetch-Site headers
      3. Parse {"url": "https://..."} JSON response
      4. Fallback: generate() API, Resume Cloud (/zfile/), instant download button
    """
    import requests as req_lib
    session = req_lib.Session()
    ua = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    try:
        logger.info(f"{PLUGIN_NAME}: driveseed resumeBot for {file_url}")
        resp = session.get(file_url, headers=headers, timeout=20)
        html = resp.text
        soup = _quick_soup(html)
        base_url = DRIVESEED_BASE

        # File key from URL: /file/sCf1Jogdti
        key_match = re.search(r"/file/([a-zA-Z0-9]+)", file_url)
        file_key = key_match.group(1) if key_match else ""

        # Priority 1: Instant Download (direct CDN URL, no auth needed)
        for sel in ["a[href*='cdn.video-gen']", "a[href*='video-gen']", "a[href*='cdn.']:not([href*='login'])"]:
            inst = soup.select_one(sel)
            if inst:
                href = inst.get("href", "")
                if href.startswith("http") and not "login" in href:
                    logger.info(f"{PLUGIN_NAME}: using Instant Download: {href[:80]}")
                    return href

        # Priority 2: Resume Cloud /zfile/ -> btn-success link (workers.dev stream)
        zfile_a = soup.select_one("a[href*='/zfile/']")
        if zfile_a and file_key:
            zfile_url = base_url + f"/zfile/{file_key}"
            logger.info(f"{PLUGIN_NAME}: trying Resume Cloud: {zfile_url}")
            try:
                zresp = session.get(zfile_url, headers={**headers, "Referer": file_url}, timeout=20)
                zsoup = _quick_soup(zresp.text)
                # btn-success is the "Cloud Resume Download" button
                btn = zsoup.select_one("a.btn-success")
                if btn:
                    href = btn.get("href", "")
                    if href.startswith("http"):
                        logger.info(f"{PLUGIN_NAME}: Resume Cloud got: {href[:80]}")
                        return href
                # Fallback: any workers.dev or external stream URL
                for a in zsoup.find_all("a", href=True):
                    href = a.get("href", "")
                    if "workers.dev" in href or "video-gen" in href:
                        return href
            except Exception as ze:
                logger.warning(f"{PLUGIN_NAME}: zfile error: {ze}")

        # Priority 3: Token POST API (works if PHPSESSID cookie is set)
        phpsessid = session.cookies.get("PHPSESSID", "")
        token_match = re.search(r"formData\.append\(['\"]token['\"],\s*['\"]([a-f0-9]+)['\"]\)", html)
        token = token_match.group(1) if token_match else ""
        dl_id_match = re.search(r"fetch\(['\"](?:/download\?id=)([a-zA-Z0-9/+=]+)['\"]", html)
        dl_id = dl_id_match.group(1) if dl_id_match else ""

        logger.debug(f"{PLUGIN_NAME}: token={token[:20] if token else 'NONE'}, dl_id={dl_id[:20] if dl_id else 'NONE'}")

        if token and dl_id and phpsessid:
            dl_url = base_url + f"/download?id={dl_id}"
            post_headers = {
                "User-Agent": ua, "Accept": "*/*",
                "Origin": base_url, "Sec-Fetch-Site": "same-origin",
                "Referer": file_url, "x-token": "driveseed.org",
            }
            post_resp = session.post(dl_url, data={"token": token},
                                     headers=post_headers,
                                     cookies={"PHPSESSID": phpsessid}, timeout=15)
            try:
                data = post_resp.json()
                direct_url = data.get("url", "")
                if direct_url and direct_url.startswith("http"):
                    logger.info(f"{PLUGIN_NAME}: token API got: {direct_url[:80]}")
                    return direct_url
            except Exception:
                pass

    except Exception as e:
        logger.error(f"{PLUGIN_NAME}: _driveseed_resume_bot error: {e}", exc_info=True)
    return None


# ---- Internal Helpers -------------------------------------------------------

def _quick_soup(html):
    from bs4 import BeautifulSoup
    return BeautifulSoup(html, "html.parser")


def _parse_article_list(soup):
    """Parse UHDMovies article grid into search result list."""
    items = []
    for article in soup.select("article.gridlove-post, article"):
        title_el = article.select_one("h1.sanket, h2.entry-title, h3, h1")
        if not title_el:
            continue
        title_raw = title_el.get_text(strip=True)
        title_raw = re.sub(r"^Download\s+", "", title_raw)
        title_match = re.search(r"^(.*?\))", title_raw)
        title = clean_title(title_match.group(1) if title_match else title_raw)

        link_el = article.select_one("div.entry-image > a, a[href]")
        url = link_el.get("href") if link_el else None
        if not url or not url.startswith("http"):
            continue

        img_el = article.select_one("div.entry-image > a > img, img[data-src], img[src]")
        poster = None
        if img_el:
            poster = img_el.get("data-src") or img_el.get("src")

        year_match = re.search(r"\b(20\d{2})\b", title_raw)
        year = year_match.group(1) if year_match else None

        is_tv = bool(re.search(r"\b(season|S0\d)\b", title_raw, re.IGNORECASE))
        media_type = "tvshow" if is_tv else "movie"

        items.append(search_response(
            name=title,
            url=url,
            poster_url=poster,
            media_type=media_type,
            year=year
        ))
    return items
