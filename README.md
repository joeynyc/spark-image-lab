![Spark Image Lab: local image generation and editing for NVIDIA DGX Spark, powered by Qwen-Image-2.1](docs/assets/spark-image-lab-banner.png)

# Spark Image Lab

Local image generation and editing for **NVIDIA DGX Spark**, powered by
Qwen-Image-2.1 and Gradio. Keep prompts, reference images, and results on your
machine. No cloud inference service is required.

**Public alpha: 0.1.0-alpha.2.** Validated on NVIDIA GB10 with 128 GB unified
memory. DGX Spark systems are the target platform. Gaming GPUs, Windows, macOS
inference, and multi-user hosting are not supported targets.

## What It Does

- Generate images or edit up to ten reference images with Qwen-Image-2.1.
- Set prompt, width, height, steps, and seed in a simple two-column interface.
- Download the PNG and its generation record, including runtime and memory.
- Every successful generation appears in a persistent history table and image
  gallery. Select a row or image to restore its settings and available references.
- Reuse the current result as a reference for the next edit.
- Preserve PNG alpha when the model produces transparency.

The preset demo table has been replaced by **your generation history**.
The main creation controls and bottom image gallery retain the original layout.

## Quick Start

Run on the Spark itself, locally or through NVIDIA Sync's SSH connection.
You need an ARM64 GB10 system, a working NVIDIA driver, Docker with GPU support,
and Docker Compose 2.30 or later. Allow at least **80 GiB free disk space** for
the NVIDIA container, model, build cache, and initial outputs.

```bash
git clone https://github.com/joeynyc/spark-image-lab.git
cd spark-image-lab
./spark build
./spark doctor
```

Read the [model license](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/b3179ad355be050328e483a9dfdd9e60cd62adfa/LICENSE)
before downloading. The pinned model uses the **Qwen Research License**, which
limits use to research/evaluation and requires a separate license for commercial
use. This application's MIT license does not grant additional model rights.

```bash
./spark download --accept-model-license
./spark start
./spark logs
```

Initial model loading can take several minutes. Once the server is ready,
open [Spark Image Lab](http://127.0.0.1:7862/) on the Spark. For access from
another computer, forward the loopback-only port through SSH:

```bash
ssh -N -L 7862:127.0.0.1:7862 YOUR_SPARK_SSH_ALIAS
```

Then open the same URL on that computer.

## Performance

Measured on the GX10 at 1024 x 1024, 40 steps, BF16, CFG 1, KV cache enabled.
Two timed trials per batch size after warmup; same-prompt text-to-image variations.

| Batch | Mean total time | Images/minute | Peak allocated GPU memory |
| --- | ---: | ---: | ---: |
| 1 | 52.6 s | 1.14 | 36.9 GiB |
| 2 | 101.8 s | 1.18 | 43.0 GiB |
| 4 | 201.4 s | 1.19 | 55.7 GiB |

Batch four improved throughput by only 4.4%, so the app defaults to **one active
generation** and a queue of up to eight pending requests. Loading and file writes
are excluded from these timings. Editing, different prompts, and higher
resolutions were not part of this batch comparison. See [benchmarks](docs/benchmarks.md).

## Data and Privacy

`model/` contains downloaded weights. `outputs/` contains PNGs, JSON generation
records, and persistent copies of reference uploads. These directories, caches,
and local settings are excluded from Git and from the Docker build context.

The server is bound to loopback at the Docker host, public Gradio sharing is off,
and Gradio/Hugging Face telemetry is disabled. Building and downloading require
internet access; inference uses the locally downloaded model. Anyone with access
to the app can see the shared history. This is a trusted, single-owner tool,
not an authenticated public service. See [security](SECURITY.md).

## Project Guide

- [Setup and operation](docs/setup.md)
- [History and generation records](docs/history.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Benchmarks and reproducibility](docs/benchmarks.md)
- [Development and contributions](CONTRIBUTING.md)
- [Release checklist and tags](docs/releases.md)
- [Changelog](CHANGELOG.md)
- [Third-party notices](NOTICE)

Application code is [MIT licensed](LICENSE). Model weights are not included.
An independent community project, not an official NVIDIA or Qwen product.
