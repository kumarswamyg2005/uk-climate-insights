"""Keep the free Render instance awake by visiting our own public URL every 10 minutes.

Render stops a free web service after 15 minutes without inbound traffic, and the next visitor
waits about a minute. A scheduled GitHub Actions ping couldn't prevent that: GitHub ran it 8 times
in 36 hours instead of every 10 minutes. This loop runs inside the instance instead. Its request
leaves the container and comes back in through Render's proxy, so it counts as traffic. It asks
for a static file, which WhiteNoise serves without touching the database, so Neon can still
suspend.

Runs only where RENDER_EXTERNAL_URL is set (Render sets it; local runs, Docker Compose and CI
don't). Cost: the instance stays up all month, about 744 of the workspace's 750 free hours.
"""

import os
import sys
import time
import urllib.request


def main() -> None:
    base = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")
    if not base:
        return
    url = f"{base}/static/climate/css/app.css"
    interval = float(os.environ.get("KEEP_AWAKE_SECONDS", "600"))  # under the 15-minute limit
    while True:
        time.sleep(interval)
        try:
            # The URL is our own, from Render's environment, not user input.
            with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310
                response.read(1)
        except Exception as exc:  # a failed ping must never stop the loop
            print(f"keep-awake: {exc}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
