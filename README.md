# SmartCrowd Safety Operations

SmartCrowd is a local-first Flask application for AI-powered crowd monitoring, incident evidence, and occupancy analytics. It supports webcams, USB cameras, uploaded videos, RTSP/IP sources, concurrent camera pipelines, restricted zones, directional counting, heatmaps, alert screenshots, and downloadable reports.

## Production architecture

The application separates responsibilities so additional AI capabilities can be introduced without rewriting camera or dashboard workflows.

- `backend/detection/` - shared YOLOv8 inference, isolated Supervision ByteTrack identities, frame encoding, zones, and camera workers
- `backend/analytics/` - sampled occupancy metrics and heatmap generation
- `backend/alerts/` - cooldown-aware crowd and zone incidents with evidence capture
- `backend/services/` - startup diagnostics and platform health checks
- `backend/data_store.py` - SQLite settings cache, camera registrations, events, reports, and durable occupancy samples
- `backend/routes/` - focused REST blueprints for monitoring, settings, analytics, reports, cameras, and startup health
- `frontend/` - responsive dashboard, health-gated startup, responsible-use consent, historical charts, and operation feedback

One YOLO model is shared across camera workers behind an inference lock. Each camera owns a separate ByteTrack tracker, avoiding cross-camera identity mixing while preventing unnecessary model-memory duplication.

## Installation

Use Python 3.10 or newer. Keep `yolov8n.pt` in `models/`.

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

The application runs through Waitress at `http://127.0.0.1:5000` by default. Override host, port, model path, or runtime limits with `SCM_*` environment variables, for example `SCM_PORT`, `SCM_MODEL_PATH`, `SCM_MAX_CAMERAS`, and `SCM_TARGET_INFERENCE_FPS`.

## Operational behavior

- Startup performs backend, dependency, model artifact, storage, configuration, and camera-service diagnostics before showing the dashboard.
- A responsible-use notice must be accepted for each browser page session.
- Occupancy is sampled every five seconds and retained for seven days in SQLite; the analytics page supports 5 minute through 7 day windows plus custom ranges.
- Inference is capped by the configurable target FPS (12 by default) to keep camera processing predictable under load.
- The browser refreshes telemetry every five seconds and refreshes camera registrations every 30 seconds, with overlap protection and pause-on-background behavior.

## REST API overview

| Endpoint | Purpose |
| --- | --- |
| `POST /api/system/initialize` | Warm the model and return startup diagnostics |
| `GET /api/health` | Return detailed operational health |
| `POST /api/cameras/start` | Start webcam, USB, video, RTSP, or IP monitoring |
| `GET /api/monitoring/statistics` | Return selected or aggregate live telemetry |
| `POST /api/monitoring/<id>/zones` | Configure restricted polygon zones |
| `POST /api/monitoring/<id>/counting-line` | Configure directional IN/OUT line counting |
| `GET /api/analytics/history` | Return sampled historical occupancy data |
| `GET /api/analytics/export` | Export plotted history as CSV or JSON |
| `GET|PUT /api/settings` | Retrieve or update runtime safety settings |
| `POST /api/reports/generate` | Generate PDF, CSV, JSON, or TXT evidence reports |

## Runtime storage

| Location | Contents |
| --- | --- |
| `data/smart_crowd.db` | Cached settings, camera registrations, events, reports, and occupancy history |
| `uploads/` | Uploaded video inputs |
| `screenshots/` | Manual and automatic incident evidence |
| `exports/` | Generated reports and data exports |
| `logs/application.log` | Rotating application log |







# 🛡️ Smart Crowd Monitoring & Safety System

An AI-powered Crowd Monitoring and Safety System that performs real-time person detection, tracking, occupancy analysis, restricted zone monitoring, crowd alert generation, analytics, and reporting through a modern web dashboard.

> Developed as an educational and research project using Computer Vision, Artificial Intelligence, and Web Technologies.

---

# 📌 Overview

Smart Crowd Monitoring & Safety System is designed to improve safety by automatically monitoring people using:

- Live Webcam
- CCTV / IP Cameras
- Uploaded Videos

The system detects people in real time, tracks every individual using ByteTrack, calculates occupancy, monitors crowd density, generates alerts, and provides detailed analytics and reports.

---

# ✨ Features

## 🎥 Video Sources

- Webcam Support
- USB Camera Support
- CCTV / RTSP Camera Support
- IP Camera Support
- Video Upload Analysis

---

## 🤖 AI Features

- YOLOv8 Person Detection
- ByteTrack Person Tracking
- Real-time Occupancy Counting
- Crowd Density Analysis
- Persistent Person IDs
- Live FPS Monitoring

---

## 🚨 Safety Features

- Crowd Threshold Alerts
- Restricted Zone Monitoring
- Configurable Restricted Zone Threshold
- Line Crossing Counter (IN / OUT)
- Alert Cooldown
- Screenshot Capture
- Event Logging

---

## 📊 Analytics

- Live Occupancy Graph
- Historical Analytics
- Peak Occupancy
- Average Occupancy
- Occupancy Timeline
- Zoomable Charts
- Camera-wise Analytics

---

## 📄 Reports

Generate reports in:

- PDF
- CSV
- JSON
- TXT

---

## 📜 Logging

- Camera Events
- Alert Logs
- Tracking Logs
- Screenshot Logs
- Incident Logs
- Error Logs

---

## ⚙️ Settings

Users can configure:

- Detection Confidence
- Target Inference Rate
- Crowd Alert Threshold
- Alert Cooldown
- Heatmap Opacity
- Theme
- Screenshot Saving

---

## 🎯 Geometry Configuration

The built-in Geometry Editor allows users to configure monitoring regions visually.

