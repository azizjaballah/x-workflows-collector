# X Workflows Collector

Scheduled collector for the latest visible public X posts from a fixed set of accounts.

The project is designed for GitHub Actions on a 30-minute schedule and emits JSON that can be pushed into Postgres or consumed by another pipeline.

## Fixed accounts

The current account list lives in [config/accounts.json](./config/accounts.json):

- `DanielMiessler`
- `Mikko`
- `lennyzeltser`
- `anton_chuvakin`
- `k8em0`
- `schneierblog`

## Output shape

Each run writes one JSON document like:

```json
{
  "source": "x",
  "fetched_at": "2026-05-06T08:00:00Z",
  "posts": [
    {
      "handle": "example",
      "post_id": "123",
      "posted_at": "2026-05-06T07:30:00.000Z",
      "url": "https://x.com/example/status/123",
      "text": "Latest visible post text",
      "icon_url": "https://pbs.twimg.com/profile_images/.../avatar_400x400.jpg",
      "card_type": "article",
      "image_urls": [
        "https://pbs.twimg.com/media/example?format=jpg&name=small"
      ]
    }
  ],
  "errors": []
}
```

## Local run

Create or reuse a virtualenv, then install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m playwright install chromium
```

Run the collector:

```bash
python -m x_workflows_collector.cli \
  --accounts-file config/accounts.json \
  --output output/latest_posts.json
```

## Authenticated collection

X may show stale public profile data to unauthenticated browsers. To collect with a logged-in session, create a local Playwright storage-state file once:

```bash
python -m x_workflows_collector.cli \
  --save-auth-state .auth/x-storage-state.json
```

The command opens Chromium. Log in to X, wait until the account home page loads, then return to the terminal and press Enter. The saved state contains cookies and should be treated as a secret; `.auth/` is ignored by git.

### macOS authentication handoff

If Linux desktop rendering is unreliable, create the storage-state file on macOS and upload it directly to the repository secret used by GitHub Actions:

```bash
git clone <your-repo-url>
cd x-workflows-collector
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m playwright install chromium
python -m x_workflows_collector.cli \
  --timeout-ms 120000 \
  --save-auth-state .auth/x-storage-state.json
gh secret set X_AUTH_STATE_JSON < .auth/x-storage-state.json
```

On macOS, omit `--browser-path` unless you specifically want to use a locally installed browser. The default Playwright-managed Chromium is usually the most reliable option.

If X login does not respond inside the Playwright-launched browser, import auth from a normal Microsoft Edge session instead. First fully quit Edge, then start it from Terminal with remote debugging enabled:

```bash
open -na "Microsoft Edge" --args \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/Library/Application Support/Microsoft Edge"
```

In that Edge window, open `https://x.com/home` and confirm you are logged in. In another Terminal tab from the project directory, run:

```bash
source .venv/bin/activate
python -m x_workflows_collector.cli \
  --timeout-ms 120000 \
  --save-auth-state .auth/x-storage-state.json \
  --save-auth-state-from-cdp http://127.0.0.1:9222
gh secret set X_AUTH_STATE_JSON < .auth/x-storage-state.json
```

Run the collector with that saved session:

```bash
python -m x_workflows_collector.cli \
  --accounts-file config/accounts.json \
  --auth-state .auth/x-storage-state.json \
  --output output/latest_posts.json
```

If your machine already has Chromium in a custom path:

```bash
python -m x_workflows_collector.cli \
  --accounts-file config/accounts.json \
  --browser-path /usr/bin/chromium \
  --output output/latest_posts.json
```

## GitHub Actions

The workflow in [.github/workflows/collect-x.yml](./.github/workflows/collect-x.yml) runs every 30 minutes and on manual dispatch. It uses `runs-on: ubuntu-latest`, which is the standard GitHub-hosted runner tier suitable for free Actions usage. It:

1. Checks out the repository
2. Sets up Python
3. Installs dependencies
4. Installs Playwright Chromium
5. Restores authenticated X storage state from the optional `X_AUTH_STATE_JSON` secret
6. Runs the collector
7. Uploads the JSON result as an artifact

To use authenticated collection in GitHub Actions, create the local auth state file, copy its full JSON content into a repository secret named `X_AUTH_STATE_JSON`, and run the workflow. If the secret is absent, the workflow falls back to unauthenticated collection.

This project currently focuses on collection only. Postgres insertion can be added later as a separate step or downstream workflow.
