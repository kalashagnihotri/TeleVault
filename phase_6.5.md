# PHASE 6.5 — TELEGRAM MEDIA ARCHIVE LOCAL CONTROL CENTER

Project root:

`J:\project\telegram_media`

Platform:

* Windows
* PowerShell
* Python virtual environment:
  `.\.venv\Scripts\python.exe`
* Existing archive DB:
  `data\archive.sqlite3`
* Canonical configuration:
  `config/config.yaml`

This is a new LOCAL CONTROL CENTER for operating the existing Telegram Media
Archive safely from a browser UI.

It must NOT become a second implementation of the archive pipeline.

The existing scanner, face analysis, scene analysis, uploader, cleanup,
database, routing, caption, configuration, Telegram, and future video services
remain the source of truth.

==================================================
0. PRIMARY GOAL
===============

Build a polished local web application that lets the user operate the Telegram
Media Archive without manually typing PowerShell commands.

The Control Center should ultimately provide:

* dashboard
* queue management
* drag/drop media ingestion
* controlled pipeline runs
* dry runs
* live runs
* smoke tests
* test runner
* live terminal/log streaming
* config editor
* face recognition inspection
* scene recognition inspection
* media inspector
* Telegram status
* database diagnostics
* backup/restore tools
* cleanup preview/control
* model/system health
* job history
* safe command buttons
* searchable logs
* future video intelligence controls

This is a LOCAL ADMIN APPLICATION.

It is not intended to be publicly exposed.

==================================================

1. CORE ARCHITECTURAL RULE
   ==================================================

The UI must sit ABOVE the existing application.

Required architecture:

Browser UI
|
v
Local Control API
|
+-- Config Service
+-- Job Runner
+-- Command Registry
+-- Log Streamer
+-- Queue Service
+-- Database Read Service
+-- Media Inspector
+-- System Health Service
|
v
EXISTING TELEGRAM MEDIA ARCHIVE
|
+-- QueueScanner
+-- Face Analysis
+-- Scene Analysis
+-- Routing
+-- ArchiveUploader
+-- Cleanup
+-- Database
+-- Telegram Client
+-- Future Video Intelligence

DO NOT duplicate:

* face recognition
* scene recognition
* routing
* upload logic
* cleanup rules
* hash logic
* caption generation
* database state transitions

The UI calls existing services.

==================================================
2. RECOMMENDED STACK
====================

Backend:

* Python
* FastAPI
* WebSocket or Server-Sent Events for live logs
* Pydantic/request schemas
* existing project Python environment where practical

Frontend:

* React
* TypeScript
* Vite
* clean component architecture

Styling:

Use a lightweight modern styling system.

Do not introduce a huge UI framework unless justified.

Desktop-first responsive design.

This application is primarily used on the user's PC.

==================================================
3. LOCAL-ONLY SECURITY
======================

By default bind ONLY:

`127.0.0.1`

Do NOT bind:

`0.0.0.0`

unless explicitly configured later.

Do not expose the Control Center publicly.

No remote shell endpoint.

No arbitrary command execution endpoint.

No route such as:

POST /run-command
{
"command": "anything"
}

Instead use an allowlisted command/job registry.

==================================================
4. PROPOSED DIRECTORY STRUCTURE
===============================

Prefer something similar to:

src/
control_center/
**init**.py
app.py
api/
dashboard.py
jobs.py
config.py
queue.py
media.py
system.py
tests.py
services/
job_runner.py
command_registry.py
config_service.py
queue_service.py
media_service.py
system_service.py
log_service.py
schemas/
jobs.py
config.py
queue.py
media.py

ui/
package.json
src/
app/
components/
pages/
hooks/
services/
types/

Do not force this exact structure if a cleaner architecture emerges during
audit, but maintain strong separation.

==================================================
5. CONTROL CENTER DATABASE
==========================

Do NOT add UI/job-history tables to the production archive database unless
there is a strong architectural reason.

Prefer a separate local database:

`data/control_center.sqlite3`

Store things like:

* UI job history
* job status
* command profile
* started_at
* completed_at
* duration
* exit_code
* local log path
* safe metadata

This database must be ignored by Git.

Do not duplicate archive media state into it.

The archive DB remains authoritative for media.

==================================================
6. DASHBOARD
============

Create a dashboard showing useful current system state.

Cards should include:

