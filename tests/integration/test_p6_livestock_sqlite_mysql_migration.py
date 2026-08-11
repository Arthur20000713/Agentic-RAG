from __future__ import annotations

import shutil
import sqlite3
import uuid
from pathlib import Path

import pytest

from backend.app.db.migrations import init_db
from scripts import migrate_p6_livestock_sqlite_to_mysql as migration
from tests.integration.test_p4_sqlite_mysql_migration import (
    _app_connection,
    _prepare_database,
    _root_connection,
    isolated_mysql,
)


def _create_source(path: Path) -> None:
    connection = sqlite3.connect(path)
    init_db(connection)
    connection.execute(
        "INSERT INTO farm_profile "
        "(farm_id, name, location, created_at, updated_at) VALUES (?,?,?,?,?)",
        (
            "farm_p6",
            "P6 Farm",
            "Qinghai",
            "2025-01-01T00:00:00Z",
            "2026-01-01T00:00:00Z",
        ),
    )
    connection.execute(
        "INSERT INTO animal_profile "
        "(animal_id, farm_id, species, breed, gender, birth_date, note, "
        "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (
            "yak_p6",
            "farm_p6",
            "cattle",
            "yak",
            "female",
            "2024-01-01",
            "healthy",
            "2025-01-01T00:00:00Z",
            "2026-01-01T00:00:00Z",
        ),
    )
    connection.execute(
        "INSERT INTO body_measurement_record "
        "(animal_id, measure_date, chest_girth_cm, weight_kg, source, confidence, "
        "algorithm_version, measurement_batch_id, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (
            "yak_p6",
            "2026-07-01",
            120.0,
            205.0,
            "manual",
            0.9,
            "v1",
            "batch_p6",
            "2026-07-01T00:00:00Z",
        ),
    )
    connection.commit()
    connection.close()


def test_apply_imports_and_reconciles_all_livestock_rows(
    isolated_mysql: tuple[str, int],
    tmp_path: Path,
) -> None:
    host, port = isolated_mysql
    database = "p6_livestock_" + uuid.uuid4().hex[:12]
    _prepare_database(host, port, database)
    migration_file = (
        Path(__file__).parents[2]
        / "java-app"
        / "src"
        / "main"
        / "resources"
        / "db"
        / "migration"
        / "V7__livestock_domain.sql"
    )
    try:
        with _app_connection(host, port, database) as connection:
            cursor = connection.cursor()
            for statement in migration_file.read_text(encoding="utf-8").split(";"):
                if statement.strip():
                    cursor.execute(statement)
            cursor.execute(
                "INSERT INTO sys_user "
                "(username,password_hash,status,security_version,version) "
                "VALUES ('p6-migration-owner','not-used','ENABLED',0,0)"
            )
            target_owner_id = int(cursor.lastrowid)
            cursor.close()

        source = tmp_path / "legacy.db"
        backup = tmp_path / "legacy.backup.db"
        _create_source(source)
        shutil.copyfile(source, backup)
        digest = migration.sha256_file(source)
        plan = migration.build_import_plan(source, digest, target_owner_id)

        with _app_connection(host, port, database) as connection:
            report = migration.apply_import(
                plan,
                backup,
                digest,
                connection,
                lock_timeout_seconds=5,
            )
            cursor = connection.cursor()
            cursor.execute("SELECT owner_id, farm_code FROM farm")
            assert cursor.fetchone() == (target_owner_id, "farm_p6")
            cursor.execute(
                "SELECT a.owner_id, a.animal_code, f.farm_code "
                "FROM animal a JOIN farm f ON f.id=a.farm_id"
            )
            assert cursor.fetchone() == (target_owner_id, "yak_p6", "farm_p6")
            cursor.execute(
                "SELECT m.owner_id, m.chest_girth_cm, m.weight_kg "
                "FROM measurement_record m"
            )
            measurement = cursor.fetchone()
            assert measurement[0] == target_owner_id
            assert str(measurement[1]) == "120.000"
            assert str(measurement[2]) == "205.000"
            cursor.execute(
                "SELECT status FROM legacy_import_run WHERE domain=%s",
                (migration.DOMAIN,),
            )
            assert cursor.fetchone()[0] == "SUCCEEDED"
            cursor.close()

        assert report["importedCounts"] == plan.expected_counts
        assert report["reconciliation"]["countsMatch"] is True
        assert report["reconciliation"]["measurementOrphans"] == 0
    finally:
        with _root_connection(host, port) as root:
            cursor = root.cursor()
            cursor.execute(f"DROP DATABASE IF EXISTS `{database}`")
            cursor.close()


def test_apply_refuses_a_nonempty_target(
    isolated_mysql: tuple[str, int],
    tmp_path: Path,
) -> None:
    host, port = isolated_mysql
    database = "p6_nonempty_" + uuid.uuid4().hex[:12]
    _prepare_database(host, port, database)
    migration_file = (
        Path(__file__).parents[2]
        / "java-app/src/main/resources/db/migration/V7__livestock_domain.sql"
    )
    try:
        with _app_connection(host, port, database) as connection:
            cursor = connection.cursor()
            for statement in migration_file.read_text(encoding="utf-8").split(";"):
                if statement.strip():
                    cursor.execute(statement)
            cursor.execute(
                "INSERT INTO sys_user "
                "(username,password_hash,status,security_version,version) "
                "VALUES ('p6-nonempty-owner','not-used','ENABLED',0,0)"
            )
            owner_id = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO farm (owner_id,farm_code) VALUES (%s,'existing')",
                (owner_id,),
            )
            cursor.close()

        source = tmp_path / "legacy.db"
        backup = tmp_path / "legacy.backup.db"
        _create_source(source)
        shutil.copyfile(source, backup)
        digest = migration.sha256_file(source)
        plan = migration.build_import_plan(source, digest, owner_id)
        with _app_connection(host, port, database) as connection:
            with pytest.raises(migration.MigrationError, match="not empty"):
                migration.apply_import(
                    plan,
                    backup,
                    digest,
                    connection,
                    lock_timeout_seconds=5,
                )
    finally:
        with _root_connection(host, port) as root:
            cursor = root.cursor()
            cursor.execute(f"DROP DATABASE IF EXISTS `{database}`")
            cursor.close()
