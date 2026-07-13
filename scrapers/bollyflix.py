import cloudscraper
from bs4 import BeautifulSoup
import re
import base64
import json
import urllib.parse
import requests
import utils

def get_base_url():
    try:
        urls = requests.get('https://raw.githubusercontent.com/SaurabhKaperwan/Utils/refs/heads/main/urls.json', timeout=5).json()
        return urls.get("bollyflix", "https://bollyflix.at")
    except:
        return "https://bollyflix.at"

def get_streams(query):
    scraper = cloudscraper.create_scraper()
    base_url = get_base_url()
    
    query_encoded = urllib.parse.quote(query)
    search_url = f"{base_url}/search/{query_encoded}/"
    res = scraper.get(search_url)
    soup = BeautifulSoup(res.text, 'html.parser')
    
    first_result = soup.select_one("div.post-cards > article > a")
    if not first_result: return "[]"
        
    movie_url = first_result.get("href")
    movie_res = scraper.get(movie_url)
    movie_soup = BeautifulSoup(movie_res.text, 'html.parser')
    
    streams = []
    buttons = movie_soup.select("a.maxbutton-download-links, a.dl, a.btnn")
    for btn in buttons:
        link = btn.get("href")
        if not link: continue
        name = btn.text.strip() or "Download Link"
        
        if "?id=" in link and "fastdlserver" not in link:
            sid_id = link.split("id=")[-1]
            try:
                sid_res = scraper.get(f"https://web.sidexfee.com/?id={sid_id}")
                match = re.search(r'"link":"([^"]+)"', sid_res.text)
                if match:
                    encoded = match.group(1).replace('\\/', '/')
                    link = base64.b64decode(encoded).decode('utf-8')
            except:
                pass
                
        if "fastdlserver" in link:
            # fastdlserver redirects to the actual link via location header
            r = scraper.get(link, allow_redirects=False)
            loc = r.headers.get("Location")
            if loc: link = loc
            
        resolved = utils.resolve_link(link, scraper, "BollyFlix")
        streams.extend(resolved)
        
    return json.dumps(streams)

def get_episode_streams(query, season, episode):
    scraper = cloudscraper.create_scraper()
    base_url = get_base_url()
    
    query_encoded = urllib.parse.quote(query)
    search_url = f"{base_url}/search/{query_encoded}/"
    res = scraper.get(search_url)
    soup = BeautifulSoup(res.text, 'html.parser')
    
    first_result = soup.select_one("div.post-cards > article > a")
    if not first_result: return "[]"
        
    movie_url = first_result.get("href")
    movie_res = scraper.get(movie_url)
    movie_soup = BeautifulSoup(movie_res.text, 'html.parser')
    
    streams = []
    buttons = movie_soup.select("a.maxbutton-download-links, a.dl, a.btnn")
    for btn in buttons:
        link = btn.get("href")
        if not link: continue
        name = btn.text.strip() or "Download Link"
        
        # Check if name contains episode information
        ep_match = re.search(r'(?:episode|ep|e)\s*0?(\d+)', name, re.IGNORECASE)
        if ep_match:
            ep_num = int(ep_match.group(1))
            if ep_num != episode:
                continue # Skip because this is a different episode
                
        # Also check if it's explicitly a different season
        season_match = re.search(r'(?:season|s)\s*0?(\d+)', name, re.IGNORECASE)
        if season_match:
            season_num = int(season_match.group(1))
            if season_num != season:
                continue
        
        if "?id=" in link and "fastdlserver" not in link:
            sid_id = link.split("id=")[-1]
            try:
                sid_res = scraper.get(f"https://web.sidexfee.com/?id={sid_id}")
                match = re.search(r'"link":"([^"]+)"', sid_res.text)
                if match:
                    encoded = match.group(1).replace('\\/', '/')
                    link = base64.b64decode(encoded).decode('utf-8')
            except:
                pass
                
        if "fastdlserver" in link:
            r = scraper.get(link, allow_redirects=False)
            loc = r.headers.get("Location")
            if loc: link = loc
            
        resolved = utils.resolve_link(link, scraper, "BollyFlix")
        for r in resolved:
            r["name"] = f"BollyFlix - Season {season} Ep {episode} - {name}"
        streams.extend(resolved)
        
    return json.dumps(streams)
