# Changelog

All notable changes to this project are documented here.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## 1.1.0 - 2026-10-30

- **AI bill scanning**: a new vision reader fills the import form from a bill photo, with
  three engines in Settings (automatic free AI, any OpenAI-compatible endpoint, offline
  Tesseract) and an automatic fallback to the offline reader.
- **Six palettes**: Light, Warm Paper, Frost, Dark, Midnight Blue and Graphite, each with
  its own chart/KPI colours, generated icons and a WCAG AA contrast audit.
- **Faster start-up**: only the first page is built at launch and the menus are filled when
  opened, roughly halving the time to the first window.
- **Table and RTL pass**: visible grid lines, row-sized editors, readable selected rows and
  right-aligned Arabic fields.
- **Navigation and calendar rework**: destinations grouped under Reports, scoped calendar
  styling, localized month and weekday names.
- **Calculation, accounting and hardening pass**: self-verifying demo data, audit trail,
  backups and a much larger test suite (288 tests).

Details by theme:

### AI invoice scanning

**Fixed (import dialog)**
- Closing the import dialog raised `AttributeError: 'builtin_function_or_method' object
  has no attribute 'isRunning'` whenever no scan had been started: the OCR worker thread was
  stored on `self.thread`, which shadowed `QObject.thread()`. It now lives on
  `self._ocr_thread` and is type-checked before interrupting.

**Fixed (appearance)**
- **Automatic** theme mode now really follows Windows. The detector read
  `QApplication.palette()` — which the app itself replaces with the active theme — before
  consulting Windows, so "auto" always resolved to the palette that was already applied
  (light). It reads the Windows "app mode" value first, then Qt's color scheme, and listens
  to `colorSchemeChanged`, so flipping Windows to dark/light switches the app immediately
  (the existing one-minute poll remains as a fallback for platforms without the signal).
  The Qt color-scheme fallback also compared against the wrong enum value (light instead of
  dark).
- Status text no longer becomes unreadable on a selected table row. A per-item foreground
  (unpaid red, success green, muted inactive rows) overrode the style sheet's selected
  colour, leaving e.g. pink-red text on graphite/sepia's amber selection at ~1:1 contrast.
  The table delegate now paints selected cells with the palette's on-accent tone.
- Status chips are painted opaque (their tint mixed onto the surface colour) instead of
  translucent: previously the selected row's amber/orange accent bled through the pill and
  turned the chip text red-on-orange. The palette-contrast audit covers this pair.
- The sepia palette's success green was darkened so status numbers keep 4.5:1 on the
  alternating and hovered table-row backgrounds, not just the base surface; the audit now
  checks those rows for every palette.

**Fixed (analytics)**
- The monthly performance table's **Remaining** column drew every amount twice: the cell
  item still held the text while a status chip was set on top of it, so the number appeared
  staggered and overlapping inside the cell. The item text is now empty whenever a chip is
  shown, and a row whose balance is paid off drops its old chip on the next refresh.

**Fixed (start-up)**
- The window appears roughly twice as fast: only the initial page is built at launch (the
  rest are created on first visit instead of all ten up front), and the language/theme/
  currency menus are populated when opened rather than at start-up — the ~170-row currency
  list alone used to cost most of the top bar's initialisation. The window is also raised
  and activated when it opens, and the time to first paint is recorded in `voltiva.log`.

**Added**
- A dedicated AI vision reader (`infrastructure/ocr/ai_scanner.py`) that sends the bill photo
  to an OpenAI-compatible vision model and maps the strict-JSON reply onto the import
  dialog's fields (readings, dates, consumption, amount, account/meter numbers and the
  subscriber name). Numbers are normalized from Arabic-Indic digits, dates accept
  `YYYY-MM-DD`, `DD/MM/YYYY` or `YYYYMMDD`, and thousands separators are stripped.
- Settings → **AI Image Scanning** with three engines: **Automatic — free AI** (built-in
  service, free key from the linked page), **Custom AI** (any OpenAI-compatible base URL,
  key and model — OpenRouter, Gemini gateways, LM Studio, Ollama, …) and **Offline —
  Tesseract**. The card includes a model/endpoint/key/timeout form, a connection test that
  sends a small generated image, and a button that opens the free-key page.
- The import dialog now shows the active scanner and where to change it, fills the
  subscriber name too, and labels AI failures separately from local OCR failures.

**Changed**
- In automatic mode without a key (or when the AI service is unreachable) scanning falls
  back to the installed Tesseract reader and warns that the offline result must be
  reviewed. Custom mode requires a URL and never silently changes engines.
