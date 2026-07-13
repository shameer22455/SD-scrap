import base64
import json
import re
from urllib.parse import urlparse

def get_base_url(url):
    try:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"
    except:
        return url

def fix_url(url, domain):
    if url.startswith("http"):
        return url
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return domain + url
    return f"{domain}/{url}"

def get_latest_base_url(scraper, base_url, source):
    try:
        urls = scraper.get('https://raw.githubusercontent.com/SaurabhKaperwan/Utils/refs/heads/main/urls.json', timeout=5).json()
        return urls.get(source, base_url)
    except:
        return base_url

def bypass_unblocked(url, scraper):
    host = get_base_url(url)
    try:
        res = scraper.get(url)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(res.text, 'html.parser')
        form = soup.select_one("form#landing")
        if not form: return None
        form_url = form.get("action")
        inputs = soup.select("form#landing input")
        form_data = {i.get("name"): i.get("value") for i in inputs if i.get("name")}

        res = scraper.post(form_url, data=form_data)
        soup = BeautifulSoup(res.text, 'html.parser')
        form = soup.select_one("form#landing")
        if form:
            form_url = form.get("action")
            inputs = soup.select("form#landing input")
            form_data = {i.get("name"): i.get("value") for i in inputs if i.get("name")}
            res = scraper.post(form_url, data=form_data)
            soup = BeautifulSoup(res.text, 'html.parser')

        sk_token = None
        script = soup.find("script", string=re.compile(r"\?go="))
        if script:
            match = re.search(r"\?go=([^\"]+)", script.text)
            if match: sk_token = match.group(1)
        
        if not sk_token: return None

        cookies = {sk_token: form_data.get("_wp_http2", "")}
        res2 = scraper.get(f"{host}?go={sk_token}", cookies=cookies)
        soup2 = BeautifulSoup(res2.text, 'html.parser')
        meta = soup2.select_one("meta[http-equiv=refresh]")
        if not meta: return None
        drive_url = meta.get("content", "").split("url=")[-1]
        
        if drive_url:
            res3 = scraper.get(drive_url)
            match = re.search(r"replace\(\"([^\"]+)\"\)", res3.text)
            if match:
                path = match.group(1)
                if path == "/404": return None
                return fix_url(path, get_base_url(drive_url))
        return None
    except Exception as e:
        print("bypass error", e)
        return None

def resolve_vcloud(url, scraper):
    results = []
    try:
        base_url = get_base_url(url)
        source = "hubcloud" if "hubcloud" in url else "vcloud"
        latest_base_url = get_latest_base_url(scraper, base_url, source)
        new_url = url.replace(base_url, latest_base_url)
        base_url = latest_base_url

        from bs4 import BeautifulSoup
        res = scraper.get(new_url)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        link = ""
        if "/video/" in new_url:
            a = soup.select_one("div.vd > center > a")
            if a: link = a.get("href")
        else:
            script = soup.find("script", string=re.compile(r"url"))
            if script:
                if "vcloud" in new_url:
                    match = re.search(r"atob\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", script.text)
                    if match:
                        link = base64.b64decode(base64.b64decode(match.group(1))).decode('utf-8')
                else:
                    match = re.search(r"var url = '([^']*)'", script.text)
                    if match: link = match.group(1)
        
        if not link: return []
        if not link.startswith("https://"): link = base_url + link
        
        res2 = scraper.get(link)
        soup2 = BeautifulSoup(res2.text, 'html.parser')
        header = soup2.select_one("div.card-header")
        header_text = header.text if header else "Download"

        for btn in soup2.select("h2 a.btn"):
            href = btn.get("href")
            text = btn.text
            if not href: continue
            if "BuzzServer" in text:
                r = scraper.get(f"{href}/download", headers={"Referer": href}, allow_redirects=False)
                hx = r.headers.get("hx-redirect")
                if hx: results.append({"name": f"[BuzzServer] {header_text}", "url": get_base_url(href) + hx})
            elif "Server : 10Gbps" in text:
                r = scraper.head(href, allow_redirects=False)
                loc = r.headers.get("Location")
                if loc:
                    if "link=" in loc: loc = loc.split("link=")[-1]
                    results.append({"name": f"[10Gbps] {header_text}", "url": loc})
            elif "pixeldra" in href:
                match = re.search(r"var\s+pxl\s*=\s*[\"']([^\"']+)[\"']", res2.text)
                if match:
                    px = match.group(1)
                    bu = get_base_url(px)
                    final = px if "download" in px.lower() else f"{bu}/api/file/{px.split('/')[-1]}?download"
                    results.append({"name": f"[Pixeldrain] {header_text}", "url": final})
            elif "Gofile" in text:
                results.append({"name": f"[GoFile] {header_text}", "url": href})
            elif "FSL" in text or "Mega" in text or "Download File" in text:
                results.append({"name": f"[{text.strip()}] {header_text}", "url": href})

    except Exception as e:
        print("vcloud error", e)
    return results

