# vision-desktop-automation

Python Windows automation that uses Claude Vision API to dynamically locate desktop icons from screenshots — no hardcoded coordinates or pre-saved templates. Includes an LLM grounding.

---

## Overview

This project was built as a technical interview deliverable exploring **vision-based desktop automation** on Windows. The core challenge: locate and click a desktop icon (Notepad) regardless of its position on the screen, without knowing its coordinates in advance.

The LLM grounding approach (`AI_detection.py`) is the primary solution — it satisfies the requirement that the system must work for **any icon without pre-existing knowledge of its appearance**.

---

## How It Works

### Main Approach — LLM Grounding (`AI_detection.py`)

1. Minimizes all windows and clears the desktop
2. Takes a full-resolution screenshot with `mss`
3. Sends the screenshot to **Claude Vision API** with a prompt asking it to locate the target icon and return `(x, y)` coordinates as JSON
4. Parses the response and double-clicks the returned coordinates
5. Types post content into Notepad via clipboard, saves the file, and closes the window
6. Repeats for all 10 posts — fresh screenshot and grounding every iteration

```
Screenshot → Claude Vision API → (x, y) JSON → Double-click → Notepad opens
```

---

## Features

- **LLM-based visual grounding** — finds any icon described by name, no templates required
- **Generalized target parameter** — change `target="Notepad"` to any app name with no other code changes
- **Unknown popup handling** — `clear_screen()` detects and dismisses unexpected dialogs (antivirus alerts, UAC prompts, update notifications) without knowing their content in advance
- **Retry logic** — up to 3 detection attempts with 1s delays and a fresh screenshot each time
- **API fallback** — if JSONPlaceholder is unreachable, falls back to offline placeholder data
- **Annotated screenshots** — saves 3 detection screenshots with the found coordinates marked in red
- **File collision handling** — pre-deletes existing files before saving to avoid overwrite dialogs

---

## Project Structure

```
vision-desktop-automation/
├── AI_detection.py                  # Primary: LLM grounding via Claude Vision API
├── pyproject.toml           # uv dependency configuration
├── .env             # API key template
├── screenshots/             # Annotated detection screenshots (auto-created)
│   ├── screenshot_1.png     # Icon detected — iteration 1
│   ├── screenshot_2.png     # Icon detected — iteration 5
│   └── screenshot_3.png     # Icon detected — iteration 10
└── README.md
```

---

## Requirements

- **OS:** Windows 10 or Windows 11
- **Resolution:** 1920×1080
- **Python:** 3.12+
- **uv:** for dependency management ([install uv](https://docs.astral.sh/uv/getting-started/installation/))
- **Anthropic API key** (for `main.py` only)
- A **Notepad shortcut icon** placed on the desktop before running

---

## Setup

### 1. Clone the repo

```
git clone https://github.com/your-username/vision-desktop-automation.git
cd vision-desktop-automation
```

### 2. Install dependencies with uv

```
uv sync
```

### 3. Set up your API key

 `.env` add your Anthropic API key:


### 4. Create a shortcut on the desktop

Right-click the desktop → New → Shortcut .

### 5. Run

**LLM grounding (primary):**
```
uv run main.py
```

---

## Output

After a successful run, 10 text files are saved to `Desktop/tjm-project/`:

```
Desktop/
└── tjm-project/
    ├── post_1.txt
    ├── post_2.txt
    ├── ...
    └── post_10.txt
```

Each file contains:

```
Title: {post title}

{post body}
```

Annotated detection screenshots are saved to the `screenshots/` folder showing the icon location marked with a red circle and coordinates.

---

## Dependencies

| Package | Purpose |
|---|---|
| `anthropic` | Claude Vision API client |
| `mss` | Fast desktop screenshot capture |
| `pyautogui` | Mouse and keyboard control |
| `pygetwindow` | Window detection and management |
| `Pillow` | Image processing and annotation |
| `requests` | JSONPlaceholder API calls |
| `pywin32` | Windows clipboard access |
| `python-dotenv` | `.env` file loading |
| `botcity-framework-core` | Template matching engine (secondary approach) |

---

## Discussion: Why LLM Grounding?

The brief required a solution that works **for any icon without pre-existing knowledge of its appearance**. This rules out template matching, which requires pre-cropped images per icon and fails when the theme or icon size changes.

The LLM approach sends a raw screenshot to Claude and asks it in plain English to find the target. It works because:

- **No templates needed** — the model understands what icons look like visually
- **Adapts to any environment** — light/dark themes, icon sizes, wallpapers — no code changes
- **Truly generalized** — changing the target from `"Notepad"` to `"Chrome"` requires editing one string

The tradeoff is latency (~2–4s per call) and a small API cost (~$0.01/call). For a robustness-first requirement like this one, that's the right tradeoff.

A **hybrid strategy** would be the production choice: run template matching first (fast, free), fall back to LLM grounding only if it fails. This gives sub-second detection in the happy path and LLM robustness as a safety net.

---

## Alternative Approaches

| Approach | Generalized | Offline | Speed |
|---|---|---|---|
| Claude Vision API (this project) | ✅ | ❌ | ~3s |
| GPT-4o / Gemini Vision | ✅ | ❌ | ~3s |
| Local LLM (LLaVA / Qwen-VL) | ✅ | ✅ | ~5–10s |
| SOM Prompting (arxiv 2504.07981) | ✅ | ❌ | ~3s |
| OpenCV Template Matching | ❌ | ✅ | ~0.3s |
| EasyOCR (label text detection) | ✅ | ✅ | ~1s |
| YOLO (custom trained model) | ✅ (after training) | ✅ | ~0.1s |
| PyWinAuto / Windows UIA | ✅ | ✅ | ~0.05s |
| Win32 Shell API | ✅ | ✅ | ~0.01s |

---

## License

MIT
