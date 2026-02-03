import sys
import traceback
from PyQt6.QtWidgets import QApplication, QMessageBox
from qfluentwidgets import Theme, setTheme, setThemeColor

from dcpm.ui.main_window import MainWindow
from dcpm.ui.theme.colors import PRIMARY_COLOR


def exception_hook(exctype, value, tb):
    traceback_str = "".join(traceback.format_exception(exctype, value, tb))
    print(traceback_str, file=sys.stderr)
    # 尝试弹窗显示错误（如果 QApplication 已创建）
    if QApplication.instance():
        QMessageBox.critical(None, "Critical Error", f"An unhandled exception occurred:\n{value}\n\nSee console for details.")
    sys.exit(1)


def run(argv: list[str] | None = None) -> int:
    sys.excepthook = exception_hook

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
