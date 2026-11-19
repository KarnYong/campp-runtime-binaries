#!/usr/bin/env python3
"""Check upstream for newer CAMPP runtimes and (optionally) apply them to runtime-config.json.

    python scripts/update_runtimes.py                     # check-only report (default, changes nothing)
    python scripts/update_runtimes.py --apply [--only php,mysql] [--yes]
    python scripts/update_runtimes.py --verify [--deep]
    python scripts/update_runtimes.py --mirror-existing [--only postgresql] [--yes]   # one-time, see mirror_existing()

Exit codes: 0 ok, 1 something failed, 2 usage / unreadable manifest.
Rules this follows: campp-runtime-binaries/CLAUDE.md. Contract: specs/001-runtime-update-checker/contracts/cli.md.
Stdlib only; needs `gh` (authenticated) and `git` on PATH.
"""
import argparse
import functools
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

UA = "Mozilla/5.0"
REPO = "KarnYong/campp-runtime-binaries"
MIRROR_PREFIX = f"https://github.com/{REPO}/releases/download/"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "campp" / "src-tauri" / "runtime-config.json"


class NotListed(Exception):
    """Upstream no longer lists this line (EOL) - reported as up-to-date, not a failure."""


# ---------------------------------------------------------------- helpers

def http_get(url, range0=False, retries=2):
    """GET only (MySQL CDN / GitHub reject HEAD), browser UA. Returns (status, body)."""
    headers = {"User-Agent": UA}
    if range0:
        headers["Range"] = "bytes=0-0"
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url.strip(), headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            if e.code < 500 or attempt == retries:
                return e.code, b""
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == retries:
                raise
        time.sleep(1 + attempt)


def get_text(url):
    status, body = http_get(url)
    if status != 200:
        raise RuntimeError(f"HTTP {status} for {url}")
    return body.decode("utf-8", "replace").replace("\r", "").strip()


def get_json(url):
    return json.loads(get_text(url))


def run(cmd):
    out = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding="utf-8").stdout
    return out.replace("\r", "").strip()


def gh_json(path):
    return json.loads(run(["gh", "api", path]))


def vkey(v):
    """'8.4.27-1' -> (8, 4, 27); 'v2.11.9' -> (2, 11, 9)."""
    m = re.match(r"v?(\d+(?:\.\d+)*)", str(v).strip())
    return tuple(int(x) for x in m.group(1).split(".")) if m else ()


def is_prerelease(v):
    return bool(re.search(r"(rc|beta|alpha|dev|preview)", str(v), re.I))


def line_of(v, width):
    return ".".join(str(x) for x in vkey(v)[:width])


def url_version(url):
    m = re.search(r"\d+\.\d+\.\d+", url.strip().rsplit("/", 1)[-1])
    return m.group(0) if m else None


def check_sha256(s):
    s = (s or "").strip().lower()
    if not SHA256_RE.match(s):  # rejects SHA-512 (128 hex) and partial grabs
        raise ValueError(f"not a SHA-256: {s[:20]}... ({len(s)} chars)")
    return s


def first_sha256(text):
    m = re.search(r"\b[0-9a-f]{64}\b", text.lower())
    if not m:
        raise ValueError("no SHA-256 in sidecar")
    return m.group(0)


def load_manifest(path):
    raw = Path(path).read_bytes()
    nl = "\r\n" if b"\r\n" in raw else "\n"
    return json.loads(raw.decode("utf-8")), nl


def dump_manifest(data, nl):
    return (json.dumps(data, indent=2, ensure_ascii=False) + "\n").replace("\n", nl).encode("utf-8")


def sha256_download(url, dest_dir):
    name = url.strip().rsplit("/", 1)[-1]
    path = Path(dest_dir) / name
    h = hashlib.sha256()
    req = urllib.request.Request(url.strip(), headers={"User-Agent": UA}, method="GET")
    with urllib.request.urlopen(req, timeout=300) as r, open(path, "wb") as f:
        while chunk := r.read(1 << 20):
            h.update(chunk)
            f.write(chunk)
    return path, check_sha256(h.hexdigest())


# ---------------------------------------------------------------- upstream sources
# Each files_<c>(line) -> {platform: {"version", "url", "sha256"?, "sha256_url"?}}  (may be a subset)
# Each versions_<c>() -> stable versions/lines seen upstream (for new-line detection).

