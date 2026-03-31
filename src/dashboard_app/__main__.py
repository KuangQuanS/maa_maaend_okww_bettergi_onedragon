from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont, QFontDatabase, QIcon
from PySide6.QtWidgets import QApplication

from .controller import DashboardController
from .paths import resolve_app_root
from .ui.main_window import MainWindow


def _preferred_font_family() -> str:
    families = set(QFontDatabase.families())
    for name in ("Microsoft YaHei", "Noto Sans SC", "Microsoft JhengHei", "SimHei", "Segoe UI"):
        if name in families:
            return name
    for font_path in (
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\msyhbd.ttc"),
        Path(r"C:\Windows\Fonts\NotoSansSC-Regular.otf"),
    ):
        if not font_path.exists():
            continue
        font_id = QFontDatabase.addApplicationFont(str(font_path))
        if font_id < 0:
            continue
        for family in QFontDatabase.applicationFontFamilies(font_id):
            if family:
                return family
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="多程序编排面板")
    parser.add_argument("--smoke-test", action="store_true", help="启动界面并在短时间后自动退出。")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setApplicationName("多程序编排面板")
    icon_path = resolve_app_root() / "dashboard.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    family = _preferred_font_family()
    if family:
        app.setFont(QFont(family, 10))
    controller = DashboardController()
    window = MainWindow(controller)
    window.show()

    if args.smoke_test:
        QTimer.singleShot(1200, app.quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
