"""Offline self-check for update_runtimes.py. Run: python scripts/test_update_runtimes.py"""
import copy
import json
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import update_runtimes as u  # noqa: E402

MANIFEST = u.DEFAULT_CONFIG


def test_vkey():
    assert u.vkey("8.4.27-1") == (8, 4, 27)
    assert u.vkey("v2.11.9") == (2, 11, 9)
    assert sorted(["10.11.19", "10.9.1", "10.11.2"], key=u.vkey) == ["10.9.1", "10.11.2", "10.11.19"]
    assert u.is_prerelease("12.3.1 RC") and not u.is_prerelease("12.3.3")


def test_line_of():
    assert u.line_of("8.4.27", 2) == "8.4"
    assert u.line_of("18.6.1", 1) == "18"
    assert u.line_of("v2.11.9", 1) == "2"


def test_crlf_strip():
    assert u.vkey("8.4.27\r") == (8, 4, 27)
    assert u.url_version("https://x/y/php-8.4.23-fpm-linux-x86_64.tar.gz\r") == "8.4.23"
    assert u.first_sha256("A" * 64 + "  file.zip\r\n") == "a" * 64


def test_roundtrip():
    assert u.dump_manifest(*u.load_manifest(MANIFEST)) == MANIFEST.read_bytes()


def test_http_headers():
    seen = {}

    class R:
        status = 206
        def read(self): return b""
        def __enter__(self): return self
        def __exit__(self, *a): pass

    def fake(req, timeout):
        seen["method"], seen["ua"], seen["range"] = req.get_method(), req.get_header("User-agent"), req.get_header("Range")
        return R()

    orig, urllib.request.urlopen = urllib.request.urlopen, fake
    try:
        assert u.http_get("https://cdn.example/x.zip\r", range0=True)[0] == 206
    finally:
        urllib.request.urlopen = orig
    assert seen["method"] == "GET" and seen["ua"].startswith("Mozilla/5.0") and seen["range"] == "bytes=0-0"


def _manifest():
    return {"binaries": {
        "mysql": {"versions": [{"id": "mysql-8.4", "version": "8.4.11", "selected": True, "eol": False, "lts": True,
                                "display_name": "MySQL 8.4.11 LTS",
                                "urls": {"windowsX64": "https://m/mysql-8.4.11-winx64.zip",
                                         "windowsArm64": "https://m/mysql-8.4.11-winx64.zip",
                                         "macOSX64": "https://m/mysql-8.4.11-macos15-x86_64.tar.gz"},
                                "checksums": {"windowsX64": "a" * 64, "windowsArm64": "a" * 64, "macOSX64": "b" * 64}}]},
        "caddy": {"versions": [{"id": "caddy-2.11.7", "version": "2.11.7", "selected": True,
                                "display_name": "Caddy 2.11.7 (Latest)",
                                "urls": {"linuxX64": "https://c/caddy_2.11.7_linux_amd64.tar.gz"},
                                "checksums": {"linuxX64": "c" * 64}}]},
    }}


def _with_stub(comp, files=None, versions=(), exc=None):
    spec = u.COMPONENTS[comp]
    saved = dict(spec)

    def f(line):
        if exc:
            raise exc
        return files
    spec["files"], spec["versions"] = f, lambda: list(versions)
    return saved


def test_status():
    m = _manifest()
    saved_m = _with_stub("mysql", {"windowsX64": {"version": "8.4.13", "url": "https://m/mysql-8.4.13-winx64.zip"}},
                         ["8.4.13", "9.7.4"])
    saved_c = _with_stub("caddy", exc=RuntimeError("down"))
    try:
        cands = u.check(m)
    finally:
        u.COMPONENTS["mysql"].update(saved_m)
        u.COMPONENTS["caddy"].update(saved_c)
    st = {(c["component"], c["status"]) for c in cands}
    assert ("mysql", "patch") in st and ("mysql", "new-line") in st and ("caddy", "failed") in st
    newline = next(c for c in cands if c["status"] == "new-line")
    assert newline["line"] == "9.7"  # highest new line only
    patch = next(c for c in cands if c["status"] == "patch")
    assert patch["stale"] == ["windowsX64"]


def test_new_line_detection():
    m = _manifest()
    saved = _with_stub("mysql", {"windowsX64": {"version": "8.4.11", "url": "https://m/mysql-8.4.11-winx64.zip"}},
                       ["8.4.11", "8.0.46"])
    try:
        cands = u.check(m, only={"mysql"})
    finally:
        u.COMPONENTS["mysql"].update(saved)
    assert [c["status"] for c in cands] == ["up-to-date"]


