# Running on a rented cloud GPU

DeepStream needs an NVIDIA GPU. If your laptop doesn't have one (for example, Intel or AMD graphics), rent a GPU machine for a few hours. You then reach everything (dashboard, HLS video, RTSP) from your own laptop through an SSH tunnel.

This guide uses **Vast.ai** because it runs any Docker image, including NVIDIA's DeepStream image, with SSH. RunPod and other providers work the same way.

## 1. Rent the GPU (about 10 minutes)

1. Create an account at vast.ai and add a small amount of credit. A few hours of work costs only a few dollars.
2. Add your SSH key. This step is on your laptop, so on Windows use PowerShell:
   ```powershell
   ssh-keygen -t ed25519          # press Enter for all prompts
   type $env:USERPROFILE\.ssh\id_ed25519.pub
   ```
   Copy the printed line into **Vast → Account → SSH Keys**.
3. **Templates → create a new template:**
   - **Image:** `nvcr.io/nvidia/deepstream:7.1-triton-multiarch`
   - **Launch mode:** *SSH*
   - **Disk:** 40 GB or more
4. **Search** for a machine:
   - **GPU:** RTX 3090, 4090, A4000, A5000 or T4. These all have the NVENC video encoder. Avoid A100 and H100, which don't.
   - **Max CUDA** filter set to **≥ 12.6**. DeepStream 7.1 needs driver 560 or newer.
   - Prefer good reliability and a fast download speed.
5. Click **Rent**. Wait until the instance is *Running*, then copy its **SSH command**, which contains the IP and port.

## 2. Connect with port forwarding

Run this in PowerShell on your laptop. Replace `PORT` and `IP` with the values from Vast.

```powershell
ssh -p PORT root@IP -L 8000:localhost:8000 -L 8888:localhost:8888 -L 8554:localhost:8554
```

Keep this window open. The `-L` options make the remote services appear on your laptop:

- `http://localhost:8000` is the dashboard.
- `http://localhost:8888/processed/` is the annotated video.
- `rtsp://localhost:8554/traffic` opens the raw stream in VLC. In VLC, set *Tools → Preferences → Input/Codecs → RTP over RTSP (TCP)*.

## 3. Install and run (inside the SSH session)

```bash
nvidia-smi                                   # GPU visible?
cd /root
git clone https://github.com/<your-user>/vehicle-analytics.git
cd vehicle-analytics
cp .env.example .env
bash scripts/setup.sh                        # ~10 min

# colour model (~10 min) - see color_classifier/README.md
cd color_classifier && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# upload kaggle.json first:  scp -P PORT kaggle.json root@IP:/root/
mkdir -p ~/.kaggle && mv /root/kaggle.json ~/.kaggle/ && chmod 600 ~/.kaggle/kaggle.json
kaggle datasets download -d landrykezebou/vcor-vehicle-color-recognition-dataset -p data/vcor --unzip
python train.py --data-dir data/vcor --epochs 6
deactivate && cd ..

bash scripts/run_all.sh
tmux attach -t vehicle
```

Then open `http://localhost:8000` on your laptop.

## 4. Save your work before you stop the instance

Copy the trained model and the generated detector config back to your laptop, then commit them to GitHub. Run this in PowerShell, from inside your local repo folder:

```powershell
scp -P PORT root@IP:/root/vehicle-analytics/models/color/vehicle_color_resnet18.onnx models/color/
scp -P PORT root@IP:/root/vehicle-analytics/models/color/labels_color.txt models/color/
```

**Stop or destroy the instance when you finish.** Billing continues while it runs.
