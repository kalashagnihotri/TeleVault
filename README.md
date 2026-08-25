# 🚀 TeleVault — Private Media Archive & Personal AI Memory Engine

**TeleVault** is an enterprise-grade, local-first media archiving and personal intelligence platform. It seamlessly ingests photos, videos, receipts, and documents from mobile devices (Android $\rightarrow$ temporary Google Drive sync $\rightarrow$ local Windows processing) into an encrypted, deduplicated, multi-modal **Telegram Cloud Archive** paired with a modern **Control Center Dashboard & Personal AI Suite**.

---

## 🌟 Key Capabilities & Architecture

```
[ Mobile Phone ] ──(Sync)──► [ Temp Drive Queue ]
                                     │
                                     ▼ (Local Ingestion & AI Pipeline)
[ Local PC / Control Center ] ◄──────┤
  ├── SHA-256 Deduplication          ├── Face Recognition (YuNet + SFace)
  ├── 512-dim Vision Embeddings      ├── Scene Classification (Places365)
  ├── Document OCR & Receipts        └── Video Storyboard Intelligence
                                     │
                                     ▼ (Encrypted Cloud Backup)
                     [ Telegram Topic Channels & Private Cloud ]
```

### 1. Zero-Loss Backup Correctness & Deduplication
- **SHA-256 Exact Deduplication**: Prevents duplicate uploads across devices and directories.
- **Transactional Safety**: Source files are **never deleted** from the temporary queue until Telegram confirms document upload and the SQLite database transaction commits.
- **Telegram Dual-Mode Ingest**: Stores high-res compressed preview alongside the 100% untouched original raw document file.

### 2. Multi-Modal Intelligence Engine
- **Face Recognition**: YuNet CNN detector + SFace 128-dim embeddings with automatic reference calibration and person timeline distribution.
- **Scene Classification**: ResNet-18 / Places365 indoor and outdoor taxonomy.
- **Semantic Vision Embeddings**: 512-dim cross-modal embedding projections for natural language visual search (*"kids playing near water"*, *"golden sunset on beach"*).
- **Document & Financial OCR**: Extracts merchant names, dates, amounts, and full text from invoices, receipts, and forms.
- **Video Intelligence**: Extracts duration, framerate, codecs, and 4-frame storyboard timeline previews.

### 3. Production Reliability (Phase 6.5I)
- **Pipeline Replay Engine**: Full audit ledger (`pipeline_execution_history`) allowing 100% reproducible step-by-step pipeline re-runs.
- **Model Version Registry**: Tracks lineage and SHA-256 checksums across model weights.
- **Git-like Config History**: Immutable YAML version snapshots with unified textual diffing and 1-click rollback.
- **3-Tier Priority Queue**: Prioritizes failed retries (P1) over new uploads (P2) and background reprocessing (P3).
- **Consolidated Failure Recovery Center**: Categorizes root causes (Corrupted File, Telegram Timeout, Missing Model) with 1-click batch retries.
- **Storage Intelligence**: Storage category breakdowns, largest file rankings, and compression savings estimators.
- **Automated Sandbox Restore Testing**: Simulates cold restores in an isolated sandbox, verifying 100% row reconciliation and Backup Confidence Score (e.g. 100%).

### 4. Personal AI Experience (Phase 6.5J)
- **True Conversational AI Archive Chat**: Multi-hop query understanding combining trips, nature, dining, people, locations, and dates.
- **Memory Autobiography Generator**: Synthesizes annual life story books (*"My 2026: A Year in Moments"*) across 12 monthly narrative chapters.
- **Emotion & Atmosphere Tagger**: Suggestive mood classification (Celebrations, Peaceful Nature, Family Warmth, Work Focus).
- **Calendar Event Linkage**: Matches Google Calendar / ICS appointments with media assets by date range and location.
- **Location Intelligence & Frequency Hierarchy**: Reverse geocoding hierarchy (GPS $\rightarrow$ City $\rightarrow$ State $\rightarrow$ Country) and visit frequency rankings.

### 5. Architecture Evolution (Phase 7)
- **Mobile Companion PWA**: Offline-ready Progressive Web App manifest and companion endpoints.
- **Private Cloud Sync Protocol**: Local-first authority with optional encrypted zero-knowledge private cloud sync.
- **Plugin Marketplace**: Dynamic catalog of official & community extensions (`OCR+`, `Weather+`, `Maps+`, `AudioTranscribe+`).
- **Public REST API v1**: Token-authenticated integration endpoints (`GET /api/v1/photos`, `GET /api/v1/people`, `GET /api/v1/memories`).

---

## 🛠️ How to Run the Project

