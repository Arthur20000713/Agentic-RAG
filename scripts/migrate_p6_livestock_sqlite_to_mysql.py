"""Offline P6 livestock migration from legacy SQLite to Java-owned MySQL.

The command is dry-run by default. Applying requires an exact source SHA256,
an independent byte-for-byte backup, an explicit enabled target owner, empty
P6 target tables, and ``--apply``. The source is never modified.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

try:
    from scripts.migrate_p4_sqlite_to_mysql import (
        MigrationError,
        _ensure_quiescent_source,
        _fetch_scalar,
        _start_transaction,
        _verify_backup,
        _write_report,
        connect_mysql,
        normalize_sha256,
        parse_legacy_time,
        sha256_file,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from migrate_p4_sqlite_to_mysql import (  # type: ignore[no-redef]
        MigrationError,
        _ensure_quiescent_source,
        _fetch_scalar,
        _start_transaction,
        _verify_backup,
        _write_report,
        connect_mysql,
        normalize_sha256,
        parse_legacy_time,
        sha256_file,
    )


DOMAIN = "P6_LIVESTOCK"
LOCK_NAME = "livestock:p6:sqlite-import"
BUSINESS_ID = re.compile(r"^[A-Za-z0-9._:-]+$")
TARGET_TABLES = ("farm", "animal", "measurement_record")
REQUIRED_COLUMNS = {
    "farm_profile": {"farm_id", "name", "location", "created_at", "updated_at"},
    "animal_profile": {
        "animal_id",
        "farm_id",
        "species",
        "breed",
        "gender",
        "birth_date",
        "note",
        "created_at",
        "updated_at",
    },
    "body_measurement_record": {
        "id",
        "animal_id",
        "measure_date",
        "body_height_cm",
        "body_length_cm",
        "chest_girth_cm",
        "chest_depth_cm",
        "chest_width_cm",
        "weight_kg",
        "source",
        "confidence",
        "algorithm_version",
        "measurement_batch_id",
        "note",
        "created_at",
    },
}


@dataclass(frozen=True)
class LegacyFarm:
    farm_id: str
    name: str | None
    location: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class LegacyAnimal:
    animal_id: str
    farm_id: str | None
    species: str
    breed: str | None
    sex: str | None
    birth_date: date | None
    note: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class LegacyMeasurement:
    source_id: int
    animal_id: str
    measure_date: date
    body_height_cm: Decimal | None
    body_length_cm: Decimal | None
    chest_girth_cm: Decimal | None
    chest_depth_cm: Decimal | None
    chest_width_cm: Decimal | None
    weight_kg: Decimal | None
    source: str | None
    confidence: Decimal | None
    algorithm_version: str | None
    measurement_batch_id: str | None
    note: str | None
    created_at: datetime


@dataclass(frozen=True)
class ImportPlan:
    source_path: Path
    source_sha256: str
    source_size_bytes: int
    target_owner_id: int
    farms: tuple[LegacyFarm, ...]
    animals: tuple[LegacyAnimal, ...]
    measurements: tuple[LegacyMeasurement, ...]

    @property
    def expected_counts(self) -> dict[str, int]:
        return {
            "farms": len(self.farms),
            "animals": len(self.animals),
            "measurements": len(self.measurements),
            "idMaps": len(self.farms) + len(self.animals) + len(self.measurements),
        }


def _text(
    value: Any,
    *,
    field: str,
    maximum: int,
    required: bool = False,
) -> str | None:
    if value is None:
        if required:
            raise MigrationError(f"{field} must not be null")
        return None
    normalized = str(value).strip()
    if not normalized:
        if required:
            raise MigrationError(f"{field} must not be blank")
        return None
    if len(normalized) > maximum:
        raise MigrationError(f"{field} exceeds {maximum} characters")
    return normalized


def _business_id(value: Any, *, field: str) -> str:
    normalized = _text(value, field=field, maximum=128, required=True)
    assert normalized is not None
    if not BUSINESS_ID.fullmatch(normalized):
        raise MigrationError(f"{field} contains unsupported characters")
    return normalized


def _date(value: Any, *, field: str, required: bool = False) -> date | None:
    normalized = _text(value, field=field, maximum=32, required=required)
    if normalized is None:
        return None
    try:
        return date.fromisoformat(normalized)
    except ValueError as exc:
        raise MigrationError(f"{field} contains an invalid ISO date") from exc


def _decimal(value: Any, *, field: str) -> Decimal | None:
    if value is None or not str(value).strip():
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise MigrationError(f"{field} must be numeric") from exc
    if not number.is_finite() or number < 0:
        raise MigrationError(f"{field} must be finite and non-negative")
    if number > Decimal("999999999.999"):
        raise MigrationError(f"{field} exceeds the MySQL DECIMAL(12,3) range")
    return number


def _readonly_connection(path: Path) -> sqlite3.Connection:
    uri = path.resolve().as_uri() + "?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def _validate_schema(connection: sqlite3.Connection) -> None:
    quick_check = connection.execute("PRAGMA quick_check").fetchone()
    if quick_check is None or str(quick_check[0]).lower() != "ok":
        raise MigrationError("SQLite quick_check did not return ok")
    for table, required in REQUIRED_COLUMNS.items():
        columns = {
            str(row[1])
            for row in connection.execute(f"PRAGMA table_info(`{table}`)").fetchall()
        }
        missing = sorted(required - columns)
        if missing:
            raise MigrationError(
                f"SQLite table {table} is missing columns: {', '.join(missing)}"
            )


def build_import_plan(
    source_path: Path,
    expected_sha256: str,
    target_owner_id: int,
) -> ImportPlan:
    if target_owner_id <= 0:
        raise MigrationError("target owner ID must be positive")
    source = source_path.resolve()
    if not source.is_file():
        raise MigrationError("SQLite source does not exist or is not a regular file")
    _ensure_quiescent_source(source)
    actual_sha = sha256_file(source)
    if actual_sha != expected_sha256:
        raise MigrationError("SQLite source SHA256 does not match --expected-sha256")

    with _readonly_connection(source) as connection:
        _validate_schema(connection)
        farms = tuple(_read_farm(row) for row in connection.execute(
            "SELECT farm_id, name, location, created_at, updated_at "
            "FROM farm_profile ORDER BY farm_id"
        ))
        animals = tuple(_read_animal(row) for row in connection.execute(
            "SELECT animal_id, farm_id, species, breed, gender, birth_date, note, "
            "created_at, updated_at FROM animal_profile ORDER BY animal_id"
        ))
        measurements = tuple(_read_measurement(row) for row in connection.execute(
            "SELECT id, animal_id, measure_date, body_height_cm, body_length_cm, "
            "chest_girth_cm, chest_depth_cm, chest_width_cm, weight_kg, source, "
            "confidence, algorithm_version, measurement_batch_id, note, created_at "
            "FROM body_measurement_record ORDER BY id"
        ))

    farm_ids = {item.farm_id for item in farms}
    if len(farm_ids) != len(farms):
        raise MigrationError("farm_profile contains duplicate farm_id values")
    animal_ids = {item.animal_id for item in animals}
    if len(animal_ids) != len(animals):
        raise MigrationError("animal_profile contains duplicate animal_id values")
    for animal in animals:
        if animal.farm_id is not None and animal.farm_id not in farm_ids:
            raise MigrationError(
                f"animal_profile[{animal.animal_id}].farm_id has no farm_profile row"
            )
    for measurement in measurements:
        if measurement.animal_id not in animal_ids:
            raise MigrationError(
                f"body_measurement_record[{measurement.source_id}].animal_id "
                "has no animal_profile row"
            )
    return ImportPlan(
        source,
        actual_sha,
        source.stat().st_size,
        target_owner_id,
        farms,
        animals,
        measurements,
    )


def _read_farm(row: sqlite3.Row) -> LegacyFarm:
    farm_id = _business_id(row["farm_id"], field="farm_profile.farm_id")
    return LegacyFarm(
        farm_id,
        _text(row["name"], field=f"farm_profile[{farm_id}].name", maximum=255),
        _text(row["location"], field=f"farm_profile[{farm_id}].location", maximum=255),
        parse_legacy_time(row["created_at"], field=f"farm_profile[{farm_id}].created_at"),
        parse_legacy_time(row["updated_at"], field=f"farm_profile[{farm_id}].updated_at"),
    )


def _read_animal(row: sqlite3.Row) -> LegacyAnimal:
    animal_id = _business_id(row["animal_id"], field="animal_profile.animal_id")
    birth_date = _date(
        row["birth_date"],
        field=f"animal_profile[{animal_id}].birth_date",
    )
    if birth_date is not None and birth_date > date.today():
        raise MigrationError(f"animal_profile[{animal_id}].birth_date is in the future")
    return LegacyAnimal(
        animal_id,
        _business_id(row["farm_id"], field=f"animal_profile[{animal_id}].farm_id")
        if row["farm_id"] is not None and str(row["farm_id"]).strip()
        else None,
        _text(
            row["species"],
            field=f"animal_profile[{animal_id}].species",
            maximum=64,
            required=True,
        ) or "",
        _text(row["breed"], field=f"animal_profile[{animal_id}].breed", maximum=128),
        _text(row["gender"], field=f"animal_profile[{animal_id}].gender", maximum=32),
        birth_date,
        _text(row["note"], field=f"animal_profile[{animal_id}].note", maximum=1000),
        parse_legacy_time(row["created_at"], field=f"animal_profile[{animal_id}].created_at"),
        parse_legacy_time(row["updated_at"], field=f"animal_profile[{animal_id}].updated_at"),
    )


def _read_measurement(row: sqlite3.Row) -> LegacyMeasurement:
    try:
        source_id = int(row["id"])
    except (TypeError, ValueError) as exc:
        raise MigrationError("body_measurement_record.id must be an integer") from exc
    if source_id <= 0:
        raise MigrationError("body_measurement_record.id must be positive")
    prefix = f"body_measurement_record[{source_id}]"
    values = (
        _decimal(row["body_height_cm"], field=f"{prefix}.body_height_cm"),
        _decimal(row["body_length_cm"], field=f"{prefix}.body_length_cm"),
        _decimal(row["chest_girth_cm"], field=f"{prefix}.chest_girth_cm"),
        _decimal(row["chest_depth_cm"], field=f"{prefix}.chest_depth_cm"),
        _decimal(row["chest_width_cm"], field=f"{prefix}.chest_width_cm"),
        _decimal(row["weight_kg"], field=f"{prefix}.weight_kg"),
    )
    if all(value is None for value in values):
        raise MigrationError(f"{prefix} has no measurement value")
    confidence = _decimal(row["confidence"], field=f"{prefix}.confidence")
    if confidence is not None and confidence > 1:
        raise MigrationError(f"{prefix}.confidence must be between 0 and 1")
    return LegacyMeasurement(
        source_id,
        _business_id(row["animal_id"], field=f"{prefix}.animal_id"),
        _date(row["measure_date"], field=f"{prefix}.measure_date", required=True),  # type: ignore[arg-type]
        *values,
        _text(row["source"], field=f"{prefix}.source", maximum=64),
        confidence,
        _text(row["algorithm_version"], field=f"{prefix}.algorithm_version", maximum=128),
        _text(row["measurement_batch_id"], field=f"{prefix}.measurement_batch_id", maximum=128),
        _text(row["note"], field=f"{prefix}.note", maximum=1000),
        parse_legacy_time(row["created_at"], field=f"{prefix}.created_at"),
    )


def dry_run_report(plan: ImportPlan, backup_sha256: str | None) -> dict[str, Any]:
    return {
        "mode": "dry-run",
        "status": "validated",
        "domain": DOMAIN,
        "source": str(plan.source_path),
        "sourceSha256": plan.source_sha256,
        "backupSha256": backup_sha256,
        "sourceSizeBytes": plan.source_size_bytes,
        "targetOwnerId": plan.target_owner_id,
        "expectedCounts": plan.expected_counts,
    }


def apply_import(
    plan: ImportPlan,
    backup_path: Path,
    backup_sha256: str,
    connection: Any,
    *,
    lock_timeout_seconds: int,
) -> dict[str, Any]:
    run_uuid = str(uuid.uuid4())
    cursor = connection.cursor()
    acquired = False
    try:
        _ensure_quiescent_source(plan.source_path)
        if sha256_file(plan.source_path) != plan.source_sha256:
            raise MigrationError("SQLite source changed before the MySQL transaction")
        _ensure_quiescent_source(backup_path, label="SQLite backup")
        if sha256_file(backup_path) != backup_sha256:
            raise MigrationError("backup changed before the MySQL transaction")
        acquired = _fetch_scalar(
            cursor,
            "SELECT GET_LOCK(%s, %s)",
            (LOCK_NAME, lock_timeout_seconds),
        ) == 1
        if not acquired:
            raise MigrationError("could not acquire the P6 migration lock")
        cursor.execute("SET time_zone = '+00:00'")
        required_tables = TARGET_TABLES + ("legacy_import_run", "legacy_import_id_map")
        placeholders = ",".join(["%s"] * len(required_tables))
        table_count = _fetch_scalar(
            cursor,
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema = DATABASE() AND table_name IN (" + placeholders + ")",
            required_tables,
        )
        if table_count != len(required_tables):
            raise MigrationError("Flyway V4/V7 migration tables are not installed")
        if any(_fetch_scalar(cursor, f"SELECT COUNT(*) FROM `{table}`") for table in TARGET_TABLES):
            raise MigrationError("P6 target tables are not empty; refusing a full legacy import")
        cursor.execute(
            "SELECT username, status FROM sys_user WHERE id = %s",
            (plan.target_owner_id,),
        )
        owner = cursor.fetchone()
        if owner is None or str(owner[1]) != "ENABLED":
            raise MigrationError("target owner does not exist or is not enabled")
        if _fetch_scalar(
            cursor,
            "SELECT COUNT(*) FROM legacy_import_run WHERE domain = %s AND source_sha256 = %s",
            (DOMAIN, plan.source_sha256),
        ):
            raise MigrationError("this source SHA256 already has a P6 import ledger entry")

        _start_transaction(connection)
        cursor.execute(
            "INSERT INTO legacy_import_run (run_id, domain, source_name, source_sha256, "
            "backup_sha256, source_size_bytes, status, expected_counts_json, "
            "imported_counts_json, reconciliation_json) "
            "VALUES (%s,%s,%s,%s,%s,%s,'RUNNING',%s,JSON_OBJECT(),JSON_OBJECT())",
            (
                run_uuid,
                DOMAIN,
                plan.source_path.name,
                plan.source_sha256,
                backup_sha256,
                plan.source_size_bytes,
                json.dumps(plan.expected_counts, separators=(",", ":")),
            ),
        )
        ledger_id = int(cursor.lastrowid)
        farm_ids: dict[str, int] = {}
        animal_ids: dict[str, int] = {}
        for item in plan.farms:
            cursor.execute(
                "INSERT INTO farm (owner_id, farm_code, name, location, created_at, updated_at) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (plan.target_owner_id, item.farm_id, item.name, item.location,
                 item.created_at, item.updated_at),
            )
            farm_ids[item.farm_id] = int(cursor.lastrowid)
            _insert_map(cursor, ledger_id, "FARM", item.farm_id, cursor.lastrowid)
        for item in plan.animals:
            cursor.execute(
                "INSERT INTO animal (owner_id, farm_id, animal_code, species, breed, sex, "
                "birth_date, note, created_at, updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (plan.target_owner_id, farm_ids.get(item.farm_id), item.animal_id,
                 item.species, item.breed, item.sex, item.birth_date, item.note,
                 item.created_at, item.updated_at),
            )
            animal_ids[item.animal_id] = int(cursor.lastrowid)
            _insert_map(cursor, ledger_id, "ANIMAL", item.animal_id, cursor.lastrowid)
        for item in plan.measurements:
            cursor.execute(
                "INSERT INTO measurement_record (owner_id, animal_id, measure_date, "
                "body_height_cm, body_length_cm, chest_girth_cm, chest_depth_cm, "
                "chest_width_cm, weight_kg, source, confidence, algorithm_version, "
                "measurement_batch_id, note, created_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (plan.target_owner_id, animal_ids[item.animal_id], item.measure_date,
                 item.body_height_cm, item.body_length_cm, item.chest_girth_cm,
                 item.chest_depth_cm, item.chest_width_cm, item.weight_kg, item.source,
                 item.confidence, item.algorithm_version, item.measurement_batch_id,
                 item.note, item.created_at),
            )
            _insert_map(cursor, ledger_id, "MEASUREMENT", str(item.source_id), cursor.lastrowid)

        imported_counts = {
            "farms": _fetch_scalar(cursor, "SELECT COUNT(*) FROM farm"),
            "animals": _fetch_scalar(cursor, "SELECT COUNT(*) FROM animal"),
            "measurements": _fetch_scalar(cursor, "SELECT COUNT(*) FROM measurement_record"),
            "idMaps": _fetch_scalar(
                cursor,
                "SELECT COUNT(*) FROM legacy_import_id_map WHERE run_id = %s",
                (ledger_id,),
            ),
        }
        reconciliation = {
            "countsMatch": imported_counts == plan.expected_counts,
            "measurementOrphans": _fetch_scalar(
                cursor,
                "SELECT COUNT(*) FROM measurement_record m LEFT JOIN animal a "
                "ON a.id=m.animal_id AND a.owner_id=m.owner_id WHERE a.id IS NULL",
            ),
            "sourceUnchanged": sha256_file(plan.source_path) == plan.source_sha256,
            "ownerId": plan.target_owner_id,
        }
        if not reconciliation["countsMatch"] or reconciliation["measurementOrphans"] != 0:
            raise MigrationError("P6 reconciliation failed; rolling back")
        cursor.execute(
            "UPDATE legacy_import_run SET status='SUCCEEDED', imported_counts_json=%s, "
            "reconciliation_json=%s, finished_at=CURRENT_TIMESTAMP(6) WHERE id=%s",
            (json.dumps(imported_counts, separators=(",", ":")),
             json.dumps(reconciliation, separators=(",", ":")), ledger_id),
        )
        connection.commit()
        return {
            "mode": "apply",
            "status": "succeeded",
            "runId": run_uuid,
            "ledgerId": ledger_id,
            "domain": DOMAIN,
            "sourceSha256": plan.source_sha256,
            "backupSha256": backup_sha256,
            "targetOwnerId": plan.target_owner_id,
            "importedCounts": imported_counts,
            "reconciliation": reconciliation,
        }
    except Exception:
        try:
            connection.rollback()
        except Exception:
            pass
        raise
    finally:
        if acquired:
            try:
                cursor.execute("SELECT RELEASE_LOCK(%s)", (LOCK_NAME,))
                cursor.fetchone()
            except Exception:
                pass
        cursor.close()


def _insert_map(cursor: Any, run_id: int, entity: str, source: str, target: Any) -> None:
    cursor.execute(
        "INSERT INTO legacy_import_id_map (run_id, entity_type, source_id, target_id) "
        "VALUES (%s,%s,%s,%s)",
        (run_id, entity, source, int(target)),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Dry-run or apply the offline P6 livestock SQLite to MySQL migration."
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--target-owner-id", type=int, required=True)
    parser.add_argument("--backup", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--lock-timeout-seconds", type=int, default=10)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        if arguments.lock_timeout_seconds < 0 or arguments.lock_timeout_seconds > 60:
            raise MigrationError("--lock-timeout-seconds must be between 0 and 60")
        expected = normalize_sha256(arguments.expected_sha256)
        plan = build_import_plan(arguments.source, expected, arguments.target_owner_id)
        backup_sha = _verify_backup(
            plan.source_path,
            arguments.backup,
            expected,
            arguments.apply,
        )
        if arguments.apply:
            connection = connect_mysql()
            try:
                report = apply_import(
                    plan,
                    arguments.backup.resolve(),
                    backup_sha or "",
                    connection,
                    lock_timeout_seconds=arguments.lock_timeout_seconds,
                )
            finally:
                connection.close()
        else:
            report = dry_run_report(plan, backup_sha)
        _write_report(report, arguments.report)
        return 0
    except MigrationError as exc:
        print(f"migration refused: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"migration failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
