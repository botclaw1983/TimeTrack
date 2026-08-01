"""Statistics window with summary and detailed session tabs."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt, QDate, QSettings, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from apps import TRACKED_APPS
from formatting import format_duration, format_percent
from paths import is_portable, settings_path
from storage import AppSessionRow, PeriodStats, Storage

WEEKDAYS_RU = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")

COL_DATE = 0
COL_START = 1
COL_END = 2
COL_TOTAL = 3
COL_ACTIVE = 4
COL_RATIO = 5
COL_MANUAL = 6
COL_APPS_START = 7

DETAIL_COLS = ("Дата", "Начало", "Окончание", "Программа", "Общее", "Активное")
DETAIL_MIN_SECONDS = 30  # не показывать очень короткие сессии


class StatsWindow(QMainWindow):
    manual_time_added = Signal()

    def __init__(self, storage: Storage, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._storage = storage
        if is_portable():
            self._settings = QSettings(str(settings_path()), QSettings.Format.IniFormat)
        else:
            self._settings = QSettings()
        self._seed_custom_on_switch = False
        self._app_columns = {app.key: COL_APPS_START + index for index, app in enumerate(TRACKED_APPS)}
        self.setWindowTitle("TimeTrack — статистика")
        self.resize(980, 620)
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #f3f5f7; color: #1c242b; }
            QComboBox, QDateEdit, QSpinBox {
                background: #ffffff;
                border: 1px solid #c9d0d6;
                border-radius: 4px;
                padding: 4px 8px;
                min-height: 26px;
            }
            QPushButton {
                background: #1c242b;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 6px 14px;
                min-height: 26px;
            }
            QPushButton:hover { background: #2d3944; }
            QPushButton:pressed { background: #151b20; }
            QCheckBox { spacing: 6px; color: #5a6570; }
            QTabWidget::pane {
                border: 1px solid #d5dbe1;
                border-radius: 4px;
                top: -1px;
                background: #f3f5f7;
            }
            QTabBar::tab {
                background: transparent;
                border: none;
                padding: 8px 14px;
                color: #5a6570;
            }
            QTabBar::tab:selected {
                color: #1c242b;
                font-weight: 600;
                border-bottom: 2px solid #1c242b;
            }
            QTableWidget {
                background: transparent;
                alternate-background-color: rgba(28, 36, 43, 0.04);
                border: none;
            }
            QHeaderView::section {
                background: transparent;
                border: none;
                border-bottom: 1px solid #d5dbe1;
                padding: 6px 4px;
                font-weight: 600;
            }
            """
        )

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("TimeTrack")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setWeight(QFont.Weight.DemiBold)
        title.setFont(title_font)
        layout.addWidget(title)

        subtitle = QLabel("Учёт общего и активного рабочего времени")
        subtitle.setStyleSheet("color: #5a6570;")
        layout.addWidget(subtitle)

        controls = QHBoxLayout()
        controls.setSpacing(10)
        self._period_combo = QComboBox()
        self._period_combo.addItem("День", "day")
        self._period_combo.addItem("Неделя", "week")
        self._period_combo.addItem("Месяц", "month")
        self._period_combo.addItem("Произвольный период", "custom")
        self._period_combo.currentIndexChanged.connect(self._on_period_mode_changed)
        controls.addWidget(self._period_combo)

        self._anchor_date = QDateEdit()
        self._anchor_date.setCalendarPopup(True)
        self._anchor_date.setDisplayFormat("dd.MM.yyyy")
        self._anchor_date.setDate(QDate.currentDate())
        self._anchor_date.dateChanged.connect(self._on_filter_changed)
        controls.addWidget(self._anchor_date)

        self._custom_range = QWidget()
        custom_row = QHBoxLayout(self._custom_range)
        custom_row.setContentsMargins(0, 0, 0, 0)
        custom_row.setSpacing(8)
        from_label = QLabel("С")
        from_label.setStyleSheet("color: #5a6570;")
        to_label = QLabel("По")
        to_label.setStyleSheet("color: #5a6570;")
        self._from_date = QDateEdit()
        self._from_date.setCalendarPopup(True)
        self._from_date.setDisplayFormat("dd.MM.yyyy")
        self._from_date.setDate(QDate.currentDate().addDays(-6))
        self._from_date.dateChanged.connect(self._on_custom_date_changed)
        self._to_date = QDateEdit()
        self._to_date.setCalendarPopup(True)
        self._to_date.setDisplayFormat("dd.MM.yyyy")
        self._to_date.setDate(QDate.currentDate())
        self._to_date.dateChanged.connect(self._on_custom_date_changed)
        custom_row.addWidget(from_label)
        custom_row.addWidget(self._from_date)
        custom_row.addWidget(to_label)
        custom_row.addWidget(self._to_date)
        self._custom_range.setVisible(False)
        controls.addWidget(self._custom_range, stretch=1)
        controls.addStretch()
        layout.addLayout(controls)

        self._range_label = QLabel()
        self._range_label.setStyleSheet("color: #5a6570;")
        layout.addWidget(self._range_label)

        metrics = QHBoxLayout()
        metrics.setSpacing(28)
        self._total_value = self._metric_block("Общее время")
        self._active_value = self._metric_block("Активное время")
        self._ratio_value = self._metric_block("Доля активности")
        metrics.addLayout(self._total_value[0])
        metrics.addLayout(self._active_value[0])
        metrics.addLayout(self._ratio_value[0])
        metrics.addStretch()
        layout.addLayout(metrics)

        self._tabs = QTabWidget()
        layout.addWidget(self._tabs, stretch=1)

        summary_page = QWidget()
        summary_layout = QVBoxLayout(summary_page)
        summary_layout.setContentsMargins(0, 12, 0, 0)
        summary_layout.setSpacing(12)

        table_header = QHBoxLayout()
        self._show_manual_col = QCheckBox("Показать «Добавлено вручную»")
        self._show_manual_col.setChecked(True)
        self._show_manual_col.toggled.connect(self._on_column_toggles_changed)
        self._show_apps_col = QCheckBox("Показать программы")
        self._show_apps_col.setChecked(True)
        self._show_apps_col.toggled.connect(self._on_column_toggles_changed)
        table_header.addWidget(self._show_manual_col)
        table_header.addWidget(self._show_apps_col)
        table_header.addStretch()
        summary_layout.addLayout(table_header)

        summary_headers = [
            "Дата",
            "Начало",
            "Окончание",
            "Общее",
            "Активное",
            "% активного",
            "Добавлено вручную",
            *[app.title for app in TRACKED_APPS],
        ]
        self._table = QTableWidget(0, len(summary_headers))
        self._table.setHorizontalHeaderLabels(summary_headers)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setShowGrid(False)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(COL_DATE, QHeaderView.ResizeMode.Stretch)
        for col in range(1, len(summary_headers)):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setAlternatingRowColors(True)
        self._table.itemSelectionChanged.connect(self._on_table_selection_changed)
        summary_layout.addWidget(self._table, stretch=1)

        manual = QHBoxLayout()
        manual.setSpacing(8)
        manual_label = QLabel("Добавить вручную")
        manual_label.setStyleSheet("color: #5a6570;")
        self._manual_date = QDateEdit()
        self._manual_date.setCalendarPopup(True)
        self._manual_date.setDisplayFormat("dd.MM.yyyy")
        self._manual_date.setDate(QDate.currentDate())
        self._manual_hours = QSpinBox()
        self._manual_hours.setRange(0, 24)
        self._manual_hours.setSuffix(" ч")
        self._manual_hours.setValue(0)
        self._manual_minutes = QSpinBox()
        self._manual_minutes.setRange(0, 59)
        self._manual_minutes.setSuffix(" мин")
        self._manual_minutes.setValue(0)
        self._manual_add_btn = QPushButton("Добавить")
        self._manual_add_btn.clicked.connect(self._add_manual_time)
        manual.addWidget(manual_label)
        manual.addWidget(self._manual_date)
        manual.addWidget(self._manual_hours)
        manual.addWidget(self._manual_minutes)
        manual.addWidget(self._manual_add_btn)
        manual.addStretch()
        summary_layout.addLayout(manual)

        detail_page = QWidget()
        detail_layout = QVBoxLayout(detail_page)
        detail_layout.setContentsMargins(0, 12, 0, 0)
        detail_layout.setSpacing(12)

        detail_controls = QHBoxLayout()
        detail_controls.setSpacing(8)
        detail_date_label = QLabel("День")
        detail_date_label.setStyleSheet("color: #5a6570;")
        self._detail_date = QDateEdit()
        self._detail_date.setCalendarPopup(True)
        self._detail_date.setDisplayFormat("dd.MM.yyyy")
        self._detail_date.setDate(QDate.currentDate())
        self._detail_date.dateChanged.connect(self._on_detail_date_changed)
        self._detail_hint = QLabel("Сессии только за выбранный день")
        self._detail_hint.setStyleSheet("color: #5a6570;")
        detail_controls.addWidget(detail_date_label)
        detail_controls.addWidget(self._detail_date)
        detail_controls.addWidget(self._detail_hint)
        detail_controls.addStretch()
        detail_layout.addLayout(detail_controls)

        self._detail_table = QTableWidget(0, len(DETAIL_COLS))
        self._detail_table.setHorizontalHeaderLabels(list(DETAIL_COLS))
        self._detail_table.verticalHeader().setVisible(False)
        self._detail_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._detail_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._detail_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._detail_table.setShowGrid(False)
        self._detail_table.verticalHeader().setDefaultSectionSize(28)
        detail_header = self._detail_table.horizontalHeader()
        # Interactive быстрее ResizeToContents при тысячах строк.
        detail_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        detail_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        detail_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        detail_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        detail_header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        detail_header.setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)
        self._detail_table.setColumnWidth(0, 130)
        self._detail_table.setColumnWidth(1, 70)
        self._detail_table.setColumnWidth(2, 70)
        self._detail_table.setColumnWidth(4, 100)
        self._detail_table.setColumnWidth(5, 100)
        self._detail_table.setAlternatingRowColors(True)
        detail_layout.addWidget(self._detail_table, stretch=1)

        self._tabs.addTab(summary_page, "Сводка")
        self._tabs.addTab(detail_page, "Детализация")
        self._tabs.currentChanged.connect(self._on_tab_changed)
        self._detail_load_token = 0

        self._load_filters()
        self._seed_custom_on_switch = True
        self._apply_column_visibility()
        self.refresh()

    def _metric_block(self, caption: str) -> tuple[QVBoxLayout, QLabel]:
        block = QVBoxLayout()
        block.setSpacing(4)
        label = QLabel(caption)
        label.setStyleSheet("color: #5a6570; font-size: 12px;")
        value = QLabel("—")
        font = QFont()
        font.setPointSize(20)
        font.setWeight(QFont.Weight.DemiBold)
        value.setFont(font)
        block.addWidget(label)
        block.addWidget(value)
        return block, value

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._refresh_summary()
        if self._tabs.currentIndex() == 1:
            self._schedule_detail_refresh()

    def refresh(self) -> None:
        """Обновить только сводку. Детализацию не трогаем — иначе UI подвисает."""
        self._refresh_summary()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self._save_filters()
        event.ignore()
        self.hide()

    def hideEvent(self, event) -> None:  # noqa: N802
        self._clear_detail_table()
        self._save_filters()
        super().hideEvent(event)

    def _parse_saved_date(self, value: str, fallback: QDate) -> QDate:
        if not value:
            return fallback
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            return fallback
        return QDate(parsed.year, parsed.month, parsed.day)

    def _load_bool(self, key: str, default: bool = True) -> bool:
        value = self._settings.value(key, default)
        if isinstance(value, str):
            return value.lower() in {"1", "true", "yes"}
        return bool(value)

    def _load_filters(self) -> None:
        mode = str(self._settings.value("stats/period_mode", "day"))
        anchor = self._parse_saved_date(
            str(self._settings.value("stats/anchor_date", "")),
            QDate.currentDate(),
        )
        from_date = self._parse_saved_date(
            str(self._settings.value("stats/from_date", "")),
            QDate.currentDate().addDays(-6),
        )
        to_date = self._parse_saved_date(
            str(self._settings.value("stats/to_date", "")),
            QDate.currentDate(),
        )
        show_manual = self._load_bool("stats/show_manual_column", True)
        show_apps = self._load_bool("stats/show_apps_columns", True)
        detail_day = self._parse_saved_date(
            str(self._settings.value("stats/detail_date", "")),
            QDate.currentDate(),
        )

        self._period_combo.blockSignals(True)
        self._anchor_date.blockSignals(True)
        self._from_date.blockSignals(True)
        self._to_date.blockSignals(True)
        self._show_manual_col.blockSignals(True)
        self._show_apps_col.blockSignals(True)
        self._detail_date.blockSignals(True)

        index = self._period_combo.findData(mode)
        self._period_combo.setCurrentIndex(index if index >= 0 else 0)
        self._anchor_date.setDate(anchor)
        self._from_date.setDate(from_date)
        self._to_date.setDate(to_date)
        self._show_manual_col.setChecked(show_manual)
        self._show_apps_col.setChecked(show_apps)
        self._detail_date.setDate(detail_day)

        is_custom = self._period_combo.currentData() == "custom"
        self._custom_range.setVisible(is_custom)
        self._anchor_date.setVisible(not is_custom)

        self._period_combo.blockSignals(False)
        self._anchor_date.blockSignals(False)
        self._from_date.blockSignals(False)
        self._to_date.blockSignals(False)
        self._show_manual_col.blockSignals(False)
        self._show_apps_col.blockSignals(False)
        self._detail_date.blockSignals(False)

    def _save_filters(self) -> None:
        self._settings.setValue("stats/period_mode", self._period_combo.currentData())
        self._settings.setValue(
            "stats/anchor_date",
            self._qdate_to_date(self._anchor_date.date()).isoformat(),
        )
        self._settings.setValue(
            "stats/from_date",
            self._qdate_to_date(self._from_date.date()).isoformat(),
        )
        self._settings.setValue(
            "stats/to_date",
            self._qdate_to_date(self._to_date.date()).isoformat(),
        )
        self._settings.setValue("stats/show_manual_column", self._show_manual_col.isChecked())
        self._settings.setValue("stats/show_apps_columns", self._show_apps_col.isChecked())
        self._settings.setValue(
            "stats/detail_date",
            self._qdate_to_date(self._detail_date.date()).isoformat(),
        )
        self._settings.sync()

    def _on_period_mode_changed(self) -> None:
        mode = self._period_combo.currentData()
        is_custom = mode == "custom"
        self._custom_range.setVisible(is_custom)
        self._anchor_date.setVisible(not is_custom)
        if is_custom and self._seed_custom_on_switch:
            anchor = self._anchor_date.date()
            self._to_date.blockSignals(True)
            self._from_date.blockSignals(True)
            self._to_date.setDate(anchor)
            self._from_date.setDate(anchor.addDays(-6))
            self._from_date.blockSignals(False)
            self._to_date.blockSignals(False)
        self._save_filters()
        self.refresh()

    def _on_filter_changed(self) -> None:
        self._save_filters()
        self.refresh()

    def _on_custom_date_changed(self) -> None:
        start = self._from_date.date()
        end = self._to_date.date()
        if end < start:
            sender = self.sender()
            if sender is self._from_date:
                self._to_date.blockSignals(True)
                self._to_date.setDate(start)
                self._to_date.blockSignals(False)
            else:
                self._from_date.blockSignals(True)
                self._from_date.setDate(end)
                self._from_date.blockSignals(False)
        self._save_filters()
        self.refresh()

    def _on_column_toggles_changed(self, _checked: bool) -> None:
        self._apply_column_visibility()
        self._save_filters()

    def _on_detail_date_changed(self) -> None:
        self._save_filters()
        if self._tabs.currentIndex() == 1:
            self._schedule_detail_refresh()

    def _on_tab_changed(self, index: int) -> None:
        if index == 1:
            self._schedule_detail_refresh()
        else:
            # Очищаем тяжёлую таблицу — иначе переключение вкладки подвисает.
            self._clear_detail_table()

    def _schedule_detail_refresh(self) -> None:
        self._detail_load_token += 1
        token = self._detail_load_token
        QTimer.singleShot(0, lambda: self._refresh_detail(token))

    def _clear_detail_table(self) -> None:
        self._detail_load_token += 1
        self._detail_table.setUpdatesEnabled(False)
        self._detail_table.clearContents()
        self._detail_table.setRowCount(0)
        self._detail_table.setUpdatesEnabled(True)
        self._detail_hint.setText("Сессии только за выбранный день")

    def _apply_column_visibility(self) -> None:
        self._table.setColumnHidden(COL_MANUAL, not self._show_manual_col.isChecked())
        show_apps = self._show_apps_col.isChecked()
        for col in self._app_columns.values():
            self._table.setColumnHidden(col, not show_apps)

    def _on_table_selection_changed(self) -> None:
        items = self._table.selectedItems()
        if not items:
            return
        day_value = items[0].data(Qt.ItemDataRole.UserRole)
        if isinstance(day_value, date):
            qday = QDate(day_value.year, day_value.month, day_value.day)
            self._manual_date.setDate(qday)
            self._detail_date.blockSignals(True)
            self._detail_date.setDate(qday)
            self._detail_date.blockSignals(False)
            self._save_filters()
            if self._tabs.currentIndex() == 1:
                self._schedule_detail_refresh()

    def _add_manual_time(self) -> None:
        hours = self._manual_hours.value()
        minutes = self._manual_minutes.value()
        if hours == 0 and minutes == 0:
            QMessageBox.information(self, "TimeTrack", "Укажите количество часов или минут.")
            return
        day = self._qdate_to_date(self._manual_date.date())
        added = self._storage.add_manual_time(day, hours, minutes)
        if added <= 0:
            return
        self._manual_hours.setValue(0)
        self._manual_minutes.setValue(0)
        self.refresh()
        self.manual_time_added.emit()

    def _qdate_to_date(self, value: QDate) -> date:
        return date(value.year(), value.month(), value.day())

    def _current_period(self) -> PeriodStats:
        mode = self._period_combo.currentData()
        if mode == "custom":
            start = self._qdate_to_date(self._from_date.date())
            end = self._qdate_to_date(self._to_date.date())
            return self._storage.get_range(start, end)

        anchor = self._qdate_to_date(self._anchor_date.date())
        if mode == "week":
            return self._storage.get_week(anchor)
        if mode == "month":
            return self._storage.get_month(anchor)
        return self._storage.get_range(anchor, anchor)

    @staticmethod
    def _right_item(text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return item

    def _format_app_duration(self, seconds: int) -> str:
        return format_duration(seconds) if seconds > 0 else "—"

    @staticmethod
    def _merge_sessions(sessions: list[AppSessionRow]) -> list[AppSessionRow]:
        """Склеить подряд идущие сессии одной программы."""
        if not sessions:
            return []
        merged: list[AppSessionRow] = []
        current = sessions[0]
        for session in sessions[1:]:
            if session.day == current.day and session.app_key == current.app_key:
                current = AppSessionRow(
                    day=current.day,
                    start_time=current.start_time,
                    end_time=session.end_time,
                    app_key=current.app_key,
                    app_name=current.app_name,
                    total_seconds=current.total_seconds + session.total_seconds,
                    active_seconds=current.active_seconds + session.active_seconds,
                )
            else:
                merged.append(current)
                current = session
        merged.append(current)
        return merged

    def _refresh_summary(self) -> None:
        period = self._current_period()
        if period.start == period.end:
            self._range_label.setText(period.start.strftime("%d.%m.%Y"))
        else:
            self._range_label.setText(
                f"{period.start.strftime('%d.%m.%Y')} — {period.end.strftime('%d.%m.%Y')}"
            )

        self._total_value[1].setText(format_duration(period.total_seconds))
        self._active_value[1].setText(format_duration(period.active_seconds))
        self._ratio_value[1].setText(format_percent(period.activity_ratio))

        days = [d for d in period.days if d.has_data]
        if self._period_combo.currentData() == "day" and not days:
            days = list(period.days)

        self._table.setUpdatesEnabled(False)
        self._table.blockSignals(True)
        self._table.setRowCount(len(days))
        for row, day_stats in enumerate(days):
            weekday = WEEKDAYS_RU[day_stats.day.weekday()]
            date_item = QTableWidgetItem(f"{day_stats.day.strftime('%d.%m.%Y')} ({weekday})")
            date_item.setData(Qt.ItemDataRole.UserRole, day_stats.day)
            self._table.setItem(row, COL_DATE, date_item)
            self._table.setItem(row, COL_START, QTableWidgetItem(day_stats.start_time or "—"))
            self._table.setItem(row, COL_END, QTableWidgetItem(day_stats.end_time or "—"))
            self._table.setItem(row, COL_TOTAL, self._right_item(format_duration(day_stats.total_seconds)))
            self._table.setItem(row, COL_ACTIVE, self._right_item(format_duration(day_stats.active_seconds)))
            self._table.setItem(row, COL_RATIO, self._right_item(format_percent(day_stats.activity_ratio)))
            manual_text = (
                format_duration(day_stats.manual_seconds)
                if day_stats.manual_seconds > 0
                else "—"
            )
            self._table.setItem(row, COL_MANUAL, self._right_item(manual_text))
            for app in TRACKED_APPS:
                seconds = day_stats.app_totals.get(app.key, 0)
                self._table.setItem(
                    row,
                    self._app_columns[app.key],
                    self._right_item(self._format_app_duration(seconds)),
                )
        self._table.blockSignals(False)
        self._table.setUpdatesEnabled(True)
        self._apply_column_visibility()

    def _refresh_detail(self, token: int | None = None) -> None:
        if token is not None and token != self._detail_load_token:
            return
        if self._tabs.currentIndex() != 1:
            return

        day = self._qdate_to_date(self._detail_date.date())
        sessions = self._merge_sessions(self._storage.get_sessions(day, day))
        sessions = [s for s in sessions if s.total_seconds >= DETAIL_MIN_SECONDS]
        weekday = WEEKDAYS_RU[day.weekday()]
        self._detail_hint.setText(
            f"Сессии за {day.strftime('%d.%m.%Y')} ({weekday}): {len(sessions)}"
        )

        self._detail_table.setUpdatesEnabled(False)
        self._detail_table.clearContents()
        self._detail_table.setRowCount(len(sessions))
        for row, session in enumerate(sessions):
            session_weekday = WEEKDAYS_RU[session.day.weekday()]
            self._detail_table.setItem(
                row,
                0,
                QTableWidgetItem(f"{session.day.strftime('%d.%m.%Y')} ({session_weekday})"),
            )
            self._detail_table.setItem(row, 1, QTableWidgetItem(session.start_time[:5]))
            self._detail_table.setItem(row, 2, QTableWidgetItem(session.end_time[:5]))
            self._detail_table.setItem(row, 3, QTableWidgetItem(session.app_name))
            self._detail_table.setItem(row, 4, self._right_item(format_duration(session.total_seconds)))
            self._detail_table.setItem(row, 5, self._right_item(format_duration(session.active_seconds)))
        self._detail_table.setUpdatesEnabled(True)
