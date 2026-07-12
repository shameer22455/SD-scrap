import cloudscraper
from bs4 import BeautifulSoup
import json
import urllib.parse
import requests

# OnlineMoviesHindi is not in the urls.json officially so we just keep its latest known or fallback
def get_base_url():
    return "https://onlinemovieshindi.com"

def get_streams(query):
    scraper = cloudscraper.create_scraper()
    base_url = get_base_url()
    
    query_encoded = urllib.parse.quote(query)
    search_url = f"{base_url}/?s={query_encoded}"
    res = scraper.get(search_url)
    soup = BeautifulSoup(res.text, 'html.parser')
    
    first_result = soup.select_one("div.result-item article a")
    if not first_result: return "[]"
        
    movie_url = first_result.get("href")
    movie_res = scraper.get(movie_url)
    movie_soup = BeautifulSoup(movie_res.text, 'html.parser')
    
    streams = []
    for iframe in movie_soup.select("iframe"):
        src = iframe.get("src")
        if src and ("video" in src or "embed" in src or "player" in src):
            streams.append({"name": "OnlineMoviesHindi - Player", "url": src})
            
    return json.dumps(streams)
