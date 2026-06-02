from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .collector import (
    collect_latest_posts,
    default_browser_path,
    load_accounts,
    save_auth_state,
    save_auth_state_from_cdp,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect the latest visible public X post for fixed accounts.")
    parser.add_argument(
        "--accounts-file",
        default="config/accounts.json",
        help="Path to the JSON file that contains the fixed accounts list.",
    )
    parser.add_argument(
        "--browser-path",
        default=None,
        help="Optional browser executable path. If omitted, the collector will try local Chromium and then Playwright's default browser.",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=45000,
        help="Browser timeout in milliseconds.",
    )
    parser.add_argument(
        "--wait-ms",
        type=int,
        default=4000,
        help="Extra wait after navigation in milliseconds.",
    )
    parser.add_argument(
        "--auth-state",
        default=None,
        help="Path to a Playwright storage-state JSON file to use for authenticated X collection.",
    )
    parser.add_argument(
        "--save-auth-state",
        default=None,
        help="Open a browser for one-time X login and save Playwright storage state to this path, then exit.",
    )
    parser.add_argument(
        "--save-auth-state-from-cdp",
        default=None,
        metavar="CDP_URL",
        help="Connect to an existing Chromium-family browser over CDP and save its storage state to --save-auth-state.",
    )
    parser.add_argument(
        "--output",
        default="output/latest_posts.json",
        help="Output JSON file path.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    browser_path = args.browser_path if args.browser_path else default_browser_path()

    if args.save_auth_state and args.save_auth_state_from_cdp:
        try:
            save_auth_state_from_cdp(
                auth_state=args.save_auth_state,
                cdp_url=args.save_auth_state_from_cdp,
                timeout_ms=args.timeout_ms,
            )
        except Exception as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        print(f"saved auth state to {args.save_auth_state}", file=sys.stderr)
        return 0

    if args.save_auth_state:
        try:
            save_auth_state(
                auth_state=args.save_auth_state,
                browser_path=browser_path,
                timeout_ms=args.timeout_ms,
            )
        except Exception as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        print(f"saved auth state to {args.save_auth_state}", file=sys.stderr)
        return 0

    try:
        accounts = load_accounts(args.accounts_file)
        payload = collect_latest_posts(
            handles=accounts,
            browser_path=browser_path,
            timeout_ms=args.timeout_ms,
            wait_ms=args.wait_ms,
            auth_state=args.auth_state,
        )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
