# Real-Time Vehicle Analytics Pipeline

An end-to-end computer vision system that:

1. **ingests** a live RTSP video stream through MediaMTX,
2. **detects, tracks and colour-classifies** vehicles on the GPU with NVIDIA DeepStream,
3. **counts** vehicles that cross a virtual line (direction-aware) and logs every crossing to **PostgreSQL**,
4. **shows** live and historical analytics on a **React** dashboard, together with the annotated video.

**Tested result** (free Google Colab Tesla T4, DeepStream 8.0, 1280×720 traffic video at 25 FPS):

| Measure | Result |
|---|---|
| Pipeline speed | ~24 FPS sustained, real time for the 25 FPS input |
| Counting | in/out counts match nvdsanalytics' own cumulative counter exactly |
| Database | every crossing stored (`db inserted` = counted events, queue stays at 0) |
| Colour classifier | 0.875 validation accuracy on 15 colours (VCoR dataset) |

---

## 1. Technology stack

| Layer | Technology | Version | Role in this project |
|---|---|---|---|
| Video source | FFmpeg | distro package | Loops an MP4 traffic video and publishes it over RTSP, behaving like a live camera |
| Video broker | MediaMTX | latest release | Single RTSP/HLS hub: receives the camera stream, re-publishes the annotated output as RTSP and HLS |
| Vision engine | NVIDIA DeepStream SDK (GStreamer) + Python bindings `pyds` | 8.0 (tested) / 7.1 (container path) | GPU pipeline: decode, batch, detect, track, classify, count, draw, encode |
| Primary detector (PGIE) | TrafficCamNet (ResNet18 DetectNet_v2), TensorRT | ships with DeepStream | Finds vehicles in every frame (`car` class kept) |
| Tracker | NvDCF (`nvtracker`) | ships with DeepStream | Gives each vehicle a stable ID across frames, so it is counted once |
| Secondary classifier (SGIE) | ResNet18 fine-tuned on VCoR → ONNX → TensorRT FP16 | trained here | Classifies the colour of each vehicle crop (15 colours) |
| Line counting | `nvdsanalytics` | ships with DeepStream | Direction-aware virtual-line crossing (`in` / `out`) |
| Database | PostgreSQL | 14+ (16 tested) | Stores every crossing event with a microsecond timestamp |
| DB writer | Python thread + queue, `psycopg2` `execute_values` | — | Asynchronous, batched inserts from the DeepStream probe |
| API | FastAPI + Uvicorn | 0.110+ | Read-only REST API; also serves the dashboard and passes the HLS video through |
| Frontend | React 18 + Vite, hls.js | — | Live metrics, colour breakdown, chart, recent-events table, live video |
| Model training | PyTorch + torchvision, ONNX | 2.2+ | Fine-tunes and exports the colour classifier (Kaggle T4) |
| GPU platform | Google Colab (free T4) or any NVIDIA GPU machine | — | Runs the DeepStream pipeline |

---

## 2. Architecture

```mermaid
flowchart TD
    CAM["Looped MP4 (live camera)"] -- "FFmpeg: RTSP publish" --> MTX[("MediaMTX<br/>RTSP :8554 · HLS :8888")]
    MTX -- "rtsp://…/traffic" --> SRC

    subgraph DS["DeepStream pipeline (GPU)"]
        direction TB
        SRC["nvurisrcbin<br/>NVDEC decode"] --> MUX["nvstreammux<br/>1280×720 batch"]
        MUX --> PGIE["nvinfer PGIE<br/>TrafficCamNet: detect"]
        PGIE --> TRK["nvtracker<br/>NvDCF: track IDs"]
        TRK --> SGIE["nvinfer SGIE<br/>colour on each box"]
        SGIE --> ANA["nvdsanalytics<br/>line crossing in / out"]
        ANA --> OSD["nvdsosd<br/>draw boxes + labels"]
        OSD --> ENC["NVENC H.264<br/>RTSP server :8555/ds"]
    end

    subgraph STORE["Storage (async)"]
        direction TB
        Q["in-memory queue"] --> W["DB writer thread<br/>batched INSERT"]
        W --> PG[("PostgreSQL<br/>vehicle_events")]
    end

    ANA -. "pad probe: crossing event" .-> Q
    ENC -- "pulled as /processed" --> MTX

    PG --> API["FastAPI :8000"]
    MTX -- "HLS /processed via /hls" --> API
    API -- "JSON every 1 s + HLS video" --> UI["React dashboard"]
```

