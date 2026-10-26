"""Read-only OKX authentication check. No trading or transfer endpoints."""
import base64
import hashlib
import hmac
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

DOMAINS = {"eea": "https://eea.okx.com", "global": "https://openapi.okx.com", "us": "https://us.okx.com"}


class CheckError(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise CheckError("Átirányítás elutasítva; ellenőrizd a régiót.")


def signature(secret, timestamp, path):
    message = timestamp + "GET" + path
    return base64.b64encode(hmac.new(secret.encode(), message.encode(), hashlib.sha256).digest()).decode()


class Client:
    def __init__(self, region, mode, env=None):
        env = os.environ if env is None else env
        if region not in DOMAINS or mode not in ("demo", "live"):
            raise CheckError("Érvénytelen régió vagy kulcstípus.")
        self.base = DOMAINS[region]
        self.mode = mode
        self.credentials = [env.get(k, "").strip() for k in ("OKX_API_KEY", "OKX_SECRET_KEY", "OKX_PASSPHRASE")]
        if not all(self.credentials):
            raise CheckError("Hiányzó GitHub Secret: OKX_API_KEY, OKX_SECRET_KEY vagy OKX_PASSPHRASE.")
        self.opener = build_opener(NoRedirect())

    def get(self, path, timestamp=None):
        # A closed allowlist makes accidental order/transfer calls impossible.
        if path not in ("/api/v5/public/time", "/api/v5/account/config"):
            raise CheckError("Nem engedélyezett végpont.")
        headers = {"Content-Type": "application/json", "User-Agent": "SS-CRYPTO-connection-check/1"}
        if path == "/api/v5/account/config":
            if not timestamp:
                raise CheckError("Hiányzó szerveridő.")
            key, secret, passphrase = self.credentials
            headers.update({"OK-ACCESS-KEY": key, "OK-ACCESS-SIGN": signature(secret, timestamp, path),
                            "OK-ACCESS-TIMESTAMP": timestamp, "OK-ACCESS-PASSPHRASE": passphrase})
            if self.mode == "demo":
                headers["x-simulated-trading"] = "1"
        req = Request(self.base + path, headers=headers, method="GET")
        try:
            with self.opener.open(req, timeout=20) as response:
                result = json.loads(response.read(1_000_001))
        except HTTPError as exc:
            raise CheckError(f"HTTP {exc.code}; ellenőrizd a régiót, IP-korlátot és jogosultságot.") from None
        except (URLError, TimeoutError, OSError, ValueError):
            raise CheckError("Hálózati vagy JSON-válaszhiba; számlakapcsolat nem igazolt.") from None
        if not isinstance(result, dict):
            raise CheckError("Érvénytelen API-válasz.")
        if result.get("code") != "0":
            code = str(result.get("code", "unknown"))
            code = code if re.fullmatch(r"[0-9]{1,8}", code) else "unknown"
            # Never log an API response or reflected secret/account details.
            raise CheckError(f"OKX hibakód: {code}. Ellenőrizd a kulcstípust, régiót, passphrase-t és IP-korlátot.")
        if not isinstance(result.get("data"), list) or not result["data"]:
            raise CheckError("Hiányos API-válasz.")
        return result["data"]

    def check(self):
        started = time.monotonic()
        data = self.get("/api/v5/public/time")
        try:
            server_ms = int(data[0]["ts"])
            timestamp = datetime.fromtimestamp(server_ms / 1000, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        except (KeyError, TypeError, ValueError, OverflowError, OSError):
            raise CheckError("Érvénytelen OKX-szerveridő.") from None
        if time.monotonic() - started > 10:
            raise CheckError("Túl lassú időszinkron; indítsd újra az ellenőrzést.")
        config = self.get("/api/v5/account/config", timestamp)
        if not isinstance(config[0], dict) or not config[0].get("acctLv"):
            raise CheckError("A számlakonfiguráció válasza hiányos.")
        return "SIKER: OKX-hitelesítés és számlakonfiguráció olvasása igazolt. Megbízás nem történt."


def main():
    try:
        print(Client(os.getenv("OKX_REGION", "eea"), os.getenv("OKX_KEY_MODE", "demo")).check())
        return 0
    except CheckError as exc:
        print(f"SIKERTELEN: {exc}")
        return 1
    except Exception:
        print("SIKERTELEN: váratlan válasz; a kapcsolat nem igazolt.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
