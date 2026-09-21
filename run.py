import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


def main() -> int:
    from PyQt6.QtGui import QFont, QIcon
    from PyQt6.QtWidgets import QApplication

    from kse.presentation.app_context import AppContext
    from kse.presentation.main_window import MainWindow
    from kse.presentation import theme

    app = QApplication(sys.argv)
    app.setApplicationName("Voltiva")
    app.setStyle("Fusion")
    theme.register_fonts()
    app.setFont(QFont("Cairo", 10))

    context = AppContext()
    theme.apply(app, context.current_theme())
    app.setWindowIcon(QIcon(context.current_icon_path()))
    window = MainWindow(context)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())