def test_platform_lag():
    entry = {"version": "8.5.12", "urls": {"windowsX64": "https://g/php-8.5.12-Win32-vs17-x64.zip",
                                            "linuxX64": "https://g/php-8.5.8-fpm-linux-x86_64.tar.gz"}}
    files = {"windowsX64": {"version": "8.5.12"}, "linuxX64": {"version": "8.5.9"}}
    assert u.stale_platforms(entry, u.COMPONENTS["php"], files) == ["linuxX64"]


def _got(ver, sha, name, plats):
    return {p: {"version": ver, "url": f"https://up/{name}", "path": Path(name), "sha": sha} for p in plats}


def test_stage_in_place():
    m = _manifest()
    before = copy.deepcopy(m["binaries"]["mysql"]["versions"][0])
    c = {"component": "mysql", "entry_index": 0, "current": "8.4.11"}
    got = _got("8.4.13", "d" * 64, "mysql-8.4.13-winx64.zip", ["windowsX64"])
    u.stage_update(m, c, got, {"windowsX64": "https://mirror/mysql-8.4.13-winx64.zip"})
    e = m["binaries"]["mysql"]["versions"][0]
    for k in ("id", "selected", "eol", "lts"):
        assert e[k] == before[k]
    assert e["version"] == "8.4.13" and e["display_name"] == "MySQL 8.4.13 LTS"
    assert e["urls"]["windowsArm64"] == e["urls"]["windowsX64"] == "https://mirror/mysql-8.4.13-winx64.zip"
    assert e["checksums"]["windowsArm64"] == "d" * 64
    assert set(e["urls"]) == set(before["urls"])  # no new keys
    assert e["urls"]["macOSX64"] == before["urls"]["macOSX64"]  # untouched platform kept


def test_platform_split():
    m = _manifest()
    c = {"component": "mysql", "entry_index": 0, "current": "8.4.11"}
    got = _got("8.4.13", "d" * 64, "x.tar.gz", ["linuxX64"])
    u.stage_update(m, c, got, {"linuxX64": "https://x"})
    assert not any(k.startswith("linux") for k in m["binaries"]["mysql"]["versions"][0]["urls"])


def test_stage_caddy_promote():
    m = _manifest()
    c = {"component": "caddy", "entry_index": 0, "current": "2.11.7"}
    got = _got("2.11.9", "e" * 64, "caddy_2.11.9_linux_amd64.tar.gz", ["linuxX64"])
    u.stage_update(m, c, got, {"linuxX64": "https://c/caddy_2.11.9_linux_amd64.tar.gz"})
    vs = m["binaries"]["caddy"]["versions"]
    assert [v["selected"] for v in vs] == [True, False]
    assert vs[0]["id"] == "caddy-2.11.9" and vs[0]["display_name"] == "Caddy 2.11.9 (Latest)"
    assert vs[1]["display_name"] == "Caddy 2.11.7"


