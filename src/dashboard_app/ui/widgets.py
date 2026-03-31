from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..defaults import app_subtitle, state_label, summary_label


STATE_TONE = {
    "IDLE": ("#F3F6FB", "#4B5B73"),
    "VALIDATING": ("#E7F1FF", "#2563EB"),
    "LAUNCHING": ("#E8F7FF", "#0369A1"),
    "STARTING": ("#FFF4D8", "#B45309"),
    "RUNNING": ("#E9FBEF", "#15803D"),
    "CLEANUP": ("#F3E8FF", "#7C3AED"),
    "DONE": ("#ECFDF3", "#047857"),
    "FAILED": ("#FDECEC", "#DC2626"),
    "CANCELLED": ("#F3F4F6", "#6B7280"),
}


class AppCard(QWidget):
    def __init__(self, app_id: str, label: str, show_ocr_button: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.app_id = app_id
        self.setObjectName("appCardHost")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self.card = QFrame()
        self.card.setObjectName("appCard")
        root.addWidget(self.card)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(22)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(19, 46, 76, 18))
        self.card.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self.card)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(12)
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        self.title_label = QLabel(label)
        self.title_label.setObjectName("appCardTitle")
        self.subtitle_label = QLabel(app_subtitle(app_id))
        self.subtitle_label.setObjectName("appCardSubtitle")
        title_col.addWidget(self.title_label)
        title_col.addWidget(self.subtitle_label)
        header.addLayout(title_col, 1)

        self.state_badge = QLabel(state_label("IDLE"))
        self.state_badge.setObjectName("stateBadge")
        self.state_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.state_badge.setMinimumWidth(86)
        header.addWidget(self.state_badge, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)

        path_title = QLabel("程序路径")
        path_title.setObjectName("cardSectionTitle")
        layout.addWidget(path_title)

        self.path_edit = QLineEdit()
        self.path_edit.setObjectName("cardPath")
        self.path_edit.setReadOnly(True)
        self.path_edit.setPlaceholderText("未设置可执行文件路径")
        layout.addWidget(self.path_edit)

        summary_title = QLabel("运行摘要")
        summary_title.setObjectName("cardSectionTitle")
        layout.addWidget(summary_title)

        self.summary_label = QLabel("等待任务启动。")
        self.summary_label.setObjectName("summaryText")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self.warning_box = QFrame()
        self.warning_box.setObjectName("warningBox")
        warning_layout = QVBoxLayout(self.warning_box)
        warning_layout.setContentsMargins(12, 10, 12, 10)
        warning_layout.setSpacing(4)
        self.warning_title = QLabel("注意")
        self.warning_title.setObjectName("warningTitle")
        self.warning_label = QLabel("")
        self.warning_label.setObjectName("warningText")
        self.warning_label.setWordWrap(True)
        warning_layout.addWidget(self.warning_title)
        warning_layout.addWidget(self.warning_label)
        layout.addWidget(self.warning_box)

        footer = QHBoxLayout()
        footer.setSpacing(10)
        self.parallel_checkbox = QCheckBox("允许并行")
        self.parallel_checkbox.setObjectName("parallelToggle")
        footer.addWidget(self.parallel_checkbox)
        footer.addStretch(1)
        layout.addLayout(footer)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.run_button = QPushButton("运行")
        self.run_button.setObjectName("primaryButton")
        self.stop_button = QPushButton("停止")
        self.stop_button.setObjectName("secondaryButton")
        self.path_button = QPushButton("选择路径")
        self.path_button.setObjectName("ghostButton")
        buttons.addWidget(self.run_button)
        buttons.addWidget(self.stop_button)
        buttons.addWidget(self.path_button)
        if show_ocr_button:
            self.ocr_button = QPushButton("OCR 兜底")
            self.ocr_button.setObjectName("ghostButton")
            buttons.addWidget(self.ocr_button)
        else:
            self.ocr_button = None
        layout.addLayout(buttons)

        self.warning_box.hide()

    def _set_badge_tone(self, state: str) -> None:
        background, foreground = STATE_TONE.get(state, STATE_TONE["IDLE"])
        self.state_badge.setStyleSheet(
            f"background:{background}; color:{foreground}; border:1px solid {background};"
            "border-radius:14px; padding:6px 12px; font-weight:700;"
        )

    def set_data(self, payload: dict) -> None:
        state = payload.get("state", "IDLE")
        self.title_label.setText(payload.get("label", self.app_id))
        self.subtitle_label.setText(app_subtitle(self.app_id))
        self.path_edit.setText(payload.get("path", ""))
        self.state_badge.setText(state_label(state))
        self._set_badge_tone(state)
        self.summary_label.setText(summary_label(payload.get("summary", "")) or "等待任务启动。")
        warnings = payload.get("warnings", [])
        self.warning_label.setText("\n".join(warnings))
        self.warning_box.setVisible(bool(warnings))
        self.parallel_checkbox.blockSignals(True)
        self.parallel_checkbox.setChecked(bool(payload.get("allow_parallel", False)))
        self.parallel_checkbox.blockSignals(False)
