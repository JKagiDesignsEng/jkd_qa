import json, re, base64, math
from datetime import datetime
from pathlib import Path
from subprocess import run
from typing import Dict, Any, List

import numpy as np
from PIL import Image
from skimage.metrics import structural_similarity as ssim

# -------- Paths (mounted in docker-compose) ----------
DATA_DIR = Path("/data")
URLS_DEFAULT = DATA_DIR / "urls.txt"
OUT_DEFAULT = DATA_DIR / "screenshots"
TRAINER_DIR_DEFAULT = DATA_DIR / "trainer_screenshots"
DIFF_DIR_DEFAULT = DATA_DIR / "diff"
REPORTS_DIR_DEFAULT = DATA_DIR / "reports"

# -------- I/O & utilities ----------------------------


def ensure_dirs(*paths: Path):
    for p in paths:
        p.mkdir(parents=True, exist_ok=True)


def sanitize_filename(url: str, max_len: int = 150) -> str:
    safe = re.sub(r"^https?://", "", url)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", safe)
    safe = re.sub(r"_+", "_", safe).strip("_")
    if len(safe) > max_len:
        safe = safe[:max_len]
    if not safe:
        safe = "screenshot"
    return safe + ".png"


def list_urls(path: Path) -> List[str]:
    if not path.exists():
        return []
    raw = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()]
    return [
        ln if re.match(r"^https?://", ln, re.I) else f"https://{ln}"
        for ln in raw
        if ln and not ln.startswith("#")
    ]


def png_to_array(p: Path) -> np.ndarray:
    with Image.open(p) as im:
        return np.array(im.convert("RGB"))


def compute_metrics(imgA: np.ndarray, imgB: np.ndarray) -> Dict[str, Any]:
    # align sizes (resize current to trainer’s dimensions)
    h, w = imgA.shape[:2]
    if imgB.shape[:2] != (h, w):
        imgB = np.array(Image.fromarray(imgB).resize((w, h), Image.LANCZOS))
    grayA = np.dot(imgA[..., :3], [0.299, 0.587, 0.114]).astype(np.float32)
    grayB = np.dot(imgB[..., :3], [0.299, 0.587, 0.114]).astype(np.float32)
    score, diff = ssim(grayA, grayB, full=True, data_range=255.0)
    mse = float(np.mean((grayA - grayB) ** 2))
    diff_norm = (1.0 - diff) * 255.0
    diff_vis = diff_norm.clip(0, 255).astype(np.uint8)
    return {"ssim": float(score), "mse": mse, "diff_vis": diff_vis}


def save_diff_image(diff_vis: np.ndarray, path: Path):
    Image.fromarray(diff_vis).save(path)


def run_script(
    urls_file: Path, out_dir: Path, timeout: int, wait: float, headful: bool
) -> Dict[str, Any]:
    ensure_dirs(out_dir)
    cmd = [
        "python",
        "/app/screenshot_urls.py",
        "--urls",
        str(urls_file),
        "--out",
        str(out_dir),
        "--timeout",
        str(timeout),
        "--wait",
        str(wait),
    ]
    if headful:
        cmd.append("--headful")
    result = run(cmd, capture_output=True, text=True)
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
    }


def write_report(report: Dict[str, Any], reports_dir: Path) -> Path:
    ensure_dirs(reports_dir)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = reports_dir / f"report-{ts}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path
