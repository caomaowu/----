import os
import sys
import logging
import traceback
from PyQt6.QtWidgets import QApplication

from dcpm.ui.theme.colors import PRIMARY_COLOR


def exception_hook(exctype, value, tb):
    from PyQt6.QtCore import Qt
    from qfluentwidgets import InfoBar, InfoBarPosition

    traceback_str = "".join(traceback.format_exception(exctype, value, tb))
    logging.critical(f"Unhandled exception:\n{traceback_str}")
    print(traceback_str, file=sys.stderr)
    # 尝试弹窗显示错误（如果 QApplication 已创建）
    if QApplication.instance():
         # 尝试获取当前活动窗口作为父窗口
        parent = QApplication.activeWindow()
        if parent:
             InfoBar.error(
                title='Critical Error',
                content=f"An unhandled exception occurred:\n{value}",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=-1, # 不自动关闭
                parent=parent
            )
    sys.exit(1)


def run(argv: list[str] | None = None) -> int:
    # Configure logging
    log_file = os.path.join(os.getcwd(), 'crash.log')
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        encoding='utf-8',
        filemode='a'
    )
    logging.info("Application starting...")

    sys.excepthook = exception_hook

    if argv is None:
        argv = sys.argv
    smoke = "--smoke" in argv

    os.environ.setdefault("QT_API", "pyqt6")
    app = QApplication(argv)
    from qfluentwidgets import Theme, setTheme, setThemeColor
    from dcpm.ui.main_window import MainWindow

    setTheme(Theme.LIGHT)
    setThemeColor(PRIMARY_COLOR)

    window = MainWindow()
    if smoke:
        _ = window
        return 0

    window.show()

    return app.exec()
