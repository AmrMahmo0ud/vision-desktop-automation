import time
import io
import base64
import json
import re
import logging
import os
from pathlib import Path

import mss
import pyautogui
import pygetwindow as gw
import requests
import win32clipboard
import anthropic
from dotenv import load_dotenv
from PIL import Image, ImageDraw

# ── Setup ──────────────────────────────────────────────────────────────────────

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")
log = logging.getLogger(__name__)

pyautogui.FAILSAFE = True

SAVE_DIR = Path.home() / "Desktop" / "tjm-project"
SAVE_DIR.mkdir(parents=True, exist_ok=True)

SCREENSHOTS_DIR = Path("screenshots")
SCREENSHOTS_DIR.mkdir(exist_ok=True)


# ── Block 1: Screenshot ────────────────────────────────────────────────────────

def take_screenshot() -> Image.Image:
    """Minimizes all windows, deselects icons, takes a clean desktop screenshot."""
    
    with mss.mss() as sct:
        raw = sct.grab(sct.monitors[1])
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

    log.info(f"Screenshot taken: {img.size}")
    return img


# ── Block 2: Screen clearing ────────────────────────────────────

def clear_screen(user_wait: float = 10.0) -> None:
    """
    Checks if any window or popup is blocking the desktop before clicking.
    
    Strategy:
    1. After Win+M, check if any windows are still visible
    2. If a normal window is visible — minimize it
    3. If a dialog/popup is visible (can't be minimized) — 
        give the user `user_wait` seconds to handle it manually,
        then auto-press Enter (the safe/default choice)
    
    This handles unexpected popups (antivirus, updates, alerts)
    without knowing what they look like in advance.
    """
    
    # These are system-level window titles we always ignore
    IGNORE_TITLES = {"", "Program Manager", "Windows Input Experience", 
                    "Microsoft Text Input Application"}

    log.info("Checking for blocking windows before clicking...")

    # Step 1: try Win+M to minimize everything
    pyautogui.hotkey("win", "m")
    time.sleep(1.0)

    # Step 2: get all currently visible windows
    all_windows = gw.getAllWindows()
    blocking = [
        w for w in all_windows
        if w.visible
        and w.title not in IGNORE_TITLES
        and w.width > 100   # ignore tiny background processes
        and w.height > 100
    ]

    if not blocking:
        log.info("Screen is clear — no blocking windows found")
        return

    log.warning(f"Found {len(blocking)} potentially blocking window(s):")
    for w in blocking:
        log.warning(f"  '{w.title}' at ({w.left},{w.top}) size={w.width}x{w.height}")

    # Step 3: try to minimize each blocking window
    still_blocking = []
    for win in blocking:
        try:
            win.minimize()
            time.sleep(0.3)
            log.info(f"Minimized: '{win.title}'")
        except Exception:
            # Can't minimize — likely a dialog/popup that requires action
            still_blocking.append(win)
            log.warning(f"Cannot minimize '{win.title}' — likely a dialog")

    if not still_blocking:
        log.info("All blocking windows minimized successfully")
        return

    # Step 4: for dialogs that can't be minimized — give user time to act
    for dialog in still_blocking:
        log.warning(f"Mandatory dialog detected: '{dialog.title}'")
        log.warning(f"You have {user_wait:.0f} seconds to handle it manually...")

        # Countdown — check every second if the dialog was dismissed
        for remaining in range(int(user_wait), 0, -1):
            time.sleep(1.0)
            # Check if dialog is still there
            still_open = any(
                w.title == dialog.title
                for w in gw.getAllWindows()
                if w.visible
            )
            if not still_open:
                log.info(f"Dialog '{dialog.title}' was handled by user")
                break
            log.warning(f"  {remaining}s remaining...")
        else:
            # User didn't act — auto-press Enter (default/safe choice)
            log.warning(f"Timeout! Auto-pressing Enter on '{dialog.title}'")
            try:
                dialog.activate()
                time.sleep(0.3)
                pyautogui.press("enter")
                time.sleep(0.5)
                log.info("Auto-dismissed dialog with Enter")
            except Exception as e:
                log.error(f"Could not auto-dismiss dialog: {e}")

    # Step 5: final Win+M to make sure desktop is clean before clicking
    pyautogui.hotkey("win", "m")
    time.sleep(1.0)
    pyautogui.moveTo(960, 540, duration=0.2)
    time.sleep(0.2)
    pyautogui.click()
    time.sleep(0.3)
    log.info("Screen cleared — safe to click")
    
    
