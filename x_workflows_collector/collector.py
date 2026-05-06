from __future__ import annotations

import json
import re
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from scrapling import DynamicFetcher


STATUS_RE = re.compile(r"^/(?P<handle>[A-Za-z0-9_]+)/status/(?P<id>\d+)$")
METRIC_TAIL_RE = re.compile(r"(?:\s+\d[\d.,]*[KMB]?\b){2,}$")


@dataclass
class Post:
    handle: str
    post_id: str
    posted_at: str
    url: str
    text: str
    icon_url: Optional[str]
    card_type: Optional[str]
    image_urls: list[str]


@dataclass
class CollectionError:
    handle: str
    error: str


def parse_iso8601(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def normalize_handle(handle: str) -> str:
    handle = handle.strip()
    if handle.startswith("@"):
        handle = handle[1:]
    return handle


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def default_browser_path() -> Optional[str]:
    return shutil.which("chromium") or shutil.which("chromium-browser")


def load_accounts(accounts_file: str | Path) -> list[str]:
    data = json.loads(Path(accounts_file).read_text(encoding="utf-8"))
    accounts = data.get("accounts", [])
    if not isinstance(accounts, list) or not accounts:
        raise ValueError("accounts file must contain a non-empty 'accounts' list")
    return [normalize_handle(str(account)) for account in accounts]


def extract_post_from_article(article, fallback_handle: str) -> Optional[Post]:
    timestamps = [node.attrib.get("datetime") for node in article.css("time") if node.attrib.get("datetime")]
    if not timestamps:
        return None

    status_path = None
    handle = fallback_handle
    post_id = None
    for link in article.css("a[href]"):
        href = link.attrib.get("href")
        if not href:
            continue
        match = STATUS_RE.match(href)
        if not match:
            continue
        status_path = href
        handle = match.group("handle")
        post_id = match.group("id")
        break

    if not status_path or not post_id:
        return None

    text = extract_text_from_article(article, handle)
    icon_url = extract_icon_url(article)
    card_type = detect_card_type(article)
    image_urls = extract_image_urls(article)

    return Post(
        handle=handle,
        post_id=post_id,
        posted_at=timestamps[0],
        url=f"https://x.com{status_path}",
        text=text,
        icon_url=icon_url,
        card_type=card_type,
        image_urls=image_urls,
    )


def extract_text_from_article(article, handle: str) -> str:
    text_parts = []
    for node in article.css('[data-testid="tweetText"] *::text'):
        part = node.get().strip()
        if part:
            text_parts.append(part)

    if text_parts:
        return " ".join(text_parts)

    raw_text = " ".join(node.get().strip() for node in article.css("*::text") if node.get().strip())
    text = normalize_whitespace(raw_text)
    text = re.sub(
        rf"^(?:Pinned\s+)?(?:.+?\s+)?@{re.escape(handle)}\s+·\s+",
        "",
        text,
        count=1,
    )
    text = re.sub(r"^(?:[A-Z][a-z]{2,8}\s+\d{1,2}(?:,\s+\d{4})?|[0-9]+[smhdw])\s+", "", text, count=1)
    text = re.sub(r"^(?:Article|Video|Image|Quote)\s+", "", text, count=1)
    text = METRIC_TAIL_RE.sub("", text).strip()
    return text


def detect_card_type(article) -> Optional[str]:
    if article.css('[data-testid="article-cover-image"]'):
        return "article"
    if article.css('[data-testid="tweetPhoto"]'):
        return "photo"
    if article.css('[data-testid="videoPlayer"]'):
        return "video"
    return None


def extract_icon_url(article) -> Optional[str]:
    for img in article.css("img"):
        src = img.attrib.get("src")
        if src and "profile_images" in src:
            return src
    return None


def extract_page_icon_url(response, fallback_handle: str) -> Optional[str]:
    normalized_handle = normalize_handle(fallback_handle).lower()
    candidates: list[str] = []

    for img in response.css("img"):
        src = img.attrib.get("src")
        alt = normalize_whitespace(img.attrib.get("alt", ""))
        if not src or "profile_images" not in src:
            continue

        alt_handle = alt.replace("@", "").strip().lower()
        if alt_handle == normalized_handle:
            return src

        candidates.append(src)

    return candidates[0] if candidates else None


def extract_image_urls(article) -> list[str]:
    urls: list[str] = []
    for img in article.css("img"):
        src = img.attrib.get("src")
        alt = img.attrib.get("alt", "")
        if not src:
            continue
        if "profile_images" in src:
            continue
        if "emoji" in src or "abs.twimg.com" in src:
            continue
        if alt == "" and "media" not in src:
            continue
        if src not in urls:
            urls.append(src)
    return urls


def fetch_latest_post(
    handle: str,
    browser_path: Optional[str],
    timeout_ms: int,
    wait_ms: int,
) -> Post:
    handle = normalize_handle(handle)
    profile_url = f"https://x.com/{handle}"
    fetch_kwargs = {
        "headless": True,
        "timeout": timeout_ms,
        "wait": wait_ms,
        "load_dom": True,
        "network_idle": False,
        "wait_selector": "body",
    }
    if browser_path:
        fetch_kwargs["executable_path"] = browser_path

    response = DynamicFetcher.fetch(profile_url, **fetch_kwargs)

    posts = []
    for article in response.css("article"):
        post = extract_post_from_article(article, handle)
        if post is not None:
            posts.append(post)

    if not posts:
        raise RuntimeError(f"No posts found on {profile_url}")

    posts.sort(key=lambda post: parse_iso8601(post.posted_at), reverse=True)
    latest_post = posts[0]
    if latest_post.icon_url is None:
        latest_post.icon_url = extract_page_icon_url(response, handle)
    return latest_post


def collect_latest_posts(
    handles: list[str],
    browser_path: Optional[str],
    timeout_ms: int,
    wait_ms: int,
) -> dict:
    posts: list[Post] = []
    errors: list[CollectionError] = []

    for handle in handles:
        try:
            posts.append(fetch_latest_post(handle, browser_path, timeout_ms, wait_ms))
        except Exception as exc:
            errors.append(CollectionError(handle=handle, error=str(exc)))

    return {
        "source": "x",
        "fetched_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "posts": [asdict(post) for post in posts],
        "errors": [asdict(error) for error in errors],
    }
