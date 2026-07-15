"""Build-guide providers.

Every URL gets the generic treatment: fetch the page, extract og:title /
<title> so the library entry is readable. On top of that, provider-specific
parsers extract structured sections (skills, gear, paragon...) when they can.
Parsers are best-effort by contract: any exception or empty result falls
back to the generic behaviour, so a site redesign can never break the
library itself.
"""
import html
import os
import re
import shutil
import ssl
import subprocess
import urllib.error
import urllib.request

from grimoire.parseutil import strip_tags  # noqa: F401  (re-exported for tests)

# Browser-complete headers: Cloudflare-fronted guide sites 403 sparse
# bot-looking requests.
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
BROWSER_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "identity",
}

# Decky's bundled Python ships an OpenSSL whose default CA paths don't
# exist on SteamOS, so a plain urlopen(https) dies with
# CERTIFICATE_VERIFY_FAILED on the Deck. Load the system bundle explicitly.
_CA_CANDIDATES = (
    os.environ.get("SSL_CERT_FILE"),
    "/etc/ssl/certs/ca-certificates.crt",  # SteamOS / Arch
    "/etc/ssl/cert.pem",
)


def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    if ctx.cert_store_stats().get("x509_ca"):
        return ctx  # default verify paths worked (dev machines)
    for cafile in _CA_CANDIDATES:
        if cafile and os.path.isfile(cafile):
            try:
                ctx.load_verify_locations(cafile)
                return ctx
            except ssl.SSLError:
                continue
    return ctx


_SSL_CONTEXT = _ssl_context()

PROVIDERS = {
    "mobalytics.gg": "mobalytics",
    "maxroll.gg": "maxroll",
    "d4builds.gg": "d4builds",
}


def detect_provider(url: str) -> str:
    for domain, name in PROVIDERS.items():
        if domain in url:
            return name
    return "web"


def _get_parser(provider: str):
    if provider == "mobalytics":
        from grimoire.providers import mobalytics as mod
    elif provider == "maxroll":
        from grimoire.providers import maxroll as mod
    elif provider == "d4builds":
        from grimoire.providers import d4builds as mod
    else:
        return None
    return mod


def _curl_get(url: str, max_bytes: int, timeout: int) -> str:
    """System curl fallback. Decky's embedded Python has a TLS handshake
    that Cloudflare fingerprints as a bot (403 even with browser headers,
    while the same request from SteamOS's own stack passes). curl ships
    with SteamOS and has a normal TLS fingerprint."""
    # Plugin processes run with a stripped environment - which() can miss
    # curl even though SteamOS ships it, so check the known path too.
    curl = shutil.which("curl") or (
        "/usr/bin/curl" if os.path.isfile("/usr/bin/curl") else None
    )
    if not curl:
        raise OSError("curl not available")
    # The loader is a bundled (pyinstaller-style) binary and exports
    # LD_LIBRARY_PATH pointing at its private libs; system curl inherits it,
    # loads the wrong libssl and dies with exit 1. Launch with a clean
    # dynamic-linker environment (restoring the pyinstaller-preserved
    # original if present).
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("LD_LIBRARY_PATH", "LD_PRELOAD", "PYTHONPATH", "PYTHONHOME")
    }
    orig = os.environ.get("LD_LIBRARY_PATH_ORIG")
    if orig:
        env["LD_LIBRARY_PATH"] = orig
    proc = subprocess.run(
        [
            curl, "-sL", "--compressed", "--max-time", str(timeout),
            "-A", BROWSER_HEADERS["User-Agent"],
            "-H", f"Accept: {BROWSER_HEADERS['Accept']}",
            "-H", f"Accept-Language: {BROWSER_HEADERS['Accept-Language']}",
            url,
        ],
        capture_output=True,
        timeout=timeout + 10,
        env=env,
    )
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", errors="replace").strip()[:200]
        raise OSError(f"curl exit {proc.returncode}: {detail}")
    return proc.stdout[:max_bytes].decode("utf-8", errors="replace")


def http_get(url: str, max_bytes: int = 2_000_000, timeout: int = 10) -> str:
    """Blocking GET returning decoded text. Callers run in an executor."""
    req = urllib.request.Request(url, headers=BROWSER_HEADERS)
    try:
        with urllib.request.urlopen(
            req, timeout=timeout, context=_SSL_CONTEXT
        ) as resp:
            return resp.read(max_bytes).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        # Bot-blocked, not broken: retry through the system TLS stack.
        if e.code in (403, 429, 503):
            try:
                return _curl_get(url, max_bytes, timeout)
            except Exception as curl_err:
                # Surface BOTH failures - a swallowed fallback error made
                # this path undebuggable on the Deck.
                raise OSError(
                    f"HTTP {e.code}; curl fallback failed: "
                    f"{type(curl_err).__name__}: {curl_err}"
                ) from None
        raise


def _extract_title(page: str) -> str:
    m = re.search(
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', page
    ) or re.search(
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title["\']', page
    ) or re.search(r"<title[^>]*>([^<]+)</title>", page)
    return html.unescape(m.group(1)).strip() if m else ""


def fetch_metadata(url: str, get=http_get) -> dict:
    """Fetch a guide page and return {title, sections}. Blocking - callers
    run this in an executor. `get` is injectable for tests.

    The page GET is itself best-effort: providers whose data comes from a
    separate API (Maxroll planner, d4builds/Firestore) can still produce a
    full result when the guide site throttles or times out the page fetch -
    maxroll.gg has been seen tarpitting repeat fetches while its planner API
    keeps answering."""
    error = ""
    try:
        page = get(url)
    except Exception as e:
        page = ""
        error = f"page fetch: {type(e).__name__}: {e}"
    title = _extract_title(page)
    sections: list = []
    variants: list = []

    parser = _get_parser(detect_provider(url))
    if parser is not None:
        try:
            parsed = parser.parse(url, page, get) or {}
            if parsed.get("title"):
                title = parsed["title"]
            sections = parsed.get("sections") or []
            # Optional: [{name, sections}] when the guide ships several
            # builds (Starter / Endgame / ...). `sections` stays the default
            # variant's, so anything ignoring variants keeps working.
            variants = parsed.get("variants") or []
        except Exception as e:
            # Best-effort by contract: structured parsing must never break
            # the generic save-the-link flow.
            sections = []
            variants = []
            error = f"parser: {type(e).__name__}: {e}"

    # The error rides along so the caller can LOG it - swallowing it
    # unlogged made real-Deck failures (SSL, DNS) invisible.
    return {"title": title, "sections": sections, "variants": variants,
            "error": error}
