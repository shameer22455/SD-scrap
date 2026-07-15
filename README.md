# SDM Plugins — Official Repository

This is the official plugin repository for the **SDM app**.

## What is this?

SDM uses a CloudStream-like plugin architecture. Each plugin is a Python (`.py`) file that the app downloads at runtime and executes via [Chaquopy](https://chaquo.com/chaquopy/).

## Plugin Contract

Every plugin **must** implement these 5 functions:

| Function | Returns | Description |
|----------|---------|-------------|
| `get_name()` | `str` | Display name of the plugin |
| `get_supported_types()` | `list[str]` | e.g. `["movie", "tv"]` |
| `get_main_page()` | `SdmHomePageResponse` | Home/browse page content |
| `search(query)` | `list[SdmSearchResponse]` | Search results |
| `load_details(url)` | `SdmLoadResponse` | Movie/show details + episodes |
| `load_links(data_url)` | `list[SdmStreamLink]` | Playable stream links |

## ⚠️ SDK Rule

Plugins **must only import from `sdm_api`**. Never import `requests`, `bs4`, or any third-party lib directly. The `sdm_api` module is bundled with the app and provides a safe, versioned interface.

```python
# ✅ Correct
from sdm_api import http, logger, movie_response, stream_link

# ❌ Wrong — will break or behave unpredictably
import requests
from bs4 import BeautifulSoup
```

## Available Plugins

| Name | File | Types | Status |
|------|------|-------|--------|
| UHD Movies | `plugins/uhdmovies.py` | movie | ✅ Active |
| Sample (template) | `plugins/sample.py` | all | 🔧 Dev |

## Creating a Plugin

1. Copy `plugins/sample.py`
2. Rename it to your plugin name (e.g. `vidsrc.py`)
3. Implement all 5 contract functions
4. Only import from `sdm_api`
5. Add an entry to `plugins.json`
6. Submit a pull request

## `plugins.json` Format

```json
{
  "name": "SDM Official Plugins",
  "manifestVersion": 1,
  "plugins": [
    {
      "name": "Plugin Display Name",
      "internalName": "pluginfilename",
      "description": "What it scrapes",
      "version": 1,
      "author": "YourName",
      "supportedTypes": ["movie"],
      "language": "en",
      "status": 1,
      "fileUrl": "https://raw.githubusercontent.com/USER/SDM_Plugins/main/plugins/pluginfilename.py",
      "fileHash": null
    }
  ]
}
```