SYSTEM

* Control Center status
* Python version
* archive DB status
* migration version
* DB integrity status
* Google Drive queue availability
* Telegram configured/not configured
* model availability

QUEUE

* Incoming Images
* Incoming Videos
* READY_TO_UPLOAD
* pending face analysis
* pending scene analysis
* failed scene analysis
* failed face analysis
* NEEDS_LOCAL_API
* BACKED_UP
* cleanup eligible

RECENT ACTIVITY

* last pipeline run
* last test run
* last Telegram backup
* last failure
* last job

AI

* face model identity
* calibration status
* current scene analysis version
* Places365 model status

Use existing DB/config/model services.

Do not hardcode counts.

==================================================
7. GLOBAL MODE INDICATOR
========================

The application must always clearly show the operating mode.

Example top header:

DRY / SAFE
LIVE ARMED
CLEANUP ARMED

Use unmistakable visual distinction.

Default state on application startup:

LIVE MODE = NOT ARMED
CLEANUP = NOT ARMED

Even if cleanup is enabled in YAML, test/smoke jobs must be able to explicitly
force cleanup OFF in memory.

==================================================
8. RUN CENTER
=============

Build a page containing safe predefined actions.

Initial command profiles should include:

READ-ONLY / SAFE:

* Inspect Queue
* Database Integrity Check
* Show Media State Counts
* Verify Models
* Verify Configuration
* Inspect Pending Face Jobs
* Inspect Pending Scene Jobs

TESTS:

* Full Test Suite
* Face Tests
* Scene Tests
* Routing Tests
* Uploader Tests
* Caption Tests
* Control Center Tests

PIPELINE:

* Scan Only
* Face Analysis Only
* Scene Analysis Only
* Upload Ready Media
* Controlled Pipeline
* Dry Run
* Smoke Test

Eventually:

* Video Pass 1
* Video Pass 2
* Video Pass 3

Do NOT allow an unrestricted shell command to be passed from the browser.

==================================================
9. COMMAND REGISTRY
===================

Implement a backend allowlisted command registry.

Example concept:

CommandProfile:
id
display_name
description
risk_level
requires_live_arm
requires_cleanup_arm
allows_telegram
uses_production_db
executor

Examples:

pytest_full
pytest_face
pytest_scene
pytest_routing
db_integrity
queue_inspect
pipeline_controlled
scene_pending
face_pending
upload_ready

The browser sends:

`job_type = pytest_full`

NOT:

`python -m pytest -q`

The backend decides the actual command/executor.

==================================================
10. SUBPROCESS SAFETY
=====================

When subprocesses are necessary:

Prefer:

`asyncio.create_subprocess_exec()`

Avoid:

`shell=True`

Do not construct commands through untrusted string interpolation.

Set working directory explicitly to project root.

Set:

`PYTHONUNBUFFERED=1`

so terminal logs stream immediately.

==================================================
11. LIVE TERMINAL
=================

Create a high-quality terminal/log panel.

Requirements:

* live stdout
* live stderr
* timestamps
* auto-scroll toggle
* pause scrolling
* search
* filter INFO/WARNING/ERROR
* Copy All
* Copy Selection
* Clear View
* Save/Download Log
* job status
* duration
* exit code

IMPORTANT:

"Clear Terminal" clears only the UI display.

It must NOT delete the persisted job log.

The user must be able to reopen historical logs.

==================================================
12. JOB SYSTEM
==============

Every action must become a Job.

Example:

Run #0048
Type: Full Test Suite
Status: PASS
Started: ...
Completed: ...
Duration: ...
Exit Code: 0

Statuses:

QUEUED
RUNNING
PASSED
FAILED
CANCELLED

Optional:

ABORTED_SAFETY

Jobs should have:

* job id
* command profile
* safe arguments
* started_at
* finished_at
* duration
* status
* exit code
* output log
* error summary

Do not store secrets in job metadata.

==================================================
13. JOB CANCELLATION
====================

Provide a Stop button for cancellable jobs.

Cancellation must:

* terminate only the process/job started by Control Center
* not kill unrelated Python processes
* update job state
* preserve partial logs

Do not implement broad:

taskkill /F /IM python.exe

==================================================
14. TEST LAB
============

Create a dedicated Test Lab.

Buttons/cards:

FULL

* Full Pytest Suite

IMAGE INTELLIGENCE

