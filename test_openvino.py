"""
test_openvino.py — Standalone end-to-end test for the OpenVINO image provider.

Forces the ImageGenerator to skip Leonardo/Pollinations/HuggingFace and go
straight to OpenVINO, so you can verify offline local generation works on
your Intel Arc 140V without running the full pipeline.

Usage:
    venv\\Scripts\\activate
    python test_openvino.py

Output:
    tmp/openvino_test/scene_001.png  — generated image (512x512 → upscaled to 1344x768)
    Prints timing and file size.

Requirements:
    pip install "optimum[openvino]" diffusers accelerate
"""

from __future__ import annotations

import sys
import time
from pathlib import Path


def main() -> None:
    print("\n🔍  OpenVINO End-to-End Test\n" + "─" * 50)

    # 1. Check optimum-intel is installed
    try:
        from optimum.intel import OVStableDiffusionPipeline  # noqa: F401
        print("✅  optimum[openvino] installed")
    except ImportError:
        print('❌  optimum[openvino] not installed.')
        print('    Run: pip install "optimum[openvino]" diffusers accelerate')
        sys.exit(1)

    # 2. Import ImageGenerator and force provider to OPENVINO
    try:
        from image_generator import ImageGenerator, _Provider
        from models import VideoFormat, VisualStyle, Scene
        print("✅  ImageGenerator imported")
    except ImportError as exc:
        print(f"❌  Import error: {exc}")
        sys.exit(1)

    # 3. Build a minimal test scene
    work_dir = Path("tmp") / "openvino_test"
    work_dir.mkdir(parents=True, exist_ok=True)

    scene = Scene(
        number=1,
        narration="एक छोटे से गाँव में एक लड़की रहती थी।",
        image_prompt="A young girl standing in a lush green Indian village, golden hour, cinematic",
    )

    gen = ImageGenerator(api_key="", work_dir=work_dir, hf_token="")
    # Force straight to OpenVINO — skip all cloud providers
    gen._provider = _Provider.OPENVINO

    # 4. Run generation
    print(f"\n⏳  Generating image via OpenVINO (first run downloads ~1.5GB model)…")
    t0 = time.monotonic()
    try:
        result = gen.generate_one(scene, VisualStyle.PEACEFUL_NATURE, VideoFormat.LANDSCAPE)
        elapsed = time.monotonic() - t0
    except Exception as exc:
        print(f"\n❌  OpenVINO generation failed: {exc}")
        sys.exit(1)

    # 5. Verify output
    if not result.exists() or result.stat().st_size < 1024:
        print(f"\n❌  Output file missing or too small: {result}")
        sys.exit(1)

    size_kb = result.stat().st_size // 1024
    print(f"\n✅  Image generated in {elapsed:.1f}s")
    print(f"   Path : {result.resolve()}")
    print(f"   Size : {size_kb} KB")
    print(f"   Provider used: {gen.active_provider}")
    print("\n✅  OpenVINO end-to-end test PASSED\n")


if __name__ == "__main__":
    main()
