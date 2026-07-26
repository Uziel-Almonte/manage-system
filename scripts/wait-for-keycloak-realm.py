#!/usr/bin/env python3
"""Wait until Keycloak has finished importing the realm (OIDC discovery returns 200)."""
import os
import sys
import time
import urllib.error
import urllib.request

HOST = os.environ.get("KEYCLOAK_HOST", "keycloak")
PORT = os.environ.get("KEYCLOAK_PORT", "8080")
REALM = os.environ.get("KEYCLOAK_REALM", "inventory-realm")
ATTEMPTS = int(os.environ.get("KEYCLOAK_WAIT_ATTEMPTS", "120"))
DELAY = float(os.environ.get("KEYCLOAK_WAIT_DELAY", "2"))

URL = f"http://{HOST}:{PORT}/realms/{REALM}/.well-known/openid-configuration"


def main() -> int:
    for attempt in range(1, ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(URL, timeout=5) as response:
                if response.status == 200:
                    print(f"OK  Keycloak realm ready ({URL})")
                    return 0
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempt == ATTEMPTS or attempt % 10 == 0:
                print(
                    f"… still waiting for Keycloak realm "
                    f"(attempt {attempt}/{ATTEMPTS}): {exc}",
                    file=sys.stderr,
                )
        time.sleep(DELAY)

    print(f"FAIL Keycloak realm not ready: {URL}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