### How data moves
1. **Ingestion.** FFmpeg reads a local MP4 at real speed (`-re`), loops it forever and publishes it to MediaMTX at `rtsp://host:8554/traffic`.
2. **Decode and batch.** `nvurisrcbin` pulls the stream over TCP, decodes it on the GPU (NVDEC) and reconnects if the stream drops. `nvstreammux` scales frames to 1280×720 and batches them (batch size 1 today; more cameras = more sources).
3. **Detect.** The primary `nvinfer` runs TrafficCamNet on every frame; only the `car` class is kept.
4. **Track.** `nvtracker` (NvDCF) gives each vehicle a persistent `object_id`, also through short occlusions.
5. **Classify colour.** The secondary `nvinfer` runs **only on the detector's bounding boxes**: each box is cropped, resized to 224×224 and classified into 15 colours. It classifies a track once and reuses the result.
6. **Count.** `nvdsanalytics` checks whether a tracked vehicle's bottom-centre point crossed the line, and in which direction.
7. **Persist.** A pad probe on the `nvdsanalytics` output reads the metadata (box, track ID, colour, crossing). On each new crossing it puts a `VehicleEvent` on a queue without waiting. A background thread inserts the queued events into PostgreSQL in batches, so the video never waits for the database.
8. **Visualise.** `nvdsosd` draws boxes, `#id colour` labels, the line and counters. The video is encoded with NVENC and served on an internal RTSP server; MediaMTX pulls it as `/processed` and re-publishes it as HLS. The React app polls the API every second and plays the HLS video through the API's `/hls` route.

### Why each vehicle is counted exactly once
- The **tracker** keeps the same ID for a vehicle across frames.
- **nvdsanalytics** reports a crossing only on the frame where the track's path crosses the line in the configured direction (`mode=balanced` ignores jitter on the line).
- The probe also keeps a set of `(source, track_id, line)` keys as a safety net, so one track can never produce a second row.

---

## 3. Key files

**[deepstream/app.py](deepstream/app.py)** is the core of the project. `build_pipeline()` creates and links the GStreamer elements in the order shown above, and links the RTSP source once the stream arrives. `write_analytics_config()` turns the `--line x1,y1,x2,y2` argument into the nvdsanalytics config, with two opposite arrows on the same line so each crossing is labelled `in` or `out`. The `VehicleCounter` probe runs on every frame after nvdsanalytics: it reads each vehicle's bounding box (`rect_params`), tracker ID (`object_id`), colour (from the classifier metadata) and crossing status (`lcStatus`), skips IDs that were already counted, and hands each new crossing to the database writer.

**[deepstream/db_writer.py](deepstream/db_writer.py)** saves events without slowing the video. The probe only puts an event on a queue (`put_nowait`, never waits); a background thread takes events off the queue and inserts them into PostgreSQL in batches (every 50 events or 250 ms). If the database goes down, it keeps the batch, reconnects and retries.

**[color_classifier/train.py](color_classifier/train.py)** trains the colour model. It fine-tunes an ImageNet ResNet18 on the VCoR dataset (15 colours), keeps the epoch with the best validation accuracy, and exports a single ONNX file plus the label list that DeepStream's secondary `nvinfer` loads.

**[scripts/prepare_pgie_config.py](scripts/prepare_pgie_config.py)** builds the detector config from the TrafficCamNet config that ships with the installed DeepStream version, so model paths always match the SDK. It keeps only the `car` class and falls back to FP16 when no INT8 calibration file exists.

**[backend/main.py](backend/main.py)** is the FastAPI server behind the dashboard. It answers the summary, events and per-minute queries from PostgreSQL, serves the built React app, and passes MediaMTX's HLS video through `/hls` so the dashboard and its video share one address.

**[frontend/src/](frontend/src/)** is the React dashboard. It polls the API every second for counts, the colour breakdown and recent crossings, and plays the annotated video with hls.js.

**[mediamtx/mediamtx.yml](mediamtx/mediamtx.yml)** configures the video broker: `traffic` receives the camera stream from FFmpeg, and `processed` pulls DeepStream's annotated output and re-publishes it as RTSP and HLS.

**[scripts/setup_colab.sh](scripts/setup_colab.sh)** installs the full DeepStream 8.0 stack on Colab without Docker (CUDA 12.8, TensorRT 10.9, DeepStream 8.0, `pyds` in a Python 3.12 environment). **[notebooks/colab_demo.ipynb](notebooks/colab_demo.ipynb)** runs the whole project on Colab cell by cell.

