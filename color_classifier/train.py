#!/usr/bin/env python3
"""
Train + export the vehicle colour classifier used as DeepStream's secondary GIE.

Why train our own?
  DeepStream 7.x no longer ships the old car-colour sample model (it was a
  Caffe model, and TensorRT 10 dropped Caffe support). So we fine-tune an
  ImageNet ResNet18 on the public VCoR dataset (~10k car images, 15 colours)
  and export it to ONNX. nvinfer builds a TensorRT FP16 engine from it.

Output (written to ../models/color/):
  vehicle_color_resnet18.onnx   input  'input'  [N,3,224,224]  RGB, ImageNet-normalised
                                output 'probs'  [N,num_classes] softmax probabilities
  labels_color.txt              class names separated by ';' (nvinfer classifier format)

Usage:
  python3 train.py --data-dir data/vcor --epochs 6
"""
import argparse
import os
import time

import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from torchvision import datasets, models, transforms

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models", "color")
MEAN, STD = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]


def find_split(root, name):
    """Find the 'train' / 'val' folder anywhere under root (zip layouts differ)."""
    for dirpath, dirnames, _ in os.walk(root):
        if os.path.basename(dirpath) == name and dirnames:
            return dirpath
    raise FileNotFoundError(f"No '{name}' folder under {root}")


class WithSoftmax(nn.Module):
    """nvinfer's built-in classifier parser expects probabilities, so add softmax to the graph."""

    def __init__(self, net):
        super().__init__()
        self.net = net

    def forward(self, x):
        return torch.softmax(self.net(x), dim=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data/vcor")
    ap.add_argument("--epochs", type=int, default=6)
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--lr", type=float, default=3e-4)
    args = ap.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    train_dir, val_dir = find_split(args.data_dir, "train"), find_split(args.data_dir, "val")

    # NOTE: no hue / saturation jitter - that would change the very colour we predict.
    train_tf = transforms.Compose([
        transforms.RandomResizedCrop(224, scale=(0.6, 1.0)),
        transforms.RandomHorizontalFlip(),
        transforms.ColorJitter(brightness=0.25, contrast=0.2),
        transforms.ToTensor(),
        transforms.Normalize(MEAN, STD),
    ])
    val_tf = transforms.Compose([
        transforms.Resize((224, 224)),  # same as nvinfer (stretch, no aspect ratio)
        transforms.ToTensor(),
        transforms.Normalize(MEAN, STD),
    ])
    train_ds = datasets.ImageFolder(train_dir, train_tf)
    val_ds = datasets.ImageFolder(val_dir, val_tf)
    classes = train_ds.classes
    print(f"Classes ({len(classes)}): {classes}")
    print(f"Train {len(train_ds)} | Val {len(val_ds)} | device {device}")

    train_dl = DataLoader(train_ds, args.batch_size, shuffle=True, num_workers=4, pin_memory=True)
    val_dl = DataLoader(val_ds, args.batch_size, shuffle=False, num_workers=4, pin_memory=True)

    net = models.resnet18(weights=models.ResNet18_Weights.IMAGENET1K_V1)
    net.fc = nn.Linear(net.fc.in_features, len(classes))
    net = net.to(device)

    opt = torch.optim.AdamW(net.parameters(), lr=args.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)
    loss_fn = nn.CrossEntropyLoss(label_smoothing=0.05)
    scaler = torch.cuda.amp.GradScaler(enabled=device == "cuda")

    best_acc, best_state = 0.0, None
    for epoch in range(1, args.epochs + 1):
        net.train()
        t0, running = time.time(), 0.0
        for x, y in train_dl:
            x, y = x.to(device, non_blocking=True), y.to(device, non_blocking=True)
            opt.zero_grad(set_to_none=True)
            with torch.autocast(device_type=device, enabled=device == "cuda"):
                loss = loss_fn(net(x), y)
            scaler.scale(loss).backward()
            scaler.step(opt)
            scaler.update()
            running += loss.item() * x.size(0)
        sched.step()

        net.eval()
        correct = 0
        with torch.no_grad():
            for x, y in val_dl:
                pred = net(x.to(device)).argmax(1).cpu()
                correct += (pred == y).sum().item()
        acc = correct / len(val_ds)
        print(f"epoch {epoch}/{args.epochs}  loss {running / len(train_ds):.4f}  "
              f"val_acc {acc:.3f}  ({time.time() - t0:.0f}s)")
        if acc > best_acc:
            best_acc = acc
            best_state = {k: v.detach().cpu().clone() for k, v in net.state_dict().items()}

    # ---- export best model to ONNX --------------------------------------------
    net.load_state_dict(best_state)
    export = WithSoftmax(net.cpu().eval())
    os.makedirs(OUT_DIR, exist_ok=True)
    onnx_path = os.path.join(OUT_DIR, "vehicle_color_resnet18.onnx")
    torch.onnx.export(
        export, torch.randn(1, 3, 224, 224), onnx_path,
        input_names=["input"], output_names=["probs"],
        dynamic_axes={"input": {0: "batch"}, "probs": {0: "batch"}},
        opset_version=17,
    )
    with open(os.path.join(OUT_DIR, "labels_color.txt"), "w") as f:
        f.write(";".join(classes) + "\n")   # classifier labels: one line, ';' separated

    print(f"\nBest val accuracy: {best_acc:.3f}")
    print(f"Saved {os.path.normpath(onnx_path)}")
    print(f"Saved {os.path.normpath(os.path.join(OUT_DIR, 'labels_color.txt'))}")


if __name__ == "__main__":
    main()
