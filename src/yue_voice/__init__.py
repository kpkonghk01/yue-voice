"""Cantonese paragraph synthesis with bounded ASR verification."""

from .cli import main
from .models import GenerationControls, SynthesisRequest, VoiceMode

__all__ = ["GenerationControls", "SynthesisRequest", "VoiceMode", "main"]