* Scene Tests
* Screenshot Tests
* Document Tests
* Face Tests
* Routing Tests
* Caption Tests

DATABASE

* Migration Tests
* DB Integrity
* Cleanup Tests

TELEGRAM

* Uploader Unit Tests
* Controlled Smoke Test

Each test card should show:

* last result
* duration
* last run
* PASS/FAIL
* Run button
* Open Log button

==================================================
15. TEST LOGGING OPTIONS
========================

Allow test settings such as:

Normal
Verbose
Very Verbose

Map them safely:

pytest -q
pytest -v
pytest -vv

Do not expose arbitrary pytest arguments initially.

Allow:

* stop on first failure
* show captured output
* select known safe test profile

Store complete logs.

==================================================
16. DRAG & DROP INGESTION
=========================

Create a Queue / Import page.

Allow:

* drag/drop images
* drag/drop videos
* file picker
* multiple files

Backend workflow:

browser upload
->
temporary local upload file
->
validate extension/type
->
compute SHA-256
->
show duplicate information if known
->
resolve configured Incoming destination
->
copy safely
->
verify final file size/hash
->
only after verification mark import success

Configured Incoming paths must come from config.

Do not hardcode Google Drive paths into frontend code.

Support existing formats:

Images:
.jpg
.jpeg
.png
.webp

Videos:
.mp4
.mov
.mkv
.webm

Do not accept arbitrary executable files.

==================================================
17. DROP-ZONE RESULT
====================

After import display:

Filename
Type
Size
SHA-256 short hash
Destination
Duplicate status
Import status

Then provide:

[Run Analysis]

or:

[Leave in Queue]

Do not automatically upload to Telegram merely because a file was dragged in.

==================================================
18. DUPLICATE POLICY
====================

Exact duplicates remain SHA-256 based.

Do not introduce perceptual duplicate deletion.

If an uploaded file already exists by SHA-256:

show:

EXACT DUPLICATE

and let existing project behavior remain authoritative.

Do not delete anything automatically.

==================================================
19. CONFIGURATION EDITOR
========================

Create a structured config editor.

Do NOT make raw YAML the main editing experience.

Sections:

GENERAL

* dry run
* relevant paths

FACE ANALYSIS

* enabled
* routing enabled
* names in captions
* face-related configurable parameters

SCENE ANALYSIS

* enabled
* minimum confidence
* max ML labels
* screenshot heuristics
* document heuristics
* model path if appropriate

TELEGRAM

* group ID
* topic IDs
* upload mode
* size limits

CLEANUP

* enabled
* mode
* safety days
* verify hash
* permanent-delete confirmation

Only expose fields that are actually part of the config schema.

==================================================
20. CONFIG SAVE SAFETY
======================

When saving configuration:

1. validate input
2. construct candidate config
3. run existing config parser/validation
4. show a human-readable diff
5. create backup
6. atomic write
7. reload config
8. show effective resulting values

Config backups should go to a local ignored runtime directory such as:

`data/config_backups/`

Do not litter the repository with tracked backups.

==================================================
21. RAW YAML ADVANCED MODE
==========================

Provide an Advanced tab:

Raw YAML

But saving raw YAML still requires:

* parse validation
* schema validation
* backup
* atomic replacement

Show syntax errors clearly.

==================================================
22. SECRETS
===========

Never send actual secret values back to the browser once loaded if avoidable.

For Telegram bot token display:

Telegram Bot Token
••••••••••••••••
[Replace]

Do not expose:

* bot token
* API credentials
* private keys
* passwords

in:

* logs
* API responses
* terminal
* job history
* config diff
* diagnostics

If replacement is implemented, use write-only behavior.

==================================================
23. MEDIA INSPECTOR
===================

Create a Media page.

Search by:

* media ID
* filename
* short hash
* state
* route
* label
* person
* date

Selecting an item should show:

FILE

* filename
* media type
* size
* SHA-256
* original path, optionally masked/safe

METADATA

* date taken
* GPS presence
* location label

FACE

* face state
* detections
* box sizes
* known people
* unknown decisions
* latest attempt
* analysis version
* model identity

SCENE

* scene state
* scene version
* labels
* scene error code

ROUTING

* final route
* explanation

TELEGRAM

* group
* topic
* preview message ID
* original message ID
* file ID
* upload confirmation