def _gh_stable_tags(repo):
    rels = gh_json(f"repos/{repo}/releases?per_page=100")  # ponytail: newest 100 only; enough for every tracked line
    return [r for r in rels if not r["prerelease"] and not r["draft"] and not is_prerelease(r["tag_name"])]


@functools.lru_cache(None)
def _caddy():
    return _gh_stable_tags("caddyserver/caddy")


CADDY_SUFFIX = {"windowsX64": "windows_amd64.zip", "windowsArm64": "windows_arm64.zip",
                "linuxX64": "linux_amd64.tar.gz", "linuxArm64": "linux_arm64.tar.gz",
                "macOSX64": "mac_amd64.tar.gz", "macOSArm64": "mac_arm64.tar.gz"}


def files_caddy(line):
    vs = [r["tag_name"].lstrip("v") for r in _caddy() if line_of(r["tag_name"], 1) == line]
    v = max(vs, key=vkey)
    # sha256 deliberately None: caddy's checksums.txt is SHA-512
    return {p: {"version": v, "url": f"https://github.com/caddyserver/caddy/releases/download/v{v}/caddy_{v}_{s}"}
            for p, s in CADDY_SUFFIX.items()}


@functools.lru_cache(None)
def _php_win():
    return get_json("https://downloads.php.net/~windows/releases/releases.json")


@functools.lru_cache(None)
def _php_static():
    return tuple(x["name"] for x in get_json("https://dl.static-php.dev/static-php-cli/bulk/?format=json"))


STATIC_PLAT = {"linuxX64": "linux-x86_64", "linuxArm64": "linux-aarch64",
               "macOSX64": "macos-x86_64", "macOSArm64": "macos-aarch64"}


def php_files(win, static_names, line):
    """Pure: Windows from php.net releases.json, Linux/macOS from static-php (patches may differ)."""
    if line not in win:
        raise NotListed("not listed (EOL)")
    rel = win[line]
    key = next(k for k in rel if re.match(r"^ts-v[cs]\d+-x64$", k))
    zip_ = rel[key]["zip"]
    out = {"windowsX64": {"version": rel["version"].split("-")[0],
                          "url": f"https://downloads.php.net/~windows/releases/{zip_['path']}",
                          "sha256": zip_["sha256"]}}
    names = set(static_names)
    cands = {m.group(1) for n in names if (m := re.match(r"php-(\d+\.\d+\.\d+)-fpm-", n)) and line_of(m.group(1), 2) == line}
    full = [v for v in cands if all(f"php-{v}-fpm-{s}.tar.gz" in names for s in STATIC_PLAT.values())]
    if full:
        v = max(full, key=vkey)
        for p, s in STATIC_PLAT.items():
            out[p] = {"version": v, "url": f"https://dl.static-php.dev/static-php-cli/bulk/php-{v}-fpm-{s}.tar.gz"}
    return out


def files_php(line):
    return php_files(_php_win(), _php_static(), line)


@functools.lru_cache(None)
def _mysql_tags():
    out = run(["git", "ls-remote", "--tags", "https://github.com/mysql/mysql-server", "mysql-*"])
    return [m.group(1) for ln in out.splitlines() if (m := re.search(r"refs/tags/mysql-(\d+\.\d+\.\d+)$", ln))]


def _ok(url):
    return http_get(url, range0=True)[0] in (200, 206)


def files_mysql(line):
    cdn = f"https://cdn.mysql.com/Downloads/MySQL-{line}/"
    for v in sorted((t for t in _mysql_tags() if line_of(t, 2) == line), key=vkey, reverse=True)[:3]:
        if not _ok(f"{cdn}mysql-{v}-winx64.zip"):
            continue  # tag exists before CDN files do
        out = {"windowsX64": {"version": v, "url": f"{cdn}mysql-{v}-winx64.zip"}}
        # probe each arch on its own: 8.4.13 dropped macOS x86_64 but still ships arm64
        for plat, arch in (("macOSX64", "x86_64"), ("macOSArm64", "arm64")):
            for osv in ("macos26", "macos15", "macos14"):
                if _ok(f"{cdn}mysql-{v}-{osv}-{arch}.tar.gz"):
                    out[plat] = {"version": v, "url": f"{cdn}mysql-{v}-{osv}-{arch}.tar.gz"}
                    break
        return out
    raise RuntimeError(f"no CDN files for any recent {line} tag")