def test_sha512_rejected():
    for bad in ("a" * 128, "a" * 63, "z" * 64):
        try:
            u.check_sha256(bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted {bad[:10]}")
    assert u.check_sha256("A" * 64) == "a" * 64


def test_mariadb_anchor():
    name = "mariadb-11.8.10-linux-systemd-x86_64.tar.gz"
    files = [{"file_name": name + ".asc", "checksum": {"sha256sum": "1" * 64}},
             {"file_name": name, "checksum": {"sha256sum": "2" * 64}}]
    assert u.mariadb_sha(files, name) == "2" * 64


def test_php_split():
    win = {"8.5": {"version": "8.5.13-1", "nts-vs17-x64": {}, "ts-vs17-x64": {"zip": {"path": "php-8.5.13-1-Win32-vs17-x64.zip", "sha256": "f" * 64}}}}
    names = [f"php-8.5.{p}-fpm-{s}.tar.gz" for p in (8, 9) for s in u.STATIC_PLAT.values()] + ["php-8.5.10-fpm-linux-x86_64.tar.gz"]
    files = u.php_files(win, names, "8.5")
    assert u.headline_of(files) == "8.5.13"
    assert files["linuxX64"]["url"].endswith("php-8.5.9-fpm-linux-x86_64.tar.gz")  # 8.5.10 incomplete set -> skipped
    win74 = {"7.4": {"version": "7.4.33", "ts-vc15-x64": {"zip": {"path": "php-7.4.33-Win32-vc15-x64.zip", "sha256": "f" * 64}}}}
    assert u.php_files(win74, [], "7.4")["windowsX64"]["version"] == "7.4.33"
    try:
        u.php_files(win, [], "7.3")
        raise AssertionError("expected NotListed")
    except u.NotListed:
        pass


def test_mariadb_windows_reuse():
    m = {"binaries": {"mariadb": {"versions": [{
        "id": "mariadb-11.8", "version": "11.8.10", "selected": True, "display_name": "MariaDB 11.8.10",
        "urls": {"linuxX64": "https://a/mariadb-11.8.10-linux-systemd-x86_64.tar.gz",
                 "windowsX64": "https://a/mariadb-11.8.10-winx64.zip",
                 "windowsArm64": "https://a/mariadb-11.8.10-winx64.zip"},
        "checksums": {"linuxX64": "1" * 64, "windowsX64": "2" * 64, "windowsArm64": "2" * 64}}]}}}
    c = {"component": "mariadb", "entry_index": 0, "current": "11.8.10"}
    got = _got("11.8.11", "3" * 64, "mariadb-11.8.11-winx64.zip", ["windowsX64"])
    u.stage_update(m, c, got, {"windowsX64": "https://a/mariadb-11.8.11-winx64.zip"})
    e = m["binaries"]["mariadb"]["versions"][0]
    assert e["urls"]["windowsArm64"] == e["urls"]["windowsX64"] == "https://a/mariadb-11.8.11-winx64.zip"
    assert e["checksums"]["windowsArm64"] == e["checksums"]["windowsX64"] == "3" * 64
    assert e["checksums"]["linuxX64"] == "1" * 64  # Linux not stale -> untouched


def test_mirrored_stage_keeps_upstream_as_fallback():
    m = _manifest()
    c = {"component": "mysql", "entry_index": 0, "current": "8.4.11"}
    got = _got("8.4.13", "d" * 64, "mysql-8.4.13-winx64.zip", ["windowsX64"])  # upstream url https://up/...
    u.stage_update(m, c, got, {"windowsX64": u.MIRROR_PREFIX + "mysql-8.4.13/mysql-8.4.13-winx64.zip"})
    e = m["binaries"]["mysql"]["versions"][0]
    assert e["fallback_urls"]["windowsX64"] == "https://up/mysql-8.4.13-winx64.zip"
    assert e["fallback_urls"]["windowsArm64"] == e["fallback_urls"]["windowsX64"]  # reuse follows
    assert "macOSX64" not in e["fallback_urls"]  # untouched platform gets none
    # Direct-upstream staging (url == upstream) records no fallback
    m2 = _manifest()
    c2 = {"component": "caddy", "entry_index": 0, "current": "2.11.7"}
    got2 = _got("2.11.9", "e" * 64, "caddy_2.11.9_linux_amd64.tar.gz", ["linuxX64"])
    u.stage_update(m2, c2, got2, {"linuxX64": "https://up/caddy_2.11.9_linux_amd64.tar.gz"})
    assert "fallback_urls" not in m2["binaries"]["caddy"]["versions"][0]


def test_all_urls_includes_fallbacks():
    m = {"binaries": {"x": {"versions": [
        {"urls": {"linuxX64": "https://mirror/a"}, "checksums": {"linuxX64": "a" * 64},
         "fallback_urls": {"linuxX64": "https://up/a"}},
        {"url": "https://mirror/b", "checksum": "b" * 64, "fallback_url": "https://up/b"}]}}}
    assert u.all_urls(m) == {"https://mirror/a": "a" * 64, "https://up/a": "a" * 64,
                             "https://mirror/b": "b" * 64, "https://up/b": "b" * 64}


def test_glibc_ceiling():
    import io
    import tarfile
    with tempfile.TemporaryDirectory() as d:
        def make(name, payload):
            p = Path(d) / name
            with tarfile.open(p, "w:gz") as t:
                info = tarfile.TarInfo("pg/bin/initdb")
                info.size = len(payload)
                t.addfile(info, io.BytesIO(payload))
            return p
        old = make("old.tar.gz", b"\x7fELF....GLIBC_2.17..GLIBC_2.34..")
        new = make("new.tar.gz", b"\x7fELF....GLIBC_2.34..GLIBC_2.36..")
        text = make("txt.tar.gz", b"README mentions GLIBC_2.99")  # not ELF: ignored
        assert u.max_glibc(old) == (2, 34) and u.glibc_ok("linuxX64", old)
        assert u.max_glibc(new) == (2, 36) and not u.glibc_ok("linuxArm64", new)
        assert u.glibc_ok("windowsX64", new)  # only Linux is checked
        assert u.max_glibc(text) is None and u.glibc_ok("linuxX64", text)


def test_verify_single_default():
    m = {"binaries": {"x": {"versions": [{"id": "a", "selected": True}, {"id": "b", "selected": True}]}}}
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "m.json"
        p.write_text(json.dumps(m))
        errs = u.verify(p, urls=[])
    assert any("2 selected" in e for e in errs)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ok")
