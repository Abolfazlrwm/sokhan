import pytest
from fastapi.testclient import TestClient
from sokhan.api.body_limit import MULTIPART_OVERHEAD_BYTES
from sokhan.main import create_app

MIB = 1024 * 1024


@pytest.fixture()
def small_cap_client(app, monkeypatch):
    from sokhan.config import get_settings

    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    get_settings.cache_clear()
    with TestClient(create_app()) as test_client:
        yield test_client
    get_settings.cache_clear()


def test_declared_oversized_body_is_rejected_up_front(small_cap_client, auth):
    too_big = b"\0" * (MIB + MULTIPART_OVERHEAD_BYTES + 1)
    response = small_cap_client.post(
        "/jobs", headers=auth, files={"file": ("big.wav", too_big, "audio/wav")}
    )
    assert response.status_code == 413


def test_chunked_oversized_body_is_cut_off_mid_stream(small_cap_client, auth):
    def body():
        for _ in range(4):
            yield b"\0" * MIB

    response = small_cap_client.post(
        "/jobs",
        headers={**auth, "Content-Type": "multipart/form-data; boundary=x"},
        content=body(),
    )
    assert response.status_code == 413


def test_upload_under_the_cap_still_works(
    small_cap_client, auth, wav_bytes, fake_engine, wait_for_job
):
    response = small_cap_client.post(
        "/jobs", headers=auth, files={"file": ("ok.wav", wav_bytes, "audio/wav")}
    )
    assert response.status_code == 201
    job = wait_for_job(small_cap_client, auth, response.json()["id"])
    assert job["status"] == "completed"
