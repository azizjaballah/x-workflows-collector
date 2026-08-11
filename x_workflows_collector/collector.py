from __future__ import annotations

import json
import re
import shutil
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

STATUS_RE = re.compile(r"^/(?P<handle>[A-Za-z0-9_]+)/status/(?P<id>\d+)$")
METRIC_TAIL_RE = re.compile(r"(?:\s+\d[\d.,]*[KMB]?\b){2,}$")


@dataclass
class Post:
    requested_handle: str
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
        requested_handle=normalize_handle(fallback_handle),
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


def extract_text_from_article_data(article_data: dict, handle: str) -> str:
    tweet_text = normalize_whitespace(str(article_data.get("tweet_text") or ""))
    if tweet_text:
        return tweet_text

    raw_text = normalize_whitespace(str(article_data.get("text") or ""))
    text = re.sub(
        rf"^(?:Pinned\s+)?(?:.+?\s+)?@{re.escape(handle)}\s+·\s+",
        "",
        raw_text,
        count=1,
    )
    text = re.sub(r"^(?:[A-Z][a-z]{2,8}\s+\d{1,2}(?:,\s+\d{4})?|[0-9]+[smhdw])\s+", "", text, count=1)
    text = re.sub(r"^(?:Article|Video|Image|Quote)\s+", "", text, count=1)
    text = METRIC_TAIL_RE.sub("", text).strip()
    return text


def extract_icon_url_from_images(images: list[dict]) -> Optional[str]:
    for image in images:
        src = image.get("src")
        if src and "profile_images" in src:
            return str(src)
    return None


def extract_page_icon_url_from_images(images: list[dict], fallback_handle: str) -> Optional[str]:
    normalized_handle = normalize_handle(fallback_handle).lower()
    candidates: list[str] = []

    for image in images:
        src = image.get("src")
        alt = normalize_whitespace(str(image.get("alt") or ""))
        if not src or "profile_images" not in src:
            continue

        alt_handle = alt.replace("@", "").strip().lower()
        if alt_handle == normalized_handle:
            return str(src)

        candidates.append(str(src))

    return candidates[0] if candidates else None


def extract_image_urls_from_images(images: list[dict]) -> list[str]:
    urls: list[str] = []
    for image in images:
        src = image.get("src")
        alt = str(image.get("alt") or "")
        if not src:
            continue
        src = str(src)
        if "profile_images" in src:
            continue
        if "emoji" in src or "abs.twimg.com" in src:
            continue
        if alt == "" and "media" not in src:
            continue
        if src not in urls:
            urls.append(src)
    return urls


def extract_post_from_article_data(article_data: dict, fallback_handle: str) -> Optional[Post]:
    timestamp = article_data.get("datetime")
    if not timestamp:
        return None

    status_path = article_data.get("status_path")
    if not status_path:
        return None

    match = STATUS_RE.match(str(status_path))
    if not match:
        return None

    handle = match.group("handle") or fallback_handle
    post_id = match.group("id")
    images = article_data.get("images")
    if not isinstance(images, list):
        images = []

    return Post(
        requested_handle=normalize_handle(fallback_handle),
        handle=handle,
        post_id=post_id,
        posted_at=str(timestamp),
        url=f"https://x.com{status_path}",
        text=extract_text_from_article_data(article_data, handle),
        icon_url=extract_icon_url_from_images(images),
        card_type=article_data.get("card_type"),
        image_urls=extract_image_urls_from_images(images),
    )


ARTICLE_DATA_SCRIPT = r"""
() => Array.from(document.querySelectorAll("article")).map((article) => {
  const time = article.querySelector("time[datetime]");
  const links = Array.from(article.querySelectorAll("a[href]"));
  const statusPath = links
    .map((link) => link.getAttribute("href"))
    .find((href) => /^\/[A-Za-z0-9_]+\/status\/\d+$/.test(href || ""));
  const tweetText = article.querySelector('[data-testid="tweetText"]');
  const images = Array.from(article.querySelectorAll("img")).map((img) => ({
    src: img.getAttribute("src") || "",
    alt: img.getAttribute("alt") || "",
  }));
  let cardType = null;
  if (article.querySelector('[data-testid="article-cover-image"]')) {
    cardType = "article";
  } else if (article.querySelector('[data-testid="tweetPhoto"]')) {
    cardType = "photo";
  } else if (article.querySelector('[data-testid="videoPlayer"]')) {
    cardType = "video";
  }

  return {
    datetime: time ? time.getAttribute("datetime") : null,
    status_path: statusPath || null,
    tweet_text: tweetText ? tweetText.innerText : "",
    text: article.innerText || "",
    images,
    card_type: cardType,
  };
})
"""


