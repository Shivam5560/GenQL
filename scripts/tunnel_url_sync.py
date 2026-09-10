#!/usr/bin/env python3
"""Point Vercel at the current Cloudflare quick-tunnel URL, and redeploy.

A quick tunnel needs no domain and no Cloudflare account, and in exchange the
hostname is random and changes every time cloudflared restarts. That is fine for
a backend nothing has bookmarked — but the frontend on Vercel holds the URL in
four environment variables, two of which are `NEXT_PUBLIC_` and therefore baked
into the browser bundle at build time. So a new URL is not an environment
change, it is a rebuild. This script does both, in that order.

It is idempotent and cheap to run: if the URL Vercel already holds is the one
the tunnel is serving, it changes nothing and triggers no deployment. That is
what makes it safe to run from a timer, from a unit's `ExecStartPost`, or by
hand after a reboot, without spending a build every time.

Run it with no arguments after the stack is up:

    VERCEL_TOKEN=... python3 scripts/tunnel_url_sync.py

`--dry-run` prints what it would change and touches nothing.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

API = "https://api.vercel.com"
_HTTP_OK = 200
TUNNEL_CONTAINER = "genql-tunnel"
# cloudflared prints the hostname once, inside a box drawn in the log, at
# startup. Matching the URL shape rather than the surrounding banner keeps this
# working when they redraw the banner, which they have before.
URL_PATTERN = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")

# What each variable should hold. GoTrue sits behind a path prefix because one
# quick tunnel is one hostname; see docker/Caddyfile for why that split.
#
# Server-side only, and deliberately so. The browser reaches both services
# through the frontend's own `/api/backend/*` proxy, so no NEXT_PUBLIC_ copy of
# either URL exists to go stale — which is also why a rotation no longer needs
# the client bundle rebuilt, only the functions redeployed.
VARIABLES = {
    "GENQL_API_ORIGIN": "",
    "GOTRUE_URL": "/gotrue",
}


class SyncError(RuntimeError):
    """Anything that should stop the sync with a readable message."""


def current_tunnel_url(container: str = TUNNEL_CONTAINER) -> str:
    """The URL cloudflared announced on its most recent start.

    Read from the container's logs rather than from a status endpoint because a
    quick tunnel has no API — the log line is the only place the hostname is
    published. The last match wins: a restarted container has both the old and
    the new URL in its log, and only the newest is being served.
    """
    try:
        logs = subprocess.run(
            ["docker", "logs", container],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
    except FileNotFoundError as exc:
        raise SyncError("docker is not on PATH") from exc
    except subprocess.CalledProcessError as exc:
        raise SyncError(f"could not read logs from {container!r}: {exc.stderr.strip()}") from exc

    found = URL_PATTERN.findall(logs.stdout + logs.stderr)
    if not found:
        raise SyncError(
            f"{container!r} has not announced a tunnel URL yet — it may still be starting"
        )
    return found[-1]


def wait_until_serving(base: str, attempts: int = 10, delay: float = 3.0) -> None:
    """Do not repoint Vercel at a URL that is not answering yet.

    A tunnel takes a few seconds to become routable after cloudflared prints it.
    Publishing early would swap a working URL for one that 502s, which is
    strictly worse than leaving the old one in place.
    """
    probe = f"{base}/tunnel-health"
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(probe, timeout=10) as response:  # noqa: S310
                if response.status == _HTTP_OK:
                    return
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        if attempt < attempts - 1:
            time.sleep(delay)
    raise SyncError(f"{probe} never answered — not repointing Vercel at a dead tunnel")


def _request(method: str, path: str, token: str, payload: dict | None = None) -> dict:
    body = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(  # noqa: S310
        f"{API}{path}",
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            **({"Content-Type": "application/json"} if body else {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            return json.loads(response.read() or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:400]
        raise SyncError(f"{method} {path} failed: {exc.code} {detail}") from exc


def sync(token: str, project: str, team: str, base: str, *, dry_run: bool) -> bool:
    """Set every variable to the new URL. True when something actually changed."""
    existing = _request("GET", f"/v9/projects/{project}/env?teamId={team}&decrypt=true", token)
    by_key = {
        item["key"]: item
        for item in existing.get("envs", [])
        if "production" in (item.get("target") or [])
    }

    changed = False
    for key, suffix in VARIABLES.items():
        want = base + suffix
        current = by_key.get(key)
        if current and current.get("value") == want:
            print(f"  = {key} already correct")
            continue
        changed = True
        if dry_run:
            print(f"  ~ {key} -> {want}  (dry run)")
            continue
        if current:
            _request(
                "PATCH",
                f"/v9/projects/{project}/env/{current['id']}?teamId={team}",
                token,
                {"value": want},
            )
        else:
            # A variable Vercel does not have yet: create it rather than fail,
            # so a fresh project reaches a working state from one run.
            _request(
                "POST",
                f"/v10/projects/{project}/env?teamId={team}",
                token,
                {
                    "key": key,
                    "value": want,
                    "type": "encrypted",
                    "target": ["production"],
                },
            )
        print(f"  ~ {key} -> {want}")
    return changed


def redeploy(token: str, project: str, team: str, *, dry_run: bool) -> None:
    """Rebuild from the newest production deployment's commit.

    Required, not optional: two of the four variables are `NEXT_PUBLIC_`, which
    Next.js inlines at build time. Updating them without rebuilding leaves the
    browser bundle pointing at the previous tunnel.
    """
    listing = _request(
        "GET", f"/v6/deployments?projectId={project}&teamId={team}&target=production&limit=1", token
    )
    deployments = listing.get("deployments") or []
    if not deployments:
        raise SyncError("no production deployment to rebuild from")
    newest = deployments[0]

    if dry_run:
        print(f"  would redeploy from {newest.get('url')}")
        return

    created = _request(
        "POST",
        f"/v13/deployments?teamId={team}&forceNew=1",
        token,
        {
            "name": newest.get("name") or project,
            "deploymentId": newest["uid"],
            "target": "production",
        },
    )
    print(f"  redeploying -> https://{created.get('url')}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=os.environ.get("VERCEL_PROJECT_ID"))
    parser.add_argument("--team", default=os.environ.get("VERCEL_TEAM_ID"))
    parser.add_argument("--container", default=TUNNEL_CONTAINER)
    parser.add_argument("--url", help="skip log parsing and use this URL")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    token = os.environ.get("VERCEL_TOKEN")
    if not token:
        print("VERCEL_TOKEN is not set", file=sys.stderr)
        return 2
    if not args.project or not args.team:
        print("VERCEL_PROJECT_ID and VERCEL_TEAM_ID must be set", file=sys.stderr)
        return 2

    try:
        base = args.url or current_tunnel_url(args.container)
        print(f"tunnel: {base}")
        wait_until_serving(base)
        print("tunnel is answering, syncing Vercel:")
        if sync(token, args.project, args.team, base, dry_run=args.dry_run):
            redeploy(token, args.project, args.team, dry_run=args.dry_run)
        else:
            # The common case on a reboot where the URL happened to survive, and
            # the whole reason this is safe to run on a timer.
            print("  nothing changed — no redeploy")
    except SyncError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
