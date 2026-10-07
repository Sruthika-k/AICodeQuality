"""FastAPI backend application for AICodeQuality."""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from backend.app.loop_controller import LoopController, LoopResult
from backend.app.report_generator import generate_markdown_report

# Configure secure logging
log_dir = Path(__file__).parent.parent / "logs"
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / 'aicodequality.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# Initialize FastAPI application
app = FastAPI(
    title="AICodeQuality API",
    description="Automated Python code enhancement loop with Gemini Flash, Bandit, and Pylint.",
    version="1.0.0",
)

# Configure CORS for Vite dev server (default port 5173) and local development
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:5175",
    "http://127.0.0.1:5175",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "*",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request and Response schemas
class CodePromptRequest(BaseModel):
    prompt: str = Field(..., description="Prompt describing the Python program or code to generate/repair", max_length=10000)
    initial_code: Optional[str] = Field(None, description="Optional existing Python code to repair", max_length=50000)
    iteration_cap: int = Field(3, ge=1, le=5, description="Maximum number of refinement iterations (1-5)")
    pylint_threshold: float = Field(8.0, ge=0.0, le=10.0, description="Pylint score threshold for convergence (0-10)")

    @field_validator('prompt')
    @classmethod
    def validate_prompt_size(cls, v: str) -> str:
        if len(v.encode('utf-8')) > 10000:
            raise ValueError("Prompt exceeds 10KB limit")
        return v

    @field_validator('initial_code')
    @classmethod
    def validate_code_size(cls, v: Optional[str]) -> Optional[str]:
        if v and len(v.encode('utf-8')) > 50000:
            raise ValueError("Initial code exceeds 50KB limit")
        return v


class CodeReviewRequest(BaseModel):
    code: str = Field(..., description="Python code to review and improve", max_length=50000)
    iteration_cap: int = Field(3, ge=1, le=5, description="Maximum number of refinement iterations (1-5)")
    pylint_threshold: float = Field(8.0, ge=0.0, le=10.0, description="Pylint score threshold for convergence (0-10)")

    @field_validator('code')
    @classmethod
    def validate_code_size(cls, v: str) -> str:
        if len(v.encode('utf-8')) > 50000:
            raise ValueError("Code exceeds 50KB limit")
        return v


class IssueModel(BaseModel):
    tool: str
    severity: str
    line: int
    message: str
    rule_id: str


class IterationModel(BaseModel):
    iteration: int
    code: str
    pylint_score: float
    bandit_high_medium_count: int
    bandit_low_count: int
    pylint_issue_count: int
    total_issues_count: int
    has_syntax_error: bool
    threshold_met: bool
    feedback_text: Optional[str] = None
    diff: Optional[str] = None
    diff_lines: List[Dict[str, Any]] = Field(default_factory=list)
    issues: List[IssueModel] = []


class BeforeAfterSummaryModel(BaseModel):
    initial_iteration: int
    final_iteration: int
    total_iterations: int
    converged: bool
    initial_pylint_score: float
    final_pylint_score: float
    pylint_score_delta: float
    initial_total_issues: int
    final_total_issues: int
    issues_eliminated: int
    table: str
    initial_avg_complexity: Optional[float] = None
    final_avg_complexity: Optional[float] = None
    initial_max_complexity: Optional[int] = None
    final_max_complexity: Optional[int] = None
    initial_maintainability_index: Optional[float] = None
    final_maintainability_index: Optional[float] = None


class CodeOptimizationResponse(BaseModel):
    prompt: str
    final_code: str
    converged: bool
    total_iterations: int
    final_pylint_score: float
    final_bandit_high_medium: int
    status: str
    iterations: List[IterationModel]
    metrics_summary: Optional[BeforeAfterSummaryModel] = None
    iteration_cap: int
    pylint_threshold: float


@app.get("/health", tags=["Health"])
@app.get("/api/health", tags=["Health"])
def health_check() -> Dict[str, str]:
    """Health-check endpoint returning service status."""
    return {"status": "healthy", "service": "AICodeQuality API"}


