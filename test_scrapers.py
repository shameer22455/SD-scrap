import sys
sys.path.append('scrapers')

import bollyflix
import vegamovies
import moviesdrive
import moviesmod
import onlinemovieshindi

query = "Mirzapur"
season = 3
episode = 1

print(f"--- Testing Bollyflix for TV Show (S{season} E{episode}) ---")
try:
    print(bollyflix.get_episode_streams(query, season, episode))
except Exception as e:
    print(f"Error: {e}")

print(f"\n--- Testing MoviesMod for TV Show (S{season} E{episode}) ---")
try:
    print(moviesmod.get_episode_streams(query, season, episode))
except Exception as e:
    print(f"Error: {e}")
