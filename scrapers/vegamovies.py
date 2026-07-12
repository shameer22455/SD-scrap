import cloudscraper
from bs4 import BeautifulSoup
import json
import urllib.parse
import requests

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
    except:
        return "[]"
    
    movie_res = scraper.get(movie_url)
    movie_soup = BeautifulSoup(movie_res.text, 'html.parser')
    
    streams = []
    buttons = movie_soup.select("a.maxbutton-download-links, a.btn, a[href*='vcloud']")
    for btn in buttons:
        link = btn.get("href")
        if not link: continue
        name = btn.text.strip() or "Download Link"
        if "vcloud" in link.lower() or "download" in link.lower() or "fastserver" in link.lower():
            streams.append({"name": "VegaMovies - " + name, "url": link})
            
    return json.dumps(streams)