### Supported Geometry

- Restricted Zones
- Counting Line
- Zone Threshold Configuration

Unlike manual coordinate editing, users can draw directly over the video.

---

# 🖥️ Dashboard Pages

- Overview
- Monitoring
- Analytics
- Reports
- Logs
- Settings
- About
- Help

---

# 🚀 Technology Stack

## Backend

- Python
- Flask
- OpenCV
- SQLite

## AI

- YOLOv8
- ByteTrack

## Frontend

- HTML5
- CSS3
- JavaScript
- Bootstrap 5
- Chart.js
- Font Awesome

---

# 📂 Project Structure

```
SmartCrowdMonitoring/

│
├── backend/
│   ├── app.py
│   ├── config.py
│   ├── routes/
│   ├── services/
│   ├── detection/
│   ├── database/
│   ├── exports/
│   ├── uploads/
│   ├── screenshots/
│   └── logs/
│
├── frontend/
│   ├── templates/
│   ├── static/
│   │
│   ├── css/
│   ├── js/
│   └── images/
│
├── models/
│
├── requirements.txt
│
└── README.md
```

---

# ⚙️ Installation

## Clone Repository

```bash
git clone https://github.com/yourusername/SmartCrowdMonitoring.git

cd SmartCrowdMonitoring
```

---

## Create Virtual Environment

```bash
python -m venv venv
```

Windows

```bash
venv\Scripts\activate
```

Linux

```bash
source venv/bin/activate
```

---

## Install Dependencies

```bash
pip install -r requirements.txt
```

---

## Run Application

```bash
python app.py
```

or

```bash
python -m backend.app
```

---

# 🖥️ System Requirements

Minimum

- Windows 10/11
- Python 3.10+
- 8 GB RAM
- Dual Core Processor

Recommended

- Windows 11
- Python 3.10+
- Intel i5/i7
- 16 GB RAM
- NVIDIA GPU (optional)

---

# 📷 Workflow

```
Camera

↓

Capture Frames

↓

YOLOv8 Detection

↓

ByteTrack Tracking

↓

Occupancy Calculation

↓

Crowd Analysis

↓

Restricted Zone Monitoring

↓

Alert Generation

↓

Dashboard Update

↓

Reports & Logs
```

---

# ⚙️ Geometry Editor

The Geometry Editor enables administrators to visually configure surveillance regions.

Supports

- Draw Restricted Zones
- Draw Counting Line
- Undo
- Clear
- Zone Threshold
- Save Geometry

The system automatically stores geometry using original video coordinates to ensure accurate overlay regardless of display resolution.

---

# 📊 Dashboard Metrics

- Current Occupancy
- Average Occupancy
- Peak Occupancy
- Crowd Density
- Processing FPS
- Runtime
- Tracking Count
- Line Crossing Count
- System Status

---

# 🚨 Alert Types

The system can generate alerts for

- Crowd Threshold Exceeded
- Restricted Zone Occupancy
- Camera Disconnection
- System Errors

---

# 📁 Export Formats

- PDF
- CSV
- JSON
- TXT

---

# 🎯 Use Cases

- Universities
- Schools
- Shopping Malls
- Airports
- Railway Stations
- Hospitals
- Corporate Offices
- Industrial Plants
- Public Events
- Government Buildings

---

# 🔒 Privacy

This project performs local AI inference.

No cloud processing is required.

Camera streams remain within the local system unless configured otherwise.

---

# ⚠️ Disclaimer

This software has been developed strictly for educational, research, and demonstration purposes.

The developers are not responsible for any misuse of this project.

Users must comply with all applicable privacy laws, surveillance regulations, and local legal requirements before deploying the software in real-world environments.

## Cloud deployment

The repository includes a `Procfile` for Render, Railway, and other Procfile-compatible hosts. The production entrypoint is `run.py`, which serves the existing Flask application through Waitress.

1. Install dependencies with `pip install -r requirements.txt`.
2. Ensure `models/yolov8n.pt` is committed or provide an absolute `SCM_MODEL_PATH`.
3. Set `SCM_SECRET_KEY` to a long random value and keep `SCM_DEBUG=false`.
4. Configure the platform-provided `PORT`; the application reads it through `SCM_PORT` when set.
5. For durable uploads, screenshots, exports, logs, and SQLite data, set `SCM_STORAGE_ROOT` to a mounted persistent volume. Ephemeral cloud disks can lose these files on redeploy.
6. Start the service with `python run.py` (or let the `Procfile` do so).

The application creates its required storage directories at startup and resolves relative paths from the project root. Webcam and USB sources generally require a machine-local deployment; cloud deployments should use uploaded video or reachable RTSP/IP sources.

### Multi-user isolation

Each browser receives a signed, randomly generated session identifier. Camera workers, settings, SQLite data, uploads, screenshots, exports, and analytics are scoped to that session. Session files are stored below `SCM_STORAGE_ROOT/sessions/<session-id>/` and inactive sessions are cleaned up after `SCM_SESSION_TTL_SECONDS` (one hour by default). Use a persistent storage volume for these files when running on a cloud platform.

---

# 📈 Future Enhancements

- Multi-Camera Dashboard
- Heatmap Analytics
- Email Alerts
- SMS Alerts
- Face Recognition (Optional)
- Object Detection Expansion
- Cloud Dashboard
- Mobile Notifications
- Role-Based Authentication
- User Management
- Live Streaming Support
- GPU Optimization

---

# 👨‍💻 Author

**Khadar Masthan SK**

B.Tech Information Technology

SASTRA Deemed University

---

# ⭐ If you found this project useful

Give this repository a ⭐ on GitHub.

It helps others discover the project and motivates future improvements.
