# eBay Pokemon Card Alert

Polls eBay's Browse API every ~5 minutes for specific graded Pokemon card
listings and pushes a notification via [ntfy.sh](https://ntfy.sh) when a
new one appears.

## 1. Set up ntfy (for receiving alerts)

1. Install the ntfy app (iOS/Android) or just use the web version at ntfy.sh.
2. Pick a topic name - this is like a "channel." Make it hard to guess since
   anyone who knows the topic name can read your alerts, e.g.
   `pokealert-8f2k1d`.
3. Subscribe to that topic in the app.
4. No account or signup needed.

## 2. Create a GitHub repo

1. Create a new repository on GitHub (private is fine, public gives you
   unlimited free Actions minutes).
2. Upload all the files in this folder to the repo (or `git init` + push).

## 3. Add your eBay credentials as repo secrets

Go to your repo -> Settings -> Secrets and variables -> Actions -> New
repository secret, and add:

| Secret name          | Value                                         |
|-----------------------|-----------------------------------------------|
| `EBAY_CLIENT_ID`      | Your eBay App ID (Client ID)                  |
| `EBAY_CLIENT_SECRET`  | Your eBay Cert ID (Client Secret)             |
| `EBAY_ENV`            | `PRODUCTION` (or `SANDBOX` while testing)     |
| `DEFAULT_NTFY_TOPIC`  | Your ntfy topic name from step 1              |

Note: your Sandbox keys only search fake test data. To search real, live
eBay listings you need a **Production** keyset - go back to
developer.ebay.com -> Application Keys -> create a Production keyset,
and use those values here once ready.

## 4. Edit config.json

List the cards you want to track. Each entry:

```json
{
  "name": "Charizard 1999 Base Set PSA 10",
  "query": "Charizard 1999 Base Set PSA 10",
  "max_price": 8000,
  "ntfy_topic": ""
}
```

- `name`: label used in notifications and internal tracking (keep unique).
- `query`: the actual eBay search text - be as specific as you can.
- `max_price`: optional. Omit or set to `null` for no limit.
- `ntfy_topic`: optional. Leave `""` to use `DEFAULT_NTFY_TOPIC`, or set a
  different topic per card if you want separate notification channels.

You can track up to ~15-17 cards at the 5-minute polling interval without
exceeding eBay's default rate limit of 5,000 Browse API calls/day. If you
add more cards later, slow the schedule down (e.g. `*/10 * * * *`).

## 5. Test it

Go to your repo's Actions tab -> "Check eBay listings" -> "Run workflow"
to trigger it manually and confirm it runs without errors before waiting
for the schedule.

## How it works

- `ebay_alert.py` logs into eBay, searches each configured card, and
  compares results against `seen.json` (listing IDs already alerted on).
- Any new matching listing triggers a push notification with the title,
  price, and a link to the listing.
- The GitHub Actions workflow commits the updated `seen.json` back to the
  repo after each run so state persists between runs.