- Bills are sent to the configured AI provider for reading; the key is stored in the local
  program database. The offline engine remains available for fully private scanning.

### Unified tables, sidebar and RTL fields

**Fixed (tables)**
- Every table now draws cell grid lines and header column separators (`gridline-color`
  uses the palette border), so rows and columns read as a real table in all six palettes.
  The tariff dialog's inline tiers/fees tables were previously borderless and looked like a
  plain strip of text.
- In-table editors and drop-downs are capped at 28px inside the 34px rows; the old 50px
  editors overflowed their row and hid the cell borders. Editors copy the cell's alignment,
  so typing starts where the value already sits.
- The tariff tiers/fees tables size to their rows (minimum two rows) instead of reserving a
  large empty body, and both offer double-click / F2 / type-to-edit with an I-beam cursor
  plus a "double-click any cell to edit it" hint.
- Selected table rows paint the accent background with the matching `on_accent` text;
  previously graphite rendered light text on the amber selection (low contrast).

**Fixed (RTL fields)**
- In Arabic, text and date fields right-align with the form labels. Numeric/date text is
  LTR by nature and used to hug the left edge, leaving each field looking half empty; the
  RTL style sheet pins inputs to the leading edge and `DateEdit` applies it to the spin
  box's internal editor.

**Changed (sidebar)**
- Every navigation destination is a 36px row and every section caption a 28px label in all
  ten languages (Hindi font fallback used to shrink the rows). In narrow windows the sidebar
  shows generated per-theme icons instead of font glyphs, so the compact rail is identical
  across languages.

### Navigation & calendar usability

**Fixed (calendar)**
- The date picker's month grid was rendered by the global table style: day cells were
  wide enough to clip most dates (only a few numbers were visible) and the weekday names
  disappeared. The calendar now has scoped styling, a 360x280 minimum area, weekday names,
  visible per-theme navigation arrows, and theme-aware weekend colours.
- Month and weekday names follow the app language instead of the OS locale (an English UI
  showed "Oktober"), including week start and right-to-left order for Arabic; Arabic marks
  Friday/Saturday as the weekend.

**Changed (navigation)**
- Monthly Review moved under the "Reports" group next to Analytics, so no section wraps a
  single destination; Settings is a standalone button pinned above the version label.
- Section captions are now visibly non-interactive (smaller, no border, no hover) and kept
  apart from the clickable rows, ending the "Insights header looks like a button" confusion.
- Group labels translated in all ten languages ("Reports", "التقارير", "Rapports", …).

### Theme system expansion

**Added (themes)**
- Six built-in palettes instead of two: Light, Warm Paper (sepia), Frost (cool blue-grey),
  Dark, Midnight Blue, and Graphite (charcoal + amber). Each declares its light/dark kind,
  its own chart series, KPI tints, and generated chevron/check icons.
- The theme picker (top bar menu and Settings) is grouped into light and dark sections with
  localized names in all ten languages; "Automatic" still follows the OS.
- New `accent_solid`, `on_accent`, and `on_danger` tokens keep filled controls, menu
  selections, and checked navigation items readable on every palette.
- `scripts/check_contrast.py` now audits `on_accent`/`on_danger` pairs as well; all palettes
  pass WCAG AA for body text (4.5:1) and control/chart colors (3:1).

**Fixed (themes)**
- Choosing a palette from the top bar menu left the selector on "Automatic" and kept stale
  widget colours: `AppContext` now notifies theme listeners, and the window refreshes the top
  bar and rebuilds pages on every change.
- The Settings "active theme" hint squeezed the combo into a narrow column and wrapped onto
  three lines; it now sits on one line under the selector.

### UI polish & Arabic input pass

**Fixed (UI)**
- The status bar printed the invoice count in Western digits in Arabic mode; it now follows
  the selected digit style.
- The subscribers table showed account/subscription numbers in Western digits while the
  invoices table localized them; both pages now agree.
- Read-only path fields (database, app icon) render LTR, so an Arabic folder name no longer
  scrambles the drive/backslash segments of the path.
- The analytics health score is fully localized (`٠/١٠٠`, not `٠/100`).

**Changed (UX)**
- The billing card (previous debt / official amount) moved next to the calculation result, so
  the form column fits a standard window with far less scrolling.
- Enter in any reading/billing field runs the calculation; Tab follows the visual field order.
- Dialog primary actions (tariff, subscriber, payment, manual import) are default buttons, so
  Enter saves and Esc cancels.

**Fixed (input)**
- Arabic-Indic digits typed into the search boxes, the account lookup, or the subscriber form
  are normalized to ASCII before matching/storing, instead of creating a duplicate subscriber
  or returning no results.