@app.post("/api/optimize", response_model=CodeOptimizationResponse, tags=["Optimization"])
@app.post("/optimize", response_model=CodeOptimizationResponse, tags=["Optimization"])
def optimize_code(request: CodePromptRequest) -> CodeOptimizationResponse:
    """Accepts a prompt and optional code, runs the optimization loop, and returns results.

    Returns the final code, the iterations, and the metrics summary.
    """
    if not request.prompt or not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt must not be empty.")

    logger.info(f"Optimize request received (mode: generate, cap: {request.iteration_cap})")

    try:
        controller = LoopController(
            iteration_cap=request.iteration_cap,
            pylint_threshold=request.pylint_threshold,
            max_bandit_high_med=0
        )
        result: LoopResult = controller.run(
            prompt=request.prompt.strip(),
            initial_code=request.initial_code.strip() if request.initial_code else None,
        )
        logger.info(f"Optimize completed (converged: {result.converged}, iterations: {result.total_iterations})")

        # Convert iterations to response format
        formatted_iterations = []
        for it in result.iterations:
            formatted_iterations.append(
                IterationModel(
                    iteration=it.iteration,
                    code=it.code,
                    pylint_score=it.pylint_score,
                    bandit_high_medium_count=it.bandit_high_medium_count,
                    bandit_low_count=it.bandit_low_count,
                    pylint_issue_count=it.pylint_issue_count,
                    total_issues_count=it.total_issues_count,
                    has_syntax_error=it.has_syntax_error,
                    threshold_met=it.threshold_met,
                    feedback_text=it.feedback_text,
                    diff=it.diff,
                    diff_lines=it.diff_lines,
                    issues=[
                        IssueModel(
                            tool=issue.tool,
                            severity=issue.severity,
                            line=issue.line,
                            message=issue.message,
                            rule_id=issue.rule_id,
                        )
                        for issue in it.extracted_issues
                    ],
                )
            )

        # Convert before/after summary
        summary_model = None
        if result.before_after_summary:
            s = result.before_after_summary
            summary_model = BeforeAfterSummaryModel(
                initial_iteration=s.initial_iteration,
                final_iteration=s.final_iteration,
                total_iterations=s.total_iterations,
                converged=s.converged,
                initial_pylint_score=s.initial_pylint_score,
                final_pylint_score=s.final_pylint_score,
                pylint_score_delta=s.pylint_score_delta,
                initial_total_issues=s.initial_total_issues,
                final_total_issues=s.final_total_issues,
                issues_eliminated=s.issues_eliminated,
                table=s.table,
                initial_avg_complexity=s.initial_avg_complexity,
                final_avg_complexity=s.final_avg_complexity,
                initial_max_complexity=s.initial_max_complexity,
                final_max_complexity=s.final_max_complexity,
                initial_maintainability_index=s.initial_maintainability_index,
                final_maintainability_index=s.final_maintainability_index,
            )

        return CodeOptimizationResponse(
            prompt=result.prompt,
            final_code=result.final_code,
            converged=result.converged,
            total_iterations=result.total_iterations,
            final_pylint_score=result.final_pylint_score,
            final_bandit_high_medium=result.final_bandit_high_medium,
            status=result.status,
            iterations=formatted_iterations,
            metrics_summary=summary_model,
            iteration_cap=request.iteration_cap,
            pylint_threshold=request.pylint_threshold,
        )

    except ValueError as exc:
        logger.error(f"Validation error in optimize: {str(exc)}")
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(exc)}") from exc
    except RuntimeError as exc:
        logger.error(f"Runtime error in optimize: {str(exc)}")
        raise HTTPException(status_code=503, detail=f"Service error: {str(exc)}") from exc
    except Exception as exc:
        logger.error(f"Unexpected error in optimize: {type(exc).__name__}: {str(exc)}")
        raise HTTPException(status_code=500, detail=f"Loop execution failed: {str(exc)}") from exc


