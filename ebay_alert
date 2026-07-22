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


def search_listings(token, query, max_price=None, limit=20):
    """Search the Browse API for a query, optionally filtered by max price."""
    filters = [f"categoryIds:{{{POKEMON_CARD_CATEGORY_ID}}}"]
    if max_price:
        filters.append(f"price:[..{max_price}],priceCurrency:USD")

    params = {
        "q": query,
        "limit": str(limit),
        "sort": "newlyListed",
        "filter": ",".join(filters),
    }
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
        max_price = card.get("max_price")
        topic = card.get("ntfy_topic") or default_topic

        log(f"Checking: {name}")
        seen_ids = set(seen.get(name, []))

        listings = search_listings(token, query, max_price)
        time.sleep(0.3)  # be polite between calls

        new_ids = []
        for item in listings:
            item_id = item.get("itemId")
            if not item_id or item_id in seen_ids:
                continue

            new_ids.append(item_id)
            title = item.get("title", name)
            price = item.get("price", {}).get("value", "?")
            currency = item.get("price", {}).get("currency", "")
            listing_url = item.get("itemWebUrl", "")

            log(f"  + New listing: {title} - {price} {currency}")
            send_ntfy(
                topic,
                title=f"eBay: {name}",
                message=f"{title}\n{price} {currency}",
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
