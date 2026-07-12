import cloudscraper
from bs4 import BeautifulSoup
import json
import urllib.parse
import requests

def get_base_url():
    try:
        urls = requests.get('https://raw.githubusercontent.com/SaurabhKaperwan/Utils/refs/heads/main/urls.json', timeout=5).json()
        return urls.get("moviesmod", "https://moviesmod.at")
    except:
        return "https://moviesmod.at"

def get_streams(query):
    scraper = cloudscraper.create_scraper()
    base_url = get_base_url()
    
    query_encoded = urllib.parse.quote(query)
    search_url = f"{base_url}/?s={query_encoded}"
    res = scraper.get(search_url)
    soup = BeautifulSoup(res.text, 'html.parser')
    
    first_result = soup.select_one("article a")
    if not first_result: return "[]"
        
    movie_url = first_result.get("href")
    movie_res = scraper.get(movie_url)
    movie_soup = BeautifulSoup(movie_res.text, 'html.parser')
    
    streams = []
    for btn in movie_soup.select("a.maxbutton, a[href*='download']"):
        link = btn.get("href")
        if link:
            name = btn.text.strip() or "Download"
            streams.append({"name": "MoviesMod - " + name, "url": link})
            
    return json.dumps(streams)
