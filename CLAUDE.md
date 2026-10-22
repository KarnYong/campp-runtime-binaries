# CLAUDE.md — Adding / Updating Runtime Versions

How to add a new runtime version to CAMPP end-to-end. Two things get touched:

1. **This repo** (`KarnYong/campp-runtime-binaries`) — hosts the binaries some components mirror (via GitHub Releases).
2. **`campp/src-tauri/runtime-config.json`** — the manifest CAMPP reads to know what to download + verify.

CAMPP downloads a runtime, computes its SHA-256, and **refuses to run if it doesn't match** the checksum in the config. So the whole job is: get the right file, get its *real* SHA-256, point the config at it.

---

## 🔑 The one rule: hash the real bytes

**Never copy a checksum out of an upstream checksum file without confirming its algorithm and that it's for the actual file.** This has broken the build twice:

- **Caddy's `caddy_<v>_checksums.txt` is SHA-512, not SHA-256.** Grabbing 64 hex chars gives you half a SHA-512 → verification fails.
- **MariaDB's `sha256sums.txt` lists the `.tar.gz.asc` signature line before the `.tar.gz` line.** A naive `head -1` grabs the signature's hash, not the tarball's.

Safe checksum sources (genuine per-file SHA-256): PostgreSQL `.sha256` sidecars, MariaDB `sha256sums.txt` *when anchored to the exact `.tar.gz` name*. Everything else: **download the file and run `sha256sum` yourself.** When in doubt, hash the bytes — it's the only source that can't lie.

---

## Per-component cheat sheet

| Component | Upstream source | Platforms | Mirror to this repo? | Checksum source |
|---|---|---|---|---|
| **PHP** | Win: `downloads.php.net/~windows/releases/` (moves to `/archives/`); Linux+macOS: `dl.static-php.dev/static-php-cli/bulk/` | Win x64 + Linux/macOS x64/arm64 (no Win arm64) | **Yes** — tag `php-<winpatch>` | hash yourself |
| **MySQL** | `cdn.mysql.com/Downloads/MySQL-8.0/…` (see note) | **Win + macOS only** | **Yes** — tag `mysql-<ver>` | hash yourself |
| **phpMyAdmin** | `phpmyadmin.net` | universal zip | **Yes** — tag `phpmyadmin-<ver>` | hash yourself |
| **Caddy** | `github.com/caddyserver/caddy/releases` | all 5 | No — direct URL | ⚠️ checksums.txt is **SHA-512** → hash yourself |
| **MariaDB** | `archive.mariadb.org` | **Linux only** (LTS lines x86_64 only — no aarch64 bintar) | No — direct URL | `sha256sums.txt`, anchor to exact `.tar.gz` |
| **PostgreSQL** | `github.com/theseus-rs/postgresql-binaries/releases` | all 5 | No — direct URL | `.sha256` sidecar (real SHA-256) |
| **Adminer** | `github.com/vrana/adminer/releases` | single php file | No — direct URL | hash yourself |
| **ngrok** | `bin.ngrok.com` | all 5 | No — direct URL | n/a (no checksum field) |

**DB platform split (keep it):** MySQL serves Windows + macOS, MariaDB serves Linux. PostgreSQL serves all five.

### Component notes
- **PHP patch mismatch is normal.** Windows (php.net) and Linux/macOS (static-php.dev) ship different patch numbers; static-php lags. One config entry can carry different patches per platform (e.g. Win 8.4.25, Linux/mac 8.4.23). Set `version` to the Windows patch.
- **MySQL download is fussy.** `dev.mysql.com/get/…` and HEAD requests are blocked (Oracle edge / datacenter IPs). Download with a GET + browser UA straight from the CDN:
  `curl -sL -A "Mozilla/5.0" "https://cdn.mysql.com/Downloads/MySQL-8.0/<file>" -o <file>`
  macOS builds are tagged by OS (`macos15-x86_64`, `macos15-arm64`) — confirm the exact suffix before downloading. Windows has no arm64 build; reuse the x64 zip for `windowsArm64` (same URL + same checksum).