### 1. Prerequisites
- **Operating System**: Windows 10/11 or Linux
- **Python**: Version 3.10+ (Python 3.12 recommended)
- **Node.js & npm**: Version 18+ (for Control Center UI)
- **Telegram Bot Token & API Credentials**: From [my.telegram.org](https://my.telegram.org) and [@BotFather](https://t.me/BotFather)

---

### 2. Initial Setup & Configuration

1. **Clone the repository and enter the directory**:
   ```bash
   git clone https://github.com/kalashagnihotri/TeleVault.git
   cd TeleVault
   ```

2. **Create Python virtual environment & install dependencies**:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

3. **Configure Environment & Settings**:
   - Copy `.env.example` to `.env` and fill in your credentials:
     ```ini
     TELEGRAM_BOT_TOKEN=your_bot_token_here
     TELEGRAM_API_ID=your_api_id
     TELEGRAM_API_HASH=your_api_hash
     TELEGRAM_CHAT_ID=-100xxxxxxxxxx
     ```
   - Copy `config/config.example.yaml` to `config.yaml` (or adjust default paths).

4. **Initialize Database & Apply Migrations**:
   ```powershell
   .\scripts\init_database.ps1
   ```

---

### 3. Running the Control Center & Web UI

#### Method A: Unified Daemon (Production Mode)
Run the automated launcher script to start both the FastAPI backend and serve the compiled React dashboard on `http://127.0.0.1:8000`:
```powershell
.\scripts\start_control_center.ps1
```

#### Method B: Development Mode (Vite Hot-Reload)
1. **Start Backend**:
   ```powershell
   $env:PYTHONPATH="."
   .\.venv\Scripts\python -m uvicorn src.control_center.app:app --host 127.0.0.1 --port 8000 --reload
   ```
2. **Start Frontend Vite Dev Server**:
   ```powershell
   cd ui
   npm install
   npm run dev
   ```
   Open `http://localhost:5173` in your browser.

---

### 4. Running the Ingestion & Backup Pipeline

- **Dry-Run Mode (Simulates hashing, AI tagging, routing without uploading)**:
  ```powershell
  .\scripts\run_dry.ps1
  ```
- **Live Mode (Executes pipeline and uploads to Telegram channels)**:
  ```powershell
  .\scripts\run_live.ps1
  ```

---

## 🧠 How to Train, Enroll & Calibrate Models

### 1. Face Recognition Model & Person Enrollment (YuNet + SFace)

TeleVault uses a dual-engine architecture:
- **YuNet (OpenCV Zoo)**: Fast CNN face detector.
- **SFace**: 128-dimensional cosine feature extractor.

#### Enrolling Known People:
1. Place reference photos of known individuals in `private_data/faces/references/<Person_Name>/`:
   ```
   private_data/faces/references/
   ├── Alice_Smith/
   │   ├── alice_1.jpg
   │   ├── alice_2.jpg
   │   └── alice_3.jpg
   └── Bob_Jones/
       ├── bob_1.jpg
       └── bob_2.jpg
   ```
2. Ensure at least **3 to 5 clear, unoccluded reference photos** per person across varied lighting and angles.
3. The system automatically computes a cryptographic SHA-256 dataset hash over the folder and generates a new active calibration record in `face_calibrations`.

#### Running Negative Benchmark Calibration:
To evaluate false-positive rejection rates against benchmark sets (e.g. LFW negatives):
```powershell
python scripts/prepare_lfw_negatives.py
```

#### Re-evaluating Archive Faces with New Models:
When updating reference photos or tuning acceptance thresholds ($0.85 \rightarrow 0.90$):
```powershell
python scripts/requeue_face_analysis.py
```

---

### 2. Scene Classification Model (Places365 ResNet-18)

TeleVault categorizes environments into natural, urban, document, and indoor taxonomy using Places365.

#### Exporting PyTorch Places365 to ONNX:
To convert a pre-trained PyTorch checkpoint into an optimized local ONNX runtime model:
```powershell
python scripts/export_places365_resnet18_onnx.py
```

#### Evaluating Scene Classifier Precision & Recall:
Run the evaluation harness against local ground-truth test splits:
```powershell
python scripts/evaluate_scene_model.py
```

---

### 3. Model Lineage & Version Registry Management

Register or inspect custom model checkpoints directly via the Model Registry:
- **List models**: `GET /api/models/list`
- **Register new model via API**:
  ```bash
  curl -X POST http://127.0.0.1:8000/api/models/register \
    -H "Content-Type: application/json" \
    -d '{
      "model_name": "YuNet Face Detector",
      "version": "2024-Ultra",
      "category": "FACE_DETECTOR",
      "description": "Next-gen ultra fast face detector"
    }'
  ```

---

## 🧪 Testing & Quality Assurance

### 1. Running Unit & Integration Test Suites
TeleVault includes comprehensive regression and fault-injection test coverage:
```powershell
$env:PYTHONPATH="."
.\.venv\Scripts\pytest tests/ -v
```

### 2. Running Live Multi-Modal End-to-End Tests
Generates synthetic multi-modal test assets (portraits, landscapes, documents, receipts, videos) and executes live pipeline verification:
```powershell
$env:PYTHONPATH="."
.\.venv\Scripts\python scripts/live_phase_6_5i_test.py
```

### 3. Running Static Privacy & Logging Audit
Ensures zero token or personal secret leakage in logs, commits, or responses:
```powershell
.\.venv\Scripts\pytest tests/test_logging_audit.py -v
```

---

## 🔒 Security & Privacy Non-Negotiables

1. **Backup Integrity > Classification**: Recognition failure never suppresses or delays a media backup.
2. **Never Delete Before Commit**: Files in the incoming queue are never deleted until Telegram confirms upload receipt and SQLite commits.
3. **Exact Duplicates Blocked**: Uses full-file SHA-256 unique constraints.
4. **Zero-Telemetry & Secret Isolation**: Credentials, tokens, embeddings, and raw databases are strictly kept in local storage and excluded from version control.

---

## 📄 License & Attribution
Distributed under the **MIT License**. Created with local-first privacy engineering principles.