### Calculation & accounting correctness pass

**Fixed (billing)**
- Same-day readings were accepted; the 30-day tier scaling then divided by a zero-day
  period and multiplied the bill (1 000 kWh could be billed as 19 500). A period must now be
  strictly positive (`DATE_NOT_AFTER` in the form and in `verify`), and the calculator itself
  refuses a zero/negative period.
- Saving a calculation without explicit reading dates stored the issue date for BOTH dates,
  which made later recalculation run on a fake same-day period. The priced period is now
  carried on `InvoiceCalculation` and persisted (invoice + reading rows).
- Tariff validation accepted an open-ended tier in the middle of a table (every later tier
  became unreachable) and inverted ranges (`to <= from`); both are rejected now
  (`TARIFF_OPEN_END`, `TARIFF_BOUNDS`).
- A leading minus in a money field was stripped silently, turning `-500` into `+500`;
  negative amounts are rejected. `Money / 0` raises `ZeroDivisionError` instead of crashing
  later with an `InvalidOperation`.

**Fixed (analytics)**
- Monthly "paid" was `billed - outstanding`, which reported a fully-paid month that had only
  rolled its debt forward and a NEGATIVE paid bucket for the month that carried it. Cash is
  now applied to new billing oldest-first (FIFO) and every monthly paid figure is non-negative;
  `sum(applied) == sum(paid)` unless payments exceed new billing.

**Fixed (UI / i18n)**
- Verification mode treated validation failures as a generic error, so date/reading messages
  stayed Arabic in every language; each issue is now reported and localized individually.
- Calculation steps translated the duration as hard-coded "days" and left the meter-scenario
  step in Arabic for all non-Arabic languages.
- Editing an invoice could set PAID/PARTIAL/UNPAID against the recorded payments; a mismatched
  status is refused with a clear message (payments are recorded through "Add payment").
- "No tariff" errors printed the raw enum value (`SubscriberType.RESIDENTIAL`) instead of the
  localized label.
- Closing the app twice (window close + exit hook) attempted a backup on a closed database and
  logged a false "automatic backup failed"; `AppContext.close()` is idempotent now.

**Internal**
- `Invoice.audit_run_id` / `AuditLogEntry.run_id` annotated as `str` (UUID; the DB columns are
  TEXT), duplicate `Payment` import removed, and tests cover the new invariants.

### Hardening & visual pass

**Fixed (data integrity)**
- "Mark paid" added the full invoice total on every click (paid > total, negative
  balance). It now pays only the remaining balance; payments <= 0, over-payments and
  payments on cancelled invoices are rejected (`PaymentError`, localized EN/AR).
- Analytics counted cancelled / recalculated invoices; it now uses ACTIVE invoices only.
- Invoice numbers could repeat once a year had more than 500 invoices.
- Tariff audit-log details were built by string formatting (invalid JSON when a name
  contained a quote); now `json.dumps`.
- `SubscriberService.meters()` was shadowed by the `meters` attribute; use `meters_of()`.

**Fixed (security / robustness)**
- Restore validates the chosen file (SQLite header, integrity check, required tables,
  not newer than this app) before touching the live database; the app always keeps a
  working connection; backups are written atomically.
- Database migrations are transactional and idempotent (an interrupted upgrade used to
  crash with "duplicate column name" on the next start).
- CSV/Excel export neutralises formula injection (`=`, `+`, `-`, `@` prefixes).
- JSON import rejects NaN / Infinity / malformed numbers.
- `%` and `_` in search boxes are matched literally.
- PDF export no longer double-escapes dates and survives stray `{}` in translations.
- Exporting several invoices to JSON wrote only the first one; now all (`json_export_many`).
- OCR passes the tessdata folder through `TESSDATA_PREFIX` (paths with spaces broke).
- Unhandled exceptions are logged to `voltiva.log` and shown in a dialog instead of
  silently closing the window.

**Performance**
- New composite indexes; tariff tiers/fees load with 2 queries instead of 2 per tariff;
  `busy_timeout`, page cache and `temp_store` pragmas.

**Visual**
- Light & dark palettes pass WCAG AA (`scripts/check_contrast.py`); KPI colours are theme
  tokens instead of hard-coded hex values; hero chips are readable.
- Combo-box arrows and check marks (generated by `scripts/make_icons.py`).
- Disabled / focus states, stronger selection colour, softer table grid, full invoice
  numbers in the dashboard table, sidebar highlight follows every navigation.
- **Charts rewritten**: round axis ticks, capped bar width, value labels, animated growth,
  hover tooltip, stacked paid/remaining bars with legend, RTL mirroring, non-overlapping
  labels. New donut chart for the payment mix.