def mariadb_sha(files, name):
    """Anchor to the exact tarball name - sha256sums lists the .asc signature too."""
    return next(f["checksum"]["sha256sum"] for f in files if f["file_name"] == name)


def files_mariadb(line):
    rels = get_json(f"https://downloads.mariadb.org/rest-api/mariadb/{line}/")["releases"]
    stable = {k: r for k, r in rels.items() if not is_prerelease(r["release_name"])}
    if not stable:
        raise NotListed("no stable release")
    v = max(stable, key=vkey)
    files = stable[v].get("files", [])
    name = f"mariadb-{v}-linux-systemd-x86_64.tar.gz"
    out = {"linuxX64": {"version": v, "sha256": mariadb_sha(files, name),
                        "url": f"https://archive.mariadb.org/mariadb-{v}/bintar-linux-systemd-x86_64/{name}"}}
    win = f"mariadb-{v}-winx64.zip"
    if any(f["file_name"] == win for f in files):  # Windows build may lag; omit rather than fail the line
        out["windowsX64"] = {"version": v, "sha256": mariadb_sha(files, win),
                             "url": f"https://archive.mariadb.org/mariadb-{v}/winx64-packages/{win}"}
    return out


@functools.lru_cache(None)
def _pg():
    return _gh_stable_tags("theseus-rs/postgresql-binaries")


PG_TARGET = {"windowsX64": "x86_64-pc-windows-msvc.zip", "linuxX64": "x86_64-unknown-linux-gnu.tar.gz",
             "linuxArm64": "aarch64-unknown-linux-gnu.tar.gz", "macOSX64": "x86_64-apple-darwin.tar.gz",
             "macOSArm64": "aarch64-apple-darwin.tar.gz"}


def files_postgresql(line):
    out = {}
    rels = sorted((r for r in _pg() if line_of(r["tag_name"], 1) == line), key=lambda r: vkey(r["tag_name"]), reverse=True)
    for p, t in PG_TARGET.items():  # resolve per platform: linux builds can lag
        for r in rels:
            name = f"postgresql-{r['tag_name']}-{t}"
            assets = {a["name"]: a["browser_download_url"] for a in r["assets"]}
            if name in assets:
                out[p] = {"version": r["tag_name"], "url": assets[name], "sha256_url": assets.get(name + ".sha256")}
                break
    return out


def files_phpmyadmin(line):
    vs = [r["version"] for r in get_json("https://www.phpmyadmin.net/home_page/version.json")["releases"]
          if line_of(r["version"], 2) == line and not is_prerelease(r["version"])]
    if not vs:
        raise NotListed("not listed")
    v = max(vs, key=vkey)
    url = f"https://files.phpmyadmin.net/phpMyAdmin/{v}/phpMyAdmin-{v}-all-languages.zip"
    return {"url": {"version": v, "url": url, "sha256_url": url + ".sha256"}}


@functools.lru_cache(None)
def _adminer():
    return _gh_stable_tags("vrana/adminer")


def files_adminer(line):
    v = max((r["tag_name"].lstrip("v") for r in _adminer() if line_of(r["tag_name"], 1) == line), key=vkey)
    return {"url": {"version": v, "url": f"https://github.com/vrana/adminer/releases/download/v{v}/adminer-{v}-en.php"}}


@functools.lru_cache(None)
def _ngrok():
    vs = re.findall(r"\b(3\.\d+\.\d+)\b", get_text("https://ngrok.com/docs/agent/changelog"))
    if not vs:
        raise RuntimeError("changelog unparseable")
    return vs


def files_ngrok(line):
    return {"version": {"version": max((v for v in _ngrok() if line_of(v, 1) == line), key=vkey)}}


def _versions_mariadb():
    majors = get_json("https://downloads.mariadb.org/rest-api/mariadb/")["major_releases"]
    return [m["release_id"] for m in majors if m["release_status"] == "Stable"]


ALL6 = ["windowsX64", "windowsArm64", "linuxX64", "linuxArm64", "macOSX64", "macOSArm64"]

