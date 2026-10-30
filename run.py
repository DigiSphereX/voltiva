import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


def _install_crash_handling() -> None:
    """Log every unhandled exception to ~/.kahraba_smart/voltiva.log and show a dialog.

    PyQt6 calls ``qFatal`` (hard abort, no message) when a slot raises and no
    ``sys.excepthook`` is installed - the window would just vanish.
    """
    import logging
    import traceback
    from logging.handlers import RotatingFileHandler

    from kse.infrastructure.sqlite.db import default_data_dir

    log = logging.getLogger("voltiva")
    log.setLevel(logging.INFO)
    try:
        folder = default_data_dir()
        folder.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(folder / "voltiva.log", maxBytes=512_000, backupCount=2,
                                      encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(handler)
    except OSError:
        pass  # logging is best-effort; never block start-up

    def hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        log.error("Unhandled exception:\n%s", text)
        try:
            from PyQt6.QtWidgets import QApplication, QMessageBox
            if QApplication.instance() is not None:
                box = QMessageBox(QMessageBox.Icon.Critical, "Voltiva",
                                  f"{exc_type.__name__}: {exc}")
                box.setInformativeText("Details were saved to voltiva.log")
                box.exec()
        except Exception:  # noqa: BLE001
            pass

    sys.excepthook = hook


def main() -> int:
    import logging
    import time

    started = time.perf_counter()
    from PyQt6.QtGui import QFont, QIcon
    from PyQt6.QtWidgets import QApplication

    _install_crash_handling()

    from kse.presentation.app_context import AppContext
    from kse.presentation.main_window import MainWindow
    from kse.presentation import theme

    app = QApplication(sys.argv)
    app.setApplicationName("Voltiva")
    app.setStyle("Fusion")
    theme.register_fonts()
    app.setFont(QFont("Cairo", 10))

    context = AppContext()
    theme.apply(app, context.current_theme(), rtl=context.i18n.rtl)
    app.setWindowIcon(QIcon(context.current_icon_path()))
    window = MainWindow(context)
    window.show()
    window.raise_()
    window.activateWindow()
    logging.getLogger("voltiva").info(
        "startup: window shown in %.2fs", time.perf_counter() - started)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())