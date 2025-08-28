from fastapi import APIRouter, Query
from pathlib import Path
from helpers import (
    DATA_DIR,
    URLS_DEFAULT,
    OUT_DEFAULT,
    TRAINER_DIR_DEFAULT,
    DIFF_DIR_DEFAULT,
    REPORTS_DIR_DEFAULT,
    ensure_dirs,
    run_script,
    list_urls,
    sanitize_filename,
    png_to_array,
    compute_metrics,
    save_diff_image,
    write_report,
)

router = APIRouter()


@router.get("/trainer")
def create_trainer_images(
    urls_file: str | None = Query(
        None, description="Path to .txt inside /data (defaults to /data/urls.txt)"
    ),
    out_dir: str | None = Query(
        None,
        description="Trainer output dir inside /data (defaults to /data/trainer_screenshots)",
    ),
    timeout: int = 20,
    wait: float = 2.0,
    headful: bool = False,
):
    urls_path = DATA_DIR / urls_file if urls_file else URLS_DEFAULT
    trainer_dir = DATA_DIR / out_dir if out_dir else TRAINER_DIR_DEFAULT
    ensure_dirs(trainer_dir)

    if not urls_path.exists():
        return {"ok": False, "error": f"URLs file not found: {urls_path}"}

    # clear trainer dir (PNGs) for a fresh baseline
    for f in trainer_dir.glob("*.png"):
        try:
            f.unlink()
        except Exception:
            pass

    result = run_script(urls_path, trainer_dir, timeout, wait, headful)
    return {"ok": result["ok"], "details": result, "trainer_dir": str(trainer_dir)}


@router.get("/run")
def run_and_compare(
    urls_file: str | None = Query(
        None, description="Path to .txt inside /data (defaults to /data/urls.txt)"
    ),
    out_dir: str | None = Query(
        None, description="Screenshots dir inside /data (defaults to /data/screenshots)"
    ),
    trainer_dir: str | None = Query(
        None,
        description="Trainer dir inside /data (defaults to /data/trainer_screenshots)",
    ),
    diff_dir: str | None = Query(
        None, description="Diff output dir inside /data (defaults to /data/diff)"
    ),
    reports_dir: str | None = Query(
        None, description="Reports dir inside /data (defaults to /data/reports)"
    ),
    timeout: int = 20,
    wait: float = 2.0,
    headful: bool = False,
    ssim_threshold: float = 0.92,
):
    urls_path = DATA_DIR / urls_file if urls_file else URLS_DEFAULT
    shots_dir = DATA_DIR / out_dir if out_dir else OUT_DEFAULT
    base_dir = DATA_DIR / trainer_dir if trainer_dir else TRAINER_DIR_DEFAULT
    diffs_dir = DATA_DIR / diff_dir if diff_dir else DIFF_DIR_DEFAULT
    reps_dir = DATA_DIR / reports_dir if reports_dir else REPORTS_DIR_DEFAULT

    for p in (shots_dir, base_dir, diffs_dir, reps_dir):
        ensure_dirs(p)

    if not urls_path.exists():
        return {"ok": False, "error": f"URLs file not found: {urls_path}"}

    # clean screenshots dir (PNGs) before run
    for f in shots_dir.glob("*.png"):
        try:
            f.unlink()
        except Exception:
            pass

    exec_details = run_script(urls_path, shots_dir, timeout, wait, headful)

    urls = list_urls(urls_path)
    per_item = []
    totals = {"ok": 0, "warn": 0, "fail": 0, "no_trainer": 0}

    for u in urls:
        name = sanitize_filename(u)
        cur_path = shots_dir / name
        base_path = base_dir / name

        if not base_path.exists():
            status = "no_trainer"
            per_item.append(
                {
                    "url": u,
                    "status": status,
                    "reason": f"Trainer image not found: {base_path.name}",
                    "current": str(cur_path) if cur_path.exists() else None,
                    "trainer": str(base_path),
                }
            )
            totals[status] += 1
            continue

        if not cur_path.exists():
            status = "fail"
            per_item.append(
                {
                    "url": u,
                    "status": status,
                    "reason": f"Current screenshot not found: {cur_path.name}",
                    "current": str(cur_path),
                    "trainer": str(base_path),
                }
            )
            totals[status] += 1
            continue

        try:
            imgA = png_to_array(base_path)  # trainer
            imgB = png_to_array(cur_path)  # current
            metrics = compute_metrics(imgA, imgB)

            s = metrics["ssim"]
            m = metrics["mse"]
            status = "ok" if s >= ssim_threshold else "fail"

            diff_path = None
            if status != "ok":
                diff_path = diffs_dir / f"diff_{name}"
                save_diff_image(metrics["diff_vis"], diff_path)

            per_item.append(
                {
                    "url": u,
                    "status": status,
                    "metrics": {"ssim": s, "mse": m},
                    "current": str(cur_path),
                    "trainer": str(base_path),
                    "diff": str(diff_path) if diff_path else None,
                }
            )
            totals[status] += 1

        except Exception as e:
            status = "fail"
            per_item.append(
                {
                    "url": u,
                    "status": status,
                    "reason": f"Comparison error: {e}",
                    "current": str(cur_path),
                    "trainer": str(base_path),
                }
            )
            totals[status] += 1

    report = {
        "urls_file": str(urls_path),
        "screenshots_dir": str(shots_dir),
        "trainer_dir": str(base_dir),
        "diff_dir": str(diffs_dir),
        "ssim_threshold": ssim_threshold,
        "execution": exec_details,
        "totals": totals,
        "items": per_item,
    }
    report_path = write_report(report, reps_dir)
    report["report_path"] = str(report_path)
    return report
