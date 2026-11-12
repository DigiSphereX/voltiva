# Voltiva — Smart Electricity Billing

[![License: MIT](https://img.shields.io/badge/License-MIT-informational.svg?style=for-the-badge)](LICENSE)
[![Release](https://img.shields.io/badge/Release-v1.2.0-brightgreen.svg?style=for-the-badge)](https://github.com/DigiSphereX/voltiva/releases/latest)
[![Donate](https://img.shields.io/badge/Donate-PayPal-0070BA.svg?style=for-the-badge)](https://www.paypal.com/donate/?hosted_button_id=CFANQH892RPH2)

![Python](https://img.shields.io/badge/Python-3.12-blue)
![PyQt6](https://img.shields.io/badge/PyQt6-6.5%2B-41CD52)
![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-0078D6)
![Version](https://img.shields.io/badge/Version-1.2.0-brightgreen)

Voltiva is a free, open-source desktop application for recording, reviewing,
comparing and verifying electricity bills. It turns the official tariff rules
into an **auditable billing engine**: every amount is explained, printable and
verifiable, and the rules can be updated without editing code.

## What it does

- **Auditable invoices** — each bill shows the full calculation chain (tiers,
  fees, charges) so you can always answer *"how did you arrive at this
  number?"*.
- **Tariff management** — tariffs, fee schedules and rules are data, editable
  in-app via the Tariff Manager; simulation histories are kept for comparison.
- **AI bill scanning** — photograph or scan a bill and a vision model reads the
  readings, dates, consumption, amount, account/meter numbers and the
  subscriber name into the import form. Three engines in Settings:
  **Automatic — free AI** (built-in service, free key), **Custom AI** (any
  OpenAI-compatible URL, key and model) and **Offline — Tesseract**.
- **Smart import (OCR)** — the offline reader stays available for fully private
  scanning, and automatic mode falls back to it when the AI service is
  unreachable (requires Tesseract with the `ara` and `eng` language packs).
- **Subscribers & meters** — manage subscriber records, meters, previous
  readings and debts.
- **Analytics dashboard** — usage trends, cost breakdowns and exports.
- **Verification & review** — compare simulated versus issued amounts to spot
  discrepancies.
- **Print / PDF export** — professional printable documents and receipts, with
  no extra libraries required.
- **English demo data** — one click in Settings loads a fully fictional English
  sample (2 tariffs, 4 subscribers, 4 self-verifying invoices) so you can
  explore every screen before entering your own records.
- **Nine interface languages** — English, French, Spanish, German, Portuguese,
  Russian, Turkish, Hindi and Chinese, with automatic language and currency
  detection.
- **Six themes** — Light, Warm Paper, Frost, Dark, Midnight Blue and Graphite,
  plus an automatic mode that follows Windows; every palette passes a WCAG AA
  contrast audit.

## Download / Getting started

Requires **Python 3.12+** with **PyQt6 6.5+** (and optionally `pytesseract` +
`Pillow` + `numpy` for OCR, plus `openpyxl` for Excel export).

Double-click **`Voltiva.exe`** — the launcher with the Voltiva icon (no console
window opens) — or run the batch file:

```bat
run_voltiva.bat
```

or, from a terminal:

```powershell
pythonw.exe run.py
python run.py
```

Your data is stored in `~/.voltiva/` (or `%KSE_DATA_DIR%` if set) as a local
SQLite database — no cloud, no accounts, fully offline. A database created by an
earlier version in `~/.kahraba_smart/` is adopted automatically on first start,
so upgrading keeps every invoice, tariff and payment.

## Screenshots

All pages and key dialogs (English UI, light palette):

![Dashboard](https://raw.githubusercontent.com/DigiSphereX/voltiva/main/ScreenShot/dashboard.png)
![New invoice](https://raw.githubusercontent.com/DigiSphereX/voltiva/main/ScreenShot/new-invoice.png)
![Invoices](https://raw.githubusercontent.com/DigiSphereX/voltiva/main/ScreenShot/invoices.png)
![Verify](https://raw.githubusercontent.com/DigiSphereX/voltiva/main/ScreenShot/verify.png)
![Monthly review](https://raw.githubusercontent.com/DigiSphereX/voltiva/main/ScreenShot/review.png)
![Analytics](https://raw.githubusercontent.com/DigiSphereX/voltiva/main/ScreenShot/analytics.png)
![Tariffs](https://raw.githubusercontent.com/DigiSphereX/voltiva/main/ScreenShot/tariffs.png)
![Subscribers](https://raw.githubusercontent.com/DigiSphereX/voltiva/main/ScreenShot/subscribers.png)
![Settings](https://raw.githubusercontent.com/DigiSphereX/voltiva/main/ScreenShot/settings.png)
![Tariff dialog](https://raw.githubusercontent.com/DigiSphereX/voltiva/main/ScreenShot/tariff-dialog.png)
![Subscriber dialog](https://raw.githubusercontent.com/DigiSphereX/voltiva/main/ScreenShot/subscriber-dialog.png)
![Import dialog](https://raw.githubusercontent.com/DigiSphereX/voltiva/main/ScreenShot/import-dialog.png)

Dark palette:

![Dashboard (dark)](https://raw.githubusercontent.com/DigiSphereX/voltiva/main/ScreenShot/dashboard-dark.png)
![Invoices (dark)](https://raw.githubusercontent.com/DigiSphereX/voltiva/main/ScreenShot/invoices-dark.png)
![Analytics (dark)](https://raw.githubusercontent.com/DigiSphereX/voltiva/main/ScreenShot/analytics-dark.png)
![Settings (dark)](https://raw.githubusercontent.com/DigiSphereX/voltiva/main/ScreenShot/settings-dark.png)
![Import dialog (dark)](https://raw.githubusercontent.com/DigiSphereX/voltiva/main/ScreenShot/import-dialog-dark.png)

## How it works

Clean-architecture Python app: UI (PyQt6) → Application services → Domain
billing engine → Infrastructure (SQLite, OCR, AI reader, exporters). The billing
engine is 100% UI-independent, so the core rules can be reused or ported to
other frontends. See `src/kse/` for `domain/`, `application/`,
`infrastructure/` and `presentation/`.

## Build & test from source

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q                    # full suite (engine, OCR/AI, GUI tour, infra)
python scripts/gui_smoke.py            # headless UI smoke test
python scripts/lint_qss.py             # static check of the Qt style sheet
python scripts/check_contrast.py       # WCAG contrast audit of all six palettes
python scripts/ui_geometry_audit.py    # detect clipped or shrunk widgets
python scripts/make_screenshots.py     # regenerate ScreenShot/*.png (light + dark)
python scripts/make_icons.py           # regenerate chevron/check icons after a palette change
```

The portable launcher is a single C# file, compiled with the .NET Framework
compiler that ships with Windows:

```
csc /target:winexe /win32icon:energy.ico /r:System.Windows.Forms.dll launcher\Voltiva_launcher.cs
```

## Requirements

- Windows 10/11 (tested), Python 3.12 — install with `pip install -r requirements.txt`
- PyQt6, and optionally: pytesseract (+ Tesseract binary with the `ara` and
  `eng` language packs), Pillow, numpy, openpyxl

Keyboard shortcuts: `Ctrl+N` new invoice, `Ctrl+F` invoices + search box, `Ctrl+1` dashboard, `Ctrl+2` analytics, `Ctrl+R` monthly review, `Ctrl+Shift+V` verify, `Ctrl+T` tariffs, `Ctrl+U` subscribers, `Ctrl+,` settings. Click a column header to sort invoices; click a bar in Analytics to open that month's invoices.

## Disclaimer

Billing figures produced by Voltiva are **analytical estimates for record and
review purposes — not official documents**. Always keep the paper/PDF invoice
issued by your electricity provider as the authoritative record.

AI scanning sends the selected bill image to the provider you configure; the API
key is stored in the local program database. Use the offline Tesseract engine if
a bill must never leave the machine.

## License

MIT — see [LICENSE](LICENSE). The bundled Cairo typeface in `assets/fonts/` is
licensed under the SIL Open Font License 1.1 — see
[`assets/fonts/OFL.txt`](assets/fonts/OFL.txt).

---

## ☕ Support this project

Free and open source (MIT). If Voltiva saved you time or money, consider a small thank-you:

- [GitHub Sponsors](https://github.com/sponsors/DigiSphereX)
- [PayPal](https://www.paypal.com/donate/?hosted_button_id=CFANQH892RPH2)
