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


def test_upload_area_exists_for_fusion():
    assert site().area_name("upload") == "Uploaded clip"
