"""Train custom rock weights: python scripts/train.py --data rocks.yaml"""
import argparse
import os
import shutil


def main() -> None:
    ap = argparse.ArgumentParser(description="Ultralytics training wrapper for a rock dataset")
    ap.add_argument("--data", required=True, help="dataset yaml (train/val paths, names: [rock])")
    ap.add_argument("--base", default="yolov8n.pt", help="base weights")
    ap.add_argument("--epochs", type=int, default=50)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--device", default=None)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "models", "rock.pt"))
    a = ap.parse_args()
    from ultralytics import YOLO  # lazy
    model = YOLO(a.base)
    res = model.train(data=a.data, epochs=a.epochs, imgsz=a.imgsz, batch=a.batch, device=a.device)
    best = os.path.join(str(res.save_dir), "weights", "best.pt")
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    shutil.copy(best, a.out)
    print("weights saved to", os.path.abspath(a.out))


if __name__ == "__main__":
    main()