COMPONENTS = {
    # width: version parts that define a release line; Caddy is per-version (append + promote) so width 1.
    "caddy": dict(width=1, mirrored=False, platforms=["windowsX64", "windowsArm64", "linuxX64", "macOSX64", "macOSArm64"],
                  reuse={}, files=files_caddy, versions=lambda: [r["tag_name"] for r in _caddy()]),
    "php": dict(width=2, mirrored=True, platforms=ALL6, reuse={"windowsArm64": "windowsX64"},
                files=files_php, versions=lambda: list(_php_win())),
    "mysql": dict(width=2, mirrored=True, platforms=["windowsX64", "windowsArm64", "macOSX64", "macOSArm64"],
                  reuse={"windowsArm64": "windowsX64"}, files=files_mysql, versions=_mysql_tags),
    "mariadb": dict(width=2, mirrored=True, platforms=["linuxX64", "windowsX64", "windowsArm64"],
                    reuse={"windowsArm64": "windowsX64"},
                    files=files_mariadb, versions=_versions_mariadb),
    "phpmyadmin": dict(width=2, mirrored=True, single_file=True, platforms=["url"], reuse={}, files=files_phpmyadmin,
                       versions=lambda: [r["version"] for r in get_json("https://www.phpmyadmin.net/home_page/version.json")["releases"]]),
    "postgresql": dict(width=1, mirrored=True, platforms=list(PG_TARGET), reuse={},
                       files=files_postgresql, versions=lambda: [r["tag_name"] for r in _pg()]),
    "adminer": dict(width=1, mirrored=True, single_file=True, platforms=["url"], reuse={},
                    files=files_adminer, versions=lambda: [r["tag_name"] for r in _adminer()]),
    "ngrok": dict(width=1, mirrored=False, report_only=True, platforms=[], reuse={},
                  files=files_ngrok, versions=_ngrok),
}

HEADLINE = ("windowsX64", "url", "linuxX64", "version")


# ---------------------------------------------------------------- check

def current_urls(entry, spec):
    return {"url": entry["url"]} if spec.get("single_file") else dict(entry.get("urls", {}))


def stale_platforms(entry, spec, files):
    """Platforms already in the entry (never add keys) whose upstream file is newer."""
    if spec.get("report_only"):
        return ["version"] if vkey(files["version"]["version"]) > vkey(entry["version"]) else []
    cur = current_urls(entry, spec)
    return [p for p, f in files.items() if p in cur and p in spec["platforms"]
            and vkey(f["version"]) > vkey(url_version(cur[p]) or entry["version"])]


def headline_of(files):
    return next(files[p]["version"] for p in HEADLINE if p in files)


def check(data, only=None):
    cands = []
    for comp, spec in COMPONENTS.items():
        if only and comp not in only or comp not in data["binaries"]:
            continue
        entries = list(enumerate(data["binaries"][comp]["versions"]))
        if comp == "caddy":
            entries = [(i, e) for i, e in entries if e.get("selected")]
        lines = []
        for idx, e in entries:
            line = line_of(e["version"], spec["width"])
            lines.append(line)
            c = dict(component=comp, line=line, entry_index=idx, current=e["version"], latest="-",
                     status="failed", reason="", files={}, stale=[])
            try:
                files = spec["files"](line)
                if not files:
                    raise RuntimeError("no upstream files found")
                c["files"], c["latest"] = files, headline_of(files)
                others = sorted({f["version"] for f in files.values()} - {c["latest"]}, key=vkey)
                if others:
                    c["latest"] += f" (others {','.join(others)})"
                c["stale"] = stale_platforms(e, spec, files)
                c["status"] = "patch" if c["stale"] else "up-to-date"
            except NotListed as ex:
                c["status"], c["reason"] = "up-to-date", str(ex)
            except Exception as ex:  # one source down must not hide the rest
                c["reason"] = f"{type(ex).__name__}: {ex}"
            cands.append(c)
        try:
            up = [v for v in spec["versions"]() if not is_prerelease(v)]
            top = max(lines, key=vkey) if lines else ""
            newer = [v for v in up if vkey(line_of(v, spec["width"])) > vkey(top)]
            if newer:  # report only the highest new line (FR-012: never added)
                v = max(newer, key=vkey)
                cands.append(dict(component=comp, line=line_of(v, spec["width"]), entry_index=None, current="-",
                                  latest=v, status="new-line", reason="not added", files={}, stale=[]))
        except Exception as ex:
            cands.append(dict(component=comp, line="*", entry_index=None, current="-", latest="-",
                              status="failed", reason=f"line discovery: {ex}", files={}, stale=[]))
    return cands


