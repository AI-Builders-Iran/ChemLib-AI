"""Process-level env flags for paddlepaddle, applied before it's first imported.

Recent paddlepaddle/paddlex CPU builds can raise::

    NotImplementedError: (Unimplemented) ConvertPirAttribute2RuntimeAttribute
    not support [pir::ArrayAttribute<pir::DoubleAttribute>]
    (at ...onednn_instruction.cc:...)

from the new PIR executor's oneDNN path on some layout-detection /
object-detection ops (seen on Windows CPU installs). Passing
``enable_mkldnn=False`` to a PaddleOCR/PaddleX pipeline constructor is not
enough by itself — it doesn't reach every sub-model's compiled predictor.
These flags are read by paddle's C++ runtime at import time, so they must be
set *before* ``import paddle`` happens anywhere in the process — hence a
shared helper both ``src.layout.engines`` and ``src.ocr.engines`` call right
before their (lazy) ``from paddleocr import ...`` line.

Set ``PADDLE_ENABLE_MKLDNN=true`` to skip this (e.g. on an install/hardware
combination that doesn't hit the bug and you want oneDNN's speed).
"""

from __future__ import annotations

import os


def set_paddle_env_flags() -> None:
    enable_mkldnn = (os.getenv("PADDLE_ENABLE_MKLDNN") or "false").strip().lower() in ("1", "true", "yes")
    if enable_mkldnn:
        return
    os.environ.setdefault("FLAGS_use_mkldnn", "0")
    os.environ.setdefault("FLAGS_enable_pir_in_executor", "0")
