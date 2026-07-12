import sys
sys.path.append('scrapers')

import bollyflix
import vegamovies
import moviesdrive
import moviesmod
import onlinemovieshindi

query = "Deadpool"

print("--- Testing Bollyflix ---")
try:
    print(bollyflix.get_streams(query))
except Exception as e:
    print(f"Error: {e}")

print("\n--- Testing VegaMovies ---")
try:
    print(vegamovies.get_streams(query))
except Exception as e:
    print(f"Error: {e}")

print("\n--- Testing MoviesDrive ---")
try:
    print(moviesdrive.get_streams(query))
except Exception as e:
    print(f"Error: {e}")

print("\n--- Testing MoviesMod ---")
try:
    print(moviesmod.get_streams(query))
except Exception as e:
    print(f"Error: {e}")

print("\n--- Testing OnlineMoviesHindi ---")
try:
    print(onlinemovieshindi.get_streams(query))
except Exception as e:
    print(f"Error: {e}")
