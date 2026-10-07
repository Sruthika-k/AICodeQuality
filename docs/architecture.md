# AICodeQuality Architecture

## System Overview

AICodeQuality is an automated Python code quality and security enhancement system that uses an iterative refinement loop. The system analyzes code, identifies issues, and uses an LLM to fix them until quality thresholds are met or the iteration cap is reached.

## Technology Stack

- **Backend**: FastAPI (Python 3.10+)
- **Frontend**: React + Vite
- **LLM Engine**: Google Gemini Flash
- **Static Analysis Tools**: Bandit (security), Pylint (code quality), Radon (complexity & maintainability)
- **Visualization**: Recharts
- **Logging**: Python logging module

## Discrepancies with Design-Lock

The following differences exist between the code implementation and the design-lock specification:

1. **Iteration Cap**: Design-lock specifies "3 iterations maximum" but the code implements a configurable cap of 1-5 iterations (default 3) via UI and API parameters. This provides flexibility while maintaining the default behavior.

2. **ReportGenerator**: The code includes a `ReportGenerator` component (in `backend/app/report_generator.py`) for generating Markdown reports, which is not mentioned in the design-lock. This is an additional feature for documentation purposes.

3. **File Upload**: The code supports file upload for review mode, which is not explicitly mentioned in the design-lock.

4. **Charts/Visualization**: The code includes chart visualization using Recharts, which is not mentioned in the design-lock.

These discrepancies represent feature additions beyond the original design-lock specification, not violations of the core architecture.

## Core Components

### 1. LoopController

**File**: `backend/app/loop_controller.py`

**Purpose**: Orchestrates the analysis-generation-evaluation loop up to the iteration cap or until quality thresholds are satisfied.

**Responsibilities**:
- Manages the iterative refinement loop
- Calls LLMInterface for code generation/repair
- Calls StaticAnalyzer for code quality assessment
- Checks if quality thresholds are met
- Computes line-by-line diffs between iterations
- Records iteration data with MetricsTracker

**Key Methods**:
- `__init__(iteration_cap, pylint_threshold, max_bandit_high_med, ...)`: Initialize with configuration
- `check_threshold(bandit_high_med, pylint_score, has_syntax_error)`: Evaluate if quality thresholds are satisfied
- `run(prompt, initial_code)`: Execute the full optimization loop

**Data Flow**:
1. Receives prompt or initial code
2. For each iteration:
   - Generate code (if no initial code) or use provided code
   - Run static analysis (Bandit, Pylint, Radon)
   - Check thresholds
   - Extract and prioritize issues
   - Generate feedback for LLM
   - Compute diff with previous iteration
   - Record metrics
3. Return LoopResult with all iteration history

### 2. LLMInterface

**File**: `backend/app/llm_interface.py`

**Purpose**: Manages communication with Google Gemini Flash for generating code improvements and repairs.

**Responsibilities**:
- Configures Gemini API client
- Handles rate limit errors with automatic retry
- Strips markdown code fences from LLM responses
- Provides clear error messages for API failures

**Key Methods**:
- `__init__(api_key, model_name, max_retries, retry_delay_seconds, timeout)`: Initialize with API configuration
- `generate(prompt)`: Call Gemini Flash with retry logic for rate limits

**Error Handling**:
- Rate limit errors → Retry with exponential backoff
- Invalid arguments → ValueError
- Permission denied → ValueError
- Service unavailable → RuntimeError
- Other errors → RuntimeError with descriptive message

**Security**:
- API key loaded from environment variables
- No API keys logged
- Code snippets logged only as previews (first 100 characters)

### 3. StaticAnalyzer

**File**: `backend/app/static_analyzer.py`

**Purpose**: Executes static analysis tools (Bandit, Pylint, and Radon) against the code.

**Responsibilities**:
- Runs Bandit for security analysis
- Runs Pylint for code quality analysis
- Runs Radon for complexity and maintainability analysis
- Parses tool outputs into standardized issues
- Handles syntax errors gracefully

