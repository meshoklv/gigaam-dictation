# Third-party notices

This repository contains only the project's own source code (MIT, see `LICENSE`).
It does **not** bundle any third-party code or model weights: everything below is
downloaded by `install.sh` from its original source. Licenses were checked against
the upstream repositories / PyPI / Hugging Face metadata on 2026-10-22.

| Component | Used for | License |
|---|---|---|
| [GigaAM](https://github.com/salute-developers/GigaAM) (GigaChat Team, Sber) — code and the `v3_e2e_ctc` model | speech recognition model | MIT (Copyright (c) 2024 GigaChat Team) |
| [`istupakov/gigaam-v3-onnx`](https://huggingface.co/istupakov/gigaam-v3-onnx) | ONNX / int8 conversion of GigaAM v3, downloaded at install time | MIT (per Hugging Face model card) |
| [onnx-asr](https://github.com/istupakov/onnx-asr) | main inference backend | MIT (Copyright (c) 2025 Ilya Stupakov) |
| onnxruntime | ONNX execution | MIT |
| huggingface-hub | model download | Apache-2.0 |
| **PyQt6** | GUI | **GPL-3.0-only** (or commercial from Riverbank) |
| pynput | global hotkey | LGPL-3.0 |
| sounddevice | microphone capture | MIT |
| soundfile | wav I/O | BSD-3-Clause |
| numpy | arrays | BSD-3-Clause (and others) |
| pyobjc (Cocoa, Quartz, ApplicationServices) | macOS APIs | MIT |
| PyTorch, torchaudio, `gigaam` package (optional, `--with-torch`) | fallback backend | BSD-3-Clause / Apache-2.0 mix; `gigaam` MIT |

## Note on PyQt6 (GPL-3.0)

The application's own source is MIT and is distributed without PyQt6. However, a
combined work that imports PyQt6 is subject to PyQt6's terms: if you redistribute a
*bundled* build (e.g. a ready-made `.app` containing PyQt6), that build must comply
with GPL-3.0 (or you need a commercial PyQt license). Installing from source with
`install.sh` (PyQt6 fetched from PyPI on your own machine) is not affected.

## Note on the model

GigaAM is published under MIT, including the pretrained models. Training data is
not distributed. Check the upstream repository for the current terms before
commercial redistribution of the weights.

The pip / PyPI / Hugging Face license fields are the authors' own declarations and
were not independently audited.