### Repository structure
```
├── mediamtx/mediamtx.yml          # broker config (paths: traffic, processed)
├── deepstream/
│   ├── app.py                     # pipeline + probe (core logic)
│   ├── db_writer.py               # async, batched PostgreSQL writer thread
│   └── configs/                   # tracker, colour classifier, line crossing, PGIE example
├── color_classifier/train.py      # fine-tune ResNet18 on VCoR, export ONNX
├── models/color/                  # trained colour model (ONNX) + labels
├── database/schema.sql            # vehicle_events table + indexes
├── backend/main.py                # FastAPI API (+ dashboard + HLS pass-through)
├── frontend/                      # React dashboard (Vite)
├── notebooks/colab_demo.ipynb     # run everything on a free Colab T4
├── scripts/                       # installers, DB init, start scripts, tmux launcher
└── docs/CLOUD_GPU_SETUP.md        # running the DeepStream 7.1 container on a rented GPU
```

---

## 4. How to run

DeepStream needs an NVIDIA GPU. Choose one option.

### Option A — Google Colab, free (tested)

1. Open **[notebooks/colab_demo.ipynb in Colab](https://colab.research.google.com/github/tejasprof84/vehicle-analytics/blob/main/notebooks/colab_demo.ipynb)**.
2. **Runtime → Change runtime type → T4 GPU**.
3. Run the cells from top to bottom:

| Cell | Does | Time | Expected output |
|---|---|---|---|
| 1 | Check the GPU | seconds | `Tesla T4` |
| 2 | Clone the repo and run `setup_colab.sh` | 15–20 min | `pyds OK`, `Colab setup complete` |
| 3 | Download the traffic clip and convert it to 1280×720 | ~30 s | `width=1280 height=720` |
| 4 | Start everything (`run_all.sh`) | seconds | `Started.` |
| 5 | Print the dashboard and live-video links | instant | two `…colab.dev` links |
| 6 | Pipeline log (wait 3–5 min the first time: TensorRT builds the engines) | instant | `COUNT id=… colour dir=in`, `FPS ~24` |
| 7 | Latest database rows | instant | rows with colour, direction, timestamp |
| 8 | One annotated frame | seconds | boxes, IDs, colours, line, counters |
| 9 | Stop everything | instant | — |

Open the **Dashboard** link from cell 5 in a new tab. Colab runtimes are temporary; after a disconnect, run all cells again.

### Option B — any NVIDIA GPU machine (DeepStream 7.1 container)

Requirements: NVIDIA GPU (Turing or newer) with driver ≥ 560, the container `nvcr.io/nvidia/deepstream:7.1-triton-multiarch`. For a rented GPU, follow [docs/CLOUD_GPU_SETUP.md](docs/CLOUD_GPU_SETUP.md).

```bash
git clone https://github.com/tejasprof84/vehicle-analytics.git
cd vehicle-analytics
cp .env.example .env            # DB credentials, input video, RTSP URL
bash scripts/setup.sh           # FFmpeg, PostgreSQL, pyds, MediaMTX, Node.js, DB, dashboard build
bash scripts/run_all.sh         # MediaMTX, FFmpeg, DeepStream, API in one tmux session
tmux attach -t vehicle          # watch the logs (Ctrl+B then D to detach)
```
Then open `http://<host>:8000`.

### Phase by phase (one terminal each)

| Phase | Command | Check |
|---|---|---|
| 1 Broker | `bash scripts/start_mediamtx.sh` | `[RTSP] listener opened on :8554` |
| 1 Stream | `bash scripts/start_stream.sh [video.mp4]` | VLC → `rtsp://<host>:8554/traffic` |
| 2+3 Pipeline | `bash scripts/start_pipeline.sh [--line x1,y1,x2,y2]` | `COUNT id=… colour dir=…` lines, FPS log |
| 3 DB | `psql postgresql://vehicle:vehicle@127.0.0.1:5432/vehicle_analytics -c "SELECT * FROM vehicle_events ORDER BY id DESC LIMIT 5;"` | rows appear |
| 4 Dashboard | `bash scripts/start_backend.sh` | open `http://<host>:8000` |

The input video is set by `INPUT_VIDEO` in `.env` (default: a DeepStream sample clip).

### Endpoints

| URL | What |
|---|---|
| `rtsp://<host>:8554/traffic` | raw input stream |
| `rtsp://<host>:8554/processed` | annotated output (boxes, IDs, colours, line, counts) |
| `http://<host>:8888/processed/` | annotated output in the browser (HLS, MediaMTX player) |
| `http://<host>:8000` | React dashboard |
| `http://<host>:8000/docs` | interactive API docs (Swagger) |

### Pipeline options
```bash
python3 deepstream/app.py --help
  --uri          input RTSP URI                        (default rtsp://127.0.0.1:8554/traffic)
  --db-url       PostgreSQL DSN                        (default from $DATABASE_URL)
  --line         counting line x1,y1,x2,y2 (1280x720)  (default 0,430,1280,430)
  --sink         rtsp | fake (headless)                (default rtsp)
  --encoder      nvenc | x264 (GPUs without NVENC)     (default nvenc)
  --skip-color   run without the SGIE (debugging)
```

### Colour classifier (optional re-training)
DeepStream 7.x/8.x ship no car-colour model, so one was trained: ResNet18 fine-tuned for 6 epochs on VCoR (15 colours), **0.875 validation accuracy**. The trained model is in `models/color/`. To re-train (about 10 minutes on a GPU; a free Kaggle T4 notebook works):
```bash
cd color_classifier
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
kaggle datasets download -d landrykezebou/vcor-vehicle-color-recognition-dataset -p data/vcor --unzip
python train.py --data-dir data/vcor --epochs 6
```
See [color_classifier/README.md](color_classifier/README.md).

---

## 5. Pipeline configuration details

- **`nvstreammux`:** `width=1280 height=720 batch-size=1 live-source=1 batched-push-timeout=40000`. All coordinates (line, boxes) use this 1280×720 space.
- **Primary detector** (`configs/pgie_trafficcamnet.txt`, generated): DeepStream's TrafficCamNet config with `batch-size=1` and `filter-out-class-ids` for everything except `car`. INT8 when the SDK ships a calibration file (DeepStream 7.1), otherwise FP16 (DeepStream 8.0). A reference copy is in `pgie_trafficcamnet.example.txt`.
- **Tracker:** NvDCF (correlation filters + motion prediction) with the SDK's `config_tracker_NvDCF_perf.yml`.
- **Secondary classifier** (`configs/sgie_color.txt`):

| Key | Value | Meaning |
|---|---|---|
| `process-mode` | 2 | operate on objects, not full frames |
| `operate-on-gie-id` / `operate-on-class-ids` | 1 / 0 | only boxes from the detector's car class |
| `net-scale-factor`, `offsets` | ImageNet normalisation | same pre-processing as training |
| `classifier-async-mode` | 1 | classify once per track, reuse the result |
| `input-object-min-width/height` | 40 | skip tiny boxes (shown as `unknown`) |
| `network-mode` | 2 | FP16 |

- **Line crossing** (`configs/nvdsanalytics.txt`, generated from `--line`): each entry is `direction(x1;y1;x2;y2);line(x1;y1;x2;y2)`. Two entries share one line with opposite direction vectors (`line-crossing-in`, `line-crossing-out`); the crossing label gives the direction. `mode=balanced`.
- **Database writes** (`deepstream/db_writer.py`): the probe only calls `queue.put_nowait()`; the writer thread flushes every 250 ms or 50 events with `execute_values`, reconnects automatically and flushes remaining events on shutdown.
- **DeepStream 7.x vs 8.0 metadata:** 8.0 tags nvdsanalytics results with built-in meta types (`NVDS_FRAME_META_NVDSANALYTICS`, `NVDS_OBJ_META_NVDSANALYTICS`); 7.x uses name-registered user types. The probe accepts both. The FPS log line also prints nvdsanalytics' own cumulative counts (`lc_cum`) as a cross-check.

---

## 6. Database schema

```sql
vehicle_events(
  id BIGSERIAL PK, vehicle_id BIGINT, vehicle_class TEXT, color TEXT, color_confidence REAL,
  direction TEXT, line_name TEXT, source_id INT, frame_number BIGINT,
  bbox_left/top/width/height REAL, event_time TIMESTAMPTZ  -- UTC, microsecond precision
)
-- indexes on event_time DESC, color, direction
```
Useful queries:
```sql
SELECT color, count(*) FROM vehicle_events GROUP BY color ORDER BY 2 DESC;
SELECT date_trunc('minute', event_time) m, count(*) FROM vehicle_events GROUP BY m ORDER BY m DESC LIMIT 10;
```

---

## 7. Dashboard

- **Live metrics:** total count, in / out counts, count in the last 60 s, most common colour, time of the last crossing.
- **Colour breakdown:** a bar per colour, with percentages.
- **History:** vehicles per minute (stacked in/out), range selector (15 min, 1 h, 24 h, all time).
- **Live table:** the 25 most recent crossings, newest first.
- **Live video:** the DeepStream-annotated stream (HLS), with boxes, IDs, colours and the line.

Metrics and the table refresh every 1 s, the chart every 5 s (polling; works through any proxy or tunnel).

---

## 8. Design decisions and limitations

Choices I made where the usual setup was not available or did not fit, and the current limits of the project:

| # | Topic | Usual setup | What this project does | Why |
|---|---|---|---|---|
| 1 | GPU platform and DeepStream version | DeepStream 7.1 container on a dedicated NVIDIA GPU machine | The tested setup runs **DeepStream 8.0**, installed natively on a **free Google Colab T4**. The DeepStream **7.1 container** path (`setup.sh`, `docs/CLOUD_GPU_SETUP.md`) is included but has **not** been run end-to-end. | I had no local NVIDIA GPU (Intel integrated graphics). Colab has no Docker and runs Ubuntu 24.04 + Python 3.12, which matches DeepStream 8.0, not the 7.1 container. The pipeline code supports both versions. |
| 2 | Checking the RTSP stream | Open `rtsp://<host>:8554/traffic` in VLC | On Colab, the stream is checked **inside the runtime**: MediaMTX logs (`stream is available and online`), `ffmpeg` frames pulled from `rtsp://127.0.0.1:8554/processed`, and the live HLS player. VLC works on a normal GPU machine through an SSH tunnel (Option B). | Colab's terms do not allow tunnels/remote proxies, so the RTSP port can't be opened from another computer. |
| 3 | Video source | A live traffic camera | A **25-second free Pexels clip** (fixed camera above a road), looped by FFmpeg as a live RTSP stream. | No physical camera. DeepStream's bundled sample clips were not suitable for line counting (low sidewalk view, fisheye, dashcam). Because the clip loops, the same cars pass again every 25 s and are counted again with new track IDs; with a real camera every vehicle is new. |
| 4 | Colour classifier | A ready-made car-colour model | A **colour model trained for this project** (ResNet18 on VCoR, 87.5 % validation accuracy). Small/far boxes (< 40 px) are labelled `unknown`. | DeepStream 7.x/8.x no longer ship a car-colour model (the old one was Caffe, which TensorRT 10 dropped). Colour on tiny crops is unreliable, so they are skipped on purpose. |
| 5 | Vehicle classes | Separate car / truck / bus classes | Only TrafficCamNet's **`car`** class is kept; `vehicle_class` is always `car`. | TrafficCamNet's classes are car / bicycle / person / road sign; "car" is its vehicle class. A detector with truck/bus classes would be a drop-in change of the PGIE config. |
| 6 | Live video in the dashboard | Played directly from MediaMTX (port 8888) | Played **through the API's `/hls` route** on port 8000. | Colab gives each port its own hostname, so a URL like `<host>:8888` does not exist there. Passing the video through port 8000 keeps the dashboard and video on one origin and works everywhere. |
| 7 | Dashboard updates | Push (WebSocket) | The dashboard **polls** the API every second. | Simpler and robust behind proxies; one-second updates are enough for traffic counts. |
| 8 | Runtime | A persistent server | The Colab runtime is **temporary**: each new session needs ~15–20 min of setup plus 3–5 min of TensorRT engine build, and a free GPU is not always available. | Limits of the free Colab tier. On a persistent GPU machine (Option B) setup runs once and the engines are cached. |

---

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| `Unable to create element 'nvinfer'` | DeepStream not installed. Run inside the DS 7.1 container, or run `setup_colab.sh` on Colab. |
| `No module named pyds` | Container: re-run `setup.sh` (pyds 1.2.0, Python 3.10). Colab: re-run `setup_colab.sh` (pyds 1.2.2, Python 3.12 venv). |
| Pipeline waits forever | Check MediaMTX and FFmpeg: `ffprobe rtsp://127.0.0.1:8554/traffic`. |
| `nvv4l2h264enc` fails (A100/H100 have no NVENC) | Use `--encoder x264`. |
| No counts | Move the line with `--line` so traffic crosses it while tracked. Check `lc_cum` in the FPS log: if it rises but `in/out` don't, it's a metadata issue; if both stay 0, it's the line position or the video. |
| Colour always `unknown` | Boxes are smaller than 40 px, or the model is missing. Check `models/color/`. |
| Dashboard video says "offline" | Wait for the first TensorRT build; check that `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/hls/processed/index.m3u8` prints 200. |
| First start is slow | Expected: TensorRT builds the engines once and caches them. |
