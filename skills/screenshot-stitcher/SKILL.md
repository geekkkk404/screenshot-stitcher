---
name: screenshot-stitcher
description: Use when the task is to stitch multiple vertically scrolling iPhone screenshots into a single long image with the local screenshot-stitcher CLI. Best for same-device inputs in the intended order, and especially useful when the user needs help choosing crop or edge-margin flags.
---

# Screenshot Stitcher

Use this skill when the user wants to combine multiple iPhone screenshots into one long image.

The CLI contract is intentionally small, so the same workflow ports cleanly into Claude, Codex, OpenClaw, Hermes, and similar agent wrappers that can invoke shell commands.

## Workflow

1. Confirm the inputs are vertically scrolling screenshots from the same device width.
2. Preserve the user's input order. Do not reorder by timestamp.
3. Prefer the installed CLI:

```bash
screenshot-stitcher img1.png img2.png img3.png -o output.png
```

4. If the CLI is not installed in the environment, run the repo entrypoint instead:

```bash
python3 main.py img1.png img2.png img3.png -o output.png
```

## Useful Flags

- `--no-navbar`: page has no navigation bar
- `--no-tabbar`: page has no bottom tab bar
- `--top-crop N`: manual top crop override
- `--bottom-crop N`: manual bottom crop override
- `--x-margin N`: ignore more left/right edge pixels during matching
- `--template-height N`: adjust the template height used for overlap matching
- `--threshold V`: raise or lower overlap acceptance sensitivity

## Heuristics

- Start with the default command before tuning flags.
- If the page has sticky bars, floating controls, or scroll indicators, try a larger `--x-margin`.
- If the top chrome changes during scrolling, try `--no-navbar` or a custom `--top-crop`.
- If overlap confidence is low but the output is visually correct, report that explicitly instead of pretending the score is strong.
- If the input screenshots are out of order or have different widths, stop and surface that clearly.