**Key Methods**:
- `__init__(python_executable, timeout_seconds)`: Initialize with Python executable and timeout
- `analyze(source_code)`: Run all analysis tools on the provided code
- `_run_bandit(file_path)`: Execute Bandit and parse JSON output
- `_run_pylint(file_path)`: Execute Pylint and parse JSON output
- `_run_pylint_fallback(file_path)`: Fallback for older Pylint versions
- `_run_radon_cc(source_code)`: Calculate cyclomatic complexity
- `_run_radon_mi(source_code)`: Calculate maintainability index

**Data Structures**:
- `StaticAnalysisIssue`: Standardized issue representation (tool, severity, line, message, rule_id)
- `StaticAnalysisResult`: List of issues with metadata (pylint_score, has_syntax_error, avg_complexity, max_complexity, maintainability_index)

### 4. IssueExtractor

**File**: `backend/app/issue_extractor.py`

**Purpose**: Parses raw reports from Bandit and Pylint into structured diagnostic issues.

**Responsibilities**:
- Prioritizes issues by severity and tool
- Limits the number of issues to prevent overwhelming the LLM
- Returns most critical issues for feedback generation

**Key Methods**:
- `__init__(max_issues)`: Initialize with maximum issues to extract
- `extract(analysis_result)`: Extract and prioritize issues from analysis result

**Prioritization Logic**:
1. Bandit HIGH/MEDIUM severity issues (security critical)
2. Pylint ERROR severity issues (syntax/critical)
3. Bandit LOW severity issues
4. Pylint WARNING severity issues
5. Pylint CONVENTION/REFACTOR severity issues

### 5. FeedbackGenerator

**File**: `backend/app/feedback_generator.py`

**Purpose**: Formats diagnostics and quality metrics into actionable prompts for the LLM.

**Responsibilities**:
- Converts structured issues into human-readable feedback
- Includes quality metrics (Pylint score, issue counts)
- Provides specific recommendations for fixes

**Key Methods**:
- `generate_feedback(extracted_issues)`: Generate feedback text from extracted issues

**Output Format**:
- Issue summary by tool and severity
- Specific line numbers and messages
- Actionable improvement suggestions

### 6. MetricsTracker

**File**: `backend/app/metrics_tracker.py`

**Purpose**: Tracks iterations, security findings, code quality scores, and convergence history.

**Responsibilities**:
- Records metrics for each iteration
- Generates before/after quality comparisons
- Formats ASCII comparison tables

**Key Methods**:
- `__init__()`: Initialize empty history
- `record(iteration, issues, pylint_score, threshold_met, has_syntax_error, avg_complexity, max_complexity, maintainability_index)`: Record iteration metrics
- `get_before_after_summary(converged)`: Generate before/after comparison
- `format_before_after_table(converged)`: Format ASCII table

**Data Structures**:
- `IterationMetrics`: Per-iteration metrics (pylint_score, total_issues, counts_by_tool, complexity, maintainability)
- `BeforeAfterSummary`: Comparison between initial and final iterations with delta calculations

### 7. ReportGenerator

**File**: `backend/app/report_generator.py`

**Purpose**: Generates Markdown reports for optimization runs.

**Responsibilities**:
- Creates comprehensive Markdown reports
- Includes all iterations, diffs, and metrics
- Formats for standalone readability

**Key Methods**:
- `generate_markdown_report(prompt, initial_code, iterations, final_code, metrics_summary, ...)`: Generate Markdown report

**Report Sections**:
- Header with timestamp and configuration
- Input (prompt or initial code)
- Iteration summary table
- Per-iteration details with issues and diffs
- Before/after summary
- Final optimized code

## Data Flow

### Generate Mode Flow

```
User Input (Prompt)
    ↓
LoopController.run()
    ↓
LLMInterface.generate() → Initial Code
    ↓
StaticAnalyzer.analyze() → Issues + Metrics
    ↓
MetricsTracker.record()
    ↓
Check Threshold
    ↓
[If not met]
    ↓
IssueExtractor.extract() → Priority Issues
    ↓
FeedbackGenerator.generate_feedback() → Feedback Text
    ↓
LLMInterface.generate(refinement_prompt) → Improved Code
    ↓
[Repeat until threshold met or cap reached]
    ↓
LoopResult (final_code, iterations, metrics)
```

