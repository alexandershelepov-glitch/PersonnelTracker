from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from config import APP_NAME
from database import Database


class BackupError(RuntimeError):
    """Raised when a backup cannot be created, validated or restored safely."""


@dataclass(frozen=True)
class BackupInspection:
    path: Path
    created_at: str
    schema_version: int
    kind: str
    photo_count: int


@dataclass(frozen=True)
class RestoreResult:
    restored_from: Path
    safety_backup: Path
    inspection: BackupInspection


class BackupManager:
    """Create and restore self-contained ZIP snapshots of PersonnelTracker data.

    A backup always contains a consistent SQLite snapshot plus the complete
    ``photos`` directory. The live database is never copied byte-for-byte while
    it may be in use: SQLite's backup API creates the database snapshot instead.
    """

    FORMAT_VERSION = 1
    DB_ENTRY = "database/personnel.db"
    MANIFEST_ENTRY = "manifest.json"
    AUTO_KEEP = 7
    REQUIRED_TABLES = {
        "settings",
        "employees",
        "staff_units",
        "medical_checks",
        "periodic_checks",
        "trainings",
        "weapons",
        "events",
    }

    def __init__(self, db: Database):
        self.db = db

    @property
    def data_dir(self) -> Path:
        return self.db.path.parent

    @property
    def backups_dir(self) -> Path:
        path = self.data_dir / "backups"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def photos_dir(self) -> Path:
        return self.data_dir / "photos"

    def suggested_filename(self, kind: str = "manual", now: datetime | None = None) -> str:
        stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
        label = {
            "auto": "auto",
            "pre-restore": "before-restore",
            "manual": "backup",
        }.get(kind, kind or "backup")
        return f"PersonnelTracker-{label}-{stamp}.zip"

    def _database_snapshot(self, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        source = sqlite3.connect(self.db.path)
        destination = sqlite3.connect(target)
        try:
            source.backup(destination)
            result = destination.execute("PRAGMA integrity_check").fetchone()
            if not result or result[0] != "ok":
                raise BackupError("SQLite не подтвердил целостность создаваемой резервной копии.")
        finally:
            destination.close()
            source.close()

    @staticmethod
    def _safe_member_name(name: str) -> bool:
        if not name or "\\" in name:
            return False
        path = Path(name)
        if path.is_absolute() or ".." in path.parts:
            return False
        first = path.parts[0] if path.parts else ""
        return ":" not in first

    def _validate_database_file(self, path: Path) -> int:
        try:
            connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        except sqlite3.Error as exc:
            raise BackupError("Не удалось открыть базу данных из резервной копии.") from exc
        try:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            if not integrity or integrity[0] != "ok":
                raise BackupError("База данных в резервной копии повреждена.")
            foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
            if foreign_key_errors:
                raise BackupError("В резервной копии обнаружены нарушенные связи между записями.")
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            missing = self.REQUIRED_TABLES - tables
            if missing:
                raise BackupError(
                    "Резервная копия не является полной базой PersonnelTracker: "
                    + ", ".join(sorted(missing))
                )
            row = connection.execute(
                "SELECT value FROM settings WHERE key='schema_version'"
            ).fetchone()
            try:
                return int(row[0]) if row else 0
            except (TypeError, ValueError):
                return 0
        except sqlite3.Error as exc:
            raise BackupError("Не удалось проверить базу данных из резервной копии.") from exc
        finally:
            connection.close()

    def create_backup(self, destination: str | Path | None = None, kind: str = "manual") -> Path:
        if not self.db.path.exists():
            raise BackupError("Рабочая база данных не найдена.")

        target = Path(destination) if destination else self.backups_dir / self.suggested_filename(kind)
        if target.suffix.lower() != ".zip":
            target = target.with_suffix(".zip")
        target = target.expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="pt-backup-stage-") as temporary:
            stage = Path(temporary)
            snapshot = stage / "personnel.db"
            self._database_snapshot(snapshot)
            schema_version = self._validate_database_file(snapshot)
            photos = [path for path in self.photos_dir.rglob("*") if path.is_file()] if self.photos_dir.exists() else []
            manifest = {
                "format": "PersonnelTrackerBackup",
                "format_version": self.FORMAT_VERSION,
                "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "kind": kind,
                "schema_version": schema_version,
                "database_entry": self.DB_ENTRY,
                "photo_count": len(photos),
            }

            fd, temporary_name = tempfile.mkstemp(
                prefix=".pt-backup-", suffix=".zip", dir=target.parent
            )
            os.close(fd)
            temporary_zip = Path(temporary_name)
            try:
                with zipfile.ZipFile(temporary_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                    archive.writestr(
                        self.MANIFEST_ENTRY,
                        json.dumps(manifest, ensure_ascii=False, indent=2),
                    )
                    archive.write(snapshot, self.DB_ENTRY)
                    for photo in photos:
                        relative = photo.relative_to(self.photos_dir)
                        archive.write(photo, (Path("photos") / relative).as_posix())
                self.inspect_backup(temporary_zip)
                os.replace(temporary_zip, target)
            except Exception:
                temporary_zip.unlink(missing_ok=True)
                raise

        if kind == "auto":
            self._prune_auto_backups()
        return target

    def inspect_backup(self, archive_path: str | Path) -> BackupInspection:
        path = Path(archive_path).expanduser().resolve()
        if not path.is_file() or not zipfile.is_zipfile(path):
            raise BackupError("Выбранный файл не является корректной ZIP-копией PersonnelTracker.")

        try:
            with zipfile.ZipFile(path, "r") as archive:
                bad_member = archive.testzip()
                if bad_member:
                    raise BackupError(f"ZIP-архив повреждён: {bad_member}")
                names = archive.namelist()
                if any(not self._safe_member_name(name) for name in names):
                    raise BackupError("Архив содержит небезопасные пути и не может быть восстановлен.")
                if self.MANIFEST_ENTRY not in names or self.DB_ENTRY not in names:
                    raise BackupError("В архиве отсутствует manifest.json или база данных.")
                try:
                    manifest = json.loads(archive.read(self.MANIFEST_ENTRY).decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError, KeyError) as exc:
                    raise BackupError("Не удалось прочитать описание резервной копии.") from exc
                if manifest.get("format") != "PersonnelTrackerBackup":
                    raise BackupError("Архив создан не PersonnelTracker.")
                try:
                    format_version = int(manifest.get("format_version", 0))
                except (TypeError, ValueError):
                    format_version = 0
                if format_version != self.FORMAT_VERSION:
                    raise BackupError("Версия формата резервной копии не поддерживается.")

                with tempfile.TemporaryDirectory(prefix="pt-backup-check-") as temporary:
                    database = Path(temporary) / "personnel.db"
                    with archive.open(self.DB_ENTRY, "r") as source, database.open("wb") as target:
                        shutil.copyfileobj(source, target)
                    actual_schema = self._validate_database_file(database)

                try:
                    manifest_schema = int(manifest.get("schema_version", actual_schema))
                except (TypeError, ValueError):
                    manifest_schema = actual_schema
                schema_version = max(actual_schema, manifest_schema)
                if schema_version > self.db.CURRENT_VERSION:
                    raise BackupError(
                        "Эта копия создана более новой версией PersonnelTracker. "
                        "Сначала обновите приложение."
                    )
                photo_count = sum(1 for name in names if name.startswith("photos/") and not name.endswith("/"))
                return BackupInspection(
                    path=path,
                    created_at=str(manifest.get("created_at") or "Не указано"),
                    schema_version=schema_version,
                    kind=str(manifest.get("kind") or "manual"),
                    photo_count=photo_count,
                )
        except zipfile.BadZipFile as exc:
            raise BackupError("ZIP-архив повреждён.") from exc

    def restore_backup(self, archive_path: str | Path) -> RestoreResult:
        inspection = self.inspect_backup(archive_path)
        safety_backup = self.create_backup(kind="pre-restore")

        live_db = self.db.path
        live_photos = self.photos_dir
        with tempfile.TemporaryDirectory(prefix="pt-restore-", dir=self.data_dir) as temporary:
            stage = Path(temporary)
            candidate_db = stage / "candidate.db"
            candidate_photos = stage / "candidate-photos"
            candidate_photos.mkdir()

            with zipfile.ZipFile(inspection.path, "r") as archive:
                for name in archive.namelist():
                    if not self._safe_member_name(name):
                        raise BackupError("Архив содержит небезопасные пути.")
                with archive.open(self.DB_ENTRY, "r") as source, candidate_db.open("wb") as target:
                    shutil.copyfileobj(source, target)
                for name in archive.namelist():
                    if not name.startswith("photos/") or name.endswith("/"):
                        continue
                    relative = Path(name).relative_to("photos")
                    target = candidate_photos / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(name, "r") as source, target.open("wb") as output:
                        shutil.copyfileobj(source, output)

            self._validate_database_file(candidate_db)
            old_db = stage / "previous.db"
            old_photos = stage / "previous-photos"
            moved_old_db = False
            moved_old_photos = False
            try:
                if live_db.exists():
                    os.replace(live_db, old_db)
                    moved_old_db = True
                if live_photos.exists():
                    os.replace(live_photos, old_photos)
                    moved_old_photos = True
                os.replace(candidate_db, live_db)
                os.replace(candidate_photos, live_photos)
                self.db.initialize()
            except Exception as exc:
                try:
                    if live_db.exists():
                        live_db.unlink()
                    if moved_old_db and old_db.exists():
                        os.replace(old_db, live_db)
                    if live_photos.exists():
                        shutil.rmtree(live_photos)
                    if moved_old_photos and old_photos.exists():
                        os.replace(old_photos, live_photos)
                    else:
                        live_photos.mkdir(parents=True, exist_ok=True)
                    self.db.initialize()
                except Exception as rollback_exc:
                    raise BackupError(
                        "Восстановление не завершено, а автоматический откат не удался. "
                        f"Сохранена аварийная копия: {safety_backup}"
                    ) from rollback_exc
                raise BackupError(
                    "Восстановление отменено. Исходные данные возвращены на место."
                ) from exc

        return RestoreResult(
            restored_from=inspection.path,
            safety_backup=safety_backup,
            inspection=inspection,
        )

    def create_auto_backup_if_due(self, now: datetime | None = None) -> Path | None:
        moment = now or datetime.now()
        prefix = f"PersonnelTracker-auto-{moment.strftime('%Y%m%d')}-"
        if any(self.backups_dir.glob(prefix + "*.zip")):
            return None
        return self.create_backup(self.backups_dir / self.suggested_filename("auto", moment), kind="auto")

    def _prune_auto_backups(self) -> None:
        backups = sorted(
            self.backups_dir.glob("PersonnelTracker-auto-*.zip"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for obsolete in backups[self.AUTO_KEEP :]:
            obsolete.unlink(missing_ok=True)

    def backup_count(self) -> int:
        return len(list(self.backups_dir.glob("*.zip")))


def install_backup_features(window: Any) -> None:
    """Attach v0.7 backup controls to the existing v0.6 main window.

    Keeping this integration outside ``ui.py`` lets the data-protection feature
    remain independently testable and avoids coupling backup logic to GUI code.
    """
    from PySide6.QtWidgets import (
        QFileDialog,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QMessageBox,
        QPushButton,
        QVBoxLayout,
    )

    manager = BackupManager(window.db)
    window.backup_manager = manager

    def refresh_status() -> None:
        status.setText(
            f"Локальная папка: {manager.backups_dir}\n"
            f"Сохранено копий: {manager.backup_count()} · Автокопия: один раз в день, хранится {manager.AUTO_KEEP}"
        )

    def create_manual_backup() -> None:
        default = manager.backups_dir / manager.suggested_filename("manual")
        filename, _ = QFileDialog.getSaveFileName(
            window,
            "Создать резервную копию",
            str(default),
            "Резервная копия PersonnelTracker (*.zip)",
        )
        if not filename:
            return
        try:
            path = manager.create_backup(filename, kind="manual")
        except BackupError as exc:
            QMessageBox.critical(window, "Резервная копия", str(exc))
            return
        refresh_status()
        QMessageBox.information(window, "Резервная копия", f"Копия успешно создана:\n{path}")

    def restore_backup() -> None:
        filename, _ = QFileDialog.getOpenFileName(
            window,
            "Выберите резервную копию",
            str(manager.backups_dir),
            "Резервная копия PersonnelTracker (*.zip)",
        )
        if not filename:
            return
        try:
            inspection = manager.inspect_backup(filename)
        except BackupError as exc:
            QMessageBox.critical(window, "Нельзя восстановить", str(exc))
            return
        text = (
            "Восстановить данные из выбранной копии?\n\n"
            f"Создана: {inspection.created_at}\n"
            f"Версия схемы: {inspection.schema_version}\n"
            f"Фотографий: {inspection.photo_count}\n\n"
            "Перед заменой программа автоматически сохранит отдельную аварийную копию текущих данных."
        )
        if QMessageBox.question(
            window,
            "Подтвердите восстановление",
            text,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        try:
            result = manager.restore_backup(filename)
            window.refresh_all()
        except BackupError as exc:
            QMessageBox.critical(window, "Восстановление", str(exc))
            refresh_status()
            return
        refresh_status()
        QMessageBox.information(
            window,
            "Восстановление завершено",
            "Данные восстановлены.\n\n"
            f"Страховочная копия состояния до восстановления:\n{result.safety_backup}",
        )

    page = window.pages.widget(4)
    layout = page.layout()
    box = QGroupBox("Резервные копии")
    box_layout = QVBoxLayout(box)
    description = QLabel(
        "Копия включает базу данных и фотографии. Восстановление сначала проверяет архив и базу, "
        "а затем автоматически сохраняет текущее состояние."
    )
    description.setWordWrap(True)
    box_layout.addWidget(description)
    buttons = QHBoxLayout()
    create_button = QPushButton("Создать резервную копию")
    create_button.setProperty("role", "primary")
    create_button.clicked.connect(create_manual_backup)
    restore_button = QPushButton("Восстановить из копии")
    restore_button.clicked.connect(restore_backup)
    buttons.addWidget(create_button)
    buttons.addWidget(restore_button)
    buttons.addStretch()
    box_layout.addLayout(buttons)
    status = QLabel()
    status.setWordWrap(True)
    status.setObjectName("secondaryText")
    box_layout.addWidget(status)
    layout.insertWidget(max(0, layout.count() - 1), box)

    service_menu = window.menuBar().actions()[0].menu() if window.menuBar().actions() else None
    if service_menu is not None:
        service_menu.addSeparator()
        service_menu.addAction("Создать резервную копию", create_manual_backup)
        service_menu.addAction("Восстановить из копии", restore_backup)

    window.setWindowTitle(APP_NAME + " — версия 0.7")
    for label in window.findChildren(QLabel):
        if label.text() == "v0.6":
            label.setText("v0.7")

    try:
        created = manager.create_auto_backup_if_due()
        if created:
            print(f"Автоматическая резервная копия: {created}")
    except Exception as exc:  # Backup failure must never prevent application startup.
        print(f"Не удалось создать автоматическую резервную копию: {exc}")
    refresh_status()