PAGE_IMAGE_DATA_SCRIPT = r"""
() => Array.from(document.querySelectorAll("img")).map((img) => ({
  src: img.getAttribute("src") || "",
  alt: img.getAttribute("alt") || "",
}))
"""


def fetch_latest_post(
    handle: str,
    browser_path: Optional[str],
    timeout_ms: int,
    wait_ms: int,
) -> Post:
    # Scrapling initializes browser fingerprints during import and can fail on
    # hosted runners. Keep it out of the authenticated Playwright path.
    from scrapling import DynamicFetcher

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


def fetch_latest_post_authenticated(
    handle: str,
    browser_path: Optional[str],
    timeout_ms: int,
    wait_ms: int,
    auth_state: str | Path,
) -> Post:
    from playwright.sync_api import sync_playwright

    handle = normalize_handle(handle)
    profile_url = f"https://x.com/{handle}"
    auth_state_path = Path(auth_state)
    if not auth_state_path.exists():
        raise FileNotFoundError(f"auth state file not found: {auth_state_path}")

    with sync_playwright() as playwright:
        launch_kwargs = {"headless": True}
        if browser_path:
            launch_kwargs["executable_path"] = browser_path

        browser = playwright.chromium.launch(**launch_kwargs)
        try:
            context = browser.new_context(storage_state=str(auth_state_path))
            page = context.new_page()
            page.goto(profile_url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_selector("body", timeout=timeout_ms)
            if wait_ms > 0:
                page.wait_for_timeout(wait_ms)

            article_data = page.evaluate(ARTICLE_DATA_SCRIPT)
            page_images = page.evaluate(PAGE_IMAGE_DATA_SCRIPT)
        finally:
            browser.close()

    posts = []
    for article in article_data:
        post = extract_post_from_article_data(article, handle)
        if post is not None:
            posts.append(post)

    if not posts:
        raise RuntimeError(f"No posts found on {profile_url}")

    posts.sort(key=lambda post: parse_iso8601(post.posted_at), reverse=True)
    latest_post = posts[0]
    if latest_post.icon_url is None:
        latest_post.icon_url = extract_page_icon_url_from_images(page_images, handle)
    return latest_post


def save_auth_state(
    auth_state: str | Path,
    browser_path: Optional[str],
    timeout_ms: int,
) -> None:
    from playwright.sync_api import sync_playwright

    auth_state_path = Path(auth_state)
    auth_state_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        launch_kwargs = {"headless": False}
        if browser_path:
            launch_kwargs["executable_path"] = browser_path

        browser = playwright.chromium.launch(**launch_kwargs)
        try:
            context = browser.new_context()
            page = context.new_page()
            page.goto("https://x.com/i/flow/login", wait_until="domcontentloaded", timeout=timeout_ms)
            print("Log in to X in the opened browser window.", file=sys.stderr)
            print("After the account home page loads, return here and press Enter.", file=sys.stderr)
            input()
            context.storage_state(path=str(auth_state_path))
        finally:
            browser.close()


def save_auth_state_from_cdp(
    auth_state: str | Path,
    cdp_url: str,
    timeout_ms: int,
) -> None:
    from playwright.sync_api import sync_playwright

    auth_state_path = Path(auth_state)
    auth_state_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(cdp_url, timeout=timeout_ms)
        try:
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.pages[0] if context.pages else context.new_page()
            page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=timeout_ms)
            print("Confirm X is logged in in the connected browser.", file=sys.stderr)
            print("After the account home page loads, return here and press Enter.", file=sys.stderr)
            input()
            context.storage_state(path=str(auth_state_path))
        finally:
            browser.close()


def collect_latest_posts(
    handles: list[str],
    browser_path: Optional[str],
    timeout_ms: int,
    wait_ms: int,
    auth_state: str | Path | None = None,
) -> dict:
    posts: list[Post] = []
    errors: list[CollectionError] = []

    for handle in handles:
        try:
            if auth_state:
                posts.append(fetch_latest_post_authenticated(handle, browser_path, timeout_ms, wait_ms, auth_state))
            else:
                posts.append(fetch_latest_post(handle, browser_path, timeout_ms, wait_ms))
        except Exception as exc:
            errors.append(CollectionError(handle=handle, error=str(exc)))

    return {
        "source": "x",
        "fetched_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "posts": [asdict(post) for post in posts],
        "errors": [asdict(error) for error in errors],
    }
