import sys

from PyQt6.QtWidgets import QApplication
from qfluentwidgets import Theme, setTheme, setThemeColor

from dcpm.ui.main_window import MainWindow
from dcpm.ui.theme.colors import PRIMARY_COLOR


def run(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv
    smoke = "--smoke" in argv

    app = QApplication(argv)
    setTheme(Theme.LIGHT)
    setThemeColor(PRIMARY_COLOR)

    window = MainWindow()
    if smoke:
        _ = window
        return 0

    window.show()

    return app.exec()
