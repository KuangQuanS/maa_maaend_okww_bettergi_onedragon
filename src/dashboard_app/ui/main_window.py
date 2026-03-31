from __future__ import annotations

from functools import partial

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QTextCursor
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..controller import DashboardController
from ..defaults import app_label, state_label, step_label, summary_label
from .widgets import AppCard


TARGET_TYPE_LABELS = {
    "app": "程序",
    "workflow": "顺序",
}


class MainWindow(QMainWindow):
    def __init__(self, controller: DashboardController):
        super().__init__()
        self.controller = controller
        self._sequence_refreshing = False
        self._sequence_active_run_id = ""
        self.setWindowTitle("多程序编排面板")
        self.resize(1540, 940)
        self._apply_theme()

        central = QWidget()
        central.setObjectName("centralSurface")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        toolbar = self._build_toolbar()
        root.addWidget(toolbar)
        self._apply_shadow(toolbar, blur=28, alpha=20, offset_y=8)

        splitter = QSplitter()
        splitter.setObjectName("mainSplitter")
        splitter.setChildrenCollapsible(False)
        apps_panel = self._build_apps_panel()
        sequence_panel = self._build_sequence_panel()
        logs_panel = self._build_logs_panel()
        splitter.addWidget(apps_panel)
        splitter.addWidget(sequence_panel)
        splitter.addWidget(logs_panel)
        splitter.setSizes([520, 380, 700])
        self._apply_shadow(apps_panel, blur=26, alpha=18, offset_y=8)
        self._apply_shadow(sequence_panel, blur=26, alpha=18, offset_y=8)
        self._apply_shadow(logs_panel, blur=26, alpha=18, offset_y=8)
        root.addWidget(splitter, 1)

        self.app_cards: dict[str, AppCard] = {}
        self._build_cards()

        self.run_sequence_button.clicked.connect(self._run_sequence)
        self.stop_sequence_button.clicked.connect(self._stop_sequence)
        self.emergency_button.clicked.connect(self.controller.emergency_stop)
        self.refresh_button.clicked.connect(self.refresh_snapshot)
        self.sequence_list.itemChanged.connect(self._on_sequence_item_changed)
        self.sequence_list.currentRowChanged.connect(self._update_sequence_buttons)
        self.move_up_button.clicked.connect(partial(self._move_sequence_item, -1))
        self.move_down_button.clicked.connect(partial(self._move_sequence_item, 1))
        self.select_all_button.clicked.connect(partial(self._set_all_sequence_checked, True))
        self.clear_all_button.clicked.connect(partial(self._set_all_sequence_checked, False))

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_snapshot)
        self.timer.start(1000)
        self.refresh_snapshot()

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow {
                background: #edf3f7;
                color: #132031;
                font-size: 14px;
            }
            QWidget#centralSurface {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #eef5fb, stop:0.5 #f7fbff, stop:1 #edf4ef);
            }
            QFrame#toolbarCard, QFrame#panelCard {
                background: rgba(255, 255, 255, 0.92);
                border: 1px solid #d7e4ef;
                border-radius: 24px;
            }
            QLabel#panelTitle {
                color: #132031;
                font-size: 17px;
                font-weight: 800;
            }
            QLabel#panelSubtitle {
                color: #5e7186;
                font-size: 12px;
            }
            QLabel#sequenceStatus {
                color: #1d4466;
                background: #eef7ff;
                border: 1px solid #d9eafb;
                border-radius: 14px;
                padding: 10px 12px;
                font-weight: 700;
            }
            QFrame#appCard {
                background: #fbfdff;
                border: 1px solid #d9e7f1;
                border-radius: 22px;
            }
            QLabel#appCardTitle {
                color: #14263a;
                font-size: 18px;
                font-weight: 800;
            }
            QLabel#appCardSubtitle {
                color: #617487;
                font-size: 12px;
            }
            QLabel#cardSectionTitle {
                color: #55687a;
                font-size: 12px;
                font-weight: 700;
            }
            QLineEdit#cardPath {
                background: #f6faff;
                color: #1e3348;
            }
            QLabel#summaryText {
                color: #183149;
                line-height: 1.35em;
            }
            QFrame#warningBox {
                background: #fff7e6;
                border: 1px solid #f5d48a;
                border-radius: 16px;
            }
            QLabel#warningTitle {
                color: #a16207;
                font-size: 12px;
                font-weight: 800;
            }
            QLabel#warningText {
                color: #915f08;
            }
            QLabel#toolbarLabel {
                color: #4b5e73;
                font-size: 12px;
                font-weight: 700;
            }
            QLineEdit, QListWidget, QPlainTextEdit {
                background: #f8fbff;
                border: 1px solid #d7e4ef;
                border-radius: 14px;
                padding: 8px 10px;
                selection-background-color: #dbeafe;
                selection-color: #17324d;
            }
            QListWidget {
                outline: none;
                padding: 8px;
            }
            QListWidget::item {
                background: rgba(244, 248, 252, 0.9);
                border: 1px solid #e2ebf3;
                border-radius: 12px;
                padding: 10px 12px;
                margin: 4px 0px;
            }
            QListWidget::item:hover {
                background: #eef7ff;
            }
            QListWidget::item:selected {
                background: #e0f2fe;
                color: #0f3b53;
                border-color: #bfdbfe;
            }
            QPlainTextEdit#detailConsole {
                background: #f9fbfd;
                color: #163047;
                border-radius: 18px;
            }
            QPlainTextEdit#logConsole {
                background: #08131f;
                color: #dbe7f3;
                border: 1px solid #13283f;
                border-radius: 18px;
                font-family: "Microsoft YaHei";
                font-size: 12px;
            }
            QPushButton {
                min-height: 38px;
                border-radius: 14px;
                padding: 0 16px;
                font-weight: 700;
                border: 1px solid transparent;
            }
            QPushButton#primaryButton {
                background: #123a61;
                color: white;
            }
            QPushButton#primaryButton:hover {
                background: #184c7a;
            }
            QPushButton#secondaryButton {
                background: #eff6ff;
                color: #184b73;
                border-color: #c9dff4;
            }
            QPushButton#secondaryButton:hover {
                background: #e3f0ff;
            }
            QPushButton#ghostButton {
                background: #ffffff;
                color: #35526f;
                border-color: #d7e4ef;
            }
            QPushButton#ghostButton:hover {
                background: #f6fbff;
            }
            QCheckBox#parallelToggle {
                color: #35526f;
                spacing: 8px;
                font-weight: 700;
            }
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 12px;
                margin: 4px;
            }
            QScrollBar::handle:vertical {
                background: #c9d9e7;
                border-radius: 6px;
                min-height: 24px;
            }
            QSplitter::handle {
                background: transparent;
                width: 12px;
            }
            QStatusBar {
                color: #516477;
                background: rgba(255, 255, 255, 0.75);
            }
            """
        )

    def _apply_shadow(self, widget: QWidget, *, blur: int, alpha: int, offset_y: int) -> None:
        effect = QGraphicsDropShadowEffect(self)
        effect.setBlurRadius(blur)
        effect.setOffset(0, offset_y)
        effect.setColor(QColor(15, 44, 74, alpha))
        widget.setGraphicsEffect(effect)

    def _build_toolbar(self) -> QWidget:
        card = QFrame()
        card.setObjectName("toolbarCard")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        self.run_sequence_button = QPushButton("运行顺序")
        self.run_sequence_button.setObjectName("primaryButton")
        self.stop_sequence_button = QPushButton("停止顺序")
        self.stop_sequence_button.setObjectName("secondaryButton")
        self.emergency_button = QPushButton("紧急停止")
        self.emergency_button.setObjectName("ghostButton")
        self.refresh_button = QPushButton("刷新")
        self.refresh_button.setObjectName("ghostButton")

        layout.addWidget(self.run_sequence_button)
        layout.addWidget(self.stop_sequence_button)
        layout.addStretch(1)
        layout.addWidget(self.refresh_button)
        layout.addWidget(self.emergency_button)
        return card

    def _panel_shell(self, title: str, subtitle: str) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("panelCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title_label = QLabel(title)
        title_label.setObjectName("panelTitle")
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("panelSubtitle")
        subtitle_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        return card, layout

    def _build_apps_panel(self) -> QWidget:
        card, layout = self._panel_shell("应用控制", "单独启动程序、切换路径、查看每个任务的即时状态。")

        app_container = QWidget()
        self.app_layout = QVBoxLayout(app_container)
        self.app_layout.setContentsMargins(0, 0, 0, 0)
        self.app_layout.setSpacing(14)
        self.app_layout.addStretch(1)

        app_scroll = QScrollArea()
        app_scroll.setWidgetResizable(True)
        app_scroll.setWidget(app_container)
        layout.addWidget(app_scroll, 1)
        return card

    def _build_sequence_panel(self) -> QWidget:
        card, layout = self._panel_shell("顺序执行", "勾选决定执行哪些程序，列表上下顺序决定启动先后。")
        self.sequence_status = QLabel("当前未配置顺序。")
        self.sequence_status.setObjectName("sequenceStatus")
        self.sequence_status.setWordWrap(True)
        layout.addWidget(self.sequence_status)

        self.sequence_list = QListWidget()
        layout.addWidget(self.sequence_list, 1)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.move_up_button = QPushButton("上移")
        self.move_up_button.setObjectName("secondaryButton")
        self.move_down_button = QPushButton("下移")
        self.move_down_button.setObjectName("secondaryButton")
        self.select_all_button = QPushButton("全选")
        self.select_all_button.setObjectName("ghostButton")
        self.clear_all_button = QPushButton("清空")
        self.clear_all_button.setObjectName("ghostButton")
        actions.addWidget(self.move_up_button)
        actions.addWidget(self.move_down_button)
        actions.addStretch(1)
        actions.addWidget(self.select_all_button)
        actions.addWidget(self.clear_all_button)
        layout.addLayout(actions)
        return card

    def _build_logs_panel(self) -> QWidget:
        card, layout = self._panel_shell("运行详情", "左侧看状态，右侧看当前执行片段和控制器事件。")

        details_title = QLabel("当前运行")
        details_title.setObjectName("toolbarLabel")
        self.active_details = QPlainTextEdit()
        self.active_details.setObjectName("detailConsole")
        self.active_details.setReadOnly(True)

        events_title = QLabel("事件日志")
        events_title.setObjectName("toolbarLabel")
        self.event_log = QPlainTextEdit()
        self.event_log.setObjectName("logConsole")
        self.event_log.setReadOnly(True)

        layout.addWidget(details_title)
        layout.addWidget(self.active_details, 1)
        layout.addWidget(events_title)
        layout.addWidget(self.event_log, 1)
        return card

    def _build_cards(self) -> None:
        snapshot = self.controller.snapshot()
        apps = snapshot.get("apps", [])
        for app in apps:
            card = AppCard(app["id"], app["label"], show_ocr_button=False)
            card.run_button.clicked.connect(partial(self.controller.start_app, app["id"]))
            card.stop_button.clicked.connect(partial(self.controller.stop_app, app["id"]))
            card.path_button.clicked.connect(partial(self._choose_path, app["id"]))
            card.parallel_checkbox.toggled.connect(partial(self.controller.set_parallel_override, app["id"]))
            if app["id"] != "maa":
                card.parallel_checkbox.setEnabled(False)
                card.parallel_checkbox.setToolTip("当前程序按独占前台自动化处理，只允许与 MAA 并行。")
            else:
                card.parallel_checkbox.setToolTip("关闭后，MAA 也会改为单独运行。")
            self.app_layout.insertWidget(self.app_layout.count() - 1, card)
            self.app_cards[app["id"]] = card

    def _choose_path(self, app_id: str) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择可执行文件", "", "可执行文件 (*.exe)")
        if path:
            self.controller.set_app_path(app_id, path)
            self.refresh_snapshot()

    def _run_sequence(self) -> None:
        run_id = self.controller.start_sequence()
        if run_id is None:
            QMessageBox.information(self, "无法启动", "当前顺序没有勾选任何程序，或者已有任务正在运行。")

    def _stop_sequence(self) -> None:
        if self._sequence_active_run_id:
            self.controller.stop_run(self._sequence_active_run_id)

    def refresh_snapshot(self) -> None:
        snapshot = self.controller.snapshot()
        self._refresh_apps(snapshot)
        self._refresh_sequence(snapshot)
        self._refresh_logs(snapshot)
        active_count = len(snapshot.get("active_details", []))
        self.statusBar().showMessage(f"当前活跃运行：{active_count}")

    def _refresh_apps(self, snapshot: dict) -> None:
        for app in snapshot.get("apps", []):
            card = self.app_cards.get(app["id"])
            if card is not None:
                card.set_data(app)

    def _refresh_sequence(self, snapshot: dict) -> None:
        sequence = snapshot.get("sequence", {})
        self._sequence_active_run_id = sequence.get("active_run_id", "")
        steps = sequence.get("steps", [])
        steps_text = " -> ".join(app_label(step) for step in steps) if steps else "当前未勾选任何程序"
        summary = summary_label(sequence.get("summary", "")) or "等待运行"
        self.sequence_status.setText(
            f"状态：{state_label(sequence.get('state', 'IDLE'))}\n当前顺序：{steps_text}\n摘要：{summary}"
        )

        selected_app_id = ""
        current_item = self.sequence_list.currentItem()
        if current_item is not None:
            selected_app_id = str(current_item.data(Qt.ItemDataRole.UserRole))

        self._sequence_refreshing = True
        self.sequence_list.blockSignals(True)
        self.sequence_list.clear()
        for item_data in sequence.get("items", []):
            item = QListWidgetItem(item_data["label"])
            item.setData(Qt.ItemDataRole.UserRole, item_data["id"])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            item.setCheckState(Qt.CheckState.Checked if item_data.get("enabled") else Qt.CheckState.Unchecked)
            self.sequence_list.addItem(item)
            if item_data["id"] == selected_app_id:
                self.sequence_list.setCurrentItem(item)
        if not selected_app_id and self.sequence_list.count():
            self.sequence_list.setCurrentRow(0)
        self.sequence_list.blockSignals(False)
        self._sequence_refreshing = False
        self._update_sequence_buttons()

    def _move_sequence_item(self, offset: int) -> None:
        row = self.sequence_list.currentRow()
        target = row + offset
        if row < 0 or target < 0 or target >= self.sequence_list.count():
            return
        item = self.sequence_list.takeItem(row)
        self.sequence_list.insertItem(target, item)
        self.sequence_list.setCurrentRow(target)
        self._save_sequence_from_ui()

    def _set_all_sequence_checked(self, checked: bool) -> None:
        self._sequence_refreshing = True
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for index in range(self.sequence_list.count()):
            self.sequence_list.item(index).setCheckState(state)
        self._sequence_refreshing = False
        self._save_sequence_from_ui()

    def _on_sequence_item_changed(self, _item: QListWidgetItem) -> None:
        if not self._sequence_refreshing:
            self._save_sequence_from_ui()

    def _save_sequence_from_ui(self) -> None:
        order: list[str] = []
        enabled: dict[str, bool] = {}
        for index in range(self.sequence_list.count()):
            item = self.sequence_list.item(index)
            app_id = str(item.data(Qt.ItemDataRole.UserRole))
            order.append(app_id)
            enabled[app_id] = item.checkState() == Qt.CheckState.Checked
        self.controller.update_sequence(order, enabled)

    def _update_sequence_buttons(self) -> None:
        row = self.sequence_list.currentRow()
        count = self.sequence_list.count()
        has_selection = row >= 0
        self.move_up_button.setEnabled(has_selection and row > 0)
        self.move_down_button.setEnabled(has_selection and row < count - 1)

    def _display_target_name(self, item: dict) -> str:
        if item.get("target_type") == "app":
            return app_label(item.get("target_id", ""))
        if item.get("target_id") == "custom_sequence":
            return "当前顺序"
        for workflow in self.controller.workflows:
            if workflow.id == item.get("target_id"):
                return workflow.name
        return item.get("target_id", "")

    def _set_console_text(self, widget: QPlainTextEdit, text: str, *, follow_tail: bool = False) -> None:
        if widget.toPlainText() == text:
            return
        widget.setPlainText(text)
        if follow_tail:
            widget.moveCursor(QTextCursor.MoveOperation.End)
            bar = widget.verticalScrollBar()
            bar.setValue(bar.maximum())

    def _refresh_logs(self, snapshot: dict) -> None:
        details = []
        for item in snapshot.get("active_details", []):
            section = [
                f"[{TARGET_TYPE_LABELS.get(item['target_type'], item['target_type'])}] {self._display_target_name(item)}",
                f"状态：{state_label(item['state'])}",
                f"阶段：{step_label(item['step'])}",
                f"摘要：{summary_label(item['summary']) or '暂无'}",
            ]
            if item.get("raw_log"):
                section.append("")
                section.append(item["raw_log"])
            details.append("\n".join(section))
        self._set_console_text(self.active_details, "\n\n".join(details) or "当前没有活跃任务。", follow_tail=True)
        self._set_console_text(self.event_log, "\n".join(snapshot.get("event_log", [])), follow_tail=True)
