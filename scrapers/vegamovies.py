import cloudscraper
from bs4 import BeautifulSoup
import json
import urllib.parse
import requests
import base64
import utils

def get_base_url():
    try:
        urls = requests.get('https://raw.githubusercontent.com/SaurabhKaperwan/Utils/refs/heads/main/urls.json', timeout=5).json()
        return urls.get("vegamovies", "https://vegamovies.navy")
    except:
        return "https://vegamovies.navy"

def get_streams(query):
    scraper = cloudscraper.create_scraper()
    base_url = get_base_url()
    
    query_encoded = urllib.parse.quote(query)
    search_url = f"{base_url}/search.php?q={query_encoded}"
    res = scraper.get(search_url)
    
    try:
        data = res.json()
        if not data.get("hits"): return "[]"
        movie_url = data["hits"][0]["document"]["permalink"]
        if movie_url.startswith("/"): movie_url = base_url + movie_url
    except:
        return "[]"
    
    movie_res = scraper.get(movie_url)
    movie_soup = BeautifulSoup(movie_res.text, 'html.parser')
    
    streams = []
    buttons = movie_soup.select("a.maxbutton-download-links, a.btn, a[href*='vcloud'], a[href*='hubcloud']")
    for btn in buttons:
        link = btn.get("href")
        if not link: continue
        name = btn.text.strip() or "Download Link"
        
        if "url=" in link:
            try:
                b64 = link.split("url=")[-1]
                link = base64.b64decode(b64).decode('utf-8')
            except: pass

        if "vcloud" in link.lower() or "hubcloud" in link.lower() or "download" in link.lower() or "fastserver" in link.lower():
            resolved = utils.resolve_link(link, scraper, "VegaMovies")
            streams.extend(resolved)
            
    return json.dumps(streams)