UPLOAD ATTEMPTS

* type
* outcome
* HTTP status
* sanitized error

BACKUP

* final state
* cleanup eligibility

==================================================
24. ROUTING EXPLANATION
=======================

For media inspector, explain routing decisions.

Current policy must be read from actual source/tests.

At current Phase 6 design the intended precedence is:

1. > 1 known person -> family_groups
2. exactly 1 known person -> people
3. screenshot/document -> screenshots_documents
4. no GPS -> misc
5. travel/nature -> travel_nature
6. video -> videos
7. everyday

Do not create a second routing implementation.

Use `choose_topic()` or a safe explanation wrapper around it.

==================================================
25. FACE PANEL
==============

Create a Face Intelligence page.

Initial version should primarily be read-only.

Show:

* enabled status
* current detector
* current recognizer
* model identity
* calibration status
* thresholds
* reference person count
* reference image counts
* latest analysis results
* known/unknown statistics

Future controls:

* add reference images
* inspect reference gallery
* run calibration
* validate holdout

CRITICAL:

Never provide a UI option that bypasses failed calibration holdout.

Never expose:

`--allow-failed-holdout`

Never lower thresholds automatically just to force recognition.

==================================================
26. FACE DECISION DISPLAY
=========================

Display existing face statuses clearly:

KNOWN_MATCH
UNKNOWN_LOW_SCORE
UNKNOWN_LOW_RES
UNKNOWN_UNCALIBRATED
IGNORED_TINY
NO_FACE
ANALYSIS_ERROR where appropriate

Treat valid recognition decisions separately from technical failures.

==================================================
27. SCENE INTELLIGENCE PANEL
============================

Show:

* scenes enabled
* model identity
* model availability
* current scene analysis version
* minimum confidence
* max ML labels
* screenshot heuristic
* document heuristic

Create a single-image Scene Inspector.

Allow user to drag/drop/select an image WITHOUT adding it to production queue.

Display:

HEURISTICS

* screenshot
* document
* photographic

RAW MODEL

* top Places365 predictions
* confidences

CANONICAL

* mapped labels
* canonical confidence

FINAL

* Policy B final labels

Policy B remains:

up to 3 ML/canonical labels
PLUS heuristic labels

Example:

mountains
nature
snow
screenshot

==================================================
28. SCREENSHOT INTELLIGENCE
===========================

Expose useful interpretation:

Screenshot detected: Yes
Photographic: Yes
Document: No
Places365: Executed
Faces detected: 1
Known identity: Person One
Final labels:
#screenshot #indoor

Final route:
people

Do not remove screenshot tag when known person wins routing.

==================================================
29. DOCUMENT INTELLIGENCE
=========================

Expose document visual heuristic metrics where useful in Advanced mode:

* neutral ratio
* edge/text metric
* high saturation ratio
* final document decision

Do not make these user-editable thresholds initially unless project config
actually supports them.

==================================================
30. QUEUE PAGE
==============

Sections:

Incoming
Reserved
Ready to Upload
Face Pending
Scene Pending
Failed Analysis
Needs Local API
Backed Up
Cleanup Eligible

Allow filtering/search.

Do not expose arbitrary DB state editing.

==================================================
31. SAFE RETRY ACTIONS
======================

Only provide retry buttons when existing state-machine semantics allow it.

Examples:

Retry Scene Analysis
Retry Face Analysis
Retry Upload

Do not blindly set DB state fields.

Use existing DB/service methods.

If a safe method does not exist, do not create a UI button that edits SQL
directly.

==================================================
32. TELEGRAM PANEL
==================

Show:

* Telegram configured
* group ID, safe display
* topic mapping
* current API mode
* hosted upload limit
* recent successful uploads
* recent failures

Optional safe connectivity test later.

Do not expose token.

==================================================
33. DATABASE PANEL
==================

Read-only first.

Show:

* DB path
* DB file size
* schema migration versions
* latest migration
* row counts
* media state counts
* integrity check
* backup count

Buttons:

[Run Integrity Check]
[Create DB Backup]

DB backup must use SQLite backup API, not naive file copying.

==================================================
34. DATABASE BACKUP BUTTON
==========================

Use transactionally consistent SQLite backup.

Write backups under:

`data/db_backups/`

Show:

* backup filename
* timestamp
* media row count
* integrity result
* size

Do not implement restore in the first milestone.

