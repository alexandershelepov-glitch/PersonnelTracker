from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from backup import BackupError, BackupManager
from config import APP_NAME


class LocalBackupManager(BackupManager):
    """Backup manager with a user-selected local backup directory.

    The working SQLite database always stays where the application keeps it.
    Only ZIP backups move to the configured directory. The choice is persisted
    in the existing settings table, so no schema migration is required.
    """

    SETTING_KEY = "backup_directory"

    @property
    def default_backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def configured_backups_dir(self) -> Path:
        raw = (self.db.get_setting(self.SETTING_KEY, "") or "").strip()
        return Path(raw).expanduser() if raw else self.default_backups_dir

    @staticmethod
    def _ensure_writable_directory(path: Path) -> Path:
        candidate = path.expanduser().resolve()
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            if not candidate.is_dir():
                raise OSError("not a directory")
            # A directory may exist but still be read-only. Test an actual
            # create/delete operation so failures are detected before a backup.
            with tempfile.NamedTemporaryFile(prefix=".pt-write-test-", dir=candidate, delete=True):
                pass
        except OSError as exc:
            raise BackupError(
                "Папка резервных копий недоступна для записи: " + str(candidate)
            ) from exc
        return candidate

    @property
    def backups_dir(self) -> Path:
        return self._ensure_writable_directory(self.configured_backups_dir)

    def set_backups_dir(self, path: str | Path) -> Path:
        candidate = self._ensure_writable_directory(Path(path))
        # Persist only after the new location has passed the write test. If
        # validation fails, the previous setting remains untouched.
        self.db.set_setting(self.SETTING_KEY, str(candidate))
        return candidate

    def use_default_backups_dir(self) -> Path:
        candidate = self._ensure_writable_directory(self.default_backups_dir)
        self.db.set_setting(self.SETTING_KEY, "")
        return candidate

    def restore_backup(self, archive_path: str | Path):
        # The backup directory is machine-local configuration. A database ZIP
        # copied from another Mac/Windows PC may contain a path that does not
        # exist here, so restoring personnel data must not replace this setting.
        local_setting = self.db.get_setting(self.SETTING_KEY, "")
        result = super().restore_backup(archive_path)
        self.db.set_setting(self.SETTING_KEY, local_setting)
        return result


def install_backup_features(window: Any) -> None:
    """Install v0.7 local backup controls on the Service page."""
    from PySide6.QtWidgets import (
        QFileDialog,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QMessageBox,
        QPushButton,
        QVBoxLayout,
    )

    manager = LocalBackupManager(window.db)
    window.backup_manager = manager

    def refresh_status() -> None:
        configured = manager.configured_backups_dir
        try:
            active = manager.backups_dir
            count = manager.backup_count()
            status.setText(
                f"Папка резервных копий: {active}\n"
                f"Сохранено копий: {count} · Автокопия: один раз в день, хранится {manager.AUTO_KEEP}"
            )
        except BackupError:
            status.setText(
                f"Папка резервных копий недоступна: {configured}\n"
                "Выберите другую локальную папку. Приложение и рабочая база продолжают работать."
            )

    def choose_backup_folder() -> None:
        current = manager.configured_backups_dir
        start = current if current.exists() else manager.data_dir
        folder = QFileDialog.getExistingDirectory(
            window,
            "Выберите папку резервных копий",
            str(start),
        )
        if not folder:
            return
        old = manager.configured_backups_dir
        try:
            selected = manager.set_backups_dir(folder)
        except BackupError as exc:
            QMessageBox.critical(window, "Папка резервных копий", str(exc))
            refresh_status()
            return
        refresh_status()
        text = (
            f"Новая папка сохранена:\n{selected}\n\n"
            "Автоматические и страховочные копии теперь будут создаваться здесь."
        )
        if old.resolve() != selected.resolve() and old.exists():
            text += (
                "\n\nРанее созданные ZIP-копии не перемещались и остались в прежней папке."
            )
        QMessageBox.information(window, "Папка резервных копий", text)

    def create_manual_backup() -> None:
        try:
            default_dir = manager.backups_dir
        except BackupError as exc:
            QMessageBox.warning(
                window,
                "Папка резервных копий недоступна",
                str(exc) + "\n\nВыберите место сохранения вручную или сначала задайте новую папку.",
            )
            default_dir = manager.data_dir
        default = default_dir / manager.suggested_filename("manual")
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
        try:
            start = manager.backups_dir
        except BackupError:
            start = manager.data_dir
        filename, _ = QFileDialog.getOpenFileName(
            window,
            "Выберите резервную копию",
            str(start),
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
            "Перед заменой программа автоматически сохранит отдельную страховочную копию текущих данных."
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
            # refresh_all in the current UI does not refresh the personnel page.
            # Refresh it explicitly after a database replacement when available.
            if hasattr(window, "refresh_employees"):
                window.refresh_employees()
        except BackupError as exc:
            QMessageBox.critical(
                window,
                "Восстановление",
                str(exc) + "\n\nЕсли папка резервных копий недоступна, выберите новую папку в разделе «Сервис».",
            )
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
        "Рабочая база остаётся локальной и не зависит от интернета. "
        "Для ZIP-копий можно выбрать отдельную папку на компьютере или другом доступном диске. "
        "Восстановление проверяет архив до замены данных."
    )
    description.setWordWrap(True)
    box_layout.addWidget(description)

    buttons = QHBoxLayout()
    create_button = QPushButton("Создать резервную копию")
    create_button.setProperty("role", "primary")
    create_button.clicked.connect(create_manual_backup)
    restore_button = QPushButton("Восстановить из копии")
    restore_button.clicked.connect(restore_backup)
    folder_button = QPushButton("Выбрать папку резервных копий")
    folder_button.clicked.connect(choose_backup_folder)
    buttons.addWidget(create_button)
    buttons.addWidget(restore_button)
    buttons.addWidget(folder_button)
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
        service_menu.addAction("Выбрать папку резервных копий", choose_backup_folder)

    window.setWindowTitle(APP_NAME + " — версия 0.7")
    for label in window.findChildren(QLabel):
        if label.text() == "v0.6":
            label.setText("v0.7")

    # Automatic backup failure must never prevent application startup. This is
    # especially important if a previously selected external or network drive
    # is currently unavailable.
    try:
        created = manager.create_auto_backup_if_due()
        if created:
            print(f"Автоматическая резервная копия: {created}")
    except Exception as exc:
        print(f"Не удалось создать автоматическую резервную копию: {exc}")
    refresh_status()
