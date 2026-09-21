# Changelog

All notable changes to this project are documented here.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## 1.0.5 - 2026-09-21

- All screenshots regenerated with the **native Windows renderer** (they are no
  longer captured with the offscreen QPA plugin, which produced distorted fonts).

## 1.0.4 - 2026-09-21

- **English by default**: the interface now defaults to English on first run
  (Arabic and the other 8 languages remain selectable anytime).
- Screenshots regenerated in English covering **all pages and key dialogs**
  (dashboard, new invoice, invoices, verify, review, analytics, tariffs,
  subscribers, settings + tariff/subscriber/OCR-import dialogs, dark variant).
- Tariffs list shows the localized name (English unless the UI is Arabic);
  demo tariff names are fully English.

## 1.0.3 - 2026-09-21

- Tariff dialog: the rate-per-kWh tier table and the fees table now have
  dedicated height (four or more rows stay visible) and the whole form scrolls
  on small screens, so none of the add tables is squeezed.

## 1.0.2 - 2026-09-21

- **English demo data**: the Settings button now loads a fully fictional English
  sample (2 tariff schedules, 4 subscribers with meters, 4 self-verifying
  invoices, including the tiered commercial case). Reloading only replaces the
  demo set — your own records are never touched.
- The demo step asks for confirmation first and the dashboard refreshes
  immediately afterwards.
- Copyright updated to `Copyright (c) 2026 M. Basheer (DigiSphereX)` and now
  shown in the About boxes, matching the other published projects.
- New **`Voltiva.exe`** launcher: double-click to start the app, shows the
  Voltiva icon and opens no console window.

## 1.0.1 - 2026-09-21

- Rebranded to the worldwide product name **Voltiva** and removed all
  country-specific references from the UI, disclaimers and documents.
- Version and developer info are now a single source of truth
  (`kse.__version__`, `kse.__author__`) and shown in the About box, the
  Settings page and the sidebar footer.
- Sidebar polish: the real app icon is used for the brand logo and window;
  navigation sections are separated from their items with a subtle divider
  line, and native menus gained a cleaner separator/checked styling.
- First public release with README, CHANGELOG, LICENSE and screenshots.

## 1.0.0 - 2026-09-14

- Initial build: auditable electricity billing engine (10-tier tariff engine,
  fees, debts, simulation history).
- PyQt6 desktop UI: Dashboard, New Invoice, Invoices, Verify, Review,
  Analytics, Tariffs, Subscribers, Settings.
- 9 interface languages, automatic language/currency detection, RTL Arabic,
  dark/light/auto themes.
- Optional OCR import (Tesseract), PDF/print export, Excel export.
- SQLite persistence with backups/restore; full pytest suite.