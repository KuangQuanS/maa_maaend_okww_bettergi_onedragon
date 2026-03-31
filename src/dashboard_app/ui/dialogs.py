from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from ..models import OCRActionSpec, Offset, Rect


class OCRActionDialog(QDialog):
    def __init__(self, action: OCRActionSpec, parent=None):
        super().__init__(parent)
        self.setWindowTitle("BetterGI OCR 兜底配置")
        self.resize(520, 360)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.action_type = QComboBox()
        self.action_type.addItems(["ocr_click_text", "template_click"])
        self.action_type.setCurrentText(action.action_type)

        self.window_title = QLineEdit(action.window_title)
        self.window_class = QLineEdit(action.window_class)
        self.match_target = QLineEdit(action.match_target)
        self.template_path = QLineEdit(action.template_path)
        self.max_retry = QSpinBox()
        self.max_retry.setRange(1, 10)
        self.max_retry.setValue(action.max_retry)

        self.roi_x = QSpinBox(); self.roi_x.setRange(-10000, 10000); self.roi_x.setValue(action.roi.x)
        self.roi_y = QSpinBox(); self.roi_y.setRange(-10000, 10000); self.roi_y.setValue(action.roi.y)
        self.roi_w = QSpinBox(); self.roi_w.setRange(0, 10000); self.roi_w.setValue(action.roi.width)
        self.roi_h = QSpinBox(); self.roi_h.setRange(0, 10000); self.roi_h.setValue(action.roi.height)
        self.offset_x = QSpinBox(); self.offset_x.setRange(-2000, 2000); self.offset_x.setValue(action.click_offset.x)
        self.offset_y = QSpinBox(); self.offset_y.setRange(-2000, 2000); self.offset_y.setValue(action.click_offset.y)

        path_row = QHBoxLayout()
        path_row.addWidget(self.template_path)
        browse = QPushButton("浏览…")
        browse.clicked.connect(self._browse_template)
        path_row.addWidget(browse)

        form.addRow("动作类型", self.action_type)
        form.addRow("窗口标题", self.window_title)
        form.addRow("窗口类名", self.window_class)
        form.addRow("匹配目标", self.match_target)
        form.addRow("模板文件", path_row)
        form.addRow("区域 X", self.roi_x)
        form.addRow("区域 Y", self.roi_y)
        form.addRow("区域宽度", self.roi_w)
        form.addRow("区域高度", self.roi_h)
        form.addRow("点击偏移 X", self.offset_x)
        form.addRow("点击偏移 Y", self.offset_y)
        form.addRow("最大重试", self.max_retry)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse_template(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择模板图片", "", "图片文件 (*.png *.jpg *.bmp)")
        if path:
            self.template_path.setText(path)

    def action(self) -> OCRActionSpec:
        return OCRActionSpec(
            action_type=self.action_type.currentText(),
            window_title=self.window_title.text().strip(),
            window_class=self.window_class.text().strip(),
            roi=Rect(self.roi_x.value(), self.roi_y.value(), self.roi_w.value(), self.roi_h.value()),
            match_target=self.match_target.text().strip(),
            click_offset=Offset(self.offset_x.value(), self.offset_y.value()),
            max_retry=self.max_retry.value(),
            template_path=self.template_path.text().strip(),
            enabled=True,
        )
