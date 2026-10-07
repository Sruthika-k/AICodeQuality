import re

# Patch loop_controller.py
with open("backend/app/loop_controller.py", "r") as f:
    lc_content = f.read()

lc_content = lc_content.replace(
    "def run(self, prompt: str, initial_code: Optional[str] = None, run_id: Optional[str] = None) -> LoopResult:",
    "def run(self, prompt: str, initial_code: Optional[str] = None, run_id: Optional[str] = None, job_status_callback=None, job_cancel_check=None) -> LoopResult:"
)

lc_content = lc_content.replace(
    "for i in range(1, self.iteration_cap + 1):",
    """for i in range(1, self.iteration_cap + 1):
            if job_cancel_check and job_cancel_check():
                raise RuntimeError("Job cancelled")
            if job_status_callback:
                job_status_callback({"stage": f"Iteration {i}", "current_iteration": i})"""
)

lc_content = lc_content.replace(
    "print(\"Generating initial code from prompt...\")",
    """print("Generating initial code from prompt...")
                if job_status_callback:
                    job_status_callback({"stage": "Waiting for Gemini..."})"""
)

lc_content = lc_content.replace(
    "analysis_start = time.time()",
    """if job_status_callback:
                job_status_callback({"stage": "Running static analysis..."})
            analysis_start = time.time()"""
)

lc_content = lc_content.replace(
    "print(\"Constructing feedback prompt for LLM repair...\")",
    """print("Constructing feedback prompt for LLM repair...")
            if job_status_callback:
                job_status_callback({"stage": "Waiting for Gemini..."})"""
)

with open("backend/app/loop_controller.py", "w") as f:
    f.write(lc_content)

# Patch main.py
with open("backend/app/main.py", "r") as f:
    main_content = f.read()

# Add Background Job imports and state
jobs_code = """
import asyncio
from concurrent.futures import ThreadPoolExecutor

# In-memory store for jobs
jobs_store = {}
executor = ThreadPoolExecutor(max_workers=5)

class BackgroundRunRequest(BaseModel):
    mode: str = Field("generate", description="'generate' or 'review'")
    prompt: Optional[str] = None
    code: Optional[str] = None
    iteration_cap: int = Field(3, ge=1, le=5)
    pylint_threshold: float = Field(8.0, ge=0.0, le=10.0)

class RunStatusResponse(BaseModel):
    id: str
    status: str
    stage: Optional[str] = None
    current_iteration: int = 0
    events: List[Dict[str, Any]] = []
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None

def run_job_in_thread(job_id: str, request: BackgroundRunRequest):
    job = jobs_store[job_id]
    job["status"] = "running"
    
    def status_callback(update_dict):
        for k, v in update_dict.items():
            job[k] = v
        # Also log to events
        job["events"].append({"time": datetime.now().isoformat(), "update": update_dict})
        
    def cancel_check():
        return job.get("cancelled", False)

    try:
        controller = LoopController(
            iteration_cap=request.iteration_cap,
            pylint_threshold=request.pylint_threshold,
            max_bandit_high_med=0
        )
        
        prompt = request.prompt
        initial_code = None
        if request.mode == "review":
            prompt = "Review and improve the provided Python code while preserving its behavior."
            initial_code = request.code.strip() if request.code else None
        else:
            initial_code = request.code.strip() if request.code else None
            
        result = controller.run(
            prompt=prompt.strip() if prompt else "",
            initial_code=initial_code,
            run_id=job_id,
            job_status_callback=status_callback,
            job_cancel_check=cancel_check
        )
        
        # Convert iterations
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
                ).model_dump()
            )

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
            ).model_dump()

        res = {
            "prompt": result.prompt,
            "final_code": result.final_code,
            "converged": result.converged,
            "total_iterations": result.total_iterations,
            "final_pylint_score": result.final_pylint_score,
            "final_bandit_high_medium": result.final_bandit_high_medium,
            "status": result.status,
            "iterations": formatted_iterations,
            "metrics_summary": summary_model,
            "iteration_cap": request.iteration_cap,
            "pylint_threshold": request.pylint_threshold,
        }
        
        job["status"] = "done"
        job["result"] = res
        job["stage"] = "Done"

    except QuotaExceeded as exc:
        job["status"] = "failed"
        job["error"] = {"code": "quota_exhausted", "message": str(exc), "retry_after": exc.retry_after}
        backend_status_info["quota_exhausted"] = True
    except TimeoutError as exc:
        job["status"] = "failed"
        job["error"] = {"code": "timeout", "message": str(exc)}
    except Exception as exc:
        if str(exc) == "Job cancelled":
            job["status"] = "cancelled"
            job["stage"] = "Cancelled"
        else:
            job["status"] = "failed"
            job["error"] = {"code": "internal_error", "message": str(exc)}

@app.post("/api/runs", tags=["Jobs"])
def create_run(request: BackgroundRunRequest) -> Dict[str, str]:
    if request.mode == "generate" and not request.prompt:
        raise HTTPException(status_code=400, detail="Prompt must not be empty for generate mode.")
    if request.mode == "review" and not request.code:
        raise HTTPException(status_code=400, detail="Code must not be empty for review mode.")
        
    run_id = uuid.uuid4().hex[:8]
    jobs_store[run_id] = {
        "id": run_id,
        "status": "queued",
        "stage": "Queued",
        "current_iteration": 0,
        "events": [],
        "result": None,
        "error": None,
        "cancelled": False
    }
    
    executor.submit(run_job_in_thread, run_id, request)
    return {"run_id": run_id}

@app.get("/api/runs/{run_id}", response_model=RunStatusResponse, tags=["Jobs"])
def get_run_status(run_id: str) -> RunStatusResponse:
    if run_id not in jobs_store:
        raise HTTPException(status_code=404, detail="Run not found")
    return RunStatusResponse(**jobs_store[run_id])

@app.post("/api/runs/{run_id}/cancel", tags=["Jobs"])
def cancel_run(run_id: str) -> Dict[str, str]:
    if run_id not in jobs_store:
        raise HTTPException(status_code=404, detail="Run not found")
    jobs_store[run_id]["cancelled"] = True
    return {"status": "cancelling"}
"""

if "executor = ThreadPoolExecutor" not in main_content:
    main_content = main_content.replace(
        "class CodeOptimizationResponse(BaseModel):",
        jobs_code + "\nclass CodeOptimizationResponse(BaseModel):"
    )
    with open("backend/app/main.py", "w") as f:
        f.write(main_content)
