from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from config import SECTIONS
from database import Database


class CsvDataError(ValueError):
    """Raised when a CSV file cannot be read or safely imported."""


@dataclass(frozen=True)
class CsvPreviewRow:
    row_number: int
    data: dict[str, Any]
    status: str
    messages: tuple[str, ...] = ()

    @property
    def importable(self) -> bool:
        return self.status in {"ready", "warning"}


@dataclass(frozen=True)
class CsvPreview:
    path: Path
    rows: tuple[CsvPreviewRow, ...]
    recognized_headers: tuple[str, ...]
    ignored_headers: tuple[str, ...]

    @property
    def ready_count(self) -> int:
        return sum(row.status == "ready" for row in self.rows)

    @property
    def warning_count(self) -> int:
        return sum(row.status == "warning" for row in self.rows)

    @property
    def blocked_count(self) -> int:
        return sum(not row.importable for row in self.rows)


class CsvEmployeeManager:
    """Preview-first CSV exchange for active employees.

    Import never changes staff_units. New people are created as active employees
    and can then be assigned to an existing vacancy through the normal UI.
    """

    EXPORT_COLUMNS = [
        ("ФИО", "fio"),
        ("Табельный номер", "personnel_no"),
        ("Отдел", "department"),
        ("Отделение", "section"),
        ("Группа", "group_name"),
        ("Должность", "position"),
        ("Дата рождения", "birth_date"),
        ("Телефон", "phone"),
        ("E-mail", "email"),
        ("Фактический адрес", "factual_address"),
        ("Адрес регистрации", "registration_address"),
        ("Дата приёма", "employment_date"),
        ("График", "schedule_type"),
        ("Дата рабочей смены", "schedule_anchor_date"),
        ("Образование", "education"),
        ("Номер удостоверения", "certificate_number"),
    ]

    ALIASES = {
        "fio": {"фио", "ф и о", "фамилия имя отчество", "работник", "сотрудник"},
        "personnel_no": {"табельный номер", "таб номер", "табельный №", "таб №", "табномер", "personnel no", "personnel number"},
        "department": {"отдел", "подразделение", "department"},
        "section": {"отделение", "секция", "section"},
        "group_name": {"группа", "group"},
        "position": {"должность", "position"},
        "birth_date": {"дата рождения", "др", "birth date", "birth_date"},
        "phone": {"телефон", "тел", "phone"},
        "email": {"email", "e-mail", "электронная почта", "почта"},
        "factual_address": {"фактический адрес", "адрес фактический", "factual address"},
        "registration_address": {"адрес регистрации", "регистрация", "registration address"},
        "employment_date": {"дата приёма", "дата приема", "дата начала работы", "employment date"},
        "schedule_type": {"график", "график работы", "schedule"},
        "schedule_anchor_date": {"дата рабочей смены", "опорная дата", "дата смены", "schedule anchor"},
        "education": {"образование", "education"},
        "certificate_number": {"номер удостоверения", "№ удостоверения", "удостоверение", "certificate number"},
    }

    INSERT_FIELDS = [
        "fio", "personnel_no", "department", "position", "birth_date",
        "factual_address", "registration_address", "phone", "email",
        "employment_date", "schedule_type", "schedule_anchor_date",
        "employment_status", "section", "group_name", "education", "certificate_number",
    ]

    def __init__(self, db: Database):
        self.db = db
        self._alias_lookup: dict[str, str] = {}
        for field, aliases in self.ALIASES.items():
            for alias in aliases:
                self._alias_lookup[self._normalize_header(alias)] = field

    @staticmethod
    def _normalize_header(value: str | None) -> str:
        text = (value or "").strip().casefold().replace("ё", "е")
        text = re.sub(r"[^0-9a-zа-я]+", " ", text, flags=re.IGNORECASE)
        return " ".join(text.split())

    @staticmethod
    def _clean_text(value: Any) -> str:
        return str(value or "").replace("\ufeff", "").strip()

    @staticmethod
    def _decode(data: bytes) -> str:
        for encoding in ("utf-8-sig", "utf-8", "cp1251"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise CsvDataError("Не удалось определить кодировку CSV. Сохраните файл как UTF-8 или Windows-1251.")

    @staticmethod
    def _dialect(text: str):
        sample = text[:8192]
        try:
            return csv.Sniffer().sniff(sample, delimiters=";,\t")
        except csv.Error:
            class Fallback(csv.excel):
                delimiter = ";" if sample.splitlines() and sample.splitlines()[0].count(";") >= sample.splitlines()[0].count(",") else ","
            return Fallback

    @staticmethod
    def _parse_date(value: str, label: str) -> str | None:
        text = value.strip()
        if not text:
            return None
        for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(text, fmt).date().isoformat()
            except ValueError:
                pass
        raise CsvDataError(f"{label}: неверная дата «{text}». Используйте ДД.ММ.ГГГГ или ГГГГ-ММ-ДД.")

    @staticmethod
    def _normalize_schedule(value: str) -> str:
        text = value.strip().casefold().replace(" ", "")
        if not text or text in {"не задан", "незадан", "нет", "-", "—"}:
            return "Не задан"
        if text in {"1/3", "1через3", "1x3", "1х3"}:
            return "1/3"
        if text in {"5/2", "5через2", "5x2", "5х2"}:
            return "5/2"
        raise CsvDataError(f"Неизвестный график «{value.strip()}». Допустимо: 1/3, 5/2 или Не задан.")

    def _mapped_headers(self, fieldnames: list[str]) -> tuple[dict[str, str], list[str]]:
        mapped: dict[str, str] = {}
        ignored: list[str] = []
        for source in fieldnames:
            canonical = self._alias_lookup.get(self._normalize_header(source))
            if canonical and canonical not in mapped.values():
                mapped[source] = canonical
            else:
                ignored.append(source)
        required = {"fio", "personnel_no"}
        missing = required - set(mapped.values())
        if missing:
            labels = {"fio": "ФИО", "personnel_no": "Табельный номер"}
            raise CsvDataError("В CSV отсутствуют обязательные колонки: " + ", ".join(labels[field] for field in sorted(missing)))
        return mapped, ignored

    def _existing_people(self) -> tuple[dict[str, str], set[str]]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT personnel_no, fio FROM employees").fetchall()
        by_number = {self._clean_text(row["personnel_no"]).casefold(): self._clean_text(row["fio"]) for row in rows}
        names = {self._clean_text(row["fio"]).casefold() for row in rows if self._clean_text(row["fio"])}
        return by_number, names

    def preview_file(self, path: str | Path) -> CsvPreview:
        source = Path(path).expanduser().resolve()
        if not source.is_file():
            raise CsvDataError("CSV-файл не найден.")
        text = self._decode(source.read_bytes())
        reader = csv.DictReader(io.StringIO(text), dialect=self._dialect(text))
        if not reader.fieldnames:
            raise CsvDataError("CSV не содержит строки заголовков.")
        fieldnames = [self._clean_text(name) for name in reader.fieldnames]
        if any(not name for name in fieldnames):
            raise CsvDataError("В CSV есть пустой заголовок колонки.")
        mapped, ignored = self._mapped_headers(fieldnames)
        existing_by_number, existing_names = self._existing_people()
        seen_numbers: set[str] = set()
        seen_names: set[str] = set()
        result: list[CsvPreviewRow] = []

        # DictReader keeps its original fieldname strings, so map them by position
        # after BOM/whitespace cleanup instead of mutating reader.fieldnames.
        source_to_clean = {original: self._clean_text(original) for original in reader.fieldnames}
        clean_to_canonical = {source: canonical for source, canonical in mapped.items()}

        for row_number, raw in enumerate(reader, start=2):
            if raw is None:
                continue
            clean_values: dict[str, str] = {}
            for original, value in raw.items():
                clean_header = source_to_clean.get(original, self._clean_text(original))
                canonical = clean_to_canonical.get(clean_header)
                if canonical:
                    clean_values[canonical] = self._clean_text(value)
            if not any(clean_values.values()):
                continue

            errors: list[str] = []
            warnings: list[str] = []
            fio = clean_values.get("fio", "").strip()
            personnel_no = clean_values.get("personnel_no", "").strip()
            if not fio:
                errors.append("Не заполнено ФИО.")
            if not personnel_no:
                errors.append("Не заполнен табельный номер.")

            data: dict[str, Any] = {
                "fio": fio,
                "personnel_no": personnel_no,
                "department": clean_values.get("department", ""),
                "section": clean_values.get("section", "") or "Не указано",
                "group_name": clean_values.get("group_name", "") or None,
                "position": clean_values.get("position", ""),
                "phone": clean_values.get("phone", ""),
                "email": clean_values.get("email", ""),
                "factual_address": clean_values.get("factual_address", ""),
                "registration_address": clean_values.get("registration_address", ""),
                "education": clean_values.get("education", ""),
                "certificate_number": clean_values.get("certificate_number", ""),
                "employment_status": "Работает",
            }
            for field, label in (("birth_date", "Дата рождения"), ("employment_date", "Дата приёма"), ("schedule_anchor_date", "Дата рабочей смены")):
                try:
                    data[field] = self._parse_date(clean_values.get(field, ""), label)
                except CsvDataError as exc:
                    errors.append(str(exc))
                    data[field] = None
            try:
                data["schedule_type"] = self._normalize_schedule(clean_values.get("schedule_type", ""))
            except CsvDataError as exc:
                errors.append(str(exc))
                data["schedule_type"] = "Не задан"

            number_key = personnel_no.casefold()
            name_key = fio.casefold()
            exact_existing = bool(number_key and number_key in existing_by_number)
            if exact_existing:
                errors.append(f"Табельный номер уже есть в базе: {existing_by_number[number_key]}.")
            if number_key and number_key in seen_numbers:
                errors.append("Табельный номер повторяется внутри CSV.")
            if name_key and not exact_existing and name_key in existing_names:
                warnings.append("В базе уже есть работник с таким ФИО. Проверьте возможный дубликат.")
            if name_key and name_key in seen_names:
                warnings.append("ФИО повторяется внутри CSV.")
            if data["section"] not in SECTIONS:
                warnings.append(f"Отделение «{data['section']}» не входит в стандартный список приложения.")
            if data["schedule_type"] == "1/3" and not data.get("schedule_anchor_date"):
                warnings.append("Для графика 1/3 не указана дата известной рабочей смены.")

            if number_key:
                seen_numbers.add(number_key)
            if name_key:
                seen_names.add(name_key)
            status = "error" if errors else ("warning" if warnings else "ready")
            result.append(CsvPreviewRow(row_number, data, status, tuple(errors + warnings)))

        if not result:
            raise CsvDataError("В CSV нет строк с данными работников.")
        recognized = tuple(header for header in fieldnames if header in mapped)
        return CsvPreview(source, tuple(result), recognized, tuple(ignored))

    def import_rows(self, rows: Iterable[CsvPreviewRow]) -> int:
        selected = [row for row in rows if row.importable]
        if not selected:
            raise CsvDataError("Нет строк, разрешённых для импорта.")
        numbers = [str(row.data.get("personnel_no") or "").strip() for row in selected]
        if any(not number for number in numbers) or len({number.casefold() for number in numbers}) != len(numbers):
            raise CsvDataError("Перед импортом обнаружены пустые или повторяющиеся табельные номера.")

        placeholders = ", ".join("?" for _ in self.INSERT_FIELDS)
        columns = ", ".join(self.INSERT_FIELDS)
        try:
            with self.db.connect() as conn:
                existing = {
                    str(row[0]).strip().casefold()
                    for row in conn.execute(
                        f"SELECT personnel_no FROM employees WHERE lower(personnel_no) IN ({', '.join('lower(?)' for _ in numbers)})",
                        numbers,
                    ).fetchall()
                }
                if existing:
                    raise CsvDataError("Импорт отменён: один из табельных номеров уже появился в базе. Обновите предпросмотр.")
                for row in selected:
                    data = row.data
                    values = []
                    for field in self.INSERT_FIELDS:
                        value = data.get(field)
                        if field in {"birth_date", "employment_date", "schedule_anchor_date", "group_name"}:
                            value = value or None
                        elif field == "section":
                            value = value or "Не указано"
                        elif field == "schedule_type":
                            value = value or "Не задан"
                        elif field == "employment_status":
                            value = "Работает"
                        else:
                            value = value or ""
                        values.append(value)
                    conn.execute(f"INSERT INTO employees({columns}) VALUES ({placeholders})", values)
        except CsvDataError:
            raise
        except Exception as exc:
            raise CsvDataError("Импорт отменён. Ни одна строка не должна быть сохранена.") from exc
        return len(selected)

    @staticmethod
    def _display_date(value: str | None) -> str:
        if not value:
            return ""
        try:
            return datetime.strptime(value, "%Y-%m-%d").strftime("%d.%m.%Y")
        except ValueError:
            return value

    def export_active(self, destination: str | Path) -> Path:
        target = Path(destination).expanduser().resolve()
        if target.suffix.lower() != ".csv":
            target = target.with_suffix(".csv")
        target.parent.mkdir(parents=True, exist_ok=True)
        with self.db.connect() as conn:
            rows = conn.execute("""
                SELECT p.*,
                       COALESCE(u.department, p.department) AS effective_department,
                       COALESCE(u.section, p.section) AS effective_section,
                       COALESCE(u.group_name, p.group_name) AS effective_group,
                       COALESCE(u.position, p.position) AS effective_position
                FROM employees p
                LEFT JOIN staff_units u ON u.employee_id=p.id
                WHERE p.employment_status='Работает'
                ORDER BY p.fio COLLATE NOCASE
            """).fetchall()
        try:
            with target.open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.writer(stream, delimiter=";", quoting=csv.QUOTE_MINIMAL)
                writer.writerow([label for label, _field in self.EXPORT_COLUMNS])
                for row in rows:
                    values = {
                        "fio": row["fio"],
                        "personnel_no": row["personnel_no"],
                        "department": row["effective_department"],
                        "section": row["effective_section"],
                        "group_name": row["effective_group"],
                        "position": row["effective_position"],
                        "birth_date": self._display_date(row["birth_date"]),
                        "phone": row["phone"],
                        "email": row["email"],
                        "factual_address": row["factual_address"],
                        "registration_address": row["registration_address"],
                        "employment_date": self._display_date(row["employment_date"]),
                        "schedule_type": row["schedule_type"],
                        "schedule_anchor_date": self._display_date(row["schedule_anchor_date"]),
                        "education": row["education"],
                        "certificate_number": row["certificate_number"],
                    }
                    writer.writerow([values.get(field) or "" for _label, field in self.EXPORT_COLUMNS])
        except OSError as exc:
            raise CsvDataError("Не удалось сохранить CSV-файл.") from exc
        return target


def install_csv_features(window: Any) -> None:
    """Add CSV import/export controls to the existing v0.7 Service page."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QAbstractItemView,
        QDialog,
        QFileDialog,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QMessageBox,
        QPushButton,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
    )

    manager = CsvEmployeeManager(window.db)
    window.csv_manager = manager

    class PreviewDialog(QDialog):
        def __init__(self, preview: CsvPreview, parent=None):
            super().__init__(parent)
            self.preview = preview
            self.setWindowTitle("Предпросмотр импорта CSV")
            self.resize(1180, 650)
            root = QVBoxLayout(self)
            summary = QLabel(
                f"Строк: {len(preview.rows)} · готовы: {preview.ready_count} · с предупреждениями: {preview.warning_count} · заблокированы: {preview.blocked_count}"
            )
            summary.setWordWrap(True)
            root.addWidget(summary)
            if preview.ignored_headers:
                ignored = QLabel("Неиспользуемые колонки: " + ", ".join(preview.ignored_headers))
                ignored.setWordWrap(True)
                ignored.setObjectName("secondaryText")
                root.addWidget(ignored)
            hint = QLabel("Строки без замечаний выбраны автоматически. Строки с предупреждением нужно отметить вручную после проверки. Ошибочные строки импортировать нельзя.")
            hint.setWordWrap(True)
            root.addWidget(hint)

            headers = ["Импорт", "Строка", "Статус", "ФИО", "Таб. №", "Отдел", "Отделение", "Группа", "Должность", "Дата рождения", "Телефон", "График", "Комментарий"]
            self.table = QTableWidget(len(preview.rows), len(headers))
            self.table.setHorizontalHeaderLabels(headers)
            self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
            self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            self.table.setAlternatingRowColors(True)
            for r, item in enumerate(preview.rows):
                check = QTableWidgetItem()
                if item.importable:
                    check.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
                    check.setCheckState(Qt.Checked if item.status == "ready" else Qt.Unchecked)
                else:
                    check.setFlags(Qt.NoItemFlags)
                    check.setCheckState(Qt.Unchecked)
                check.setData(Qt.UserRole, r)
                self.table.setItem(r, 0, check)
                status_text = {"ready": "Готово", "warning": "Проверить", "error": "Ошибка"}[item.status]
                values = [
                    item.row_number,
                    status_text,
                    item.data.get("fio") or "",
                    item.data.get("personnel_no") or "",
                    item.data.get("department") or "",
                    item.data.get("section") or "",
                    item.data.get("group_name") or "",
                    item.data.get("position") or "",
                    CsvEmployeeManager._display_date(item.data.get("birth_date")),
                    item.data.get("phone") or "",
                    item.data.get("schedule_type") or "",
                    " ".join(item.messages),
                ]
                for c, value in enumerate(values, start=1):
                    cell = QTableWidgetItem(str(value))
                    cell.setToolTip(str(value))
                    self.table.setItem(r, c, cell)
            self.table.resizeColumnsToContents()
            self.table.horizontalHeader().setStretchLastSection(True)
            root.addWidget(self.table, 1)

            actions = QHBoxLayout()
            cancel = QPushButton("Отмена")
            cancel.clicked.connect(self.reject)
            proceed = QPushButton("Импортировать выбранные")
            proceed.setProperty("role", "primary")
            proceed.clicked.connect(self.accept)
            actions.addStretch()
            actions.addWidget(cancel)
            actions.addWidget(proceed)
            root.addLayout(actions)

        def selected_rows(self) -> list[CsvPreviewRow]:
            selected: list[CsvPreviewRow] = []
            for r, row in enumerate(self.preview.rows):
                item = self.table.item(r, 0)
                if row.importable and item is not None and item.checkState() == Qt.Checked:
                    selected.append(row)
            return selected

    def import_csv() -> None:
        filename, _ = QFileDialog.getOpenFileName(window, "Импорт работников из CSV", "", "CSV (*.csv);;Все файлы (*)")
        if not filename:
            return
        try:
            preview = manager.preview_file(filename)
        except CsvDataError as exc:
            QMessageBox.warning(window, "Импорт CSV", str(exc))
            return
        dialog = PreviewDialog(preview, window)
        if not dialog.exec():
            return
        selected = dialog.selected_rows()
        if not selected:
            QMessageBox.information(window, "Импорт CSV", "Не выбрано ни одной строки для импорта.")
            return
        backup_path = None
        try:
            if hasattr(window, "backup_manager"):
                backup_path = window.backup_manager.create_backup(kind="pre-import")
            count = manager.import_rows(selected)
        except Exception as exc:
            QMessageBox.critical(window, "Импорт CSV", str(exc))
            return
        window.refresh_all()
        message = f"Импортировано работников: {count}.\nНовые работники не назначались на штатные единицы автоматически."
        if backup_path:
            message += f"\n\nСтраховочная копия перед импортом:\n{backup_path}"
        QMessageBox.information(window, "Импорт CSV завершён", message)

    def export_csv() -> None:
        default = manager.db.path.parent / "PersonnelTracker_личный_состав.csv"
        filename, _ = QFileDialog.getSaveFileName(window, "Экспорт личного состава в CSV", str(default), "CSV (*.csv)")
        if not filename:
            return
        try:
            path = manager.export_active(filename)
        except CsvDataError as exc:
            QMessageBox.critical(window, "Экспорт CSV", str(exc))
            return
        QMessageBox.information(window, "Экспорт CSV", f"CSV успешно сохранён:\n{path}")

    page = window.pages.widget(4)
    layout = page.layout()
    box = QGroupBox("Импорт / экспорт CSV")
    box_layout = QVBoxLayout(box)
    description = QLabel(
        "Импорт сначала показывает предпросмотр, ошибки и возможные дубликаты. "
        "Перед фактическим импортом автоматически создаётся страховочная резервная копия."
    )
    description.setWordWrap(True)
    box_layout.addWidget(description)
    buttons = QHBoxLayout()
    import_button = QPushButton("Импортировать работников из CSV")
    import_button.setProperty("role", "primary")
    import_button.clicked.connect(import_csv)
    export_button = QPushButton("Экспортировать личный состав в CSV")
    export_button.clicked.connect(export_csv)
    buttons.addWidget(import_button)
    buttons.addWidget(export_button)
    buttons.addStretch()
    box_layout.addLayout(buttons)
    layout.insertWidget(max(0, layout.count() - 1), box)

    service_menu = window.menuBar().actions()[0].menu() if window.menuBar().actions() else None
    if service_menu is not None:
        service_menu.addSeparator()
        service_menu.addAction("Импортировать работников из CSV", import_csv)
        service_menu.addAction("Экспортировать личный состав в CSV", export_csv)