==================================================
35. CLEANUP CONTROL
===================

Cleanup is high risk.

Default UI behavior:

Cleanup NOT armed.

Provide:

Cleanup Preview

showing:

* eligible count
* filenames/IDs
* backed-up status
* backup age
* hash verification state
* intended destination

Actual Run Cleanup must require separate explicit arming.

Do not combine:

Run Pipeline

with cleanup automatically in test/smoke modes.

==================================================
36. LIVE MODE SAFETY
====================

LIVE MODE should be session-scoped.

Example:

[ARM LIVE MODE]

Then show:

LIVE ARMED

with explicit description:

* production DB
* real queue
* Telegram writes allowed

When Live Mode is not armed:

Telegram-writing jobs should be disabled.

Prefer auto-disarming after a live job completes.

==================================================
37. CONTROLLED PIPELINE BUTTON
==============================

Create a safe pipeline action:

Scanner
->
Face
->
Scene
->
Uploader

Default:

cleanup disabled in memory

This mirrors the controlled Phase 6 validation workflow.

Actual cleanup remains a separate operation.

==================================================
38. DRY RUN
===========

Provide a clearly defined Dry Run.

Dry Run should not:

* send Telegram messages
* perform cleanup
* destructively modify source media

Precisely document which DB/runtime operations still occur.

Avoid vague "dry" semantics.

==================================================
39. SMOKE TESTS
===============

Create named smoke-test profiles.

Examples later:

Scene Model Smoke Test
Screenshot Smoke Test
Document Smoke Test
Face Recognition Smoke Test
Telegram Upload Smoke Test

Production Telegram smoke must require Live Mode.

Most smoke tests should use:

* isolated temporary DB
* temporary test files
* cleanup OFF
* production queue untouched

==================================================
40. LOGGING
===========

Add structured Control Center logging.

Log categories:

CONTROL
TEST
SCAN
FACE
SCENE
UPLOAD
DATABASE
CLEANUP
SYSTEM

Never log secret values.

Support:

Normal
Verbose
Private Diagnostic

Private diagnostic mode must still redact credentials.

==================================================
41. JOB HISTORY
===============

Create a Job History page.

Columns:

ID
Type
Started
Duration
Result
Mode
User Action
Open Log

Allow:

* reopen log
* copy output
* search jobs
* filter PASS/FAIL
* filter by job type

==================================================
42. TERMINAL UX
===============

Desktop layout idea:

LEFT SIDEBAR
Dashboard
Queue
Run Center
Test Lab
Media
Faces
Scenes
Telegram
Database
Config
Logs
System

MAIN AREA
Current page

BOTTOM RESIZABLE PANEL
Live Terminal

Top bar:

Mode
DB status
Queue status
Telegram status
Current Job

==================================================
43. VISUAL STYLE
================

Create a professional engineering/admin console.

Preferred feel:

* dark mode by default
* high readability
* restrained accent colors
* strong status chips
* clear warnings
* compact but not cramped
* consistent spacing
* responsive desktop layout

Status colors conceptually:

PASS / healthy
warning
error
running
disabled

Do not rely on color alone.

Include text/icons.

==================================================
44. BUTTON SAFETY LEVELS
========================

Classify actions:

SAFE

* inspect
* test
* integrity check

CONTROLLED

* scan
* face analysis
* scene analysis

LIVE

* Telegram upload
* production pipeline

DESTRUCTIVE/HIGH RISK

* cleanup
* restore
* future permanent delete

Button appearance and confirmation should reflect risk.

==================================================
45. ERROR HANDLING
==================

Frontend errors must show:

human-readable message
safe error code
job ID

Do not display raw internal exception by default.

Provide advanced diagnostic view only where safe.

Never show credentials.

==================================================
46. FRONTEND API TYPES
======================

Use typed API models.

Do not pass raw database rows directly to the frontend.

Create explicit response schemas.

Example:

MediaSummary
MediaDetail
JobSummary
SystemHealth
QueueSummary
ConfigSafeView

==================================================
47. CONTROL CENTER TESTING
==========================

Backend tests should cover:

* command allowlist
* command injection rejection
* job lifecycle
* log streaming
* config validation
* config atomic save
* masked secrets
* queue upload validation
* SHA-256 handling
* archive DB read-only inspection
* live-mode guards
* cleanup-mode guards

