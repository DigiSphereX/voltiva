# Changelog

All notable changes to this project are documented here.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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