# ── Block 3: Claude icon detection ────────────────────────────────────────────

def find_icon(img: Image.Image, target: str = "Notepad") -> tuple[int, int]:
    """
    Sends full-resolution screenshot to Claude and asks where the target icon is.
    Claude visually identifies the icon and returns its center coordinates.
    Works for any icon — just change the `target` string.
    """
    # Save what Claude sees for debugging
    img.save(SCREENSHOTS_DIR / "debug_last_screenshot.png")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()

    # prompt fully uses the `target` variable — no hardcoded "Notepad" references
    prompt = f"""You are a precise desktop automation assistant analyzing a Windows desktop screenshot at full resolution ({img.width}x{img.height} pixels).

YOUR TASK:
Find the "{target}" application shortcut icon on the desktop.

SEARCH INSTRUCTIONS:
- Look for a small square icon graphic that represents {target}
- It will have the label "{target}" written directly below the icon graphic
- The icon sits directly on the desktop wallpaper (NOT inside any window or folder)
- There may be a small shortcut arrow in the bottom-left corner of the icon

WHAT TO IGNORE COMPLETELY:
- The taskbar at the very bottom of the screen
- Any open application windows
- The Start button
- System tray icons (bottom-right)
- Any icon whose label text does NOT say exactly "{target}"

COORDINATE INSTRUCTIONS:
- Return the CENTER pixel of the icon GRAPHIC itself
- Do NOT return the center of the text label below it
- Coordinates must match the full {img.width}x{img.height} resolution of this image

OUTPUT FORMAT:
Return ONLY a raw JSON object — no markdown, no code fences, no explanation, nothing else.

If found with high confidence:
{{"found": true, "x": 123, "y": 456, "confidence": "high"}}

If found but unsure:
{{"found": true, "x": 123, "y": 456, "confidence": "low"}}

If not found at all:
{{"found": false}}"""

    try:
        response = client.messages.create(
            
            model="claude-opus-4-7",
            max_tokens=100,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": b64,
                        }
                    },
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
            }]
        )
    except anthropic.APIError as e:
        raise ValueError(f"Claude API error: {e}")

    raw = response.content[0].text.strip()
    log.info(f"Claude raw response: {raw}")

    # Strip markdown code fences if Claude accidentally adds them
    cleaned = re.sub(r"```json|```", "", raw).strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        raise ValueError(f"Claude returned invalid JSON: {raw!r}")

    if not data.get("found"):
        raise ValueError(
            f"Claude could not find '{target}' — check screenshots/debug_last_screenshot.png"
        )

    confidence = data.get("confidence", "unknown")
    x = int(data["x"])
    y = int(data["y"])
    log.info(f"Icon '{target}' found at ({x}, {y}) — confidence: {confidence}")
    return x, y


def find_icon_with_retry(
    target: str = "Notepad",
    save_screenshot_as: str = "",
    max_attempts: int = 3,
) -> tuple[int, int]:
    """Tries up to `max_attempts` times with 1 second between failures."""
    last_error = None

    for attempt in range(1, max_attempts + 1):
        try:
            clear_screen(user_wait=10.0)
            img = take_screenshot()
            x, y = find_icon(img, target)

            if save_screenshot_as:
                annotated = img.copy()
                draw = ImageDraw.Draw(annotated)
                draw.ellipse([x - 30, y - 30, x + 30, y + 30], outline="red", width=3)
                draw.text((x + 35, y - 10), f"({x},{y})", fill="red")
                out_path = SCREENSHOTS_DIR / f"{save_screenshot_as}.png"
                annotated.save(out_path)
                log.info(f"Saved annotated screenshot: {out_path}")
                

            return x, y

        except Exception as e:
            last_error = e
            log.warning(f"Attempt {attempt}/{max_attempts} failed: {e}")
            if attempt < max_attempts:
                time.sleep(1)

    raise RuntimeError(
        f"Could not find '{target}' after {max_attempts} attempts. "
        f"Last error: {last_error}"
    )

