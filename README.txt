LINEUP v0.8.1 - Production State UI
====================================

CHANGES
-------
- Added an Awaiting Picking panel to the Planning Board
- Renamed the visible Planning Pool terminology to Ready to Schedule
- Added compact, consistently formatted state badges for Awaiting, Ready, Queued, Running and Held
- Preserved all existing route names, JSON keys and scheduling behaviour
- Awaiting Picking remains informational only; SAP production status remains the source of truth

INSTALLATION
------------
1. Back up current LINEUP folder
2. Replace app/templates/control.html with the supplied file
3. Replace app/static/control.css with the supplied file
4. app.py and app/static/control.js are included for completeness but are unchanged from v0.8.0
5. Start LINEUP normally and open /control

CHECKS
------
- Awaiting Picking orders appear in the new amber panel
- Ready-to-Schedule orders remain draggable
- Queued cards show a blue Queued badge
- Active work shows a green Running badge
- Held orders show a red Held badge
- Drag-and-drop and automatic saving still work
