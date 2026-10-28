# Vehicle colour classifier (secondary GIE)

DeepStream 7.x no longer ships a car-colour sample model, so this folder trains one.

| Item | Value |
|---|---|
| Architecture | ResNet18 (ImageNet pre-trained), fine-tuned |
| Dataset | [VCoR – Vehicle Color Recognition](https://www.kaggle.com/datasets/landrykezebou/vcor-vehicle-color-recognition-dataset) (~10.5k images, 15 colours) |
| Input | 224×224 RGB, ImageNet mean/std normalisation |
| Output | softmax probabilities (`probs`) |
| Export | ONNX (opset 17, dynamic batch) → TensorRT FP16 engine built by `nvinfer` |
| Training time | ~5–10 min on one GPU (6 epochs) |

## Steps

Run these on the GPU machine. Use a separate virtual env so PyTorch doesn't touch the DeepStream Python packages.

```bash
cd color_classifier
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Kaggle API token: kaggle.com > Settings > API > Create New Token -> kaggle.json
mkdir -p ~/.kaggle && cp /path/to/kaggle.json ~/.kaggle/ && chmod 600 ~/.kaggle/kaggle.json
kaggle datasets download -d landrykezebou/vcor-vehicle-color-recognition-dataset -p data/vcor --unzip

python train.py --data-dir data/vcor --epochs 6
deactivate
```

Outputs:

- `models/color/vehicle_color_resnet18.onnx`
- `models/color/labels_color.txt`

`deepstream/configs/sgie_color.txt` already points at these files.

> No Kaggle token? Download the zip in your browser, upload it to the machine, and unzip it into `data/vcor`.