@app.post("/api/review", response_model=CodeOptimizationResponse, tags=["Optimization"])
@app.post("/review", response_model=CodeOptimizationResponse, tags=["Optimization"])
def review_code(request: CodeReviewRequest) -> CodeOptimizationResponse:
    """Accepts existing Python code, analyzes it, and runs the refinement loop to fix issues.

    Skips the initial generation step and directly analyzes the provided code,
    then iteratively improves it while preserving behavior.

    Returns the final code, the iterations, and the metrics summary.
    """
    if not request.code or not request.code.strip():
        raise HTTPException(status_code=400, detail="Code must not be empty.")

    code_size = len(request.code.encode('utf-8'))
    logger.info(f"Review request received (mode: review, cap: {request.iteration_cap}, code size: {code_size} bytes)")

    try:
        controller = LoopController(
            iteration_cap=request.iteration_cap,
            pylint_threshold=request.pylint_threshold,
            max_bandit_high_med=0
        )
        result: LoopResult = controller.run(
            prompt="Review and improve the provided Python code while preserving its behavior.",
            initial_code=request.code.strip(),
        )
        logger.info(f"Review completed (converged: {result.converged}, iterations: {result.total_iterations})")

        # Convert iterations to response format
        formatted_iterations = []
        for it in result.iterations:
            formatted_iterations.append(
                IterationModel(
                    iteration=it.iteration,
                    code=it.code,
                    pylint_score=it.pylint_score,
                    bandit_high_medium_count=it.bandit_high_medium_count,
                    bandit_low_count=it.bandit_low_count,
                    pylint_issue_count=it.pylint_issue_count,
                    total_issues_count=it.total_issues_count,
                    has_syntax_error=it.has_syntax_error,
                    threshold_met=it.threshold_met,
                    feedback_text=it.feedback_text,
                    diff=it.diff,
                    diff_lines=it.diff_lines,
                    issues=[
                        IssueModel(
                            tool=issue.tool,
                            severity=issue.severity,
                            line=issue.line,
                            message=issue.message,
                            rule_id=issue.rule_id,
                        )
                        for issue in it.extracted_issues
                    ],
                )
            )

        # Convert before/after summary
        summary_model = None
        if result.before_after_summary:
            s = result.before_after_summary
            summary_model = BeforeAfterSummaryModel(
                initial_iteration=s.initial_iteration,
                final_iteration=s.final_iteration,
                total_iterations=s.total_iterations,
                converged=s.converged,
                initial_pylint_score=s.initial_pylint_score,
                final_pylint_score=s.final_pylint_score,
                pylint_score_delta=s.pylint_score_delta,
                initial_total_issues=s.initial_total_issues,
                final_total_issues=s.final_total_issues,
                issues_eliminated=s.issues_eliminated,
                table=s.table,
                initial_avg_complexity=s.initial_avg_complexity,
                final_avg_complexity=s.final_avg_complexity,
                initial_max_complexity=s.initial_max_complexity,
                final_max_complexity=s.final_max_complexity,
                initial_maintainability_index=s.initial_maintainability_index,
                final_maintainability_index=s.final_maintainability_index,
            )

        return CodeOptimizationResponse(
            prompt=result.prompt,
            final_code=result.final_code,
            converged=result.converged,
            total_iterations=result.total_iterations,
            final_pylint_score=result.final_pylint_score,
            final_bandit_high_medium=result.final_bandit_high_medium,
            status=result.status,
            iterations=formatted_iterations,
            metrics_summary=summary_model,
            iteration_cap=request.iteration_cap,
            pylint_threshold=request.pylint_threshold,
        )

    except ValueError as exc:
        logger.error(f"Validation error in review: {str(exc)}")
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(exc)}") from exc
    except RuntimeError as exc:
        logger.error(f"Runtime error in review: {str(exc)}")
        raise HTTPException(status_code=503, detail=f"Service error: {str(exc)}") from exc
    except Exception as exc:
        logger.error(f"Unexpected error in review: {type(exc).__name__}: {str(exc)}")
        raise HTTPException(status_code=500, detail=f"Loop execution failed: {str(exc)}") from exc


class ReportRequest(BaseModel):
    prompt: str
    initial_code: Optional[str] = None
    iterations: List[Dict[str, Any]]
    final_code: str
    metrics_summary: Optional[Dict[str, Any]] = None
    converged: bool
    total_iterations: int
    iteration_cap: int
    pylint_threshold: float
    mode: str = "generate"


@app.post("/api/report", tags=["Report"])
@app.post("/report", tags=["Report"])
def download_report(request: ReportRequest) -> Response:
    """Generate and download a Markdown report for an optimization run.

    Returns a downloadable .md file containing the complete run history.
    """
    try:
        markdown_content = generate_markdown_report(
            prompt=request.prompt,
            initial_code=request.initial_code,
            iterations=request.iterations,
            final_code=request.final_code,
            metrics_summary=request.metrics_summary,
            converged=request.converged,
            total_iterations=request.total_iterations,
            iteration_cap=request.iteration_cap,
            pylint_threshold=request.pylint_threshold,
            mode=request.mode,
        )

        filename = f"aicodequality_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

        return Response(
            content=markdown_content,
            media_type="text/markdown",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
            },
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Report generation failed: {str(exc)}") from exc
