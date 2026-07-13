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
    for btn in movie_soup.select("a.maxbutton-download-links, a.maxbutton, a[href*='download']"):
        link = btn.get("href")
        if link:
            # First level intermediate page (like vcloud or driveleech)
            if "url=" in link:
                try:
                    b64 = link.split("url=")[-1]
                    link = base64.b64decode(b64).decode('utf-8')
                except: pass
            
            try:
                # Fetch intermediate page
                doc_res = scraper.get(link)
                doc_soup = BeautifulSoup(doc_res.text, 'html.parser')
                # Find source link
                source_a = doc_soup.select_one("a.maxbutton-1, a.maxbutton-5")
                source = source_a.get("href") if source_a else link
                
                resolved = utils.resolve_link(source, scraper, "MoviesMod")
                streams.extend(resolved)
            except Exception as e:
                print("moviesmod extract error", e)
                streams.append({"name": "MoviesMod - " + btn.text.strip(), "url": link})
            
    return json.dumps(streams)
