# Production Plans Milestone 3.1 update

## Fixes included

- Adds area-based filtering to the Production Plans work-centre dashboard.
- Adds a clearer dependency check for both Flask and openpyxl when the server starts.
- Adds `INSTALL_REQUIREMENTS.bat` for installing the required Python packages.
- Returns a readable 503 message instead of a generic server error if openpyxl is missing during an export.

## Why the Excel export failed

The error was not caused by using the full Milestone 3.0 package. The Python installation used to run the server did not have `openpyxl` installed. Flask was available, so the website started, but Excel export failed when the route tried to import `openpyxl`.

## Installation

1. Stop the LINEUP server.
2. Back up the current project folder.
3. Copy the contents of this update into the LINEUP root and replace matching files.
4. Run `INSTALL_REQUIREMENTS.bat` once.
5. Restart with `start_lineup_server.bat`.
6. Press `Ctrl+F5` on the Production Plans dashboard.

## Area filter

The old status dropdown has been replaced with:

- All areas
- UNIT-1
- UNIT-2
- UNIT-3
- HVSA
- VACFORM
- WAP
- MOULDSHOP
- Other / unmapped

The filter uses the same source-work-centre membership configured for plain-plan exports in `config/production_plans.json`.
