"""PawPal+ care advisor: retrieval-augmented suggestions, answers and plan reviews."""

from .advisor import Advice, Answer, CareAdvisor, CareGap
from .guardrails import Suggestion
from .llm import ClaudeClient, make_llm
from .logging_setup import setup_logging

__all__ = ["Advice", "Answer", "CareAdvisor", "CareGap", "ClaudeClient", "Suggestion", "make_llm", "setup_logging"]
