from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


DEFAULT_POLICY = {
    "automatic_enabled": False,
    "retention_days": 30,
    "capacity_limit_bytes": 5 * 1024 * 1024 * 1024,
    "interval": "daily",
    "cleanup_scope": "audio_only",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def init_storage_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS storage_policy (
          id INTEGER PRIMARY KEY CHECK (id = 1),
          automatic_enabled INTEGER NOT NULL DEFAULT 0,
          retention_days INTEGER NOT NULL DEFAULT 30,
          capacity_limit_bytes INTEGER NOT NULL DEFAULT 5368709120,
          interval TEXT NOT NULL DEFAULT 'daily',
          cleanup_scope TEXT NOT NULL DEFAULT 'audio_only',
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS storage_cleanup_runs (
          id TEXT PRIMARY KEY,
          trigger TEXT NOT NULL,
          status TEXT NOT NULL,
          files_removed INTEGER NOT NULL DEFAULT 0,
          jobs_removed INTEGER NOT NULL DEFAULT 0,
          jobs_preserved INTEGER NOT NULL DEFAULT 0,
          bytes_freed INTEGER NOT NULL DEFAULT 0,
          started_at TEXT NOT NULL,
          completed_at TEXT NOT NULL,
          message TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_storage_cleanup_runs_completed_at
          ON storage_cleanup_runs(completed_at DESC);
        """
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO storage_policy
          (id, automatic_enabled, retention_days, capacity_limit_bytes, interval, cleanup_scope, updated_at)
        VALUES (1, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(DEFAULT_POLICY["automatic_enabled"]),
            DEFAULT_POLICY["retention_days"],
            DEFAULT_POLICY["capacity_limit_bytes"],
            DEFAULT_POLICY["interval"],
            DEFAULT_POLICY["cleanup_scope"],
            iso_now(),
        ),
    )


def read_policy(connection: sqlite3.Connection) -> dict[str, Any]:
    row = connection.execute("SELECT * FROM storage_policy WHERE id=1").fetchone()
    if row is None:
        raise RuntimeError("存储策略尚未初始化")
    policy = dict(row)
    policy["automatic_enabled"] = bool(policy["automatic_enabled"])
    return policy


def write_policy(connection: sqlite3.Connection, policy: dict[str, Any]) -> dict[str, Any]:
    connection.execute(
        """
        UPDATE storage_policy
        SET automatic_enabled=?, retention_days=?, capacity_limit_bytes=?, interval=?, cleanup_scope=?, updated_at=?
        WHERE id=1
        """,
        (
            int(bool(policy["automatic_enabled"])),
            int(policy["retention_days"]),
            int(policy["capacity_limit_bytes"]),
            str(policy["interval"]),
            str(policy["cleanup_scope"]),
            iso_now(),
        ),
    )
    return read_policy(connection)


def safe_audio_path(audio_path: str | None, root: Path, audio_root: Path) -> Path | None:
    if not audio_path:
        return None
    try:
        path = (root / audio_path).resolve()
        path.relative_to(audio_root.resolve())
    except (OSError, ValueError):
        return None
    return path if path.is_file() else None


def _parse_created_at(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _audio_entries(rows: list[sqlite3.Row], root: Path, audio_root: Path) -> list[dict[str, Any]]:
    grouped: dict[Path, dict[str, Any]] = {}
    for row in rows:
        path = safe_audio_path(row["audio_path"], root, audio_root)
        if path is None:
            continue
        created_at = _parse_created_at(row["created_at"])
        entry = grouped.setdefault(
            path,
            {"path": path, "size": path.stat().st_size, "created_at": created_at, "job_ids": []},
        )
        entry["created_at"] = min(entry["created_at"], created_at)
        entry["job_ids"].append(row["id"])
    return sorted(grouped.values(), key=lambda item: (item["created_at"], str(item["path"])))


def storage_snapshot(
    connection: sqlite3.Connection,
    root: Path,
    audio_root: Path,
    *,
    cleanup_history_limit: int = 5,
) -> dict[str, Any]:
    rows = connection.execute("SELECT * FROM jobs ORDER BY created_at").fetchall()
    entries = _audio_entries(rows, root, audio_root)
    audio_bytes = sum(item["size"] for item in entries)
    directory_bytes = 0
    directory_files = 0
    if audio_root.is_dir():
        for path in audio_root.rglob("*"):
            if not path.is_file():
                continue
            try:
                directory_bytes += path.stat().st_size
                directory_files += 1
            except OSError:
                continue
    policy = read_policy(connection)
    history = [dict(row) for row in connection.execute(
        "SELECT * FROM storage_cleanup_runs ORDER BY completed_at DESC LIMIT ?",
        (max(1, min(cleanup_history_limit, 20)),),
    ).fetchall()]
    last_auto = connection.execute(
        "SELECT completed_at FROM storage_cleanup_runs WHERE trigger='automatic' AND status='completed' ORDER BY completed_at DESC LIMIT 1"
    ).fetchone()
    next_cleanup_at: str | None = None
    if policy["automatic_enabled"]:
        if last_auto:
            interval = timedelta(days=1 if policy["interval"] == "daily" else 7)
            next_cleanup_at = (_parse_created_at(last_auto["completed_at"]) + interval).isoformat()
        else:
            next_cleanup_at = iso_now()
    return {
        "policy": policy,
        "usage": {
            "job_count": len(rows),
            "audio_count": len(entries),
            "audio_bytes": audio_bytes,
            "directory_file_count": directory_files,
            "directory_bytes": directory_bytes,
            "unmanaged_bytes": max(0, directory_bytes - audio_bytes),
            "missing_audio_count": sum(1 for row in rows if row["audio_path"] and safe_audio_path(row["audio_path"], root, audio_root) is None),
            "oldest_audio_at": entries[0]["created_at"].isoformat() if entries else None,
            "capacity_ratio": min(1, audio_bytes / policy["capacity_limit_bytes"]) if policy["capacity_limit_bytes"] else 0,
        },
        "next_cleanup_at": next_cleanup_at,
        "cleanup_history": history,
        "storage_path": str(audio_root.resolve()),
    }


def build_cleanup_plan(
    connection: sqlite3.Connection,
    root: Path,
    audio_root: Path,
    policy: dict[str, Any] | None = None,
    *,
    current_time: datetime | None = None,
) -> dict[str, Any]:
    policy = policy or read_policy(connection)
    current_time = current_time or utc_now()
    rows = connection.execute("SELECT * FROM jobs ORDER BY created_at").fetchall()
    entries = _audio_entries(rows, root, audio_root)
    retention_cutoff = current_time - timedelta(days=int(policy["retention_days"]))
    selected_paths: set[Path] = {
        item["path"] for item in entries if item["created_at"] < retention_cutoff
    }
    age_job_ids = {
        row["id"] for row in rows if _parse_created_at(row["created_at"]) < retention_cutoff
    }
    audio_bytes_before = sum(item["size"] for item in entries)
    bytes_after_age = sum(item["size"] for item in entries if item["path"] not in selected_paths)
    capacity_limit = int(policy["capacity_limit_bytes"])
    if bytes_after_age > capacity_limit:
        for item in entries:
            if item["path"] in selected_paths:
                continue
            selected_paths.add(item["path"])
            bytes_after_age -= item["size"]
            if bytes_after_age <= capacity_limit:
                break
    selected_entries = [item for item in entries if item["path"] in selected_paths]
    audio_job_ids = {job_id for item in selected_entries for job_id in item["job_ids"]}
    jobs_to_remove = age_job_ids | audio_job_ids if policy["cleanup_scope"] == "jobs" else set()
    return {
        "files": selected_entries,
        "file_count": len(selected_entries),
        "affected_job_ids": sorted(audio_job_ids),
        "jobs_to_remove": sorted(jobs_to_remove),
        "jobs_preserved": len(audio_job_ids) if policy["cleanup_scope"] == "audio_only" else 0,
        "bytes_before": audio_bytes_before,
        "bytes_to_free": sum(item["size"] for item in selected_entries),
        "bytes_after": max(0, audio_bytes_before - sum(item["size"] for item in selected_entries)),
        "retention_cutoff": retention_cutoff.isoformat(),
        "cleanup_scope": policy["cleanup_scope"],
    }


def cleanup_preview(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "file_count": plan["file_count"],
        "job_count": len(plan["jobs_to_remove"]),
        "jobs_preserved": plan["jobs_preserved"],
        "bytes_before": plan["bytes_before"],
        "bytes_to_free": plan["bytes_to_free"],
        "bytes_after": plan["bytes_after"],
        "retention_cutoff": plan["retention_cutoff"],
        "cleanup_scope": plan["cleanup_scope"],
    }


def execute_cleanup(
    connection: sqlite3.Connection,
    root: Path,
    audio_root: Path,
    *,
    trigger: str,
    run_id: str,
    current_time: datetime | None = None,
) -> dict[str, Any]:
    started_at = iso_now()
    policy = read_policy(connection)
    plan = build_cleanup_plan(connection, root, audio_root, policy, current_time=current_time)
    removed_paths: set[Path] = set()
    bytes_freed = 0
    errors: list[str] = []
    for item in plan["files"]:
        path = item["path"]
        try:
            size = path.stat().st_size
            path.unlink()
            bytes_freed += size
            removed_paths.add(path)
        except FileNotFoundError:
            removed_paths.add(path)
        except OSError as exc:
            errors.append(f"{path.name}: {exc}")

    successful_audio_job_ids = {
        job_id
        for item in plan["files"]
        if item["path"] in removed_paths
        for job_id in item["job_ids"]
    }
    jobs_removed = 0
    jobs_preserved = 0
    cleaned_at = iso_now()
    if policy["cleanup_scope"] == "jobs":
        removable = set(plan["jobs_to_remove"])
        failed_audio_job_ids = set(plan["affected_job_ids"]) - successful_audio_job_ids
        removable -= failed_audio_job_ids
        if removable:
            connection.executemany("DELETE FROM jobs WHERE id=?", [(job_id,) for job_id in removable])
        jobs_removed = len(removable)
    elif successful_audio_job_ids:
        connection.executemany(
            "UPDATE jobs SET audio_path=NULL, audio_cleaned_at=?, audio_cleanup_reason=? WHERE id=?",
            [(cleaned_at, trigger, job_id) for job_id in successful_audio_job_ids],
        )
        jobs_preserved = len(successful_audio_job_ids)

    status = "completed" if not errors else "partial"
    message = "没有符合当前策略的音频" if not plan["file_count"] and not jobs_removed else "清理完成"
    if errors:
        message = f"部分文件清理失败：{'；'.join(errors[:3])}"
    completed_at = iso_now()
    connection.execute(
        """
        INSERT INTO storage_cleanup_runs
          (id, trigger, status, files_removed, jobs_removed, jobs_preserved, bytes_freed, started_at, completed_at, message)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            trigger,
            status,
            len(removed_paths),
            jobs_removed,
            jobs_preserved,
            bytes_freed,
            started_at,
            completed_at,
            message,
        ),
    )
    return {
        "id": run_id,
        "trigger": trigger,
        "status": status,
        "files_removed": len(removed_paths),
        "jobs_removed": jobs_removed,
        "jobs_preserved": jobs_preserved,
        "bytes_freed": bytes_freed,
        "started_at": started_at,
        "completed_at": completed_at,
        "message": message,
    }


def automatic_cleanup_due(connection: sqlite3.Connection, current_time: datetime | None = None) -> bool:
    policy = read_policy(connection)
    if not policy["automatic_enabled"]:
        return False
    row = connection.execute(
        "SELECT completed_at FROM storage_cleanup_runs WHERE trigger='automatic' AND status='completed' ORDER BY completed_at DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return True
    interval = timedelta(days=1 if policy["interval"] == "daily" else 7)
    return (current_time or utc_now()) >= _parse_created_at(row["completed_at"]) + interval
