"""Post-deploy smoke test: every URL must answer with a status below 400.

    python smoke.py "http://opspilot-api:8000/api/v1/health http://opspilot-web:3000/"

Redirects are followed. Each URL is retried until SMOKE_DEADLINE_SECONDS
(default 90) have passed since the start; the exit code is 1 if any failed.
Standard library only: it runs in the API image.
"""

import os
import sys
import time
import urllib.error
import urllib.request


def check(url: str) -> int:
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"not an http(s) URL: {url}")
    # The URLs come from the chart, never from users; the scheme is checked above.
    with urllib.request.urlopen(url, timeout=5) as response:  # nosemgrep  # noqa: S310
        return int(response.status)


def main(argv: list[str]) -> int:
    urls = " ".join(argv).split()
    if not urls:
        print("usage: smoke.py <url> [<url> ...]", file=sys.stderr)
        return 2
    deadline = time.monotonic() + float(os.environ.get("SMOKE_DEADLINE_SECONDS", "90"))
    failed = []
    for url in urls:
        while True:
            try:
                print(f"ok {check(url)} {url}", flush=True)
                break
            except (urllib.error.URLError, OSError, ValueError) as error:
                if time.monotonic() >= deadline:
                    print(f"FAIL {url}: {error}", flush=True)
                    failed.append(url)
                    break
                time.sleep(3)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