- **Caddy filenames:** `caddy_<v>_windows_amd64.zip`, `_windows_arm64.zip`, `_linux_amd64.tar.gz`, `_mac_amd64.tar.gz`, `_mac_arm64.tar.gz`.

---

## Workflow

### A) Direct-upstream components (Caddy, MariaDB, PostgreSQL, Adminer, ngrok)
No upload. Just get real SHA-256s and add the config entry pointing at the upstream URL.

```bash
# Example: hash a file yourself (the always-safe method)
curl -sL -A "Mozilla/5.0" "<upstream-url>" -o /tmp/f && sha256sum /tmp/f

# PostgreSQL — trust the sidecar (real SHA-256):
curl -sL "<...>/postgresql-<v>-<target>.tar.gz.sha256" | grep -oiE '[0-9a-f]{64}' | head -1

# MariaDB — anchor to the exact tarball, NOT the .asc line:
curl -sL "https://archive.mariadb.org/mariadb-<v>/bintar-linux-systemd-x86_64/sha256sums.txt" \
  | grep -iE "mariadb-<v>-linux-systemd-x86_64\.tar\.gz$" | grep -oiE '^[0-9a-f]{64}'
```

### B) Mirrored components (PHP, MySQL, phpMyAdmin)
Download from upstream → hash → upload here → point config at this repo.

```bash
# 1. download from upstream (PowerShell Invoke-WebRequest is fine EXCEPT MySQL — see note above)
# 2. hash:
sha256sum <files>
# 3. one release per version, tag matches the config URL (php-<ver> / mysql-<ver> / phpmyadmin-<ver>):
gh release create <tag> --repo KarnYong/campp-runtime-binaries --title "<Name> <ver>" --notes "<...>"
gh release upload <tag> --repo KarnYong/campp-runtime-binaries <file1> <file2> ...
# 4. verify assets landed:
gh release view <tag> --repo KarnYong/campp-runtime-binaries --json assets --jq '.assets[].name'
```

---

## `runtime-config.json` structure

Lives in `campp/src-tauri/runtime-config.json`. Each component has a `versions` array. A version entry:

```json
{
  "id": "php-8.4",                 // stable id, referenced elsewhere
  "version": "8.4.25",             // headline patch (Windows patch for PHP)
  "selected": false,               // exactly ONE per component is true = the default
  "display_name": "PHP 8.4.25 (Active Support)",
  "eol": false,
  "lts": false,
  "checksums": {                   // real SHA-256 per platform key
    "windowsX64": "…", "windowsArm64": "…",
    "linuxX64": "…", "linuxArm64": "…",
    "macOSX64": "…", "macOSArm64": "…"
  },
  "urls": {                        // same keys → download URLs
    "windowsX64": "https://…", ...
  }
}
```

Rules:
- **Platform keys:** `windowsX64`, `windowsArm64`, `linuxX64`, `linuxArm64`, `macOSX64`, `macOSArm64`. **Omit keys a platform doesn't ship** (e.g. MariaDB LTS = `linuxX64` only; MySQL = no `linux*`). The downloader tolerates missing keys.
- **Single-file components** (phpMyAdmin, Adminer) use flat `"checksum"` + `"url"` instead of the `checksums`/`urls` maps.
- **`selected`:** keep exactly one `true` per component. Adding a new version → leave it `false` unless you intend to change the default. (Caddy is the exception where the newest patch is promoted to the selected "Latest".)
- Adding a version = **append** an entry, don't disturb existing defaults.

---

## Always verify before declaring done

```bash
# JSON parses:
python -c "import json; json.load(open('runtime-config.json')); print('ok')"

# Every new URL resolves (note: use GET-range, not HEAD — GitHub/MySQL reject HEAD; strip CR on Windows):
curl -sL --retry 2 -r 0-0 -o /dev/null -w "%{http_code}\n" "<url>"   # expect 200 or 206

# Definitive checksum check: download the real file, sha256sum it, compare to config.
```

⚠️ **Windows CRLF gotcha:** files/URLs read in Bash on this host carry trailing `\r`. Strip with `tr -d '\r'` or `${u%$'\r'}` before feeding to `curl`/comparisons, or you'll get spurious `000` connection failures and false checksum mismatches.
