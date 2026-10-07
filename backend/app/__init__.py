"""AICodeQuality Backend Application Package."""

from backend.app.feedback_generator import FeedbackGenerator
from backend.app.issue_extractor import IssueExtractor
from backend.app.llm_interface import LLMInterface, generate
from backend.app.loop_controller import IterationData, LoopController, LoopResult
from backend.app.metrics_tracker import BeforeAfterSummary, IterationMetrics, MetricsTracker
from backend.app.static_analyzer import (
    StaticAnalysisIssue,
    StaticAnalysisResult,
    StaticAnalyzer,
    analyze_code,
)

__all__ = [
    "BeforeAfterSummary",
    "FeedbackGenerator",
    "IssueExtractor",
    "IterationData",
    "IterationMetrics",
    "LLMInterface",
    "LoopController",
    "LoopResult",
    "MetricsTracker",
    "StaticAnalysisIssue",
    "StaticAnalysisResult",
    "StaticAnalyzer",
    "analyze_code",
    "generate",
]
