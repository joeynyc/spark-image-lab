# Setup and Operation

## Supported Baseline

- ARM64 Linux with NVIDIA GB10 and 128 GB unified memory.
- Target: NVIDIA DGX Spark systems built on GB10.
- Working host NVIDIA driver and NVIDIA Container Toolkit.
- Docker Engine and Compose plugin 2.30+ (the service uses `gpus: all`).
- Internet for the container build and one-time model download.
- At least 80 GiB free initially; outputs and reference copies continue to grow.

The tested driver is 580.173.02. The base image is
`nvcr.io/nvidia/pytorch:26.08-py3`; the NVIDIA container supplies PyTorch/CUDA.
Do not replace it with an x86 container or an arbitrary PyTorch wheel.
See NVIDIA's [DGX Spark documentation](https://docs.nvidia.com/dgx/dgx-spark/)
and [Container Toolkit installation guide](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
for host setup. This project does not install or change host drivers.

## Install

Clone on the Spark, then run the commands in the main README. `./spark build`
builds a local image; it does not download model weights. `./spark doctor` checks
architecture, CUDA, GPU identity, output permissions, and model file presence.
`./spark download --accept-model-license` downloads the pinned model revision
only after explicit acceptance. Review the model's terms before using the flag.

The launcher runs containers with your host UID/GID to avoid root-owned output
files. Run it as your ordinary user, not through `sudo`, after configuring
Docker access on the host. A root-owned model/output directory from an earlier
manual install may need its ownership corrected by its administrator.

Docker builds use an allowlisted context containing only the Dockerfile and
requirements. The application source is bind-mounted at runtime. Model weights,
prompts, generated images, credentials, and `.git` never enter the build context.

## Start, Stop, and Upgrade

```bash
./spark start
./spark status
./spark logs
./spark stop
```

Start performs preflight before launching. Container health stays in `starting`
while the model loads, normally several minutes. The HTTP server starts only
after the model is loaded. Logs show the local server URL when ready.

Before upgrading, stop the service and back up `outputs/`, `.env`, and any local
code changes. Update to a reviewed commit/tag, rebuild, run tests, and restart:

```bash
./spark stop
git pull --ff-only
./spark build
./spark test
./spark start
```

Rollback: stop, check out the previously recorded tag/commit, rebuild, restart.
Never delete `outputs/` or `model/` as part of an upgrade. Version 1 history is
additive and legacy per-image JSON records remain readable without modification.

## Networking and Configuration

The Docker host publishes `127.0.0.1:7862`, not a LAN interface. Use NVIDIA Sync's
SSH alias or a normal SSH connection with local port forwarding. Do not enable
Gradio public sharing or publish the port on `0.0.0.0` for this alpha.

If port 7862 is occupied, copy `.env.example` to `.env` and choose a different
`SPARK_HTTP_PORT`, then use that port in the browser and SSH tunnel. For example,
`ssh -N -L 7863:127.0.0.1:7863 YOUR_SPARK_SSH_ALIAS` forwards port 7863.

Advanced direct-Python settings: `SPARK_MODEL_DIR`, `SPARK_OUTPUT_DIR`,
`SPARK_HOST` (defaults to loopback), and `SPARK_PORT` (7860). Compose configures
the container to listen on its internal interface and restricts access at the
host. Keep the default model revision; replacing model files manually can make
generation provenance inaccurate and is outside this release's support scope.

## Existing Prototype

The earlier manually started container named `spark-image-lab` must be stopped
before starting Compose on the same port. Do not run both model processes at
once. Keep its original source and container for rollback until validation
finishes. Copy source only, retaining the existing `model/` and `outputs/`.
