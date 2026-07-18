"""Statistics window with day / week / month / custom range."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QCloseEvent, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from formatting import format_duration, format_percent
from storage import PeriodStats, Storage

WEEKDAYS_RU = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")


class StatsWindow(QMainWindow):
    def __init__(self, storage: Storage, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._storage = storage
        self.setWindowTitle("TimeTrack — статистика")
        self.resize(560, 480)
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #f3f5f7; color: #1c242b; }
            QComboBox, QDateEdit {
                background: #ffffff;
                border: 1px solid #c9d0d6;
                border-radius: 4px;
                padding: 4px 8px;
                min-height: 26px;
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
        self._period_combo = QComboBox()
        self._period_combo.addItem("День", "day")
        self._period_combo.addItem("Неделя", "week")
        self._period_combo.addItem("Месяц", "month")
        self._period_combo.addItem("Период", "custom")
        self._period_combo.currentIndexChanged.connect(self._on_period_mode_changed)
        controls.addWidget(self._period_combo, stretch=1)

        self._anchor_date = QDateEdit()
        self._anchor_date.setCalendarPopup(True)
        self._anchor_date.setDisplayFormat("dd.MM.yyyy")
        self._anchor_date.setDate(QDate.currentDate())
        self._anchor_date.dateChanged.connect(self.refresh)
        controls.addWidget(self._anchor_date)

        layout.addLayout(controls)

        self._custom_form = QWidget()
        custom_layout = QFormLayout(self._custom_form)
        custom_layout.setContentsMargins(0, 0, 0, 0)
        self._from_date = QDateEdit()
        self._from_date.setCalendarPopup(True)
        self._from_date.setDisplayFormat("dd.MM.yyyy")
        self._from_date.setDate(QDate.currentDate().addDays(-6))
        self._from_date.dateChanged.connect(self.refresh)
        self._to_date = QDateEdit()
        self._to_date.setCalendarPopup(True)
        self._to_date.setDisplayFormat("dd.MM.yyyy")
        self._to_date.setDate(QDate.currentDate())
        self._to_date.dateChanged.connect(self.refresh)
        custom_layout.addRow("С", self._from_date)
        custom_layout.addRow("По", self._to_date)
        self._custom_form.setVisible(False)
        layout.addWidget(self._custom_form)

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

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Дата", "Общее", "Активное"])
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._table.setShowGrid(False)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setAlternatingRowColors(True)
        layout.addWidget(self._table, stretch=1)

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
        self.refresh()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        event.ignore()
        self.hide()

    def _on_period_mode_changed(self) -> None:
        mode = self._period_combo.currentData()
        is_custom = mode == "custom"
        self._custom_form.setVisible(is_custom)
        self._anchor_date.setVisible(not is_custom)
        self.refresh()

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

    def refresh(self) -> None:
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

        days = [d for d in period.days if d.total_seconds > 0 or d.active_seconds > 0]
        if self._period_combo.currentData() == "day" and not days:
            days = list(period.days)

        self._table.setRowCount(len(days))
        for row, day_stats in enumerate(days):
            weekday = WEEKDAYS_RU[day_stats.day.weekday()]
            date_item = QTableWidgetItem(f"{day_stats.day.strftime('%d.%m.%Y')} ({weekday})")
            total_item = QTableWidgetItem(format_duration(day_stats.total_seconds))
            active_item = QTableWidgetItem(format_duration(day_stats.active_seconds))
            total_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            active_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, 0, date_item)
            self._table.setItem(row, 1, total_item)
            self._table.setItem(row, 2, active_item)
