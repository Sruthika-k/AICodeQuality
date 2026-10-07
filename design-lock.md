# Design Lock Specification

## 1. System Overview & Technology Stack
- **Backend**: FastAPI (Python 3.10+)
- **Frontend**: React + Vite
- **LLM Engine**: Gemini Flash
- **Static Analysis & Security**: Bandit + Pylint + Radon (complexity & maintainability)

## 2. Convergence & Iteration Policy
- **Iteration Cap**: 3 iterations maximum per code improvement cycle
- **Quality Threshold**:
  - **Bandit**: 0 High or Medium severity security issues
  - **Pylint**: Score $\ge$ 8.0 / 10

## 3. Core Architecture Components
1. **`LoopController`**: Orchestrates the analysis-generation-evaluation loop up to the iteration cap or until quality thresholds are satisfied.
2. **`LLMInterface`**: Manages communication with Google Gemini Flash for generating code improvements and repairs.
3. **`StaticAnalyzer`**: Executes static analysis tools (Bandit, Pylint, and Radon) against the code.
4. **`IssueExtractor`**: Parses raw reports from Bandit and Pylint into structured diagnostic issues.
5. **`FeedbackGenerator`**: Formats diagnostics and quality metrics into actionable prompts for the LLM.
6. **`MetricsTracker`**: Tracks iterations, security findings, code quality scores, and convergence history.
