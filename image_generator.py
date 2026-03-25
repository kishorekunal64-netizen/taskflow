"""
image_generator.py — Multi-provider image generation for RAGAI Video Factory.

Provider chain (auto-fallback):
  1. Leonardo AI      — best quality, 150 tokens/day free
  2. Pollinations.ai  — no key, no limit, FLUX-based, free
  3. HuggingFace      — FLUX.1-schnell via Inference API, free HF token
  4. OpenVINO local   — FLUX/SD offline on Intel Arc GPU, no internet needed

When Leonardo returns a rate-limit / token-exhausted error, the generator
permanently switches to the next provider for the rest of the session so
generation continues uninterrupted.
"""

from __future__ import annotations

import logging
import time
import urllib.parse
from enum import Enum, auto
from pathlib import Path
from typing import List, Optional

import requests
from PIL import Image

from models import (
    IMAGE_RESOLUTIONS,
    ImageGenerationError,
    Scene,
    VideoFormat,
    VisualStyle,
)
from style_detector import STYLE_PROMPT_MODIFIERS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_LEONARDO_BASE   = "https://cloud.leonardo.ai/api/rest/v1"
_LEONARDO_MODEL  = "b24e16ff-06e3-43eb-8d33-4416c2d75876"  # Leonardo Kino XL
_POLL_INTERVAL   = 3
_POLL_TIMEOUT    = 240
_MAX_RETRIES     = 2      # per-provider retries before switching
_RETRY_DELAY     = 4.0

# Pollinations — no auth, FLUX under the hood
_POLLINATIONS_URL = "https://image.pollinations.ai/prompt/{prompt}"
_POLLINATIONS_TIMEOUT = 90   # can be slow under load

# HuggingFace Inference API — FLUX.1-schnell (Apache 2.0, free tier)
_HF_API_URL      = "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell"
_HF_TIMEOUT      = 120

# OpenVINO local — FLUX/SD on Intel Arc GPU (offline, no API key needed)
# Model: OmniGen or SD 1.5 via optimum-intel; falls back gracefully if not installed
_OV_MODEL_ID     = "OpenVINO/LCM_Dreamshaper_v7-int8-ov"   # fast, ~15s on Arc 140V
_OV_FALLBACK_ID  = "hf-internal-testing/tiny-stable-diffusion-pipe"  # CI-safe tiny model

# HTTP status codes / error strings that mean "quota exhausted" on Leonardo
_LEONARDO_QUOTA_CODES   = {429, 402}
_LEONARDO_QUOTA_STRINGS = [
    "insufficient credits",
    "token limit",
    "rate limit",
    "quota",
    "out of credits",
    "daily limit",
]


# ---------------------------------------------------------------------------
# Provider enum
# ---------------------------------------------------------------------------

class _Provider(Enum):
    LEONARDO     = auto()
    POLLINATIONS = auto()
    HUGGINGFACE  = auto()
    OPENVINO     = auto()   # local Intel Arc GPU inference


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------

def _retry(fn, max_attempts: int = _MAX_RETRIES, base_delay: float = _RETRY_DELAY):
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < max_attempts - 1:
                delay = base_delay * (2 ** attempt)
                logger.warning("Attempt %d/%d failed: %s — retrying in %.0fs",
                               attempt + 1, max_attempts, exc, delay)
                time.sleep(delay)
    raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ImageGenerator
# ---------------------------------------------------------------------------

