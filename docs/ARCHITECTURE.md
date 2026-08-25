# System Architecture & Enterprise Design

## Overview
**TeleVault / Telegram Media Vault** is a local-first, privacy-respecting, high-throughput media ingestion, AI enrichment, and archival pipeline backed by Telegram Cloud storage and a local Control Center.

```
+-----------------------------------------------------------------------------------+
|                              LOCAL CONTROL CENTER                                 |
|   React TypeScript SPA  <--->  FastAPI Backend (Port 8000)  <--->  SQLite WAL DB |
+-----------------------------------------------------------------------------------+
                                        |
                   +--------------------+--------------------+
                   |                                         |
                   v                                         v
+------------------------------------+   +------------------------------------+
|         INGESTION & QUEUE          |   |       AI INTELLIGENCE SUITE        |
| - Staging & validation             |   | - SFace / YuNet Face Recognition   |
| - SHA-256 Deduplication            |   | - Places365 Scene Classification   |
| - File stability tracker           |   | - Heuristic Screenshot / Tax Engine|
+------------------------------------+   +------------------------------------+
                   |                                         |
                   +--------------------+--------------------+
                                        |
                                        v
+-----------------------------------------------------------------------------------+
|                                 TELEGRAM VAULT                                    |
| - Channel / Group Forum Topics (People, Travel, Work, Family, Videos, Docs)       |
| - 2-Phase Upload (2000px Preview + Full Original Document)                         |
| - Atomic SQLite Transaction Commit on Confirmation                                |
+-----------------------------------------------------------------------------------+
```

---

## Core Components

### 1. Ingestion Engine (`src/scanner.py`, `src/hashing.py`)
- Watches `incoming/images` and `incoming/videos`.
- Verifies byte stability over configurable window (`stable_seconds: 60`).
- Computes canonical SHA-256 hash.
- Strictly guards against duplicate ingestion using SQLite unique constraint.

### 2. AI Intelligence Layer (`src/face_analysis.py`, `src/scene_analysis.py`)
- **Face Recognition**: YuNet detector + SFace recognizer with top-k aggregate scoring, low-resolution adaptive margin boosts, and calibration profiles.
- **Scene Classification**: Places365 neural network + heuristic rules for screenshots, software UI, invoices, and documents.
- **Memory Engine**: Adaptive temporal clustering (6-24h sessions, 2-7d trips, 1-3w projects) and smart highlight curation.

### 3. Policy & Routing Engine (`src/routing.py`, `src/captions.py`)
- Evaluates deterministic routing rules in strict priority sequence:
  1. Identified Family Groups / Named People
  2. Travel & Nature Scenes
  3. Work & Screenshots
  4. Video Vault
  5. Everyday Archive
- Generates rich metadata captions containing ISO dates, location, identified people, and scene hashtags.

### 4. Telegram Upload Coordinator (`src/uploader.py`, `src/telegram_client.py`)
- Two-phase upload:
  - Phase 1: High-res preview photo with metadata caption.
  - Phase 2: Uncompressed original file as raw document.
- Only commits transaction upon receiving confirmed message IDs from Telegram API.

### 5. Multi-Machine Worker Architecture
- Ingestion tasks can be executed by decoupled worker nodes (`WorkerConfig`), coordinating against a centralized control center and SQLite WAL database.
