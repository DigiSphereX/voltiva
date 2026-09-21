# Voltiva — Smart Electricity Billing

[![Donate](https://img.shields.io/badge/Donate-PayPal-0070BA)](https://www.paypal.com/donate/?hosted_button_id=CFANQH892RPH2)
![Version](https://img.shields.io/badge/version-1.0.3-blue)
![Python](https://img.shields.io/badge/python-3.12-blue)
![PyQt6](https://img.shields.io/badge/PyQt6-6.5+-green)
![License](https://img.shields.io/badge/license-MIT-green)

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
- **Smart import (OCR)** — optional optical recognition reads bill totals from
  a photo or scan and pre-fills the invoice form (requires Tesseract with
  `ara`/`eng` language data).
- **Subscribers & meters** — manage subscriber records, meters, previous
  readings and debts.
- **Analytics dashboard** — usage trends, cost breakdowns and exports.
- **Verification & review** — compare simulated versus issued amounts to spot
  discrepancies.
- **Print / PDF export** — professional printable documents with full RTL
  Arabic support; no extra libraries required.
- **English demo data** — one click in Settings loads a fully fictional English
  sample (2 tariffs, 4 subscribers, 4 self-verifying invoices) so you can
  explore every screen before entering your own records.
- **Worldwide-ready** — 9 interface languages, automatic language/currency
  detection, Arabic and Western digit styles, dark/light/auto themes.

## Download / Getting started

Requires **Python 3.12+** with **PyQt6 6.5+** (and optionally `pytesseract` +
`Pillow` + `numpy` for OCR, plus `openpyxl` for Excel export).

```bat
run_kahraba.bat
```

or double-click **`Voltiva.exe`** — the application launcher with the Voltiva
icon (no console window opens).

or, from a terminal:

```powershell
pythonw.exe run.py
python run.py
```

Your data is stored in `~/.kahraba_smart/` (or `%KSE_DATA_DIR%` if set) as a
local SQLite database — no cloud, no accounts, fully offline.

## Screenshots

![Dashboard](https://raw.githubusercontent.com/DigiSphereX/voltiva/main/ScreenShot/dashboard.png)
![Invoices](https://raw.githubusercontent.com/DigiSphereX/voltiva/main/ScreenShot/invoices.png)
![Tariffs](https://raw.githubusercontent.com/DigiSphereX/voltiva/main/ScreenShot/tariffs.png)
![Analytics](https://raw.githubusercontent.com/DigiSphereX/voltiva/main/ScreenShot/analytics.png)
![Settings](https://raw.githubusercontent.com/DigiSphereX/voltiva/main/ScreenShot/settings.png)

## How it works

Clean-architecture Python app: UI (PyQt6) → Application services → Domain
billing engine → Infrastructure (SQLite, OCR, exporters). The billing engine is
100% UI-independent, so the core rules can be reused or ported to other
frontends. See `src/kse/` for `domain/`, `application/`, `infrastructure/`
and `presentation/`.

## Build & test from source

```powershell
python -m pytest -q        # full test suite (engine, OCR, GUI tour, infra)
python scripts/gui_smoke.py   # headless UI smoke test
python scripts/gui_shots.py   # render screenshots to scripts/shots/
```

## Requirements

- Windows 10/11 (tested), Python 3.12
- PyQt6, and optionally: pytesseract (+ Tesseract binary with `ara`/`eng`),
  Pillow, numpy, openpyxl

## Disclaimer

Billing figures produced by Voltiva are **analytical estimates for record and
review purposes — not official documents**. Always keep the paper/PDF invoice
issued by your electricity provider as the authoritative record.

## License

MIT — see [LICENSE](LICENSE).

---

## Support this project

Free and open source (MIT). If Voltiva saved you time or money, consider a small thank-you:

- **GitHub Sponsors** -> https://github.com/sponsors/DigiSphereX
- **PayPal** -> https://www.paypal.com/donate/?hosted_button_id=CFANQH892RPH2