**Second pass (performance, accuracy, design)**
- Invoice numbers are now UNIQUE (partial unique index; schema v4). Existing duplicates are
  renumbered by the migration (oldest keeps its number, later ones get `-D2`, `-D3`) and logged
  in the audit log; the numbering retries if a number was taken concurrently.
- Dashboard / analytics / review read one cached list of active invoices that is rebuilt only
  when data changes (own writes via `total_changes`, other connections via `data_version`):
  opening the dashboard with 3 000 invoices dropped from ~113 ms to ~6 ms; next-invoice-number
  from ~17 ms to ~0.5 ms; bulk invoice loading is faster (`Money.from_db` fast path, verified
  identical on 20 000 values). The WAL is checkpointed and `PRAGMA optimize` runs on exit.
- Analytics: "average cost per kWh", the forecast and the rate-anomaly alerts now use the
  CURRENT period's charges. They used `total_due`, which includes carried-forward debt, so unit
  cost grew with every unpaid month and produced false alerts. Receivable / paid / unpaid
  figures still use `total_due`.
- Invoices page: consumption shown as 2,100 (was 2100.000000), invoice number and headers no
  longer truncated, pill-shaped status chips (history rows marked Recalculated / Cancelled),
  Enter and the status filter search immediately, "showing X of Y" counter.
- Black strips in tables/frames fixed at the root (unset `QPalette` roles) + header QSS.
- New invoice: form grouped in cards with the result beside it (no scrolling past 12 rows).
- Charts: exact figures above bars when they fit, calmer gradients, donut colours follow the
  theme at paint time.
- Missing Arabic strings added (demo-data dialog); tests now fail if any key used in code is
  missing in English or Arabic, or if a translation changes its `{placeholders}`.
- Tooling: `scripts/make_screenshots.py` (rich demo data, EN/AR, light/dark),
  `scripts/lint_qss.py`.

**Third pass (workflow)**
- Invoices: click a column header to sort (server side, so it covers every invoice, not just the
  visible 500; money columns sort numerically); the sort arrow shows the active column.
- Analytics: click a bar to open that month's invoices (the filter chip clears it); "Save as image"
  exports the chart card as PNG.
- Ctrl+F opens the invoices page with the cursor in the search box.
- Read-only tables (subscribers, tariffs, invoice details, charges, verify) lose the row-number
  column and get zebra rows, matching the invoices table.
- RTL: the sidebar separator now sits on the sidebar's inner (left) edge.
- `requirements.txt` / `requirements-dev.txt` (compatible ranges) and a GitHub Actions workflow
  that runs the QSS lint, the contrast audit and the test suite on every push.

**Fourth pass (productivity, export suite & database maintenance)**
- **Direct Invoice Printing**: added a dedicated Print button and `Ctrl+P` shortcut in the invoice detail view using the native print engine.
- **Enhanced Export Suite**:
  - Invoices Excel export rewritten with professional corporate styling: styled header cards, thin borders, alternating zebra rows, auto-computed column widths, formula-injection protection, and localized formats.
  - Subscribers export: one-click export of subscriber rosters to both formatted Excel (.xlsx) and CSV (.csv).
  - Analytics export: monthly financial analytics table can now be exported directly to Excel and CSV.
  - Export dialogs now show localized titles and confirm successful output with the saved file name.
- **Workflow & Productivity Improvements**:
  - `F5` global shortcut refreshes the active page instantly.
  - Subscribers page: pressing Enter in search filters immediately; added a direct "Invoices" button on each subscriber row to view their filtered invoice history.
  - Subscriber safety: warns the operator if a subscriber has existing invoices or unpaid debt before confirming deletion.
  - New Invoice form: pressing Enter on account input immediately fetches/populates subscriber data; added a dedicated "Reset Form" button to clear fields and restore defaults.
  - Analytics page: double-clicking any month in the monthly table filters invoices to that month.
- **Database Maintenance & Optimization**:
  - Added an "Optimize Database" utility in Settings: runs `VACUUM`, `ANALYZE`, and `PRAGMA optimize`, compacts database files, reclaims disk space, and records the maintenance in audit logs.
- **Developer & Test Quality**:
  - Added `pytest.ini` with registered custom markers (`gui`) and filtered deprecation warnings.
  - Full test suite expanded to 248 passing tests covering new exports and maintenance routines.

**Architecture**
- The billing engine no longer imports the Qt presentation layer (display style lives in
  `domain.money`), so the domain, seed data and most tests run without PyQt6.

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