def print_report(cands):
    rows = [("COMPONENT", "LINE", "CURRENT", "LATEST", "STATUS")]
    for c in cands:
        st = c["status"]
        if st == "failed":
            st = f"failed: {c['reason']}"
        elif st == "new-line":
            st = "new-line (not added)"
        elif st == "patch" and COMPONENTS[c["component"]].get("report_only"):
            st = "patch (report-only, update by hand)"
        elif c["reason"]:
            st += f" ({c['reason']})"
        rows.append((c["component"], c["line"], c["current"], c["latest"], st))
    w = [max(len(r[i]) for r in rows) for i in range(4)]
    for r in rows:
        print("  ".join(r[i].ljust(w[i]) for i in range(4)) + "  " + r[4])


# ---------------------------------------------------------------- apply

# Oldest glibc CAMPP supports on Linux: Ubuntu 22.04 LTS (2.35). PostgreSQL's
# upstream silently moved to 2.36 in Nov 2026 and broke 22.04; never ship that again.
# ponytail: one constant; raise it when 22.04 support is dropped.
GLIBC_CEILING = (2, 35)
_GLIBC_RE = re.compile(rb"GLIBC_2\.(\d+)")


def max_glibc(path):
    """Highest GLIBC_2.x symbol version any ELF file inside a .tar.gz/.zip needs, or None."""
    import tarfile
    import zipfile
    best = None

    def scan(data):
        nonlocal best
        if data[:4] == b"\x7fELF":
            for m in _GLIBC_RE.finditer(data):
                v = (2, int(m.group(1)))
                best = v if best is None or v > best else best

    p = str(path)
    if p.endswith((".tar.gz", ".tgz")):
        with tarfile.open(p, "r:gz") as t:
            for member in t:
                if member.isfile():
                    scan(t.extractfile(member).read())
    elif p.endswith(".zip"):
        with zipfile.ZipFile(p) as z:
            for name in z.namelist():
                if not name.endswith("/"):
                    scan(z.read(name))
    return best


def glibc_ok(platform, path):
    """Linux builds must run on GLIBC_CEILING; other platforms always pass."""
    if not platform.startswith("linux"):
        return True
    need = max_glibc(path)
    return need is None or need <= GLIBC_CEILING


def fetch_candidate(c, tmp):
    """Download + hash every stale platform file. Upstream SHA-256 is a cross-check only.
    A Linux file needing a newer glibc than GLIBC_CEILING is dropped (old file kept)."""
    got, by_url = {}, {}
    for p in c["stale"]:
        f = c["files"][p]
        if f["url"] not in by_url:
            path, sha = sha256_download(f["url"], tmp)
            up = f.get("sha256") or (first_sha256(get_text(f["sha256_url"])) if f.get("sha256_url") else None)
            if up and check_sha256(up) != sha:
                raise RuntimeError(f"upstream checksum mismatch for {f['url']}")
            by_url[f["url"]] = (path, sha)
        path, sha = by_url[f["url"]]
        if not glibc_ok(p, path):
            print(f"  kept old {c['component']} {p}: {f['version']} needs glibc > {'.'.join(map(str, GLIBC_CEILING))}")
            continue
        got[p] = dict(f, path=path, sha=sha)
    return got  # may be empty: every stale file was a Linux build over the ceiling


