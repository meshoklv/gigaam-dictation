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
| PySide6 (Qt for Python) | GUI | LGPL-3.0 (Qt Company) |
| pynput | global hotkey | LGPL-3.0 |
| sounddevice | microphone capture | MIT |
| soundfile | wav I/O | BSD-3-Clause |
| numpy | arrays | BSD-3-Clause (and others) |
| pyobjc (Cocoa, Quartz, ApplicationServices) | macOS APIs | MIT |
| PyTorch, torchaudio, `gigaam` package (optional, `--with-torch`) | fallback backend | BSD-3-Clause / Apache-2.0 mix; `gigaam` MIT |

## Note on PySide6 (LGPL-3.0)

The GUI uses PySide6, which is licensed under the LGPL-3.0 (with GPL/commercial
options). It is installed from PyPI and linked dynamically, so the application's own
source stays MIT. If you redistribute a bundled build containing PySide6/Qt, keep
the LGPL notices and allow users to replace the Qt libraries.

## Note on the model

GigaAM is published under MIT, including the pretrained models. Training data is
not distributed. Check the upstream repository for the current terms before
commercial redistribution of the weights.

The pip / PyPI / Hugging Face license fields are the authors' own declarations and
were not independently audited.
