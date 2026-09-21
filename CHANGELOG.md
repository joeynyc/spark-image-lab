# Changelog

## Unreleased

- Add confirmed permanent deletion for saved generations and clean up reference
  copies only after their final use.

## 0.1.0-alpha.2 - 2026-09-20

- Prepare the project for its public alpha release with private vulnerability
  reporting guidance and patched versions of vulnerable packages inherited from
  the NVIDIA base image.
- Run the real Gradio callback integration tests in CPU-only CI.
- Verify the installed model revision before inference and contain saved reference
  files even when the reference directory has been replaced by a symlink.

## 0.1.0-alpha.1 - 2026-09-20

Initial private DGX Spark-focused repository, validated first on ASUS GX10/GB10.

- Replace fixed demo rows with persistent generation history and a live-updating gallery.
- Restore prompt, references, dimensions, steps, seed, output and timing from history.
- Retain reference uploads locally and read existing prototype PNG/JSON records.
- Preserve the familiar Gradio layout; remove default footer links.
- Add revision-pinned model setup, hardware preflight, Compose, and launcher commands.
- Add CPU tests, container integration tests, CI, contribution and security guidance.
- Document measured batch performance, licensing boundaries, and public-release gates.
