# screenshot_urls.py
import argparse
import base64
import math
import re
import sys
import time
from pathlib import Path
from typing import List

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException, WebDriverException


def read_urls(path: Path) -> List[str]:
    lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()]
    # keep only non-empty and valid-looking URLs
    return [ln for ln in lines if ln and not ln.startswith("#")]


def sanitize_filename(url: str, max_len: int = 150) -> str:
    """
    Create a filesystem-safe filename from a URL.
    """
    safe = re.sub(r"^https?://", "", url)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", safe)
    # collapse repeats
    safe = re.sub(r"_+", "_", safe).strip("_")
    # limit length but keep extension
    if len(safe) > max_len:
        safe = safe[:max_len]
    if not safe:
        safe = "screenshot"
    return safe + ".png"


def build_driver(window_width: int = 1920, window_height: int = 1080, headless: bool = True) -> webdriver.Chrome:
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--hide-scrollbars")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument(f"--window-size={window_width},{window_height}")
    driver = webdriver.Chrome(options=chrome_options)
    # Enable Page domain for CDP screenshots
    driver.execute_cdp_cmd("Page.enable", {})
    return driver


def wait_for_load(driver: webdriver.Chrome, timeout: int):
    # Wait for document ready
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )


def gentle_scroll(driver: webdriver.Chrome, pause: float = 0.1, max_steps: int = 100):
    """
    Scroll down in increments to trigger lazy-loaded images/content.
    """
    last_height = 0
    steps = 0
    while steps < max_steps:
        height = driver.execute_script("return document.body.scrollHeight || document.documentElement.scrollHeight;")
        driver.execute_script("window.scrollTo(0, arguments[0]);", min(last_height + 800, height))
        time.sleep(pause)
        new_height = driver.execute_script("return window.pageYOffset;")
        steps += 1
        if new_height == last_height:
            # Try jumping to bottom once at the end
            driver.execute_script("window.scrollTo(0, arguments[0]);", height)
            time.sleep(pause)
            break
        last_height = new_height


def capture_fullpage_png_chrome(driver: webdriver.Chrome) -> bytes:
    """
    Uses Chrome DevTools to capture a true full-page PNG, beyond the viewport.
    """
    # Get the full content size
    metrics = driver.execute_cdp_cmd("Page.getLayoutMetrics", {})
    content_size = metrics.get("contentSize", {})
    width = math.ceil(content_size.get("width", 1920))
    height = math.ceil(content_size.get("height", 1080))

    # Avoid pathological sizes (some sites have infinite scroll)
    width = min(width, 10000)
    height = min(height, 200000)

    # Override device metrics to fit the whole page
    driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {
        "mobile": False,
        "width": width,
        "height": height,
        "deviceScaleFactor": 1,
        "screenWidth": width,
        "screenHeight": height,
        "scale": 1,
    })

    # Take screenshot
    result = driver.execute_cdp_cmd("Page.captureScreenshot", {
        "format": "png",
        "fromSurface": True,
        "captureBeyondViewport": True
    })
    data = result.get("data", "")
    return base64.b64decode(data)


def screenshot_url(driver: webdriver.Chrome, url: str, out_dir: Path, timeout: int, extra_wait: float):
    print(f"[INFO] Loading: {url}")
    driver.get(url)

    try:
        wait_for_load(driver, timeout)
    except TimeoutException:
        print(f"[WARN] Timed out waiting for readyState on: {url}")

    # Optional: wait a bit for async content
    if extra_wait > 0:
        time.sleep(extra_wait)

    # Trigger lazy-loaded content
    gentle_scroll(driver, pause=0.15)

    # Capture
    try:
        png = capture_fullpage_png_chrome(driver)
        name = sanitize_filename(url)
        path = out_dir / name
        path.write_bytes(png)
        print(f"[OK] Saved: {path}")
    except WebDriverException as e:
        print(f"[ERROR] Failed to capture {url}: {e}")


def main():
    parser = argparse.ArgumentParser(description="Take full-page screenshots of URLs listed in a .txt file.")
    parser.add_argument("--urls", required=True, help="Path to .txt file of URLs (one per line).")
    parser.add_argument("--out", default="screenshots", help="Output directory for PNGs.")
    parser.add_argument("--timeout", type=int, default=20, help="Seconds to wait for initial load.")
    parser.add_argument("--wait", type=float, default=2.0, help="Extra seconds to wait after load (for JS).")
    parser.add_argument("--headful", action="store_true", help="Run with a visible browser window (not headless).")
    args = parser.parse_args()

    url_file = Path(args.urls)
    if not url_file.exists():
        print(f"[FATAL] URL file not found: {url_file}")
        sys.exit(1)

    urls = read_urls(url_file)
    if not urls:
        print("[FATAL] No URLs found in file.")
        sys.exit(1)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 🧹 Clear old screenshots before starting
    for f in out_dir.glob("*.png"):
        try:
            f.unlink()
        except Exception as e:
            print(f"[WARN] Could not delete {f}: {e}")

    driver = build_driver(headless=not args.headful)

    try:
        for url in urls:
            # ensure scheme
            if not re.match(r"^https?://", url, re.I):
                url = "https://" + url
            screenshot_url(driver, url, out_dir, args.timeout, args.wait)
    finally:
        driver.quit()



if __name__ == "__main__":
    main()
