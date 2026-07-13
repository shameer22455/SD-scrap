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
import re

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
    for btn in movie_soup.select("a.maxbutton-download-links, a.maxbutton-episode-links, a.maxbutton-g-drive, a.maxbutton-af-download, a.maxbutton-3"):
        link = btn.get("href")
        if link and not link.startswith("#") and not link.startswith("/"):
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
                
                # If it's a movie page, it has maxbutton-1
                source_a = doc_soup.select_one("a.maxbutton-1, a.maxbutton-5")
                if source_a:
                    source = source_a.get("href")
                    resolved = utils.resolve_link(source, scraper, "MoviesMod")
                    streams.extend(resolved)
                else:
                    # It might be an episode list page (episodes.modpro.blog)
                    # Instead of relying on fragile h3 a, just grab all valid looking links
                    found_episodes = False
                    for a_tag in doc_soup.select("a"):
                        ep_url = a_tag.get("href")
                        if ep_url and any(x in ep_url for x in ["vcloud", "hubcloud", "driveleech", "driveseed", "url="]):
                            # Resolve the episode link
                            resolved = utils.resolve_link(ep_url, scraper, "MoviesMod")
                            # Try to get episode name from the tag text or its parent
                            ep_name = a_tag.text.strip()
                            if not ep_name or len(ep_name) < 2:
                                ep_name = a_tag.parent.text.strip()
                            if not ep_name:
                                ep_name = btn.text.strip()
                                
                            for r in resolved:
                                r["name"] = f"MoviesMod - {ep_name}"
                            streams.extend(resolved)
                            if resolved:
                                found_episodes = True
                                
                    if not found_episodes:
                        # Only fallback if it looks like a direct playable link, otherwise skip to avoid breaking the player
                        if any(x in link for x in [".mp4", ".mkv", "vcloud", "hubcloud", "driveseed", "driveleech", "gdflix"]):
                            streams.append({"name": "MoviesMod - " + btn.text.strip(), "url": link})
            except Exception as e:
                print("moviesmod extract error", e)
                if any(x in link for x in [".mp4", ".mkv", "vcloud", "hubcloud", "driveseed", "driveleech", "gdflix"]):
                    streams.append({"name": "MoviesMod - " + btn.text.strip(), "url": link})
            
    return json.dumps(streams)

def get_episode_streams(query, season, episode):
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
    
    buttons = movie_soup.select("a.maxbutton-download-links, a.maxbutton-episode-links, a.maxbutton-g-drive, a.maxbutton-af-download, a.maxbutton-3")
    for btn in buttons:
        btn_text = btn.parent.text.strip().lower()
        if not btn_text:
            btn_text = btn.text.strip().lower()
            
        # Optional: check season in btn_text, but btn_text might just say "Download 720p" and season is above it.
        # We will check season just in case, but rely heavily on episode checking on the next page.
        link = btn.get("href")
        if link and not link.startswith("#") and not link.startswith("/"):
            if "url=" in link:
                try:
                    b64 = link.split("url=")[-1]
                    link = base64.b64decode(b64).decode('utf-8')
                except: pass
            
            try:
                doc_res = scraper.get(link)
                doc_soup = BeautifulSoup(doc_res.text, 'html.parser')
                
                # We are looking for episodes.
                found_episodes = False
                for a_tag in doc_soup.select("a"):
                    ep_url = a_tag.get("href")
                    if ep_url and any(x in ep_url for x in ["vcloud", "hubcloud", "driveleech", "driveseed", "url="]):
                        ep_name = a_tag.text.strip()
                        if not ep_name or len(ep_name) < 2:
                            ep_name = a_tag.parent.text.strip()
                            
                        # Try to find episode number in ep_name
                        ep_match = re.search(r'(?:episode|ep|e)\s*0?(\d+)', ep_name, re.IGNORECASE)
                        if ep_match:
                            ep_num = int(ep_match.group(1))
                            if ep_num != episode:
                                continue # Skip this episode since it doesn't match!
                                
                        resolved = utils.resolve_link(ep_url, scraper, "MoviesMod")
                        for r in resolved:
                            r["name"] = f"MoviesMod - {ep_name}"
                        streams.extend(resolved)
                        if resolved:
                            found_episodes = True
                            
                # If we couldn't find distinct episodes, it might be a batch link (like a zip for the season)
                if not found_episodes and any(x in link for x in [".mp4", ".mkv", "vcloud", "hubcloud", "driveseed", "driveleech", "gdflix"]):
                    # Before adding a batch link, maybe check if it matches season?
                    streams.append({"name": "MoviesMod - Season " + str(season) + " " + btn.text.strip(), "url": link})
            except Exception as e:
                print("moviesmod extract error", e)
                
    return json.dumps(streams)