def resolve_driveleech(url, scraper):
    results = []
    try:
        base_url = get_base_url(url)
        res = scraper.get(url)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(res.text, 'html.parser')

        name_tag = soup.find(lambda tag: tag.name == "li" and "Name :" in tag.text)
        size_tag = soup.find(lambda tag: tag.name == "li" and "Size :" in tag.text)
        name = name_tag.text.split("Name : ")[-1] if name_tag else "Download"
        if size_tag: name += f" [{size_tag.text.split('Size : ')[-1]}]"

        for a in soup.select("div.text-center > a"):
            text = a.text
            href = a.get("href")
            if not href: continue
            if "Cloud Download" in text:
                results.append({"name": f"[Cloud] {name}", "url": href})
            elif "Instant Download" in text:
                r = scraper.get(href, allow_redirects=False)
                loc = r.headers.get("Location")
                if loc and "?url=" in loc:
                    results.append({"name": f"[Instant] {name}", "url": loc.split("?url=")[-1]})
            elif "Resume Worker Bot" in text:
                r = scraper.get(href)
                s = BeautifulSoup(r.text, 'html.parser')
                ssid = r.cookies.get("PHPSESSID", "")
                match_token = re.search(r"formData\.append\('token', '([a-f0-9]+)'\)", r.text)
                match_id = re.search(r"fetch\('/download\?id=([a-zA-Z0-9/+]+)'", r.text)
                if match_token and match_id:
                    token = match_token.group(1)
                    did = match_id.group(1)
                    bu = href.split("/download")[0]
                    r2 = scraper.post(f"{bu}/download?id={did}", data={"token": token}, headers={"Referer": href, "Origin": bu}, cookies={"PHPSESSID": ssid})
                    try:
                        data = r2.json()
                        if "url" in data: results.append({"name": f"[ResumeBot] {name}", "url": data["url"]})
                    except: pass
            elif "Direct Links" in text:
                bl = base_url + href
                for t in ["1", "2"]:
                    r = scraper.get(f"{bl}?type={t}")
                    s = BeautifulSoup(r.text, 'html.parser')
                    for btn in s.select("a.btn-success"):
                        results.append({"name": f"[CF {t}] {name}", "url": btn.get("href")})
            elif "Resume Cloud" in text:
                r = scraper.get(base_url + href)
                s = BeautifulSoup(r.text, 'html.parser')
                btn = s.select_one("a.btn-success")
                if btn: results.append({"name": f"[ResumeCloud] {name}", "url": btn.get("href")})
            elif "gofile" in text.lower():
                results.append({"name": f"[GoFile] {name}", "url": href})
    except Exception as e:
        print("driveleech error", e)
    return results

def resolve_gdflix(url, scraper):
    results = []
    try:
        base_url = get_base_url(url)
        latest_base_url = get_latest_base_url(scraper, base_url, "gdflix")
        new_url = url.replace(base_url, latest_base_url)
        base_url = latest_base_url

        from bs4 import BeautifulSoup
        res = scraper.get(new_url)
        soup = BeautifulSoup(res.text, 'html.parser')

        name = "Download"
        name_tag = soup.find(lambda tag: tag.name == "li" and "Name :" in tag.text)
        size_tag = soup.find(lambda tag: tag.name == "li" and "Size :" in tag.text)
        if name_tag: name = name_tag.text.split("Name : ")[-1]
        if size_tag: name += f" [{size_tag.text.split('Size : ')[-1]}]"

        for container in soup.select("div.text-center"):
            a = container.select_one("a")
            if not a: continue
            text = a.text
            href = container.get("href", a.get("href"))
            if not href: continue
            
            if "FSL V2" in text or "DIRECT DL" in text or "DIRECT SERVER" in text or "CLOUD DOWNLOAD [R2]" in text:
                results.append({"name": f"[{text.strip()}] {name}", "url": href})
            elif "GD Index" in text:
                cf_link = base_url + href
                for t in ["1", "2"]:
                    r = scraper.get(f"{cf_link}?type={t}")
                    s = BeautifulSoup(r.text, 'html.parser')
                    for btn in s.select("a.btn-success"):
                        results.append({"name": f"[CF] {name}", "url": btn.get("href")})
            elif "FAST CLOUD" in text:
                r = scraper.get(base_url + href)
                s = BeautifulSoup(r.text, 'html.parser')
                btn = s.select_one("div.card-body a")
                if btn: results.append({"name": f"[FAST CLOUD] {name}", "url": btn.get("href")})
            elif "pixeldra" in href.lower():
                bu = get_base_url(href)
                final = href if "download" in href.lower() else f"{bu}/api/file/{href.split('/')[-1]}?download"
                results.append({"name": f"[Pixeldrain] {name}", "url": final})
            elif "Instant DL" in text:
                r = scraper.get(href, allow_redirects=False)
                loc = r.headers.get("Location")
                if loc and "url=" in loc:
                    results.append({"name": f"[Instant DL] {name}", "url": loc.split("url=")[-1]})
            elif "GoFile" in text:
                r = scraper.get(href)
                s = BeautifulSoup(r.text, 'html.parser')
                for ga in s.select(".row .row a"):
                    ghref = ga.get("href", "")
                    if "gofile" in ghref:
                        results.append({"name": f"[GoFile] {name}", "url": ghref})
    except Exception as e:
        print("gdflix error", e)
    return results

def resolve_link(url, scraper, source_name="MoviesMod"):
    if "url=" in url:
        try:
            b64 = url.split("url=")[-1]
            url = base64.b64decode(b64).decode('utf-8')
        except: pass

    if "unblocked" in url:
        bypassed = bypass_unblocked(url, scraper)
        if bypassed: url = bypassed

    if "driveseed" in url or "driveleech" in url:
        return resolve_driveleech(url, scraper)
    elif "vcloud" in url or "hubcloud" in url:
        return resolve_vcloud(url, scraper)
    elif "gdflix" in url:
        return resolve_gdflix(url, scraper)
    else:
        return [{"name": f"[{source_name}] Download", "url": url}]