# ── Block 4: Mouse and keyboard ────────────────────────────────────────────────

def launch_application(x: int, y: int) -> None:
    clear_screen(user_wait=10.0)
    log.info(f"Double-clicking icon at ({x}, {y})")
    pyautogui.moveTo(x, y, duration=0.4)
    pyautogui.doubleClick()


def wait_for_application(target,timeout: float = 8.0) -> None:
    """Polls until a window with 'Notepad' in the title appears."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if gw.getWindowsWithTitle(target):
            log.info("app is open!")
            time.sleep(0.5)
            return
        time.sleep(0.3)
    raise RuntimeError("app did not open within the timeout period.")


def paste_text(text: str) -> None:
    """Puts text on the clipboard then pastes it into the active window."""
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
    win32clipboard.CloseClipboard()
    time.sleep(0.1)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.2)


def save_as(filename: str) -> None:
    """Opens Save As dialog and saves the file to SAVE_DIR."""
    full_path = str(SAVE_DIR / filename)
    log.info(f"Saving as: {full_path}")
    pyautogui.hotkey("ctrl", "s")
    time.sleep(1.5)
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.1)
    pyautogui.typewrite(full_path, interval=0.03)
    pyautogui.press("enter")
    time.sleep(0.8)
    # Dismiss "Confirm Save As" dialog if it appears
    for win in gw.getWindowsWithTitle("Confirm Save As"):
        pyautogui.press("y")
        time.sleep(0.3)


def close_application(target) -> None:
    """Closes all open windows, dismissing any unsaved-changes prompt."""
    for win in gw.getWindowsWithTitle(target):
        win.close()
    time.sleep(0.5)
    # If Notepad asks to save unsaved changes, dismiss with Tab + Enter (press Don't Save)
    for win in gw.getWindowsWithTitle(target):
        win.activate()
        pyautogui.press("n")
    time.sleep(0.3)
    log.info("app closed")


# ── Block 5: API ───────────────────────────────────────────────────────────────

def fetch_posts() -> list[dict]:
    """Fetches 10 posts from JSONPlaceholder. Falls back to offline data on failure."""
    try:
        r = requests.get("https://jsonplaceholder.typicode.com/posts", timeout=10)
        r.raise_for_status()
        posts = r.json()[:10]
        log.info(f"Fetched {len(posts)} posts from API")
        return posts
    except Exception as e:
        log.warning(f"API unavailable ({e}) — using offline fallback")
        return [
            {"id": i, "title": f"Post {i}", "body": f"Content for post {i}."}
            for i in range(1, 11)
        ]


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    log.info("=== Starting automation ===")
    posts = fetch_posts()
    # target is now simply for example "Notepad" — consistent with the prompt description - change it based on what you want to detect
    app = 'Notepad'
    # Map iteration numbers to screenshot names (1st, 5th, 10th posts get saved)
    screenshot_map = {1: "screenshot_1", 5: "screenshot_2", 10: "screenshot_3"}

    for i, post in enumerate(posts, start=1):
        log.info(f"\n--- Post {i}/10 (id={post['id']}) ---")
        screenshot_name = screenshot_map.get(i, "")

        
        x, y = find_icon_with_retry(app, save_screenshot_as=screenshot_name)
        launch_application(x, y)
        wait_for_application(app)
        paste_text(f"Title: {post['title']}\n\n{post['body']}")
        save_as(f"post_{post['id']}.txt")
        close_application(app)
        time.sleep(0.5)

    log.info("=== All done! Files saved to Desktop/tjm-project/ ===")


if __name__ == "__main__":
    main()