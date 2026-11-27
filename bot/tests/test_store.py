"""TokenStore tracking: job watches, persistence and legacy migration."""

from sokhan_bot.store import TokenStore


def test_track_roundtrip(tmp_path):
    store = TokenStore(str(tmp_path / "store.json"))

    assert store.tracked() == []
    store.track("job-1", 42)
    store.track("job-2", 43)

    entries = {job_id: (chat_id, since) for job_id, chat_id, since in store.tracked()}
    assert set(entries) == {"job-1", "job-2"}
    assert entries["job-1"][0] == 42
    assert entries["job-2"][0] == 43

    store.untrack("job-1")
    assert [job_id for job_id, _, _ in store.tracked()] == ["job-2"]

    store.untrack("job-2")
    assert store.tracked() == []


def test_store_persists_across_instances(tmp_path):
    path = str(tmp_path / "store.json")
    first = TokenStore(path)
    first.set(7, "token-abc")
    first.track("job-9", 7)

    second = TokenStore(path)
    assert second.get(7) == "token-abc"
    assert second.tracked() == [("job-9", 7, second.tracked()[0][2])]


def test_legacy_token_file_is_migrated(tmp_path):
    # v1.0 wrote a plain {chat_id: token} map; the new format must load it.
    path = tmp_path / "store.json"
    path.write_text('{"123": "legacy-token"}', encoding="utf-8")

    store = TokenStore(str(path))
    assert store.get(123) == "legacy-token"
    assert store.tracked() == []

    # And saving must not corrupt the migrated data.
    store.track("job-x", 123)
    reloaded = TokenStore(str(path))
    assert reloaded.get(123) == "legacy-token"
    assert [job_id for job_id, _, _ in reloaded.tracked()] == ["job-x"]


def test_forget_drops_a_token_and_persists(tmp_path):
    path = str(tmp_path / "store.json")
    store = TokenStore(path)
    store.set(42, "old-token")

    store.forget(42)
    store.forget(99)  # unknown chats are a no-op

    assert store.get(42) is None
    assert TokenStore(path).get(42) is None