Frontend tests should cover major controls where practical.

==================================================
48. EXISTING PROJECT REGRESSION TEST
====================================

The existing archive suite must remain green.

Current recent baseline is approximately:

225 passed, 1 skipped

Do not treat this number as hardcoded forever.

After each milestone run:

`.\.venv\Scripts\python.exe -m pytest -q`

No existing pipeline regression is acceptable.

==================================================
49. DO NOT CHANGE CURRENT AI POLICY
===================================

During Control Center foundation work do NOT modify:

* face thresholds
* face calibration
* YuNet
* SFace
* low-resolution face policy
* Places365 confidence threshold
* scene canonical mapping
* screenshot policy
* document detection policy
* routing policy
* caption semantics
* cleanup safety policy

The Control Center exposes/operates them.

It does not redefine them.

==================================================
50. DO NOT TOUCH LOCAL TELEGRAM BOT API YET
===========================================

Local Bot API / >50 MB support remains deferred.

Do not implement it as part of Phase 6.5.

It may appear as:

"Not implemented / future"

in System UI.

==================================================
51. NO PUBLIC NETWORK SERVER
============================

Do not expose this application remotely.

Initial server:

localhost only.

Future private VPN/tunnel access is a later phase.

==================================================
52. GIT HYGIENE
===============

Do not commit:

* runtime control-center DB
* logs
* uploaded test media
* config backups
* production DB
* DB backups
* private models
* face references
* secrets
* temporary files
* frontend node_modules
* frontend build cache

Update `.gitignore` where necessary.

Do not use `git add .` blindly.

Do not commit automatically until implementation milestone is reviewed unless
explicitly requested.

==================================================
53. IMPLEMENTATION STRATEGY
===========================

DO NOT implement all features in one massive change.

Break Phase 6.5 into milestones.

==================================================
PHASE 6.5A — FOUNDATION
=======================

IMPLEMENT FIRST.

Scope ONLY:

Backend:

* FastAPI application
* localhost binding
* health endpoint
* system status endpoint
* archive DB summary endpoint
* queue summary endpoint
* job model/storage
* allowlisted command registry
* async job runner
* stdout/stderr streaming
* WebSocket/SSE log transport
* job cancellation
* test command profiles

Frontend:

* base shell/sidebar
* dashboard
* Run Center
* Test Lab
* terminal panel
* job history

Initial commands:

* Full Pytest
* Face Tests
* Scene Tests
* Routing Tests
* DB Integrity
* Queue Inspect

NO pipeline writes yet.

NO Telegram execution yet.

NO config writes yet.

NO drag/drop yet.

NO cleanup actions yet.

Acceptance:

1. open local UI
2. dashboard loads real project status
3. click Full Tests
4. see live pytest output in terminal
5. job reaches PASS/FAIL
6. job stored in history
7. reopen previous log
8. Copy Terminal works
9. Clear View works
10. cancel running safe test
11. existing project tests remain green

STOP AND REPORT AFTER 6.5A.

==================================================
PHASE 6.5B — QUEUE + DRAG/DROP
==============================

After 6.5A approval:

* queue page
* upload drop zone
* file validation
* SHA-256
* safe copy into configured Incoming
* post-copy hash verification
* duplicate warning
* no automatic Telegram upload

==================================================
PHASE 6.5C — CONFIG EDITOR
==========================

After 6.5B:

* structured config forms
* config diff
* config backups
* atomic writes
* safe reload
* masked secrets
* raw YAML advanced editor

==================================================
PHASE 6.5D — MEDIA INSPECTOR
============================

After 6.5C:

* media search
* media details
* face details
* scene details
* routing
* upload attempts
* Telegram IDs
* backup state

==================================================
PHASE 6.5E — AI INSPECTORS
==========================

After 6.5D:

* Face Intelligence page
* Scene Intelligence page
* single-image scene inspector
* model health
* calibration health

==================================================
PHASE 6.5F — CONTROLLED PIPELINE
================================

After previous milestones:

* Scan Only
* Face Only
* Scene Only
* Upload Ready
* Controlled Pipeline
* Dry Run
* session-scoped Live Mode
* Telegram safeguards

Cleanup remains separate.

==================================================
PHASE 6.5G — DATABASE + CLEANUP SAFETY
======================================

Finally:

