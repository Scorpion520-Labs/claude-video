"""End-to-end routing of --detail through watch.py on a local clip."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

WATCH = Path(__file__).resolve().parent.parent / "skills" / "watch" / "scripts" / "watch.py"


def _run(clip: Path, *args: str, env_extra: dict | None = None) -> str:
    proc = _run_proc(clip, *args, env_extra=env_extra)
    return proc.stdout


def _run_proc(clip: Path, *args: str, env_extra: dict | None = None) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.pop("WATCH_DETAIL", None)
    env.pop("WATCH_OUT_DIR", None)
    with tempfile.TemporaryDirectory(prefix="watch-test-home-") as home:
        env["HOME"] = home
        if env_extra:
            env.update(env_extra)
        proc = subprocess.run(
            [sys.executable, str(WATCH), str(clip), "--no-whisper", *args],
            capture_output=True, text=True, env=env,
        )
    assert proc.returncode == 0, proc.stderr
    return proc


def test_efficient_uses_keyframe_engine(cut_clip: Path):
    out = _run(cut_clip, "--detail", "efficient")
    assert "(keyframe" in out
    assert "**Detail:** efficient" in out


def test_balanced_uses_scene_engine(cut_clip: Path):
    out = _run(cut_clip, "--detail", "balanced")
    assert "(scene" in out
    assert "**Detail:** balanced" in out


def test_token_burner_uses_scene_engine(cut_clip: Path):
    out = _run(cut_clip, "--detail", "token-burner")
    assert "(scene" in out


def test_transcript_skips_frames(cut_clip: Path):
    out = _run(cut_clip, "--detail", "transcript")
    assert "skipped" in out
    assert "frame_0000.jpg" not in out


def test_flag_overrides_env(cut_clip: Path):
    out = _run(cut_clip, "--detail", "efficient", env_extra={"WATCH_DETAIL": "balanced"})
    assert "(keyframe" in out


def test_default_is_balanced(cut_clip: Path):
    out = _run(cut_clip)  # no flag, WATCH_DETAIL cleared
    assert "**Detail:** balanced" in out
    assert "(scene" in out


def test_watch_out_dir_env_creates_run_directory(cut_clip: Path, tmp_path: Path):
    base = tmp_path / "watch-runs"
    proc = _run_proc(cut_clip, "--detail", "transcript", env_extra={"WATCH_OUT_DIR": str(base)})
    marker = "[watch] working dir: "
    line = next(line for line in proc.stderr.splitlines() if line.startswith(marker))
    work_dir = Path(line.removeprefix(marker))
    assert work_dir.parent == base
    assert work_dir.name.startswith("watch-")
    assert work_dir.exists()


def test_out_dir_flag_overrides_watch_out_dir_env(cut_clip: Path, tmp_path: Path):
    explicit = tmp_path / "explicit"
    proc = _run_proc(
        cut_clip,
        "--detail",
        "transcript",
        "--out-dir",
        str(explicit),
        env_extra={"WATCH_OUT_DIR": str(tmp_path / "ignored")},
    )
    assert f"[watch] working dir: {explicit.resolve()}" in proc.stderr


def test_report_is_written_to_work_dir(cut_clip: Path, tmp_path: Path):
    explicit = tmp_path / "watch-run"
    out = _run(cut_clip, "--detail", "transcript", "--out-dir", str(explicit))
    report = explicit / "report.md"
    assert report.exists()
    assert report.read_text(encoding="utf-8") == out
    assert "# watch: video report" in out


def test_timestamps_add_cue_frames_to_detail(cut_clip: Path):
    out = _run(cut_clip, "--detail", "balanced", "--timestamps", "1,3")
    assert "reason=transcript-cue" in out
    assert "reason=scene-change" in out  # detail frames still present (additive)


def test_timestamps_with_transcript_detail_is_cue_only(cut_clip: Path):
    out = _run(cut_clip, "--detail", "transcript", "--timestamps", "1,3")
    assert "reason=transcript-cue" in out
    assert "reason=scene-change" not in out
    assert "reason=keyframe" not in out


def _frame_lines(out: str) -> int:
    return sum(1 for line in out.splitlines() if "/frames/frame_" in line and "(t=" in line)


def test_dedup_collapses_static_by_default(static_clip: Path):
    out = _run(static_clip)  # solid blue → identical frames collapse to one
    assert "near-duplicate" in out
    assert _frame_lines(out) == 1


def test_no_dedup_preserves_static_frames(static_clip: Path):
    out = _run(static_clip, "--no-dedup")
    assert "near-duplicate" not in out
    assert _frame_lines(out) > 1
