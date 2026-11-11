import ipaddress
import os
import socket
from typing import Optional
from urllib.parse import urljoin, urlparse
 
import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, Header, HTTPException
 
app = FastAPI(
    title="Link Preview API",
    description="Send a web page URL and get back its title, description, preview image, favicon, and site name as JSON. Useful for building link cards in chat apps, feeds, and bookmark tools.",
    version="1.0.0",
)
 
# Some sites block requests that don't look like a browser.
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; LinkPreviewBot/1.0)"}
 
# The secret password that only RapidAPI knows. It comes from Render's
# Environment settings, never from the code itself.
PROXY_SECRET = os.environ.get("RAPIDAPI_PROXY_SECRET")
 
 
def is_safe_url(url: str) -> bool:
    """Block localhost and private network addresses so nobody can use
    your API to poke around inside your server's network."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    try:
        ip = ipaddress.ip_address(socket.gethostbyname(parsed.hostname))
    except (socket.gaierror, ValueError):
        return False
    return not (ip.is_private or ip.is_loopback or ip.is_link_local)
 
 
def get_meta(soup, *names):
    """Look for a <meta> tag by property (og:title) or name (description)."""
    for name in names:
        tag = soup.find("meta", property=name) or soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return tag["content"].strip()
    return None
 
 
@app.get("/")
def home():
    return {"message": "Link Preview API. Try /preview?url=https://example.com"}


@app.get("/secret-check")
def secret_check():
    return {"secret_loaded": bool(PROXY_SECRET)}
 
 
@app.get("/preview")
def preview(url: str, x_rapidapi_proxy_secret: Optional[str] = Header(default=None)):
    """Get a preview of any public web page. Example: /preview?url=https://github.com"""
    # If a secret is set on Render, only requests coming through RapidAPI get in.
    if PROXY_SECRET and x_rapidapi_proxy_secret != PROXY_SECRET:
        raise HTTPException(status_code=403, detail="Use this API through RapidAPI.")
 
    if not is_safe_url(url):
        raise HTTPException(status_code=400, detail="Send a valid public http(s) URL.")
 
    try:
        response = requests.get(url, headers=HEADERS, timeout=5)
        response.raise_for_status()
    except requests.RequestException:
        raise HTTPException(status_code=502, detail="Could not fetch that page.")
 
    soup = BeautifulSoup(response.text, "html.parser")
 
    title = get_meta(soup, "og:title", "twitter:title")
    if not title and soup.title and soup.title.string:
        title = soup.title.string.strip()
 
    image = get_meta(soup, "og:image", "twitter:image")
    if image:
        image = urljoin(url, image)  # turns "/img.png" into a full link
 
    icon_tag = soup.find("link", rel=lambda r: r and "icon" in r)
    favicon = urljoin(url, icon_tag["href"]) if icon_tag and icon_tag.get("href") else urljoin(url, "/favicon.ico")
 
    return {
        "url": url,
        "title": title,
        "description": get_meta(soup, "og:description", "description", "twitter:description"),
        "image": image,
        "site_name": get_meta(soup, "og:site_name") or urlparse(url).hostname,
        "favicon": favicon,
    }
 
