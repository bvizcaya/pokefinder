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
  "query": "Charizard 1999 Base Set",
  "grade": "10",
  "grader": "PSA",
  "min_price": 2000,
  "max_price": 8000,
  "ntfy_topic": ""
}
```

- `name`: label used in notifications and internal tracking (keep unique).
- `query`: just the card name/set - keep the grade OUT of this field (see
  below for why).
- `grade`: the exact numeric grade, e.g. `"10"`. To match **multiple
  grades** for the same card (e.g. PSA 9 or PSA 10, either one), use a
  list instead: `["9", "10"]`.
- `grader`: the grading company, e.g. `"PSA"`. Also accepts a list, e.g.
  `["PSA", "BGS"]`, if you don't care which company graded it.
- `min_price` / `max_price`: optional. Omit either (or set to `null`) for
  no bound on that side. Useful for filtering out suspiciously cheap
  fakes/reprints as well as capping what you're willing to spend.
- `ntfy_topic`: optional. Leave `""` to use `DEFAULT_NTFY_TOPIC`, or set a
  different topic per card if you want separate notification channels.

### How filtering actually works, end to end

There are two layers, so a listing only ever reaches your phone if it
passes both:

1. **Server-side (eBay's own filters):** the search request sent to eBay
   already includes the price range and the exact Grade/Professional
   Grader aspect filter - eBay itself excludes non-matching listings
   before returning anything.
2. **Client-side (this script, as a safety net):** before sending a
   notification, the script re-checks the returned price against your
   `min_price`/`max_price` one more time. If eBay's price filter ever
   behaves unexpectedly (rare, but it happens with third-party APIs), a
   listing outside your range gets silently skipped - logged as
   `Skipped (outside price range)` in the workflow run - rather than
   alerting you incorrectly.

To confirm it's working as expected on your own: open a completed
GitHub Actions run and check the log output. Each card logs its filters
up front (e.g. `grade=10, grader=PSA, price 2000-8000`), each new match
is logged with its actual price, and anything filtered out is logged
with a reason. That log is your ground truth for exactly what happened
on that run.

### Why grade/grader are separate fields, not part of the search text

eBay's `q` search parameter is a fuzzy keyword match, same as typing into
the search bar - `"Charizard PSA 10"` can still match a PSA 9 or an
ungraded card if enough other words line up. Splitting `grade` and
`grader` into their own fields lets the script use eBay's **aspect
filter** instead, which checks the actual structured "Grade" and
"Professional Grader" fields sellers fill in when listing a graded card.
That's an exact match, not a keyword guess - so a PSA 9 will never show
up when you've set `grade: "10"`.

Leave `grade`/`grader` out (or blank) for a card if you want plain keyword
search instead, e.g. for tracking raw (ungraded) cards.

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