### Review Mode Flow

```
User Input (Existing Code)
    ↓
LoopController.run(initial_code=user_code)
    ↓
[Skip LLM generation step]
    ↓
StaticAnalyzer.analyze() → Issues + Metrics
    ↓
[Same as Generate Mode from here]
```

### API Response Flow

```
LoopResult
    ↓
main.py optimize_code() / review_code()
    ↓
Convert to Pydantic models
    ↓
CodeOptimizationResponse
    ↓
Frontend receives JSON
    ↓
React components render results
```

## Request/Response Models

### CodePromptRequest
- `prompt`: User prompt (max 10,000 characters)
- `initial_code`: Optional existing code (max 50,000 characters)
- `iteration_cap`: 1-5
- `pylint_threshold`: 0.0-10.0

### CodeReviewRequest
- `code`: Python code to review (max 50,000 characters)
- `iteration_cap`: 1-5
- `pylint_threshold`: 0.0-10.0

### CodeOptimizationResponse
- `prompt`: Original prompt
- `final_code`: Optimized code
- `converged`: Whether thresholds were met
- `total_iterations`: Number of iterations run
- `final_pylint_score`: Final Pylint score
- `final_bandit_high_medium`: Final Bandit high/medium count
- `status`: "CONVERGED" or "CAP_REACHED"
- `iterations`: List of iteration data with diffs
- `metrics_summary`: Before/after comparison
- `iteration_cap`: Configured cap
- `pylint_threshold`: Configured threshold

## Convergence Policy

### Quality Thresholds
- **Bandit**: 0 High or Medium severity security issues
- **Pylint**: Score ≥ 8.0 / 10

### Iteration Cap
- Default: 3 iterations
- Configurable: 1-5 iterations via UI or API

### Stopping Conditions
1. Quality thresholds met → Converged
2. Iteration cap reached → CAP_REACHED
3. Syntax error detected → Immediate stop

## Error Handling

### API Errors
- 400: Invalid input (empty, size limits)
- 422: Validation error (invalid parameters)
- 503: Service error (rate limit, unavailable)
- 500: Internal error

### Tool Errors
- Bandit failure → Log error, continue with other tools
- Pylint failure → Log error, continue with other tools
- Radon failure → Log error, skip complexity metrics (optional)

### LLM Errors
- Rate limit → Retry with exponential backoff (max 3 retries)
- Invalid API key → ValueError
- Service unavailable → RuntimeError
- Other errors → RuntimeError with message

## Logging

### Log Location
- File: `backend/logs/aicodequality.log`
- Format: `timestamp - name - level - message`

### Logged Information
- Request received (mode, cap, code size)
- LLM generation attempts and results
- Analysis results (scores, issue counts)
- Convergence status
- Errors (type, message)
- No secrets or full user code logged

### Log Levels
- INFO: Normal operations
- WARNING: Recoverable issues (rate limits, tool failures)
- ERROR: Failures requiring attention

## Security Considerations

### Input Validation
- Size limits enforced at API level
- Pydantic validators for all inputs
- Type checking on all parameters

### API Key Management
- Loaded from environment variables
- Never logged or exposed in errors
- Not included in reports

### Code Safety
- LLM instructed to output only valid Python code
- Security tools (Bandit) detect dangerous patterns
- Shell=True in subprocess is flagged by Bandit

## Performance

### Timeouts
- Run timeout: 5 minutes total
- Tool timeout: 30 seconds per tool call
- LLM timeout: 60 seconds per call

### Optimization
- Static analysis runs in parallel where possible
- Caching: None (each run is independent)
- Diff computation: Uses Python's difflib (efficient for typical code sizes)

## Frontend Architecture

### React Components
- `App.jsx`: Main application container, state management, API calls
- `Charts.jsx`: Quality trend and severity breakdown visualization

### State Management
- Local component state (useState)
- No external state management library

### Data Flow
- User input → API call → Response → State update → Render
- Mode toggle (generate/review) → Different API endpoint
- Settings (cap, threshold) → Passed in API request body

### Styling
- CSS Modules with global CSS in `index.css`
- Dark theme with custom color variables
- Responsive design for mobile/desktop
