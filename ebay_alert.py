"""
Polls eBay's Browse API for specific graded Pokemon card listings and
sends a push notification (via ntfy.sh) whenever a NEW matching listing
appears that it hasn't alerted on before.

Designed to be run on a schedule (e.g. every 5 minutes via GitHub Actions).
State (which listing IDs have already been alerted on) is kept in seen.json
so the same listing doesn't trigger a duplicate notification.

Required environment variables (set these as GitHub Actions secrets):
  EBAY_CLIENT_ID       - your eBay App ID / Client ID
  EBAY_CLIENT_SECRET   - your eBay Cert ID / Client Secret
  EBAY_ENV             - "PRODUCTION" or "SANDBOX" (default: PRODUCTION)
  DEFAULT_NTFY_TOPIC   - fallback ntfy.sh topic if a card's config doesn't
                         specify its own ntfy_topic
"""

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

CONFIG_PATH = os.environ.get("CONFIG_PATH", "config.json")
SEEN_PATH = os.environ.get("SEEN_PATH", "seen.json")
EBAY_ENV = os.environ.get("EBAY_ENV", "PRODUCTION").upper()

if EBAY_ENV == "SANDBOX":
    TOKEN_URL = "https://api.sandbox.ebay.com/identity/v1/oauth2/token"
    SEARCH_URL = "https://api.sandbox.ebay.com/buy/browse/v1/item_summary/search"
else:
    TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
    SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"

# eBay category ID for "Pokemon Individual Cards" - narrows results and
# cuts down on false positives (e.g. plush toys, other TCGs).
POKEMON_CARD_CATEGORY_ID = "183454"


def log(msg):
    print(msg, flush=True)


def get_app_token(client_id, client_secret):
    """Client-credentials OAuth flow -> application access token."""
    creds = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    body = "grant_type=client_credentials&scope=https://api.ebay.com/oauth/api_scope"
    req = urllib.request.Request(
        TOKEN_URL,
        data=body.encode(),
        headers={
            "Authorization": f"Basic {creds}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        data = json.load(resp)
    return data["access_token"]


def _as_list(value):
    """Normalize a config field that may be a single value or a list."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def search_listings(token, query, min_price=None, max_price=None, grade=None, grader=None, limit=20):
    """Search the Browse API for a query, optionally filtered by a min/max
    price range and by exact Grade / Professional Grader item aspects.

    grade/grader can each be a single value ("10") or a list of values
    (["9", "10"]) to match any one of several grades/graders in one search.

    Using aspect_filter (instead of stuffing "PSA 10" into the keyword query)
    means only listings eBay has actually tagged with that exact grade and
    grading company come back - not just anything with matching words in
    the title.
    """
    filters = [f"categoryIds:{{{POKEMON_CARD_CATEGORY_ID}}}"]
    if min_price or max_price:
        low = str(min_price) if min_price else ""
        high = str(max_price) if max_price else ""
        filters.append(f"price:[{low}..{high}],priceCurrency:USD")

    params = {
        "q": query,
        "limit": str(limit),
        "sort": "newlyListed",
        "filter": ",".join(filters),
    }

    # aspect_filter is its own query param, format:
    #   categoryId:<id>,AspectName:{value1|value2}|AspectName2:{value}
    grades = _as_list(grade)
    graders = _as_list(grader)

    aspects = []
    if grades:
        aspects.append(f"Grade:{{{'|'.join(grades)}}}")
    if graders:
        aspects.append(f"Professional Grader:{{{'|'.join(graders)}}}")
    if aspects:
        params["aspect_filter"] = f"categoryId:{POKEMON_CARD_CATEGORY_ID}," + "|".join(aspects)

    query_string = "&".join(
        f"{k}={urllib.request.quote(v)}" for k, v in params.items()
    )
    url = f"{SEARCH_URL}?{query_string}"

    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        log(f"  ! Search failed ({e.code}): {e.read().decode()[:300]}")
        return []

    return data.get("itemSummaries", [])


def send_ntfy(topic, title, message, url=None):
    if not topic:
        log("  ! No ntfy topic configured - skipping notification")
        return
    headers = {"Title": title}
    if url:
        headers["Click"] = url
    req = urllib.request.Request(
        f"https://ntfy.sh/{topic}",
        data=message.encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        urllib.request.urlopen(req)
    except urllib.error.URLError as e:
        log(f"  ! ntfy send failed: {e}")


def load_json(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def main():
    client_id = os.environ.get("EBAY_CLIENT_ID")
    client_secret = os.environ.get("EBAY_CLIENT_SECRET")
    default_topic = os.environ.get("DEFAULT_NTFY_TOPIC", "")

    if not client_id or not client_secret:
        log("Missing EBAY_CLIENT_ID / EBAY_CLIENT_SECRET environment variables")
        sys.exit(1)

    config = load_json(CONFIG_PATH, [])
    if not config:
        log(f"No cards found in {CONFIG_PATH}")
        sys.exit(0)

    seen = load_json(SEEN_PATH, {})

    log(f"Getting eBay app token ({EBAY_ENV})...")
    token = get_app_token(client_id, client_secret)

    any_new = False

    for card in config:
        name = card["name"]
        query = card["query"]
        min_price = card.get("min_price")
        max_price = card.get("max_price")
        grade = card.get("grade")
        grader = card.get("grader")
        topic = card.get("ntfy_topic") or default_topic

        grade_display = "/".join(_as_list(grade)) or "any"
        grader_display = "/".join(_as_list(grader)) or "any"
        log(f"Checking: {name} (grade={grade_display}, grader={grader_display}, "
            f"price {min_price or 0}-{max_price or 'inf'})")
        seen_ids = set(seen.get(name, []))

        listings = search_listings(token, query, min_price, max_price, grade, grader)
        time.sleep(0.3)  # be polite between calls

        new_ids = []
        for item in listings:
            item_id = item.get("itemId")
            if not item_id or item_id in seen_ids:
                continue

            new_ids.append(item_id)
            title = item.get("title", name)
            price_raw = item.get("price", {}).get("value")
            currency = item.get("price", {}).get("currency", "")
            listing_url = item.get("itemWebUrl", "")

            # Client-side price double-check. eBay's server-side price filter
            # is generally reliable, but this guarantees a listing is never
            # alerted on unless it actually satisfies both bounds - it's the
            # last checkpoint before a notification goes out.
            try:
                price_val = float(price_raw)
            except (TypeError, ValueError):
                price_val = None

            price_ok = True
            if price_val is not None:
                if min_price and price_val < float(min_price):
                    price_ok = False
                if max_price and price_val > float(max_price):
                    price_ok = False

            if not price_ok:
                log(f"  - Skipped (outside price range): {title} - "
                    f"{price_raw} {currency}")
                continue

            log(f"  + New listing: {title} - {price_raw} {currency}")
            send_ntfy(
                topic,
                title=f"eBay: {name}",
                message=f"{title}\n{price_raw} {currency}",
                url=listing_url,
            )
            any_new = True

        seen_ids.update(new_ids)
        # keep the seen set from growing forever - cap to most recent 300 IDs
        seen[name] = list(seen_ids)[-300:]

    save_json(SEEN_PATH, seen)
    log("Done. New listings found: " + ("yes" if any_new else "no"))


if __name__ == "__main__":
    main()
