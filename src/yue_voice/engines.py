"""Lazy OmniVoice and SenseVoice adapters with explicit model-cache ownership."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any, Callable, TypeVar

from .models import SynthesisRequest, VoiceMode


DEFAULT_CACHE_ROOT = Path("~/.cache/yue-voice/models")
T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class ModelCachePaths:
    """Locations owned by this process for downloaded model artifacts."""

    root: Path
    huggingface: Path
    modelscope: Path


@dataclass(slots=True)
class EngineBundle:
    """Loaded inference engines and the device evidence to report with results."""

    synthesizer: "OmniVoiceSynthesizer"
    verifier: "SenseVoiceVerifier"
    metadata: dict[str, Any]


def configure_model_cache(cache_root: Path | str = DEFAULT_CACHE_ROOT) -> ModelCachePaths:
    """Use a dedicated cache root without placing model weights in the repository."""
    root = Path(cache_root).expanduser().resolve()
    huggingface = root / "huggingface"
    modelscope = root / "modelscope"
    huggingface.mkdir(parents=True, exist_ok=True)
    modelscope.mkdir(parents=True, exist_ok=True)

    # These variables are read by the model loaders during lazy import/loading.
    os.environ["HF_HOME"] = str(huggingface)
    os.environ["MODELSCOPE_CACHE"] = str(modelscope)
    return ModelCachePaths(root=root, huggingface=huggingface, modelscope=modelscope)


def select_device(requested_device: str | None = None) -> str:
    """Prefer Apple MPS locally; CUDA is only used when the caller asks for it."""
    if requested_device:
        return requested_device

    import torch

    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def seed_everything(seed: int) -> None:
    """Seed Python and Torch before one candidate generation attempt."""
    import random

    import torch

    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


class OmniVoiceSynthesizer:
    """The actual OmniVoice loading and one-candidate synthesis boundary."""

    def __init__(self, model_id: str, device: str) -> None:
        import torch
        from omnivoice import OmniVoice

        self.model_id = model_id
        self.device = device
        dtype = torch.float16 if device == "mps" or device.startswith("cuda") else torch.float32
        self._model = OmniVoice.from_pretrained(model_id, device_map=device, dtype=dtype)

    def synthesize(self, request: SynthesisRequest) -> tuple[Any, int]:
        """Generate one waveform. WAV serialization remains owned by the service."""
        from omnivoice.models.omnivoice import OmniVoiceGenerationConfig

        controls = request.controls
        generation_config = OmniVoiceGenerationConfig(
            num_step=controls.num_step,
            guidance_scale=controls.guidance_scale,
            t_shift=controls.t_shift,
            layer_penalty_factor=controls.layer_penalty_factor,
            position_temperature=controls.position_temperature,
            class_temperature=controls.class_temperature,
            denoise=controls.denoise,
            postprocess_output=controls.postprocess_output,
        )
        kwargs: dict[str, Any] = {
            "text": request.text,
            "language": "yue",
            "duration": controls.duration,
            "speed": controls.speed,
            "generation_config": generation_config,
        }
        if request.voice_mode is VoiceMode.CLONE:
            kwargs["ref_audio"] = str(request.reference_audio)
            kwargs["ref_text"] = request.reference_text
        elif request.voice_mode is VoiceMode.DESIGN:
            kwargs["instruct"] = request.instruct

        audios = self._model.generate(**kwargs)
        if not audios:
            raise RuntimeError("OmniVoice returned no audio")
        return audios[0], int(getattr(self._model, "sampling_rate", 24000))


class SenseVoiceVerifier:
    """The yue-only SenseVoiceSmall transcription boundary."""

    def __init__(self, model_id: str, device: str) -> None:
        from funasr import AutoModel

        self.model_id = model_id
        self.device = device
        self._model = AutoModel(model=model_id, device=device, disable_update=True)

    def transcribe(self, audio_path: Path) -> str:
        """Transcribe a candidate WAV and remove optional SenseVoice rich tags."""
        result = self._model.generate(
            input=str(audio_path),
            cache={},
            language="yue",
            use_itn=True,
        )
        if not result or not isinstance(result[0], dict) or "text" not in result[0]:
            raise RuntimeError("SenseVoice returned no transcription text")

        raw_text = str(result[0]["text"])
        try:
            from funasr.utils.postprocess_utils import rich_transcription_postprocess

            return str(rich_transcription_postprocess(raw_text))
        except ImportError:
            return raw_text


def _load_with_mps_fallback(
    factory: Callable[[str], T], device: str, requested_device: str | None
) -> tuple[T, str]:
    try:
        return factory(device), device
    except Exception:
        if device == "mps" and requested_device is None:
            return factory("cpu"), "cpu"
        raise


def load_engines(
    *,
    cache_root: Path | str = DEFAULT_CACHE_ROOT,
    requested_device: str | None = None,
    tts_model_id: str = "k2-fsa/OmniVoice",
    asr_model_id: str = "iic/SenseVoiceSmall",
) -> EngineBundle:
    """Load the model pair once, using CPU only when automatic MPS loading fails."""
    cache_paths = configure_model_cache(cache_root)
    preferred_device = select_device(requested_device)
    synthesizer, tts_device = _load_with_mps_fallback(
        lambda device: OmniVoiceSynthesizer(tts_model_id, device),
        preferred_device,
        requested_device,
    )
    verifier, asr_device = _load_with_mps_fallback(
        lambda device: SenseVoiceVerifier(asr_model_id, device),
        preferred_device,
        requested_device,
    )
    return EngineBundle(
        synthesizer=synthesizer,
        verifier=verifier,
        metadata={
            "tts_model": tts_model_id,
            "asr_model": asr_model_id,
            "tts_device": tts_device,
            "asr_device": asr_device,
            "model_cache_root": str(cache_paths.root),
            "huggingface_cache": str(cache_paths.huggingface),
            "modelscope_cache": str(cache_paths.modelscope),
        },
    )