def stage_update(data, c, got, urls):
    """Mutate the manifest for one candidate. Computes everything first, then assigns."""
    comp, spec = c["component"], COMPONENTS[c["component"]]
    versions = data["binaries"][comp]["versions"]
    entry = versions[c["entry_index"]]
    got = {p: g for p, g in got.items() if p in spec["platforms"]}  # platform split: never write foreign keys
    new_v = max([entry["version"]] + [g["version"] for g in got.values() if g["version"]], key=vkey)
    if spec.get("single_file"):
        entry["url"], entry["checksum"] = urls["url"], got["url"]["sha"]
        if urls["url"] != got["url"]["url"]:
            entry["fallback_url"] = got["url"]["url"]
        entry["version"] = new_v
        entry["display_name"] = entry["display_name"].replace(c["current"], new_v)
        return
    new_urls, new_sums = dict(entry.get("urls", {})), dict(entry.get("checksums", {}))
    new_fb = dict(entry.get("fallback_urls", {}))
    for p, g in got.items():
        if p in new_urls:
            new_urls[p], new_sums[p] = urls[p], g["sha"]
            if urls[p] != g["url"]:  # mirrored: keep upstream as the app's fallback
                new_fb[p] = g["url"]
            else:
                new_fb.pop(p, None)
    for dst, src in spec["reuse"].items():
        if dst in new_urls and src in got:
            new_urls[dst], new_sums[dst] = new_urls[src], new_sums[src]
            if src in new_fb:
                new_fb[dst] = new_fb[src]
    if comp == "caddy":  # documented exception: prepend new version, promote it
        entry["selected"] = False
        entry["display_name"] = entry["display_name"].replace(" (Latest)", "")
        versions.insert(0, {"id": f"caddy-{new_v}", "version": new_v, "selected": True,
                            "display_name": f"Caddy {new_v} (Latest)", "checksums": new_sums, "urls": new_urls})
        return
    entry["display_name"] = entry["display_name"].replace(c["current"], new_v)
    entry["version"], entry["urls"], entry["checksums"] = new_v, new_urls, new_sums
    if new_fb:
        entry["fallback_urls"] = new_fb


def preflight_gh():
    try:
        run(["gh", "auth", "status"])
        push = run(["gh", "api", f"repos/{REPO}", "--jq", ".permissions.push"])
    except subprocess.CalledProcessError as e:
        raise SystemExit(f"gh not ready: {(e.stderr or '').strip()}")
    if push != "true":
        raise SystemExit(f"no push permission on {REPO}")


def _release_assets(tag):
    try:
        rel = gh_json(f"repos/{REPO}/releases/tags/{tag}")
    except subprocess.CalledProcessError:
        return None
    return {a["name"]: a.get("digest") for a in rel["assets"]}


TITLES = {"php": "PHP", "mysql": "MySQL", "phpmyadmin": "phpMyAdmin",
          "postgresql": "PostgreSQL", "mariadb": "MariaDB", "adminer": "Adminer"}


def publish(comp, version, got, yes):
    """Idempotent mirror: create release if missing, upload missing assets, refuse differing ones."""
    tag = f"{comp}-{version}"
    assets = _release_assets(tag)
    if assets is None:
        if not yes and (not sys.stdin.isatty() or input(f"Publish release {tag} to {REPO}? [y/N] ").strip().lower() != "y"):
            raise RuntimeError("publish declined")
        sources = "\n".join(sorted({f"- {g['url']}" for g in got.values()}))
        notes = (f"Mirrored from upstream by scripts/update_runtimes.py. Unmodified upstream files:\n{sources}\n\n"
                 "Source code and licences: see each upstream project.")
        run(["gh", "release", "create", tag, "--repo", REPO, "--title", f"{TITLES[comp]} {version}", "--notes", notes])
        assets = {}
    for g in {g["path"]: g for g in got.values()}.values():
        name = g["path"].name
        if name not in assets:
            run(["gh", "release", "upload", tag, str(g["path"]), "--repo", REPO])
            print(f"  uploaded {tag}/{name}")
        elif assets[name] and assets[name] != f"sha256:{g['sha']}":
            raise RuntimeError(f"asset {name} differs in {tag}")
        else:
            print(f"  already published {tag}/{name}")
    have = _release_assets(tag) or {}
    missing = [g["path"].name for g in got.values() if g["path"].name not in have]
    if missing:
        raise RuntimeError(f"assets missing after upload: {missing}")
    return {p: f"{MIRROR_PREFIX}{tag}/{g['path'].name}" for p, g in got.items()}


