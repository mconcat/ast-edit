from pathlib import Path

from scripts import report_teacher_metrics


def test_report_teacher_metrics_writes_per_model_stats(tmp_path, monkeypatch):
    # Point repo_root at a temporary directory.
    monkeypatch.setattr("src.data.schemas.repo_root", lambda: tmp_path)

    traj_root = tmp_path / "trajectories" / "raw"
    traj_root.mkdir(parents=True, exist_ok=True)

    # Create a small trajectory file with a few teacher-labeled steps.
    data = "\n".join(
        [
            '{"task_id":"t1","step":1,"reward":1.0,"teacher":{"model":"m1"}}',
            '{"task_id":"t2","step":1,"reward":0.0,"teacher":{"model":"m1"}}',
            '{"task_id":"t3","step":1,"reward":1.0,"teacher":{"model":"m2"}}',
            '{"task_id":"t4","step":1,"reward":null,"teacher":{"model":"m2"}}',
            '{"task_id":"t5","step":1}',
        ]
    )
    (traj_root / "sample.jsonl").write_text(data, encoding="utf-8")

    out_path = tmp_path / "reports" / "teacher" / "metrics.md"
    report_teacher_metrics.main(
        [
            "--traj-root",
            str(traj_root),
            "--output",
            str(out_path),
        ]
    )

    content = out_path.read_text(encoding="utf-8")

    # One row per model; precision and averages reflect rewards.
    assert "| m1 | 2 | 1 | 0.500 | 0.500 |" in content
    assert "| m2 | 1 | 1 | 1.000 | 1.000 |" in content

