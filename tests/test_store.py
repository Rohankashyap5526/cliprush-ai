from app.store import Store, public_video


def test_state_survives_restart_and_interrupted_work_is_failed(tmp_path):
    media = tmp_path / "v.mp4"
    media.write_bytes(b"x")
    path = tmp_path / "state.json"
    s = Store(path)
    s.add_video({"id": "v1", "path": str(media), "status": "processed", "clips": [{"id": "c"}]})
    s.add_video({"id": "v2", "path": str(media), "status": "rendering", "clips": []})
    s.add_video({"id": "v3", "path": str(media), "status": "queued", "clips": []})
    s.new_job({"id": "j1", "status": "rendering"})
    s.new_job({"id": "j2", "status": "completed"})

    s2 = Store(path)  # simulated restart
    assert s2.videos["v1"]["status"] == "processed" and s2.videos["v1"]["clips"] == [{"id": "c"}]
    assert s2.videos["v2"]["status"] == "failed" and s2.videos["v3"]["status"] == "failed"
    assert s2.jobs["j1"]["status"] == "failed" and "restarted" in s2.jobs["j1"]["error"]
    assert s2.jobs["j2"]["status"] == "completed"


def test_videos_with_missing_files_are_dropped(tmp_path):
    path = tmp_path / "state.json"
    s = Store(path)
    s.add_video({"id": "gone", "path": str(tmp_path / "missing.mp4"), "status": "uploaded", "clips": []})
    assert "gone" not in Store(path).videos


def test_corrupt_state_file_does_not_crash(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{not json")
    assert Store(path).videos == {}


def test_public_video_hides_server_path():
    assert "path" not in public_video({"id": "a", "path": "/srv/secret.mp4"})
