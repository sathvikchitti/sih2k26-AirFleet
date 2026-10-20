"""Assemble the files for the Hugging Face Space into one folder.

Run from the repository root:   python deploy/huggingface/prepare_space.py
Output folder (default):        hf-space/
"""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "hf-space"

FILES = {
    HERE / "Dockerfile": "Dockerfile",
    HERE / "README.md": "README.md",
    ROOT / "backend" / "requirements.txt": "requirements.txt",
    ROOT / "backend" / "models" / "cmapss_fd001_rf_v1.joblib": "models/cmapss_fd001_rf_v1.joblib",
    ROOT / "backend" / "models" / "cmapss_fd001_rf_v1_metrics.json": "models/cmapss_fd001_rf_v1_metrics.json",
    ROOT / "CMAPSSData" / "train_FD001.txt": "CMAPSSData/train_FD001.txt",
    ROOT / "CMAPSSData" / "test_FD001.txt": "CMAPSSData/test_FD001.txt",
    ROOT / "CMAPSSData" / "RUL_FD001.txt": "CMAPSSData/RUL_FD001.txt",
    ROOT / "CMAPSSData" / "readme.txt": "CMAPSSData/readme.txt",
}

missing = [str(src) for src in FILES if not src.is_file()]
if missing:
    sys.exit("Missing required files:\n  " + "\n  ".join(missing))

if OUT.exists():
    shutil.rmtree(OUT)
for src, rel in FILES.items():
    dest = OUT / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)  # binary-safe copy; NASA files keep their bytes

shutil.copytree(
    ROOT / "backend" / "app", OUT / "app",
    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
)

size = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file())
print(f"Space folder ready: {OUT}  ({size / 1e6:.1f} MB)")
print("Upload it with:  hf upload <your-username>/<space-name> hf-space . --repo-type=space")