* DB backup button
* migration view
* cleanup preview
* cleanup arm
* cleanup execution
* recovery preparation

Do not implement permanent delete unless specifically approved later.

==================================================
54. PHASE 6.5A UI PAGES
=======================

Initial sidebar:

Dashboard
Run Center
Test Lab
Jobs
System

Bottom:

Terminal

Other future pages may appear disabled with:

Coming Soon

Queue
Media
Faces
Scenes
Telegram
Database
Config

==================================================
55. INITIAL API ENDPOINT CONCEPT
================================

Possible structure:

GET /api/health
GET /api/system
GET /api/dashboard
GET /api/queue/summary

GET /api/jobs
GET /api/jobs/{id}
POST /api/jobs/{profile}/start
POST /api/jobs/{id}/cancel

GET /api/jobs/{id}/log

WS /api/jobs/{id}/stream

Exact endpoint names may differ.

Keep API clean and typed.

==================================================
56. START COMMAND
=================

Provide one simple Windows launch command.

Prefer eventually:

`.\.venv\Scripts\python.exe -m src.control_center`

which starts:

backend
+
serves frontend/build if practical

During development separate frontend/backend commands are acceptable.

Document both.

==================================================
57. DEVELOPMENT UX
==================

If frontend development requires Node:

document:

backend command
frontend command

But final user operation should move toward ONE launcher.

Do not require the user to manually start 4 services.

==================================================
58. SYSTEM STATUS PAGE
======================

Show:

PROJECT ROOT
Python executable
Python version

ARCHIVE DB
exists
integrity
migration

QUEUE
images path reachable
videos path reachable

FACE
models available
calibration status

SCENE
model available
analysis version

TELEGRAM
configured/not configured

CONTROL CENTER
backend version
frontend version

Do not reveal bot token.

==================================================
59. PERFORMANCE
===============

Dashboard polling should not hammer SQLite.

Use reasonable refresh intervals.

Do not open hundreds of DB connections unnecessarily.

Jobs and logs should stream rather than poll large files repeatedly.

==================================================
60. FAILURE ISOLATION
=====================

If the Control Center crashes:

the archive database and media must remain safe.

If a UI job crashes:

it must not automatically mark media cleaned/deleted.

UI failure must never compromise backup correctness.

==================================================
61. PHASE 6.5A REQUIRED TESTS
=============================

Add tests for:

Backend:

* health endpoint
* localhost configuration
* command profile lookup
* unknown command rejected
* subprocess arguments not shell-interpolated
* job creation
* job completion
* failed job
* cancellation
* log persistence
* job history
* DB summary
* queue summary
* secret redaction

Frontend where practical:

* dashboard renders
* Run button creates job
* terminal receives output
* Copy
* Clear View
* job result appears

Existing archive suite must still pass.

==================================================
62. DO NOT MODIFY PRODUCTION STATE DURING 6.5A
==============================================

Phase 6.5A is read-only except:

* Control Center's own local job DB
* Control Center log files

Do NOT:

* run production queue
* send Telegram messages
* run cleanup
* change archive DB state
* alter config
* requeue media

==================================================
63. REPORT AFTER PHASE 6.5A
===========================

STOP after Phase 6.5A.

Return:

1. architecture implemented
2. directory tree added
3. backend dependencies added
4. frontend dependencies added
5. API endpoints
6. command profiles
7. job persistence design
8. terminal streaming design
9. cancellation behavior
10. screenshot(s)/description of UI
11. Control Center tests
12. existing archive pytest result
13. launch instructions
14. `.gitignore` changes
15. files modified/added
16. known limitations
17. security concerns
18. blockers before Phase 6.5B

Do NOT begin Phase 6.5B until reviewed.

==================================================
64. SUCCESS CRITERIA FOR COMPLETE PHASE 6.5
===========================================

When the full Control Center is eventually complete, the user should be able to
perform almost all routine operations without PowerShell:

* see system health
* drag/drop image
* place it into Google Drive Incoming
* inspect SHA-256
* inspect queue
* run controlled analysis
* watch terminal output
* see face result
* see scene result
* see routing result
* run tests
* see logs
* change safe config values
* back up DB
* inspect Telegram status
* safely execute controlled live pipeline
* inspect failures
* retry valid operations

PowerShell remains available for development/debugging but is no longer the
normal operational interface.

Build this as an operational control plane, not merely a dashboard.
