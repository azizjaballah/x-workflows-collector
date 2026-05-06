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
5. Runs the collector
6. Uploads the JSON result as an artifact

This project currently focuses on collection only. Postgres insertion can be added later as a separate step or downstream workflow.
