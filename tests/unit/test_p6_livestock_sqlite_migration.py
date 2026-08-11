from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from scripts import migrate_p6_livestock_sqlite_to_mysql as migration


def _source(path: Path, *, species: str | None = "cattle", with_value: bool = True) -> Path:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE farm_profile (
            id INTEGER PRIMARY KEY,
            farm_id TEXT UNIQUE NOT NULL,
            name TEXT,
            location TEXT,
            created_at TEXT,
            updated_at TEXT
        );
        CREATE TABLE animal_profile (
            id INTEGER PRIMARY KEY,
            animal_id TEXT UNIQUE NOT NULL,
            farm_id TEXT,
            species TEXT,
            breed TEXT,
            gender TEXT,
            birth_date TEXT,
            note TEXT,
            created_at TEXT,
            updated_at TEXT
        );
        CREATE TABLE body_measurement_record (
            id INTEGER PRIMARY KEY,
            animal_id TEXT NOT NULL,
            measure_date TEXT NOT NULL,
            body_height_cm REAL,
            body_length_cm REAL,
            chest_girth_cm REAL,
            chest_depth_cm REAL,
            chest_width_cm REAL,
            weight_kg REAL,
            source TEXT,
            confidence REAL,
            algorithm_version TEXT,
            measurement_batch_id TEXT,
            note TEXT,
            created_at TEXT
        );
        """
    )
    connection.execute(
        "INSERT INTO farm_profile VALUES (1,?,?,?,?,?)",
        (
            "farm_001",
            "Qinghai Farm",
            "Qinghai",
            "2025-01-01T00:00:00Z",
            "2026-01-01T00:00:00Z",
        ),
    )
    connection.execute(
        "INSERT INTO animal_profile VALUES (1,?,?,?,?,?,?,?,?,?)",
        (
            "yak_032",
            "farm_001",
            species,
            "yak",
            "female",
            "2024-01-01",
            "healthy",
            "2025-01-01T00:00:00Z",
            "2026-01-01T00:00:00Z",
        ),
    )
    connection.execute(
        "INSERT INTO body_measurement_record VALUES "
        "(1,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "yak_032",
            "2026-07-01",
            None,
            None,
            120.0 if with_value else None,
            None,
            None,
            205.0 if with_value else None,
            "manual",
            0.9,
            "v1",
            "batch_001",
            None,
            "2026-07-01T00:00:00Z",
        ),
    )
    connection.commit()
    connection.close()
    return path


def test_build_plan_validates_and_projects_the_full_livestock_domain(tmp_path: Path) -> None:
    source = _source(tmp_path / "legacy.db")
    digest = migration.sha256_file(source)

    plan = migration.build_import_plan(source, digest, 42)

    assert plan.target_owner_id == 42
    assert plan.expected_counts == {
        "farms": 1,
        "animals": 1,
        "measurements": 1,
        "idMaps": 3,
    }
    assert plan.animals[0].animal_id == "yak_032"
    assert plan.measurements[0].chest_girth_cm == migration.Decimal("120.0")


def test_dry_run_requires_exact_hash_and_reports_explicit_owner(tmp_path: Path) -> None:
    source = _source(tmp_path / "legacy.db")
    digest = migration.sha256_file(source)
    report = tmp_path / "report.json"

    exit_code = migration.main(
        [
            "--source",
            str(source),
            "--expected-sha256",
            digest,
            "--target-owner-id",
            "42",
            "--report",
            str(report),
        ]
    )

    assert exit_code == 0
    rendered = report.read_text(encoding="utf-8")
    assert '"mode": "dry-run"' in rendered
    assert '"targetOwnerId": 42' in rendered
    assert '"measurements": 1' in rendered


def test_dirty_species_is_rejected_instead_of_inventing_a_default(tmp_path: Path) -> None:
    source = _source(tmp_path / "legacy.db", species=None)

    with pytest.raises(migration.MigrationError, match="species must not be null"):
        migration.build_import_plan(source, migration.sha256_file(source), 42)


def test_empty_measurement_is_rejected_before_mysql(tmp_path: Path) -> None:
    source = _source(tmp_path / "legacy.db", with_value=False)

    with pytest.raises(migration.MigrationError, match="has no measurement value"):
        migration.build_import_plan(source, migration.sha256_file(source), 42)


def test_apply_requires_an_independent_exact_backup_before_mysql(tmp_path: Path) -> None:
    source = _source(tmp_path / "legacy.db")
    digest = migration.sha256_file(source)

    assert migration.main(
        [
            "--source",
            str(source),
            "--expected-sha256",
            digest,
            "--target-owner-id",
            "42",
            "--apply",
        ]
    ) == 2

    backup = tmp_path / "legacy.backup.db"
    shutil.copyfile(source, backup)
    assert migration.sha256_file(backup) == digest


def test_hash_mismatch_and_invalid_owner_are_refused(tmp_path: Path) -> None:
    source = _source(tmp_path / "legacy.db")

    with pytest.raises(migration.MigrationError, match="does not match"):
        migration.build_import_plan(source, "0" * 64, 42)
    with pytest.raises(migration.MigrationError, match="owner ID must be positive"):
        migration.build_import_plan(source, migration.sha256_file(source), 0)