def apply(path, data, nl, cands, yes=False, deep=False):
    todo = [c for c in cands if c["status"] == "patch" and not COMPONENTS[c["component"]].get("report_only")]
    if not todo:
        print("nothing to apply")
        return 0
    if any(COMPONENTS[c["component"]]["mirrored"] for c in todo):
        preflight_gh()  # fail before wasting downloads
    failed, changed = 0, []
    with tempfile.TemporaryDirectory(prefix="campp-rt-") as tmp:
        for c in todo:
            comp, spec = c["component"], COMPONENTS[c["component"]]
            try:
                got = fetch_candidate(c, tmp)
                if not got:
                    print(f"  skipped {comp} {c['line']}: only Linux builds over the glibc ceiling were new")
                    continue
                print(f"  downloaded+hashed {comp} {c['line']}: {', '.join(sorted(got))}")
                if spec["mirrored"]:
                    entry_v = data["binaries"][comp]["versions"][c["entry_index"]]["version"]
                    tag_v = max([entry_v] + [g["version"] for g in got.values()], key=vkey)
                    urls = publish(comp, tag_v, got, yes)
                else:
                    urls = {p: g["url"] for p, g in got.items()}
                stage_update(data, c, got, urls)
                changed += list(urls.values())
                print(f"  staged {comp} {c['line']} -> {c['latest']}")
            except Exception as ex:
                failed += 1
                print(f"  FAILED {comp} {c['line']}: {ex}")
    if changed:  # atomic per run: one write of everything that succeeded
        tmp_path = Path(path).with_suffix(".json.tmp")
        tmp_path.write_bytes(dump_manifest(data, nl))
        os.replace(tmp_path, path)
        print(f"  written {path}")
        errors = verify(path, changed, deep)
        for e in errors:
            print(f"  VERIFY FAILED {e}")
        if not errors:
            print("  verified")
        failed += len(errors)
    return 1 if failed else 0



def mirror_existing(path, data, nl, only=None, yes=False, deep=False):
    """One-time move of current entries of mirrored components onto the binaries repo.

    Each upstream file is downloaded and must hash to the checksum already in the
    manifest (so the mirror holds exactly what was verified); the old URL is kept as
    the app's fallback. Idempotent: entries already on the mirror are skipped.
    """
    comps = [c for c, sp in COMPONENTS.items() if sp["mirrored"] and c in data["binaries"] and (not only or c in only)]
    preflight_gh()
    failed, changed = 0, []
    with tempfile.TemporaryDirectory(prefix="campp-mirror-") as tmp:
        for comp in comps:
            spec = COMPONENTS[comp]
            for e in data["binaries"][comp]["versions"]:
                cur = current_urls(e, spec)
                sums = {"url": e.get("checksum")} if spec.get("single_file") else e.get("checksums", {})
                todo = {pl: u for pl, u in cur.items() if not u.startswith(MIRROR_PREFIX)}
                if not todo:
                    continue
                try:
                    got, cache = {}, {}
                    for pl, u in todo.items():
                        if u not in cache:
                            fpath, sha = sha256_download(u, tmp)
                            if sums.get(pl) and sha != sums[pl]:
                                raise RuntimeError(f"{u} hashes to {sha[:12]}..., manifest says {sums[pl][:12]}...")
                            if not glibc_ok(pl, fpath):
                                raise RuntimeError(f"{u} needs glibc > {'.'.join(map(str, GLIBC_CEILING))}; fix the manifest first")
                            cache[u] = (fpath, sha)
                        fpath, sha = cache[u]
                        got[pl] = {"version": url_version(u) or e["version"], "url": u, "path": fpath, "sha": sha}
                    urls = publish(comp, e["version"], got, yes)
                    if spec.get("single_file"):
                        e["fallback_url"], e["url"] = e["url"], urls["url"]
                    else:
                        fb = dict(e.get("fallback_urls", {}))
                        for pl in got:
                            fb[pl], e["urls"][pl] = e["urls"][pl], urls[pl]
                        e["fallback_urls"] = fb
                    changed += list(urls.values())
                    print(f"  mirrored {comp} {e['version']}: {', '.join(sorted(got))}", flush=True)
                except Exception as ex:
                    failed += 1
                    print(f"  FAILED {comp} {e['version']}: {ex}", flush=True)
                finally:
                    for f in Path(tmp).iterdir():  # keep disk use to one entry at a time
                        f.unlink()
    if changed:
        tmp_path = Path(path).with_suffix(".json.tmp")
        tmp_path.write_bytes(dump_manifest(data, nl))
        os.replace(tmp_path, path)
        print(f"  written {path}")
        errors = verify(path, changed, deep)
        for err in errors:
            print(f"  VERIFY FAILED {err}")
        print("  verified" if not errors else "")
        failed += len(errors)
    return 1 if failed else 0


# ---------------------------------------------------------------- verify