class ImageGenerator:
    """
    Generates one image per scene with automatic provider fallback.

    Provider order: Leonardo AI → Pollinations.ai → HuggingFace → OpenVINO (local)
    Once a provider is exhausted/failing it is skipped for the rest of the session.
    """

    def __init__(
        self,
        api_key: str,
        work_dir: Path,
        hf_token: Optional[str] = None,
    ) -> None:
        self._leonardo_key = api_key
        self._hf_token = hf_token
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)

        # Active provider — degrades down the chain automatically
        self._provider = _Provider.LEONARDO
        self._provider_log: List[str] = []   # human-readable switch log
        self._ov_pipe = None                 # lazy-loaded OpenVINO pipeline

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_one(self, scene: Scene, style: VisualStyle, fmt: VideoFormat) -> Path:
        """Generate one image for scene using the active provider chain."""
        prompt = self._build_prompt(scene, style)
        width, height = IMAGE_RESOLUTIONS[fmt]
        dest = self.work_dir / f"scene_{scene.number:03d}.png"

        for provider in list(_Provider):
            # Skip providers we've already fallen past
            if provider.value < self._provider.value:
                continue

            try:
                result = _retry(
                    lambda p=provider: self._generate_with(p, prompt, width, height, dest),
                    max_attempts=_MAX_RETRIES,
                    base_delay=_RETRY_DELAY,
                )
                logger.info("Scene %d image ready via %s: %s",
                            int(scene.number), provider.name, result)
                return result

            except _QuotaExhausted as exc:
                msg = f"[BGM] {provider.name} quota exhausted: {exc} — switching to next provider"
                logger.warning(msg)
                self._provider_log.append(msg)
                self._advance_provider(provider)
                continue

            except Exception as exc:  # noqa: BLE001
                logger.error("Scene %d: %s failed (%s) — trying next provider",
                             int(scene.number), provider.name, exc)
                self._advance_provider(provider)
                continue

        # All providers failed — use placeholder
        logger.error("All providers failed for scene %d. Using placeholder.", int(scene.number))
        return self._placeholder_image(scene, fmt)

    def generate_all(
        self, scenes: List[Scene], style: VisualStyle, fmt: VideoFormat
    ) -> List[Scene]:
        for scene in scenes:
            scene.image_path = self.generate_one(scene, style, fmt)
        return scenes

    @property
    def active_provider(self) -> str:
        return self._provider.name

    # ------------------------------------------------------------------
    # Provider dispatch
    # ------------------------------------------------------------------

    def _generate_with(
        self, provider: _Provider, prompt: str, width: int, height: int, dest: Path
    ) -> Path:
        if provider == _Provider.LEONARDO:
            return self._leonardo(prompt, width, height, dest)
        elif provider == _Provider.POLLINATIONS:
            return self._pollinations(prompt, width, height, dest)
        elif provider == _Provider.HUGGINGFACE:
            return self._huggingface(prompt, dest)
        else:
            return self._openvino(prompt, width, height, dest)

    def _advance_provider(self, failed: _Provider) -> None:
        """Move active provider one step down the chain."""
        order = list(_Provider)
        idx = order.index(failed)
        if idx + 1 < len(order):
            next_p = order[idx + 1]
            if self._provider.value <= failed.value:
                self._provider = next_p
                logger.info("Image provider switched to: %s", next_p.name)

    # ------------------------------------------------------------------
    # Leonardo AI
    # ------------------------------------------------------------------

    def _leonardo(self, prompt: str, width: int, height: int, dest: Path) -> Path:
        gen_id = self._leonardo_submit(prompt, width, height)
        url = self._leonardo_poll(gen_id)
        return self._download(url, dest)

    def _leonardo_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._leonardo_key}",
            "Content-Type": "application/json",
        }

    def _leonardo_submit(self, prompt: str, width: int, height: int) -> str:
        payload = {
            "modelId": _LEONARDO_MODEL,
            "prompt": prompt,
            "width": int(width),
            "height": int(height),
            "num_images": 1,
            "guidance_scale": 7,
            "num_inference_steps": 30,
        }
        resp = requests.post(
            f"{_LEONARDO_BASE}/generations",
            json=payload,
            headers=self._leonardo_headers(),
            timeout=30,
        )
        self._check_leonardo_quota(resp)
        if not resp.ok:
            raise ImageGenerationError(
                f"Leonardo POST /generations {resp.status_code}: {resp.text}"
            )
        gen_id = resp.json().get("sdGenerationJob", {}).get("generationId", "")
        if not gen_id:
            raise ImageGenerationError(f"Leonardo missing generationId: {resp.text[:300]}")
        logger.info("Leonardo job submitted — id=%s", gen_id)
        return gen_id

    def _leonardo_poll(self, gen_id: str) -> str:
        url = f"{_LEONARDO_BASE}/generations/{gen_id}"
        deadline = time.monotonic() + _POLL_TIMEOUT
        while time.monotonic() < deadline:
            resp = requests.get(url, headers=self._leonardo_headers(), timeout=30)
            self._check_leonardo_quota(resp)
            if not resp.ok:
                raise ImageGenerationError(f"Leonardo poll {resp.status_code}: {resp.text}")
            gen = resp.json().get("generations_by_pk", {})
            status = gen.get("status", "")
            if status == "COMPLETE":
                images = gen.get("generated_images", [])
                if not images:
                    raise ImageGenerationError(f"Generation {gen_id} COMPLETE but no images.")
                return images[0]["url"]
            if status in ("FAILED", "CANCELLED"):
                raise ImageGenerationError(f"Leonardo job {gen_id} ended: {status}")
            logger.debug("Generation %s status=%s", gen_id, status)
            time.sleep(_POLL_INTERVAL)
        raise ImageGenerationError(f"Leonardo generation {gen_id} timed out.")

    @staticmethod
    def _check_leonardo_quota(resp: requests.Response) -> None:
        """Raise _QuotaExhausted if the response signals token exhaustion."""
        if resp.status_code in _LEONARDO_QUOTA_CODES:
            raise _QuotaExhausted(f"HTTP {resp.status_code}: {resp.text[:200]}")
        if not resp.ok:
            body_lower = resp.text.lower()
            if any(s in body_lower for s in _LEONARDO_QUOTA_STRINGS):
                raise _QuotaExhausted(f"HTTP {resp.status_code}: {resp.text[:200]}")

    # ------------------------------------------------------------------
    # Pollinations.ai  (no key required)
    # ------------------------------------------------------------------

    def _pollinations(self, prompt: str, width: int, height: int, dest: Path) -> Path:
        encoded = urllib.parse.quote(prompt)
        url = (
            f"https://image.pollinations.ai/prompt/{encoded}"
            f"?width={width}&height={height}&nologo=true&enhance=true"
        )
        logger.info("Pollinations request: w=%d h=%d", width, height)
        resp = requests.get(url, timeout=_POLLINATIONS_TIMEOUT)
        if not resp.ok:
            raise ImageGenerationError(
                f"Pollinations returned {resp.status_code}: {resp.text[:200]}"
            )
        if len(resp.content) < 1024:
            raise ImageGenerationError("Pollinations returned suspiciously small response")
        dest.write_bytes(resp.content)
        logger.info("Pollinations image → %s (%d bytes)", dest, len(resp.content))
        return dest

    # ------------------------------------------------------------------
    # HuggingFace FLUX.1-schnell
    # ------------------------------------------------------------------

    def _huggingface(self, prompt: str, dest: Path) -> Path:
        headers: dict = {"Content-Type": "application/json"}
        if self._hf_token:
            headers["Authorization"] = f"Bearer {self._hf_token}"

        payload = {"inputs": prompt}
        logger.info("HuggingFace FLUX.1-schnell request")
        resp = requests.post(_HF_API_URL, json=payload, headers=headers, timeout=_HF_TIMEOUT)

        # HF returns 503 when model is loading — treat as retriable, not quota
        if resp.status_code == 503:
            estimated = resp.json().get("estimated_time", 20)
            logger.info("HF model loading, waiting %.0fs...", estimated)
            time.sleep(min(float(estimated), 30))
            raise ImageGenerationError("HuggingFace model still loading — will retry")

        if resp.status_code == 429:
            raise _QuotaExhausted(f"HuggingFace rate limit: {resp.text[:200]}")

        if not resp.ok:
            raise ImageGenerationError(
                f"HuggingFace returned {resp.status_code}: {resp.text[:200]}"
            )

        # Response is raw image bytes
        if len(resp.content) < 1024:
            raise ImageGenerationError("HuggingFace returned suspiciously small response")

        dest.write_bytes(resp.content)
        logger.info("HuggingFace image → %s (%d bytes)", dest, len(resp.content))
        return dest

    # ------------------------------------------------------------------
    # OpenVINO local inference (Intel Arc GPU — offline, no API key)
    # ------------------------------------------------------------------

    def _openvino(self, prompt: str, width: int, height: int, dest: Path) -> Path:
        """Run local image generation via OpenVINO on Intel Arc GPU.

        Requires: pip install optimum[openvino] diffusers
        Model is downloaded once and cached in ~/.cache/huggingface/
        Falls back gracefully if optimum-intel is not installed.
        """
        try:
            from optimum.intel import OVStableDiffusionPipeline  # type: ignore
        except ImportError:
            raise ImageGenerationError(
                "OpenVINO provider requires: pip install optimum[openvino] diffusers\n"
                "Install it to enable offline local image generation on Intel Arc GPU."
            )

        if self._ov_pipe is None:
            logger.info("Loading OpenVINO model %s (first run — downloads ~1.5GB)…", _OV_MODEL_ID)
            try:
                self._ov_pipe = OVStableDiffusionPipeline.from_pretrained(
                    _OV_MODEL_ID,
                    device="GPU",          # Intel Arc via OpenVINO
                    compile=False,
                )
                self._ov_pipe.reshape(
                    batch_size=1,
                    height=min(height, 512),
                    width=min(width, 512),
                    num_images_per_prompt=1,
                )
                self._ov_pipe.compile()
                logger.info("OpenVINO pipeline ready on GPU")
            except Exception as exc:
                # GPU init failed — try CPU fallback
                logger.warning("OpenVINO GPU init failed (%s) — retrying on CPU", exc)
                self._ov_pipe = OVStableDiffusionPipeline.from_pretrained(
                    _OV_MODEL_ID, device="CPU", compile=False,
                )
                self._ov_pipe.reshape(
                    batch_size=1,
                    height=min(height, 512),
                    width=min(width, 512),
                    num_images_per_prompt=1,
                )
                self._ov_pipe.compile()
                logger.info("OpenVINO pipeline ready on CPU")

        logger.info("OpenVINO generating: %s", prompt[:80])
        result = self._ov_pipe(
            prompt=prompt,
            num_inference_steps=8,    # LCM needs only 4–8 steps
            guidance_scale=1.0,       # LCM: guidance_scale=1 for best results
            height=min(height, 512),
            width=min(width, 512),
        )
        img = result.images[0]
        # Upscale to requested resolution with LANCZOS
        if img.width != width or img.height != height:
            img = img.resize((width, height), Image.LANCZOS)
        img.save(str(dest), format="PNG")
        logger.info("OpenVINO image → %s (%dx%d)", dest, width, height)
        return dest

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _build_prompt(self, scene: Scene, style: VisualStyle) -> str:
        modifier = STYLE_PROMPT_MODIFIERS.get(style, "")
        return f"{scene.image_prompt} {modifier}".strip()

    def _download(self, url: str, dest: Path) -> Path:
        resp = requests.get(url, timeout=60)
        if not resp.ok:
            raise ImageGenerationError(f"Image download failed: {resp.status_code}")
        dest.write_bytes(resp.content)
        logger.info("Downloaded → %s (%d bytes)", dest, len(resp.content))
        return dest

    def _placeholder_image(self, scene: Scene, fmt: VideoFormat) -> Path:
        width, height = IMAGE_RESOLUTIONS[fmt]
        img = Image.new("RGB", (width, height), color=(30, 30, 50))
        dest = self.work_dir / f"scene_{scene.number:03d}_placeholder.png"
        img.save(dest, format="PNG")
        logger.warning("Using placeholder image for scene %d", int(scene.number))
        return dest


# ---------------------------------------------------------------------------
# Internal sentinel exception
# ---------------------------------------------------------------------------

class _QuotaExhausted(Exception):
    """Raised when a provider signals its quota/rate-limit is exhausted."""
