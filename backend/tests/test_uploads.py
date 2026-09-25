import io

import pytest

from argus.config import site
from argus.ingest.clips import parse_clip
from argus.uploads import UploadManager, _stem, clip_start_epoch


def test_upload_clip_name_parses_like_a_camera_clip():
    stem = _stem("abc123def0", 125.4)
    clip = parse_clip(stem, site())
    assert clip.camera == "Uabc123def0"
    assert clip.start_t == clip_start_epoch()
    assert clip.end_t - clip.start_t == 126


def test_rejects_non_video_files(tmp_path, monkeypatch):
    monkeypatch.setattr("argus.uploads.UPLOAD_DIR", tmp_path)
    mgr = UploadManager()
    with pytest.raises(ValueError):
        mgr.submit(io.BytesIO(b"hello"), "notes.txt")
    assert mgr.get("../../etc") is None and mgr.get("not-an-id") is None


def test_uploads_are_scored_as_daytime():
    from argus.fusion.score import time_factor
    start = clip_start_epoch()
    assert time_factor(start, site()) == 1.0
    assert time_factor(start + 3600, site()) == 1.0      # an hour-long clip stays in daytime


def test_upload_area_exists_for_fusion():
    assert site().area_name("upload") == "Uploaded clip"


def test_quick_scan_is_recorded_on_the_job(tmp_path, monkeypatch):
    monkeypatch.setattr("argus.uploads.UPLOAD_DIR", tmp_path)
    mgr = UploadManager()
    mgr._queue.put = lambda _id: None          # don't start processing in the test
    job = mgr.submit(io.BytesIO(b"\x00" * 16), "clip.mp4", thorough=False)
    assert job.meta["thorough"] is False
    job2 = mgr.submit(io.BytesIO(b"\x00" * 16), "clip.mp4")
    assert job2.meta["thorough"] is True