def all_urls(data):
    out = {}
    for comp in data["binaries"].values():
        for e in comp["versions"]:
            if "url" in e:
                out[e["url"]] = e.get("checksum")
            for p, u in e.get("urls", {}).items():
                out[u] = e.get("checksums", {}).get(p)
            for p, u in e.get("fallback_urls", {}).items():
                out[u] = e.get("checksums", {}).get(p)
            if "fallback_url" in e:
                out[e["fallback_url"]] = e.get("checksum")
    return out


def verify(path, urls=None, deep=False):
    errors = []
    try:
        data = json.loads(Path(path).read_bytes().decode("utf-8"))
    except Exception as ex:
        return [f"manifest does not parse: {ex}"]
    for name, comp in data["binaries"].items():
        n = sum(1 for e in comp["versions"] if e.get("selected"))
        if n != 1:
            errors.append(f"{name}: {n} selected entries (need exactly 1)")
        for e in comp["versions"]:
            for s in list(e.get("checksums", {}).values()) + ([e["checksum"]] if "checksum" in e else []):
                if not SHA256_RE.match(s or ""):
                    errors.append(f"{e.get('id')}: bad checksum {s!r}")
    sums = all_urls(data)
    targets = list(sums) if urls is None else list(dict.fromkeys(urls))
    with ThreadPoolExecutor(8) as ex:
        for u, ok in zip(targets, ex.map(lambda u: _safe_ok(u), targets)):
            if not ok:
                errors.append(f"unreachable: {u}")
    tags = {}
    for u in targets:
        if u.startswith(MIRROR_PREFIX):
            tag, name = u[len(MIRROR_PREFIX):].split("/", 1)
            tags.setdefault(tag, []).append((name, u))
    for tag, items in tags.items():
        assets = _release_assets(tag) or {}
        for name, u in items:
            d = assets.get(name)
            if d and sums.get(u) and d != f"sha256:{sums[u]}":
                errors.append(f"digest mismatch: {u}")
    if deep:
        with tempfile.TemporaryDirectory(prefix="campp-verify-") as tmp:
            for u in targets:
                if sums.get(u):
                    try:
                        p, sha = sha256_download(u, tmp)
                        p.unlink()
                        if sha != sums[u]:
                            errors.append(f"checksum mismatch (fresh download): {u}")
                    except Exception as e:
                        errors.append(f"download failed: {u}: {e}")
    return errors


def _safe_ok(u):
    try:
        return _ok(u)
    except Exception:
        return False


# ---------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(description="Check/apply upstream runtime updates for CAMPP.")
    ap.add_argument("--config", default=str(DEFAULT_CONFIG))
    ap.add_argument("--only", help="comma list: " + ",".join(COMPONENTS))
    ap.add_argument("--apply", action="store_true", help="download, hash, mirror and write patch candidates")
    ap.add_argument("--yes", action="store_true", help="don't ask before publishing mirror releases")
    ap.add_argument("--verify", action="store_true", help="only verify the manifest")
    ap.add_argument("--deep", action="store_true", help="re-download and re-hash URLs during verify")
    ap.add_argument("--mirror-existing", action="store_true",
                    help="one-time: move current entries of mirrored components to the binaries repo (upstream kept as fallback)")
    a = ap.parse_args(argv)
    only = set(a.only.split(",")) if a.only else None
    if only and only - set(COMPONENTS):
        print(f"unknown component(s): {', '.join(sorted(only - set(COMPONENTS)))}", file=sys.stderr)
        return 2
    try:
        data, nl = load_manifest(a.config)
    except Exception as ex:
        print(f"cannot read manifest {a.config}: {ex}", file=sys.stderr)
        return 2
    if a.mirror_existing:
        return mirror_existing(a.config, data, nl, only, a.yes, a.deep)
    if a.verify and not a.apply:
        errors = verify(a.config, deep=a.deep)
        for e in errors:
            print(e)
        print("verified" if not errors else f"{len(errors)} problem(s)")
        return 1 if errors else 0
    cands = check(data, only)
    print_report(cands)
    rc = 1 if any(c["status"] == "failed" for c in cands) else 0
    if a.apply:
        rc = max(rc, apply(a.config, data, nl, cands, a.yes, a.deep))
    return rc


if __name__ == "__main__":
    sys.exit(main())
