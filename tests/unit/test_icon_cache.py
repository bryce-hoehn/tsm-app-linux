"""IconCache path handling and its refusal to retry known-missing icons."""

from __future__ import annotations

from tsm.core.services.icon_cache import IconCache


def test_path_for_returns_none_until_the_file_exists(tmp_path):
    cache = IconCache(tmp_path)

    assert cache.path_for("inv_misc_gem_01") is None

    (tmp_path / "inv_misc_gem_01.jpg").write_bytes(b"\xff\xd8jpeg")
    assert cache.path_for("inv_misc_gem_01") == tmp_path / "inv_misc_gem_01.jpg"


def test_path_for_ignores_an_empty_slug(tmp_path):
    assert IconCache(tmp_path).path_for("") is None


def test_ensure_fetched_skips_slugs_already_on_disk(tmp_path):
    """No thread is started when everything is cached, so on_done never fires."""
    (tmp_path / "cached.jpg").write_bytes(b"\xff\xd8jpeg")
    cache = IconCache(tmp_path)
    calls: list[list[str]] = []

    cache.ensure_fetched(["cached"], calls.append)

    assert calls == []


def test_a_failed_slug_is_not_requested_again(tmp_path):
    """One offline miss must not mean a network attempt on every repaint."""
    cache = IconCache(tmp_path)
    cache._missing.add("gone")
    calls: list[list[str]] = []

    cache.ensure_fetched(["gone"], calls.append)

    assert calls == []


def test_worker_records_failures_and_reports_what_arrived(tmp_path, monkeypatch):
    cache = IconCache(tmp_path)

    def boom(*_args, **_kwargs):
        raise OSError("offline")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    fetched: list[list[str]] = []

    cache._worker(["a", "b"], fetched.append)

    assert fetched == [[]]
    assert cache._missing == {"a", "b"}
    assert cache.path_for("a") is None
