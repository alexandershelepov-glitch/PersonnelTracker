"""Обязательный GUI smoke test (пункт 7 ТЗ v0.4-final).

Запускается вручную в .venv:  .venv/bin/python tests/smoke_gui.py
Не подхватывается unittest discover (имя не test_*.py).
Проверяет реальное окно: сортировку, фильтры, multi-select копирование,
группу в карточке и запрет пустого номера штатной единицы."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QItemSelectionModel, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton, QAbstractItemView

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ui import EmployeeDialog, MainWindow, StaffUnitDialog  # noqa: E402

RESULTS: list[tuple[str, bool]] = []


def check(name: str, condition: bool) -> None:
    RESULTS.append((name, bool(condition)))
    print(("PASS " if condition else "FAIL ") + name)


def column_values(table, column: int) -> list[str]:
    return [table.item(row, column).text() for row in range(table.rowCount())]


def click_header(window, column: int) -> None:
    from PySide6.QtCore import QPoint
    header = window.staff_table.horizontalHeader()
    x = header.sectionViewportPosition(column) + header.sectionSize(column) // 2
    QTest.mouseClick(header.viewport(), Qt.LeftButton, Qt.NoModifier, QPoint(x, header.height() // 2))


def close_modal_later(delay: int = 300) -> None:
    def close():
        widget = QApplication.activeModalWidget() or QApplication.activePopupWidget()
        if widget:
            widget.close()
    QTimer.singleShot(delay, close)


def toggle_filter_value(window, header_index: int, value_text: str) -> None:
    """Открыть фильтр колонки и снять/поставить галочку значения."""
    def interact():
        popup = QApplication.activePopupWidget()
        assert popup is not None, "меню фильтра не открылось"
        for action in popup.actions():
            if action.text() == value_text:
                action.trigger()
                break
        popup.close()
    QTimer.singleShot(300, interact)
    window.open_staff_filter(header_index)
    QApplication.processEvents()


def main() -> int:
    app = QApplication(sys.argv)
    tmp = tempfile.TemporaryDirectory()
    window = MainWindow(Path(tmp.name) / "smoke.db")
    window.service.create_demo_data()
    employees = window.service.list_employees()
    employees_by_id = {int(employee["id"]): employee for employee in employees}
    units = []
    # Переименовываем штатные единицы, сохраняя их текущих occupants:
    # переназначение занятой единицы другому работнику запрещено сервисом.
    for unit, number, group in zip(window.service.list_staff_units(), ("2", "10", "М-1", "М-10"), ("1 группа", "2 группа", "", "3 группа")):
        units.append(window.service.save_staff_unit({
            "unit_number": number, "department": "3 отдел", "section": "1 отделение" if number != "М-10" else "2 отделение",
            "group_name": group, "position": "инспектор", "employee_id": unit["employee_id"]}, unit["id"]))
    window.service.add_weapon(employees[0]["id"], "ПМ", "АБ123")
    window.refresh_all()
    window.show()
    QTest.qWaitForWindowExposed(window)
    table = window.staff_table
    headers = window.staff_headers

    # --- A. Сортировка ---
    col_no = headers.index("№")
    click_header(window, col_no)
    check("A0: клик по заголовку сортирует, а не открывает фильтр", QApplication.activePopupWidget() is None)
    check("A1: № по возрастанию (natural)", column_values(table, col_no) == ["2", "10", "М-1", "М-10"])
    click_header(window, col_no)
    check("A2: № по убыванию", column_values(table, col_no) == ["М-10", "М-1", "10", "2"])
    col_fio = headers.index("ФИО")
    click_header(window, col_fio)
    fio_asc = column_values(table, col_fio)
    click_header(window, col_fio)
    check("A3: ФИО туда-обратно", fio_asc == sorted(fio_asc, key=str.casefold) and column_values(table, col_fio) == list(reversed(fio_asc)))
    col_age = headers.index("Возраст")
    click_header(window, col_age)
    ages = [v for v in column_values(table, col_age) if v != "—"]
    check("A4: возраст как число", ages == sorted(ages, key=int) and len(ages) == 4)
    col_birth = headers.index("Дата рождения")
    click_header(window, col_birth)
    births = [v for v in column_values(table, col_birth) if v != "—"]
    check("A5: дата рождения как дата", births == sorted(births))

    # --- B. Фильтры ---
    col_section = headers.index("Отделение")
    before = table.rowCount()
    toggle_filter_value(window, col_section, "2 отделение")
    check("B1: фильтр по отделению уменьшил ПОКАЗАНО", table.rowCount() == before - 1 and "ПОКАЗАНО: 3" in window.staff_metrics_label.text())
    check("B1b: маркер ▼ в заголовке", "▼" in table.horizontalHeaderItem(col_section).text())
    col_group = headers.index("Группа")
    toggle_filter_value(window, col_group, "2 группа")
    check("B2: два фильтра одновременно", table.rowCount() == before - 2 and "ПОКАЗАНО: 2" in window.staff_metrics_label.text())
    window.staff_search.setText("Иванов")
    check("B3: фильтры учитывают поиск", table.rowCount() == 1)
    window.reset_staff_filters()
    check("B4: сброс фильтров", table.rowCount() == before and not window.staff_filters and "▼" not in table.horizontalHeaderItem(col_section).text())
    col_weapon = headers.index("Вооружение")
    toggle_filter_value(window, col_weapon, "—")
    check("B5: фильтр по вооружению работает", 0 < table.rowCount() < before)
    window.reset_staff_filters()

    # --- C. Multi-select + копирование ---
    check("C0: ExtendedSelection", table.selectionMode() == QAbstractItemView.ExtendedSelection)
    window.refresh_staff()
    selection = table.selectionModel()
    selection.clearSelection()
    for row in (0, 2, 3):
        selection.select(table.model().index(row, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)
    check("C1: выделено 3 строки", len(selection.selectedRows()) == 3)
    QTest.keyClick(table, Qt.Key_C, Qt.ControlModifier)
    QTest.qWait(100)
    text = QApplication.clipboard().text()
    lines = text.split("\n")
    visible = sum(1 for c in range(table.columnCount()) if not table.isColumnHidden(c))
    check("C2: скопированы все 3 строки", len(lines) == 3)
    check("C3: таб-формат только видимых колонок", all(len(line.split("\t")) == visible for line in lines))

    # --- D. Группа в карточке ---
    card = EmployeeDialog(window.service, employees[0]["id"], window)
    check("D1: группа из штатной единицы", card.group_label.text() == "1 группа")
    card.close()
    window.service.save_staff_unit({"unit_number": "2", "department": "3 отдел", "section": "1 отделение", "group_name": "4 группа", "position": "инспектор", "employee_id": employees[0]["id"]}, units[0])
    card = EmployeeDialog(window.service, employees[0]["id"], window)
    check("D2: карточка показывает новую группу", card.group_label.text() == "4 группа")
    card.close()

    # --- E. Пустой номер штатной единицы ---
    units_before = len(window.service.list_staff_units())
    dialog = StaffUnitDialog(window.service, parent=window)
    dialog.number.setText("   ")
    dialog.position.setText("инспектор")
    close_modal_later()
    dialog.save()
    check("E1: пустой номер отклонён", dialog.result() != StaffUnitDialog.Accepted and len(window.service.list_staff_units()) == units_before)

    window.close()
    tmp.cleanup()
    failed = [name for name, ok in RESULTS if not ok]
    print(f"\nSMOKE: {len(RESULTS) - len(failed)}/{len(RESULTS)} проверок пройдено")
    if failed:
        print("ПРОВАЛЕНЫ:", *failed, sep="\n  - ")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
