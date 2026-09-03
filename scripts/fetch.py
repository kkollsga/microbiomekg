#!/usr/bin/env python3
"""Fetch every raw source for MicrobiomeKG into data/raw/<source>/.

Run with:  python3 scripts/fetch.py
       or: uv run --no-sync --with requests python3 scripts/fetch.py

Behaviour:
  * A file already present at its full expected size is skipped (status "cached").
  * Partial downloads land in <name>.part and resume via HTTP Range when the
    server advertises Accept-Ranges: bytes; the .part is renamed into place only
    once the body is complete, so a bare filename always means "complete".
  * Every request carries a full browser header set (see BROWSER_HEADERS) with a
    per-host Referer, because several of these hosts refuse plain clients.
  * data/raw/manifest.json records url, bytes, sha256, fetched_at and status for
    every file, including the members extracted out of archives.

Flags:
  --chembl-sqlite   also pull the 5.76 GB chembl_37_sqlite.tar.gz (off by default)
  --only SOURCE     run one source (repeatable), e.g. --only kegg --only card
  --force           re-download even when a complete file is already present
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
MANIFEST = RAW / "manifest.json"

# A full browser header set is the session default, not a retry-only fallback:
# HMDB sits behind Cloudflare and Disbiome/gutMDisorder have both refused
# non-browser clients, so every request in this script sends these.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "sec-ch-ua": '"Chromium";v="128", "Not;A=Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
}

# Referer defaults to each site's own front page.
SITE_FRONT_PAGE = {
    "ftp.ncbi.nlm.nih.gov": "https://ftp.ncbi.nlm.nih.gov/",
    "raw.githubusercontent.com": "https://github.com/",
    "api.github.com": "https://github.com/",
    "disbiome.ugent.be": "https://disbiome.ugent.be/",
    "hmdb.ca": "https://hmdb.ca/downloads",
    "card.mcmaster.ca": "https://card.mcmaster.ca/",
    "reactome.org": "https://reactome.org/",
    "rest.kegg.jp": "https://www.kegg.jp/",
    "www.ebi.ac.uk": "https://www.ebi.ac.uk/chembl/",
    "ftp.ebi.ac.uk": "https://ftp.ebi.ac.uk/",
    "bio-annotation.cn": "http://bio-annotation.cn/gutMDisorder/",
    "www.bio-annotation.cn": "http://bio-annotation.cn/gutMDisorder/",
    "mimedb.org": "https://mimedb.org/downloads",
    "www.aiddlab.com": "http://www.aiddlab.com/MASI/download.html",
    "web.archive.org": "https://web.archive.org/",
    "datadryad.org": "https://datadryad.org/",
    "static-content.springer.com": "https://www.nature.com/",
    "pmc.ncbi.nlm.nih.gov": "https://pmc.ncbi.nlm.nih.gov/",
}

SESSION = requests.Session()
SESSION.headers.update(BROWSER_HEADERS)

MANIFEST_DATA: dict[str, dict] = {}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def referer_for(url: str) -> str:
    host = re.sub(r"^https?://([^/]+).*$", r"\1", url)
    return SITE_FRONT_PAGE.get(host, f"https://{host}/")


def request(method: str, url: str, *, timeout: float = 60, **kw):
    headers = dict(kw.pop("headers", {}))
    headers.setdefault("Referer", referer_for(url))
    return SESSION.request(method, url, timeout=timeout, headers=headers, **kw)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def record(key: str, **fields) -> None:
    entry = {"fetched_at": now()}
    entry.update(fields)
    MANIFEST_DATA[key] = entry
    save_manifest()


def record_file(source: str, path: Path, url: str, status: str, **extra) -> None:
    key = f"{source}/{path.relative_to(RAW / source).as_posix()}"
    st = path.stat()
    # Re-hashing is skipped only when size AND mtime both match what the manifest
    # already recorded, so an unchanged 6.5 GB HMDB drop does not cost a full
    # SHA-256 pass on every run. Any edit moves mtime and forces a rehash.
    prev = MANIFEST_DATA.get(key, {})
    if prev.get("bytes") == st.st_size and prev.get("mtime") == int(st.st_mtime):
        digest = prev["sha256"]
    else:
        digest = sha256_of(path)
    record(
        key,
        url=url,
        path=str(path.relative_to(ROOT)),
        bytes=st.st_size,
        mtime=int(st.st_mtime),
        sha256=digest,
        status=status,
        **extra,
    )


def record_problem(source: str, name: str, url: str, status: str, error: str) -> None:
    record(
        f"{source}/{name}",
        url=url,
        path=None,
        bytes=None,
        sha256=None,
        status=status,
        error=error,
    )


def save_manifest() -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    tmp = MANIFEST.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(MANIFEST_DATA, indent=2, sort_keys=True) + "\n")
    tmp.replace(MANIFEST)


def load_manifest() -> None:
    if MANIFEST.exists():
        try:
            MANIFEST_DATA.update(json.loads(MANIFEST.read_text()))
        except json.JSONDecodeError:
            log("manifest.json unreadable; starting a fresh one")


# ---------------------------------------------------------------- downloading

# Content-Length describes the bytes on the wire, but requests transparently
# decodes gzip, so a compressed response writes MORE bytes than the header
# advertises (raw.githubusercontent.com: 1,708,429 gzipped vs 16,241,290 plain).
# Every sizing and range request therefore asks for identity encoding, so the
# advertised length is the length we actually write and byte offsets line up.
IDENTITY = {"Accept-Encoding": "identity"}


def remote_size(url: str, timeout: float = 60) -> tuple[int | None, bool]:
    """Return (content_length, supports_ranges). Both best-effort."""
    try:
        r = request(
            "HEAD", url, timeout=timeout, allow_redirects=True, headers=IDENTITY
        )
        if r.status_code >= 400:
            return None, False
        size = r.headers.get("Content-Length")
        ranges = r.headers.get("Accept-Ranges", "").lower() == "bytes"
        # Europe PMC answers HEAD on its supplementaryFiles endpoint with
        # Content-Length: 0 and then streams megabytes on GET. A zero here means
        # "the server did not size this", never "the file is empty" — taking it
        # literally rejects every complete download as incomplete.
        length = int(size) if size else None
        return (length or None), ranges
    except requests.RequestException:
        return None, False


def download(
    source: str,
    url: str,
    filename: str,
    *,
    timeout: float = 120,
    force: bool = False,
    expect_prefix: bytes | None = None,
) -> Path | None:
    """Download url into data/raw/<source>/<filename>, resuming where possible."""
    dest_dir = RAW / source
    dest = dest_dir / filename
    part = dest_dir / (filename + ".part")
    # filename may carry a subdirectory (drug_screens/maier2018/...), so the
    # parent is made rather than just the source root.
    dest.parent.mkdir(parents=True, exist_ok=True)

    size, ranges = remote_size(url, timeout=min(timeout, 60))

    if dest.exists() and not force:
        local = dest.stat().st_size
        if size is None or local == size:
            log(f"  cached {source}/{filename} ({local:,} B)")
            record_file(source, dest, url, "cached", expected_bytes=size)
            return dest
        log(
            f"  {source}/{filename} is {local:,} B but server says {size:,} B; refetching"
        )
        dest.rename(part)

    start = part.stat().st_size if part.exists() else 0
    headers = dict(IDENTITY)
    mode = "wb"
    if start and ranges and size and start < size:
        headers["Range"] = f"bytes={start}-"
        mode = "ab"
        log(f"  resuming {source}/{filename} at {start:,} B")
    elif start:
        start = 0  # server can't resume; restart cleanly

    try:
        with request(
            "GET",
            url,
            timeout=timeout,
            headers=headers,
            stream=True,
            allow_redirects=True,
        ) as r:
            if r.status_code == 416 and size and start == size:
                pass  # already complete
            elif r.status_code not in (200, 206):
                raise requests.HTTPError(f"HTTP {r.status_code}", response=r)
            elif "Range" in headers and r.status_code == 200:
                mode, start = "wb", 0  # server ignored Range
            if r.status_code in (200, 206):
                with part.open(mode) as fh:
                    for chunk in r.iter_content(1 << 20):
                        if chunk:
                            fh.write(chunk)
    except requests.RequestException as exc:
        detail = f"{type(exc).__name__}: {exc}"
        log(f"  FAILED {source}/{filename}: {detail}")
        record_problem(source, filename, url, "unreachable", detail)
        return None

    got = part.stat().st_size if part.exists() else 0
    if size is not None and got != size:
        detail = f"incomplete: got {got} of {size} bytes"
        log(f"  FAILED {source}/{filename}: {detail}")
        record_problem(source, filename, url, "incomplete", detail)
        return None
    if expect_prefix and part.open("rb").read(len(expect_prefix)) != expect_prefix:
        detail = f"unexpected content (does not start with {expect_prefix!r})"
        log(f"  FAILED {source}/{filename}: {detail}")
        record_problem(source, filename, url, "unexpected-content", detail)
        return None

    part.replace(dest)
    log(f"  fetched {source}/{filename} ({dest.stat().st_size:,} B)")
    record_file(source, dest, url, "fetched", expected_bytes=size)
    return dest


def write_text_file(source: str, filename: str, url: str, text: str) -> Path:
    dest_dir = RAW / source
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    dest.write_text(text)
    record_file(source, dest, url, "fetched")
    log(f"  fetched {source}/{filename} ({dest.stat().st_size:,} B)")
    return dest


def stale_members(
    source: str, out: Path, names: list[str], archive_key: str, force: bool
) -> list[str]:
    """Which of `names` must be (re-)extracted from the archive at archive_key.

    Presence alone is not freshness. NCBI rebuilds its taxdump daily and CARD
    ships new bundles under the same URL, and a rebuilt member can keep its byte
    count while changing content — so extracted files are tied to the sha256 of
    the archive they came from, and any archive change re-extracts. This also
    self-heals a run that downloaded a new archive but died before extracting.
    """
    archive_sha = MANIFEST_DATA.get(archive_key, {}).get("sha256")
    todo = []
    for name in names:
        target = out / name
        entry = MANIFEST_DATA.get(
            f"{source}/{target.relative_to(RAW / source).as_posix()}", {}
        )
        if (
            force
            or not target.exists()
            or entry.get("from_archive_sha256") != archive_sha
        ):
            todo.append(name)
    return todo


def wayback_url(timestamp: str, original: str) -> str:
    """A Wayback playback URL for the *original* bytes.

    The `if_` infix is what suppresses archive.org's rewritten wrapper; without
    it a captured CSV comes back with a navigation banner spliced into it.
    """
    return f"http://web.archive.org/web/{timestamp}if_/{original}"


def extract_zip_members(
    source: str, archive: Path, out: Path, url: str, wanted: callable, force: bool
) -> list[Path]:
    """Extract the members of `archive` for which wanted(name) is true.

    Same freshness rule as stale_members(): extracted files are tied to the
    sha256 of the archive they came from, so a re-published archive re-extracts.
    """
    import zipfile

    out.mkdir(parents=True, exist_ok=True)
    arc_key = f"{source}/{archive.relative_to(RAW / source).as_posix()}"
    arc_sha = MANIFEST_DATA[arc_key]["sha256"]
    written = []
    with zipfile.ZipFile(archive) as zf:
        names = [n for n in zf.namelist() if wanted(Path(n).name)]
        todo = stale_members(source, out, [Path(n).name for n in names], arc_key, force)
        for name in names:
            target = out / Path(name).name
            if target.name in todo:
                with zf.open(name) as src, target.open("wb") as dst:
                    while chunk := src.read(1 << 20):
                        dst.write(chunk)
            record_file(source, target, url, "extracted", from_archive_sha256=arc_sha)
            log(
                f"  {'extracted' if target.name in todo else 'verified'} "
                f"{target.relative_to(RAW / source)} ({target.stat().st_size:,} B)"
            )
            written.append(target)
    return written


# ------------------------------------------------------------------- sources


def fetch_ncbi(args) -> None:
    log("NCBI Taxonomy")
    base = "https://ftp.ncbi.nlm.nih.gov/pub/taxonomy/new_taxdump/"
    # The .md5 sidecar is ALWAYS refetched, never cached. It is 53 bytes whatever
    # it contains, so "present at its full size" cannot detect that NCBI has
    # regenerated the dump — and a stale sidecar checked against a fresh tarball
    # reports a digest mismatch that looks like corruption but is just staleness.
    md5 = download(
        "ncbi_taxonomy",
        base + "new_taxdump.tar.gz.md5",
        "new_taxdump.tar.gz.md5",
        force=True,
    )
    tar = download(
        "ncbi_taxonomy",
        base + "new_taxdump.tar.gz",
        "new_taxdump.tar.gz",
        timeout=600,
        force=args.force,
    )
    if not tar:
        return

    if md5:
        want = md5.read_text().split()[0]
        h = hashlib.md5()
        with tar.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        got = h.hexdigest()
        ok = got == want
        log(f"  md5 {'OK' if ok else f'MISMATCH want={want} got={got}'}")
        MANIFEST_DATA["ncbi_taxonomy/new_taxdump.tar.gz"]["md5"] = got
        MANIFEST_DATA["ncbi_taxonomy/new_taxdump.tar.gz"]["md5_verified"] = ok
        save_manifest()
        if not ok:
            return

    # Only the five members we need; the tarball holds a lot more.
    wanted = [
        "names.dmp",
        "nodes.dmp",
        "rankedlineage.dmp",
        "merged.dmp",
        "delnodes.dmp",
    ]
    out = RAW / "ncbi_taxonomy"
    tar_key = "ncbi_taxonomy/new_taxdump.tar.gz"
    tar_sha = MANIFEST_DATA[tar_key]["sha256"]
    missing = stale_members("ncbi_taxonomy", out, wanted, tar_key, args.force)
    if missing:
        log(f"  extracting {', '.join(missing)}")
        with tarfile.open(tar, "r:gz") as tf:
            for name in missing:
                member = tf.getmember(name)
                with tf.extractfile(member) as src, (out / name).open("wb") as dst:
                    while chunk := src.read(1 << 20):
                        dst.write(chunk)
    for name in wanted:
        p = out / name
        if p.exists():
            record_file(
                "ncbi_taxonomy",
                p,
                base + "new_taxdump.tar.gz",
                "extracted",
                from_archive_sha256=tar_sha,
            )
            verb = "extracted" if name in missing else "verified"
            log(f"  {verb} {name} ({p.stat().st_size:,} B)")


def fetch_bugsigdb(args) -> None:
    log("BugSigDB")
    # v1.3.1 has no release assets; the versioned export is the file at the tag.
    tagged = (
        "https://raw.githubusercontent.com/waldronlab/BugSigDBExports/"
        "v1.3.1/full_dump.csv"
    )
    main = (
        "https://raw.githubusercontent.com/waldronlab/BugSigDBExports/"
        "main/full_dump.csv"
    )
    download("bugsigdb", tagged, "full_dump_v1.3.1.csv", force=args.force)
    download("bugsigdb", main, "full_dump_main.csv", force=args.force)


DISBIOME_ENDPOINTS = [
    "experiment",
    "organism",
    "disease",
    "method",
    "sample",
    "publication",
]


def fetch_disbiome(args) -> None:
    log("Disbiome")
    base = "https://disbiome.ugent.be"
    # One reachability probe first: the host has been failing at the TCP level,
    # and there is no point walking twelve URL variants against a dead socket.
    try:
        r = request("GET", base + "/", timeout=60)
        reachable, why = True, f"HTTP {r.status_code}"
    except requests.RequestException as exc:
        reachable, why = False, f"{type(exc).__name__}: {exc}"
    log(f"  front page: {why}")

    if not reachable:
        # Confirm with one export endpoint and one bundle fetch, then stop.
        for url, name, tmo in (
            (f"{base}/export/experiment", "export_experiment.json", 60),
            (f"{base}/main.bundle.js", "main.bundle.js", 120),
        ):
            try:
                r = request("GET", url, timeout=tmo)
                log(f"  {url} -> HTTP {r.status_code}, {len(r.content):,} B")
            except requests.RequestException as exc:
                why2 = f"{type(exc).__name__}: {exc}"
                log(f"  {url} -> {why2}")
                record_problem("disbiome", name, url, "unreachable", why2)
        record_problem(
            "disbiome",
            "_host",
            base + "/",
            "unreachable",
            f"front page unreachable with full browser headers: {why}",
        )
        return

    got_json = False
    for ep in DISBIOME_ENDPOINTS:
        for url in (f"{base}/export/{ep}", f"{base}/export/{ep}/"):
            try:
                r = request(
                    "GET", url, timeout=90, headers={"Accept": "application/json"}
                )
            except requests.RequestException as exc:
                record_problem(
                    "disbiome",
                    f"{ep}.json",
                    url,
                    "unreachable",
                    f"{type(exc).__name__}: {exc}",
                )
                continue
            body = r.text.lstrip()
            if r.status_code == 200 and body[:1] in "[{":
                write_text_file("disbiome", f"{ep}.json", url, r.text)
                got_json = True
                break
            record_problem(
                "disbiome",
                f"{ep}.json",
                url,
                "manual",
                f"HTTP {r.status_code}, content-type "
                f"{r.headers.get('Content-Type')}, body starts {body[:60]!r}",
            )
    if not got_json:
        # SPA HTML instead of JSON: grab the bundle so the real endpoint can be grepped.
        url = f"{base}/main.bundle.js"
        try:
            r = request("GET", url, timeout=120)
            if r.status_code == 200:
                write_text_file("disbiome", "main.bundle.js", url, r.text)
        except requests.RequestException as exc:
            record_problem(
                "disbiome",
                "main.bundle.js",
                url,
                "unreachable",
                f"{type(exc).__name__}: {exc}",
            )


def fetch_hmdb(args) -> None:
    log("HMDB")
    url = "https://hmdb.ca/system/downloads/current/hmdb_metabolites.zip"

    # hmdb.ca is behind an interactive Cloudflare challenge, so the operator
    # downloads this by hand. Honour whatever they dropped in — either the zip
    # or the XML unpacked from it — rather than pointlessly re-hitting the 403.
    for name in ("hmdb_metabolites.zip", "hmdb_metabolites.xml"):
        placed = RAW / "hmdb" / name
        if placed.exists() and placed.stat().st_size:
            log(f"  operator-supplied hmdb/{name} ({placed.stat().st_size:,} B)")
            record_file(
                "hmdb",
                placed,
                url,
                "manual-present",
                note="placed by hand; hmdb.ca blocks automated download",
            )
            return

    try:
        r = request("GET", url, timeout=120, stream=True, allow_redirects=True)
    except requests.RequestException as exc:
        record_problem(
            "hmdb",
            "hmdb_metabolites.zip",
            url,
            "unreachable",
            f"{type(exc).__name__}: {exc}",
        )
        log(f"  FAILED: {exc}")
        return
    if r.status_code == 200 and r.headers.get("Content-Type", "").startswith(
        "application/zip"
    ):
        r.close()
        download("hmdb", url, "hmdb_metabolites.zip", timeout=1200, force=args.force)
        return
    mitigation = r.headers.get("cf-mitigated")
    detail = (
        f"HTTP {r.status_code} from {r.headers.get('server')}"
        + (f", cf-mitigated: {mitigation}" if mitigation else "")
        + " — sent with the full browser header set; this is an interactive "
        "Cloudflare challenge, which no header set can satisfy. Download "
        "hmdb_metabolites.zip by hand from https://hmdb.ca/downloads into "
        "data/raw/hmdb/."
    )
    r.close()
    log(f"  MANUAL: {detail}")
    record_problem("hmdb", "hmdb_metabolites.zip", url, "manual", detail)


def fetch_card(args) -> None:
    log("CARD")
    for url, name in (
        ("https://card.mcmaster.ca/latest/data", "card-data.tar.bz2"),
        ("https://card.mcmaster.ca/latest/ontology", "card-ontology.tar.bz2"),
    ):
        arc = download("card", url, name, timeout=300, force=args.force)
        if not arc:
            continue
        out = RAW / "card" / name.replace(".tar.bz2", "")
        out.mkdir(parents=True, exist_ok=True)
        arc_key = f"card/{name}"
        arc_sha = MANIFEST_DATA[arc_key]["sha256"]
        with tarfile.open(arc, "r:bz2") as tf:
            members = [m for m in tf.getmembers() if m.isfile()]
            want = stale_members(
                "card", out, [Path(m.name).name for m in members], arc_key, args.force
            )
            for member in members:
                target = out / Path(member.name).name
                if target.name not in want:
                    continue
                with tf.extractfile(member) as src, target.open("wb") as dst:
                    while chunk := src.read(1 << 20):
                        dst.write(chunk)
        for p in sorted(out.iterdir()):
            if p.is_file():
                record_file("card", p, url, "extracted", from_archive_sha256=arc_sha)
                verb = "extracted" if p.name in want else "verified"
                log(f"  {verb} {p.relative_to(RAW / 'card')} ({p.stat().st_size:,} B)")


def fetch_reactome(args) -> None:
    log("Reactome")
    base = "https://reactome.org/download/current/"
    for name in (
        "ReactomePathways.txt",
        "ReactomePathwaysRelation.txt",
        "ChEBI2Reactome.txt",
        "ChEBI2Reactome_All_Levels.txt",
        "NCBI2Reactome.txt",
    ):
        download("reactome", base + name, name, timeout=300, force=args.force)


KEGG_ENDPOINTS = [
    ("/list/pathway", "list_pathway.tsv"),
    ("/list/pathway/hsa", "list_pathway_hsa.tsv"),
    ("/list/compound", "list_compound.tsv"),
    ("/link/compound/pathway", "link_compound_pathway.tsv"),
    ("/conv/compound/pubchem", "conv_compound_pubchem.tsv"),
    # /list/organism is retired — it answers 400 as of 2026-09-02. /list/genome is
    # the live organism roster, but it returns two columns (T-number, "code; name")
    # where /list/organism returned four: the taxonomic lineage column is gone, so
    # KEGG organism codes must be joined to NCBI taxids through another route.
    ("/list/genome", "list_genome.tsv"),
]


def fetch_kegg(args) -> None:
    log("KEGG (sequential, 1 s between calls)")
    base = "https://rest.kegg.jp"
    for i, (path, name) in enumerate(KEGG_ENDPOINTS):
        dest = RAW / "kegg" / name
        if dest.exists() and dest.stat().st_size and not args.force:
            log(f"  cached kegg/{name} ({dest.stat().st_size:,} B)")
            record_file("kegg", dest, base + path, "cached")
            continue
        if i:
            time.sleep(1.0)
        url = base + path
        try:
            r = request("GET", url, timeout=180)
            r.raise_for_status()
        except requests.RequestException as exc:
            record_problem(
                "kegg", name, url, "unreachable", f"{type(exc).__name__}: {exc}"
            )
            log(f"  FAILED kegg/{name}: {exc}")
            continue
        write_text_file("kegg", name, url, r.text)


CHEMBL_API = "https://www.ebi.ac.uk/chembl/api/data"
CHEMBL_DELAY = 0.25  # <= 5 req/s, well under it


def chembl_get(path: str, params: dict) -> dict:
    for attempt in range(4):
        try:
            r = request(
                "GET",
                f"{CHEMBL_API}/{path}",
                timeout=180,
                params=params,
                headers={"Accept": "application/json"},
            )
            if r.status_code == 429:
                time.sleep(5 * (attempt + 1))
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            if attempt == 3:
                raise
            time.sleep(3 * (attempt + 1))
    raise RuntimeError("unreachable")


def chembl_page_all(path: str, collection: str, params: dict, dest: Path) -> int:
    """Page an endpoint into a JSONL file, one record per line."""
    tmp = dest.with_suffix(dest.suffix + ".part")
    total, offset = None, 0
    with tmp.open("w") as fh:
        while True:
            page = chembl_get(path, {**params, "offset": offset})
            if total is None:
                total = page["page_meta"]["total_count"]
                log(f"  {path}: {total:,} records")
            rows = page[collection]
            for row in rows:
                fh.write(json.dumps(row, separators=(",", ":")) + "\n")
            offset += len(rows)
            if not rows or offset >= total:
                break
            time.sleep(CHEMBL_DELAY)
    tmp.replace(dest)
    return offset


def fetch_chembl(args) -> None:
    log("ChEMBL")
    out = RAW / "chembl"
    out.mkdir(parents=True, exist_ok=True)

    mech = out / "mechanism.jsonl"
    if mech.exists() and not args.force:
        log(f"  cached chembl/mechanism.jsonl ({mech.stat().st_size:,} B)")
        record_file("chembl", mech, f"{CHEMBL_API}/mechanism.json", "cached")
    else:
        n = chembl_page_all("mechanism.json", "mechanisms", {"limit": 1000}, mech)
        log(f"  fetched chembl/mechanism.jsonl ({n:,} rows, {mech.stat().st_size:,} B)")
        record_file("chembl", mech, f"{CHEMBL_API}/mechanism.json", "fetched", rows=n)

    mol = out / "molecule_max_phase4.jsonl"
    mol_only = (
        "molecule_chembl_id,pref_name,max_phase,first_approval,molecule_type,"
        "withdrawn_flag,therapeutic_flag,oral,parenteral,topical,"
        "atc_classifications,molecule_properties,molecule_structures"
    )
    mol_url = f"{CHEMBL_API}/molecule.json?max_phase=4&only={mol_only}"
    if mol.exists() and not args.force:
        log(f"  cached chembl/molecule_max_phase4.jsonl ({mol.stat().st_size:,} B)")
        record_file("chembl", mol, mol_url, "cached")
    else:
        n = chembl_page_all(
            "molecule.json",
            "molecules",
            {"limit": 1000, "max_phase": 4, "only": mol_only},
            mol,
        )
        log(f"  fetched chembl/molecule_max_phase4.jsonl ({n:,} rows)")
        record_file("chembl", mol, mol_url, "fetched", rows=n)

    # Targets: only the ones mechanisms actually reference.
    tgt = out / "target.jsonl"
    tgt_url = f"{CHEMBL_API}/target.json?target_chembl_id__in=..."
    if tgt.exists() and not args.force:
        log(f"  cached chembl/target.jsonl ({tgt.stat().st_size:,} B)")
        record_file("chembl", tgt, tgt_url, "cached")
    else:
        ids = sorted(
            {json.loads(line).get("target_chembl_id") for line in mech.open()} - {None}
        )
        log(f"  {len(ids):,} distinct target ids referenced by mechanisms")
        tmp = tgt.with_suffix(".jsonl.part")
        seen = 0
        with tmp.open("w") as fh:
            for i in range(0, len(ids), 50):
                batch = ids[i : i + 50]
                page = chembl_get(
                    "target.json",
                    {"target_chembl_id__in": ",".join(batch), "limit": 1000},
                )
                for row in page["targets"]:
                    fh.write(json.dumps(row, separators=(",", ":")) + "\n")
                    seen += 1
                time.sleep(CHEMBL_DELAY)
        tmp.replace(tgt)
        log(f"  fetched chembl/target.jsonl ({seen:,} rows)")
        record_file("chembl", tgt, tgt_url, "fetched", rows=seen)

    ftp = "https://ftp.ebi.ac.uk/pub/databases/chembl/ChEMBLdb/latest/"
    download(
        "chembl",
        ftp + "chembl_uniprot_mapping.txt",
        "chembl_uniprot_mapping.txt",
        timeout=300,
        force=args.force,
    )
    download("chembl", ftp + "LICENSE", "LICENSE", timeout=120, force=args.force)

    if args.chembl_sqlite:
        log("  --chembl-sqlite given: pulling the 5.76 GB SQLite dump")
        download(
            "chembl",
            ftp + "chembl_37_sqlite.tar.gz",
            "chembl_37_sqlite.tar.gz",
            timeout=7200,
            force=args.force,
        )
    else:
        record_problem(
            "chembl",
            "chembl_37_sqlite.tar.gz",
            ftp + "chembl_37_sqlite.tar.gz",
            "skipped",
            "5.76 GB; not fetched by default — pass --chembl-sqlite",
        )


# bio-annotation.cn refuses connections, but the site's own bulk-export files
# were captured by the Wayback Machine. These are the last good snapshots of the
# two files the Resource page offered; the "if_" infix asks for the original
# bytes rather than archive.org's rewritten wrapper.
GUTMDISORDER_WAYBACK = [
    (
        "human.xlsx",
        "http://web.archive.org/web/20200812224039if_/"
        "http://bio-annotation.cn:80/gutMDisorder/public/res/human.xlsx",
    ),
    (
        "mouse.xlsx",
        "http://web.archive.org/web/20200812224042if_/"
        "http://bio-annotation.cn:80/gutMDisorder/public/res/mouse.xlsx",
    ),
]


def fetch_gutmdisorder(args) -> None:
    log("gutMDisorder")

    # Origin first only if something is missing; otherwise record and move on.
    have = [
        n
        for n, _ in GUTMDISORDER_WAYBACK
        if (RAW / "gutmdisorder" / n).exists()
        and (RAW / "gutmdisorder" / n).stat().st_size
    ]
    if len(have) == len(GUTMDISORDER_WAYBACK) and not args.force:
        for name, wb in GUTMDISORDER_WAYBACK:
            path = RAW / "gutmdisorder" / name
            log(f"  cached gutmdisorder/{name} ({path.stat().st_size:,} B)")
            record_file(
                "gutmdisorder",
                path,
                wb,
                "cached",
                note="origin host is down; bytes come from a Wayback snapshot",
            )
        return

    ok = True
    for name, wb in GUTMDISORDER_WAYBACK:
        # archive.org rate-limits snapshot playback hard (HTTP 429); space these out.
        if download("gutmdisorder", wb, name, timeout=180, force=args.force) is None:
            ok = False
        time.sleep(8)
    if ok:
        return

    for url in (
        "http://bio-annotation.cn/gutMDisorder/",
        "https://bio-annotation.cn/gutMDisorder/",
    ):
        try:
            r = request("GET", url, timeout=60)
            log(f"  {url} -> HTTP {r.status_code}, {len(r.content):,} B")
            if r.status_code == 200:
                write_text_file("gutmdisorder", "index.html", url, r.text)
                record_problem(
                    "gutmdisorder",
                    "_downloads",
                    url,
                    "manual",
                    "front page reachable; pick the bulk file off the "
                    "download page by hand into data/raw/gutmdisorder/",
                )
                return
        except requests.RequestException as exc:
            detail = f"{type(exc).__name__}: {exc}"
            log(f"  {url} -> {detail}")
            record_problem("gutmdisorder", "index.html", url, "unreachable", detail)


# mimedb.org is behind the same interactive Cloudflare challenge as hmdb.ca (both
# are Wishart-lab sites), so the origin cannot be fetched by any client that does
# not run JavaScript. Genes (216 MB) and genomes (202 MB) are deliberately
# skipped: whatever taxon->metabolite evidence MiMeDB publishes would be in the
# metabolite and microbe files, and it turns out neither carries any (see
# data/raw/mimedb/v2/PROVENANCE.md).
#
# The two releases need opposite handling, which is why there are two lists.
#
# **v2.0 is the release the loader reads and there is no automated route to it.**
# Its downloads were never captured by the Wayback Machine, so an operator has to
# place the four files by hand. This script therefore only ever *detects* them —
# the `manual-present` pattern `fetch_hmdb` uses — and prints the exact filenames
# and destination when they are absent. It does not re-probe the origin for them:
# the blocker is an interactive challenge, a request cannot pass it, and a probe
# whose answer is known is a request spent to print a line we could print anyway.
#
# **v1.0 is the fallback and *is* obtainable**, because its bulk files were
# archived. That is the only reason the Wayback logic below still exists.
MIMEDB_V2_DIR = "v2"
MIMEDB_V2_FILES = [
    "mimedb_metabolites_v2.csv",
    "mimedb_metabolites_v2.xml",
    "mimedb_microbes_v2.csv",
    "mimedb_microbes_v2.xml",
]
MIMEDB_V2_PAGE = "https://mimedb.org/downloads"
MIMEDB_ORIGIN = "https://mimedb.org/system/downloads/1.0/"
MIMEDB_FILES = [
    ("mimedb_metabolites_v1.csv", "20240507091752"),
    ("mimedb_metabolites_v1.xml.zip", "20240507091828"),
    ("mimedb_microbes_v1.csv", "20240507091821"),
    ("mimedb_microbes_v1.xml.zip", "20240507091808"),
]
MIMEDB_SKIPPED = {
    "mimedb_genes_v1.csv.zip": "216 MB of gene records; no edge in the model needs them",
    "mimedb_genomes_v1.csv.zip": "202 MB of genome records; no edge in the model needs them",
    "mimedb.sdf.zip": "structures only",
    "mimedb_all_spectra.zip": "2.43 GB of raw spectra",
}


def fetch_mimedb_v2(args) -> bool:
    """Record the hand-placed v2.0 files, or say exactly which are missing.

    Returns whether all four are here. Never fetches: see the comment above
    ``MIMEDB_V2_DIR``. ``args`` is unused and named for symmetry with the other
    fetchers — ``--force`` cannot re-download a file no client can reach, and
    honouring it here would delete the operator's only copy.
    """
    here, absent = [], []
    for name in MIMEDB_V2_FILES:
        path = RAW / "mimedb" / MIMEDB_V2_DIR / name
        (here if path.exists() and path.stat().st_size else absent).append((name, path))

    for name, path in here:
        log(
            f"  operator-supplied mimedb/{MIMEDB_V2_DIR}/{name} "
            f"({path.stat().st_size:,} B)"
        )
        record_file(
            "mimedb",
            path,
            MIMEDB_V2_PAGE,
            "manual-present",
            note="placed by hand; mimedb.org is behind an interactive "
            "Cloudflare challenge and v2.0 was never archived by the "
            "Wayback Machine, so no client can fetch this",
        )
    for name, path in absent:
        record_problem(
            "mimedb",
            f"{MIMEDB_V2_DIR}/{name}",
            MIMEDB_V2_PAGE,
            "manual",
            f"MiMeDB v2.0 has no automated route: mimedb.org serves an interactive "
            f"Cloudflare challenge, and unlike v1.0 these files were never captured "
            f"by the Wayback Machine. Download all four of "
            f"{', '.join(MIMEDB_V2_FILES)} from {MIMEDB_V2_PAGE} in a browser and "
            f"put them in data/raw/mimedb/{MIMEDB_V2_DIR}/. "
            f"Until then the loader falls back to the v1.0 files beside that "
            f"directory. Provenance and checksums: "
            f"data/raw/mimedb/{MIMEDB_V2_DIR}/PROVENANCE.md",
        )
    if absent:
        log(
            f"  MANUAL: {len(absent)} of {len(MIMEDB_V2_FILES)} v2.0 files absent — "
            f"place them in data/raw/mimedb/{MIMEDB_V2_DIR}/ from {MIMEDB_V2_PAGE}"
        )
    return not absent


def fetch_mimedb(args) -> None:
    log("MiMeDB")

    # v2.0 first: it is the release the loader reads, and it is operator-placed.
    # v1.0 is still recorded either way — it is the documented fallback, and on a
    # fresh clone it is the only release any client can actually obtain.
    if fetch_mimedb_v2(args):
        log("  v2.0 complete; v1.0 below is the loader's fallback")

    missing = [
        n
        for n, _ in MIMEDB_FILES
        if not (RAW / "mimedb" / n).exists() or not (RAW / "mimedb" / n).stat().st_size
    ]
    if not missing and not args.force:
        for name, ts in MIMEDB_FILES:
            path = RAW / "mimedb" / name
            log(f"  cached mimedb/{name} (v1.0 fallback, {path.stat().st_size:,} B)")
            record_file(
                "mimedb",
                path,
                wayback_url(ts, MIMEDB_ORIGIN + name),
                "cached",
                note="v1.0 fallback; origin is Cloudflare-challenged, so the "
                "bytes come from a Wayback snapshot",
            )
        return

    # One origin probe, to record the exact blocker rather than assume it.
    probe = MIMEDB_ORIGIN + MIMEDB_FILES[0][0]
    try:
        r = request("GET", probe, timeout=60, stream=True, allow_redirects=True)
        blocker = f"HTTP {r.status_code} from {r.headers.get('server')}" + (
            f", cf-mitigated: {r.headers.get('cf-mitigated')}"
            if r.headers.get("cf-mitigated")
            else ""
        )
        direct_ok = r.status_code == 200 and "text/html" not in r.headers.get(
            "Content-Type", ""
        )
        r.close()
    except requests.RequestException as exc:
        blocker, direct_ok = f"{type(exc).__name__}: {exc}", False
    log(f"  origin probe: {blocker}")

    for name, ts in MIMEDB_FILES:
        if direct_ok:
            got = download(
                "mimedb", MIMEDB_ORIGIN + name, name, timeout=600, force=args.force
            )
            if got:
                continue
        # archive.org rate-limits snapshot playback (HTTP 429); space these out.
        wb = wayback_url(ts, MIMEDB_ORIGIN + name)
        if download("mimedb", wb, name, timeout=600, force=args.force) is None:
            record_problem(
                "mimedb",
                name,
                MIMEDB_ORIGIN + name,
                "manual",
                f"origin blocked ({blocker}) and the Wayback snapshot "
                f"{wb} did not deliver. Download {name} by hand from "
                f"{MIMEDB_V2_PAGE} into data/raw/mimedb/. This is the "
                f"v1.0 fallback; prefer placing the v2.0 files in "
                f"data/raw/mimedb/{MIMEDB_V2_DIR}/ instead.",
            )
        time.sleep(8)

    for name, why in MIMEDB_SKIPPED.items():
        record_problem("mimedb", name, MIMEDB_ORIGIN + name, "skipped", why)


# NJC19 is deposited on Dryad under CC0, but Dryad now gates file downloads
# behind a JavaScript "Validating..." interstitial and its v2 API answers
# 401 ("must have current bearer token") — so the deposit is manual. The same
# network, in tabular form, is Supplementary Table 1 of the Scientific Data
# paper, which Europe PMC serves without a challenge; that is the primary file.
NJC19_PMCID = "PMC7320173"
NJC19_SUPP_ZIP = (
    f"https://www.ebi.ac.uk/europepmc/webservices/rest/{NJC19_PMCID}/supplementaryFiles"
)
NJC19_DRYAD_DOI = "10.5061/dryad.dr7sqv9v8"
NJC19_DRYAD_FILES = [
    ("NJC19_network_data_and_code.zip", 342682),
    ("Microbial_taxonomic_data_for_NJC19_construction.zip", 342683),
    ("Microbial_taxonomic_data_for_NJC19_validation.zip", 342680),
    ("Cytoscape_file_for_NJC19_visualization.zip", 342681),
    ("README.pdf", 342679),
]


def fetch_njc19(args) -> None:
    log("NJC19")
    arc = download(
        "njc19",
        NJC19_SUPP_ZIP,
        f"{NJC19_PMCID}_supplementaryFiles.zip",
        timeout=300,
        force=args.force,
    )
    if arc:
        extract_zip_members(
            "njc19",
            arc,
            RAW / "njc19",
            NJC19_SUPP_ZIP,
            lambda n: n.lower().endswith(".xlsx"),
            args.force,
        )

    # One attempt at the Dryad deposit; it is the richer artefact (JSON network
    # plus the conversion code) but is not machine-fetchable.
    for name, fid in NJC19_DRYAD_FILES:
        url = f"https://datadryad.org/api/v2/files/{fid}/download"
        dest = RAW / "njc19" / name
        if dest.exists() and dest.stat().st_size and not args.force:
            log(f"  operator-supplied njc19/{name} ({dest.stat().st_size:,} B)")
            record_file(
                "njc19",
                dest,
                url,
                "manual-present",
                note="placed by hand; datadryad.org gates downloads",
            )
            continue
        record_problem(
            "njc19",
            name,
            url,
            "manual",
            "datadryad.org serves a JavaScript 'Validating...' interstitial on "
            "/downloads/file_stream and its v2 API answers 401 'Unauthorized, "
            "must have current bearer token'. Download by hand from "
            f"https://datadryad.org/dataset/doi:{NJC19_DRYAD_DOI} into "
            "data/raw/njc19/ if the JSON network is wanted; Supplementary Table 1 "
            "above carries the same 8,224 events in tabular form.",
        )
    log(f"  Dryad deposit doi:{NJC19_DRYAD_DOI} recorded as manual (JS interstitial)")


# aiddlab.com is NOT down — its TLS certificate has expired. Every request dies
# at the handshake with "certificate verify failed: certificate has expired",
# and http:// 301-redirects to https, so there is no plain-HTTP route around it.
# Behind that handshake the server still answers 200 on all eight files its
# Download page lists (confirmed 2026-09-03 with `curl -k`). Fetching them would
# mean turning off certificate verification, which is a security decision for
# the operator, not for this script — so the six files the Wayback Machine never
# captured are recorded as `manual` with the exact command that gets them.
# Of the eight, only substanceInfo was ever archived.
MASI_ORIGIN = "https://www.aiddlab.com/MASI/downloadFiles/"
MASI_WAYBACK = [
    ("MASI_v1.0_download_substanceInfo.txt", "20240728033042"),
    ("MASI_v1.0_download_substanceInfo.xlsx", "20240420002051"),
]
MASI_UNARCHIVED = [
    "MASI_v1.0_download_microbeSubstanceInteractionRecords_ver20200928.txt",
    "MASI_v1.0_download_microbeSubstanceInteractionRecords_ver20200928.xlsx",
    "MASI_v1.0_download_microbesInfo.txt",
    "MASI_v1.0_download_microbesInfo.xlsx",
    "MASI_v1.0_download_microbeDiseaseAssociationRecords.txt",
    "MASI_v1.0_download_microbeDiseaseAssociationRecords.xlsx",
]


def fetch_masi(args) -> None:
    log("MASI")

    have = [
        n
        for n, _ in MASI_WAYBACK
        if (RAW / "masi" / n).exists() and (RAW / "masi" / n).stat().st_size
    ]
    if len(have) == len(MASI_WAYBACK) and not args.force:
        for name, ts in MASI_WAYBACK:
            path = RAW / "masi" / name
            log(f"  cached masi/{name} ({path.stat().st_size:,} B)")
            record_file(
                "masi",
                path,
                wayback_url(ts, MASI_ORIGIN + name),
                "cached",
                note="origin host is gone; bytes come from a Wayback snapshot",
            )
    else:
        # One origin probe, then the archive; the host has not completed a TLS
        # handshake since at least 2024, so there is nothing to retry against.
        try:
            r = request("GET", "https://www.aiddlab.com/MASI/download.html", timeout=25)
            log(f"  origin: HTTP {r.status_code}, {len(r.content):,} B")
        except requests.RequestException as exc:
            log(f"  origin: {type(exc).__name__}: {exc}")
            log("  (expired certificate, not a dead host — see MASI_UNARCHIVED)")
        for name, ts in MASI_WAYBACK:
            # Wayback captured the pre-redirect http:// URLs; playback keys on those.
            wb = wayback_url(ts, MASI_ORIGIN.replace("https://", "http://") + name)
            if download("masi", wb, name, timeout=180, force=args.force) is None:
                record_problem(
                    "masi",
                    name,
                    MASI_ORIGIN + name,
                    "manual",
                    f"origin gone and Wayback playback {wb} failed",
                )
            time.sleep(8)

    # The interaction tables are the reason to want MASI at all, and they are
    # simply not recoverable — recorded so the gap is visible in the manifest
    # rather than looking like an oversight.
    for name in MASI_UNARCHIVED:
        record_problem(
            "masi",
            name,
            MASI_ORIGIN + name,
            "manual",
            "the origin serves this file but its TLS certificate has expired, and "
            "the Wayback Machine never captured it (a domain-wide CDX query over "
            "aiddlab.com/MASI* returns only substanceInfo). Fetch it deliberately, "
            "accepting the expired certificate:  curl -k -A 'Mozilla/5.0' -o "
            f"data/raw/masi/{name} '{MASI_ORIGIN + name}'  — or download it in a "
            "browser from https://www.aiddlab.com/MASI/download.html after "
            "accepting the certificate warning. Until then the measured "
            "drug-microbe evidence in data/raw/drug_screens/ is the substitute.",
        )


# The measured drug x taxon evidence behind MASI's curated edges. Maier's
# supplementary comes from Europe PMC (nature.com's static-content host answers
# 403 for this article's MediaObjects); Zimmermann's comes from nature.com,
# because Europe PMC has no supplementary package for PMC6597290 and the PMC
# article's own /bin/ path is behind a reCAPTCHA interstitial.
MAIER_PMCID = "PMC6108420"
MAIER_SUPP_ZIP = (
    f"https://www.ebi.ac.uk/europepmc/webservices/rest/{MAIER_PMCID}/supplementaryFiles"
)
ZIMMERMANN_SUPP = (
    "https://static-content.springer.com/esm/"
    "art%3A10.1038%2Fs41586-019-1291-3/MediaObjects/"
    "41586_2019_1291_MOESM1_ESM.xlsx"
)


def fetch_drug_screens(args) -> None:
    log("Drug x taxon screens (Maier 2018, Zimmermann 2019)")

    arc = download(
        "drug_screens",
        MAIER_SUPP_ZIP,
        f"maier2018/{MAIER_PMCID}_supplementaryFiles.zip",
        timeout=300,
        force=args.force,
    )
    if arc:
        # Only the tables and the guide that names them; the zip also holds the
        # article's figure renderings, which are not data.
        extract_zip_members(
            "drug_screens",
            arc,
            RAW / "drug_screens" / "maier2018",
            MAIER_SUPP_ZIP,
            lambda n: n.lower().endswith(".xlsx") or "TABLE_INFORMATION_GUIDE" in n,
            args.force,
        )

    download(
        "drug_screens",
        ZIMMERMANN_SUPP,
        "zimmermann2019/41586_2019_1291_MOESM1_ESM.xlsx",
        timeout=600,
        force=args.force,
    )


def note_pubmed(args) -> None:
    log("PubMed / PubChem: no bulk fetch by design (ids come from the other sources)")
    record(
        "pubmed_pubchem/_decision",
        url=None,
        path=None,
        bytes=None,
        sha256=None,
        status="not-fetched",
        error="By design: no bulk download. Paper ids (PMIDs) arrive with "
        "BugSigDB/Disbiome/CARD rows and compound ids via KEGG "
        "/conv/compound/pubchem; per-id lookups happen at build time if at all.",
    )


SOURCES = {
    "ncbi": fetch_ncbi,
    "bugsigdb": fetch_bugsigdb,
    "disbiome": fetch_disbiome,
    "hmdb": fetch_hmdb,
    "card": fetch_card,
    "reactome": fetch_reactome,
    "kegg": fetch_kegg,
    "chembl": fetch_chembl,
    "gutmdisorder": fetch_gutmdisorder,
    "mimedb": fetch_mimedb,
    "njc19": fetch_njc19,
    "masi": fetch_masi,
    "drug_screens": fetch_drug_screens,
    "pubmed": note_pubmed,
}


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--chembl-sqlite",
        action="store_true",
        help="also fetch the 5.76 GB chembl_37_sqlite.tar.gz",
    )
    ap.add_argument(
        "--only",
        action="append",
        choices=sorted(SOURCES),
        help="run only this source (repeatable)",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="re-download even when a complete file is present",
    )
    args = ap.parse_args()

    RAW.mkdir(parents=True, exist_ok=True)
    load_manifest()

    failures = []
    for name in args.only or list(SOURCES):
        try:
            SOURCES[name](args)
        except Exception as exc:  # a dead source must not abort the rest
            log(f"!! {name} raised {type(exc).__name__}: {exc}")
            record_problem(name, "_source", "", "error", f"{type(exc).__name__}: {exc}")
            failures.append(name)

    save_manifest()
    log(
        f"manifest written to {MANIFEST.relative_to(ROOT)} "
        f"({len(MANIFEST_DATA)} entries)"
    )
    if failures:
        log(f"sources that raised: {', '.join(failures)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
