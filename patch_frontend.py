import re

with open("frontend/src/App.jsx", "r", encoding="utf-8") as f:
    app_jsx = f.read()

# I will write a script to rewrite App.jsx

new_state_vars = """
  const [runId, setRunId] = useState(null);
  const [jobStatus, setJobStatus] = useState(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
"""
app_jsx = app_jsx.replace("const [pipelineStep, setPipelineStep] = useState(null); // Track active pipeline step", "const [pipelineStep, setPipelineStep] = useState(null);\n" + new_state_vars)

# timer effect
timer_effect = """
  useEffect(() => {
    let timer = null;
    if (loading) {
      timer = setInterval(() => setElapsedSeconds(s => s + 1), 1000);
    } else {
      setElapsedSeconds(0);
    }
    return () => clearInterval(timer);
  }, [loading]);

  useEffect(() => {
    let interval = null;
    if (runId && loading) {
      interval = setInterval(async () => {
        try {
          const res = await fetch(`${API_BASE_URL}/api/runs/${runId}`);
          if (!res.ok) return;
          const job = await res.json();
          setJobStatus(job);
          
          if (job.status === "done") {
            setResult(job.result);
            if (job.result.iterations && job.result.iterations.length > 0) {
              setActiveTab(job.result.iterations.length - 1);
            }
            setLoading(false);
            setRunId(null);
          } else if (job.status === "failed") {
             const errorData = job.error || {};
             if (errorData.code === "quota_exhausted") {
               setError(`Quota exhausted. Try again in ${errorData.retry_after}s. <button onClick={() => alert('Demo mode activated!')}>Try demo mode</button>`);
             } else if (errorData.code === "timeout") {
               setError("Timeout: The request took too long.");
             } else if (errorData.code === "internal_error") {
               setError(`Backend Error: ${errorData.message}`);
             } else {
               setError("An unknown error occurred.");
             }
             setLoading(false);
             setRunId(null);
          } else if (job.status === "cancelled") {
             setError("Job cancelled.");
             setLoading(false);
             setRunId(null);
          }
        } catch (err) {
           console.error("Polling error", err);
        }
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [runId, loading]);

  const handleCancel = async () => {
    if (runId) {
      try {
        await fetch(`${API_BASE_URL}/api/runs/${runId}/cancel`, { method: "POST" });
      } catch (e) {
        console.error("Cancel failed", e);
      }
    }
  };
"""

app_jsx = app_jsx.replace("  // Check backend status on mount", timer_effect + "\n  // Check backend status on mount")

# Rewrite handleRun
handleRun_old = """  const handleRun = async () => {
    if (mode === "generate" && !prompt.trim()) return;
    if (mode === "review" && !code.trim()) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const endpoint = mode === "generate" ? "/api/optimize" : "/api/review";
      const body = mode === "generate"
        ? {
            prompt: prompt.trim(),
            iteration_cap: iterationCap,
            pylint_threshold: pylintThreshold,
          }
        : {
            code: code.trim(),
            iteration_cap: iterationCap,
            pylint_threshold: pylintThreshold,
          };

      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 120000); // 2 minute timeout

      const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Server error (${response.status})`);
      }

      const data = await response.json();
      setResult(data);
      if (data.iterations && data.iterations.length > 0) {
        setActiveTab(data.iterations.length - 1); // Select the latest iteration
      }
    } catch (err) {
      if (err.name === 'AbortError') {
        setError("Request timed out. Refinement did not complete. Check the backend logs or API availability.");
      } else {
        const isNetworkError = err.message && (
          err.message.includes('fetch') || 
          err.message.includes('Network') ||
          err.message.includes('ECONNREFUSED')
        );
        if (isNetworkError) {
          setError("Backend Offline: Unable to reach the FastAPI server at " + API_BASE_URL);
        } else {
          setError(err.message || "Failed to communicate with optimization backend");
        }
      }
    } finally {
      setLoading(false);
    }
  };"""

handleRun_new = """  const handleRun = async () => {
    if (mode === "generate" && !prompt.trim()) return;
    if (mode === "review" && !code.trim()) return;

    setLoading(true);
    setError(null);
    setResult(null);
    setJobStatus(null);
    setElapsedSeconds(0);

    try {
      const body = {
        mode: mode,
        prompt: prompt.trim(),
        code: code.trim(),
        iteration_cap: iterationCap,
        pylint_threshold: pylintThreshold,
      };

      const response = await fetch(`${API_BASE_URL}/api/runs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Server error (${response.status})`);
      }

      const data = await response.json();
      setRunId(data.run_id);
    } catch (err) {
        const isNetworkError = err.message && (
          err.message.includes('fetch') || 
          err.message.includes('Network') ||
          err.message.includes('ECONNREFUSED')
        );
        if (isNetworkError) {
          setError("Backend Offline: Unable to reach the FastAPI server at " + API_BASE_URL);
        } else {
          setError(err.message || "Failed to communicate with optimization backend");
        }
        setLoading(false);
    }
  };"""

app_jsx = app_jsx.replace(handleRun_old, handleRun_new)

# Update loading card
loading_old = """        {loading && (
          <section className="card loading-card">
            <div className="loading-animation">
              <div className="pulse-ring"></div>
              <div className="pulse-dot"></div>
            </div>
            <div className="loading-text">
              <h3>Running refinement...</h3>
              <p>Executing Gemini Flash repair, Bandit AST scan, and Pylint evaluation...</p>
            </div>
          </section>
        )}"""

loading_new = """        {loading && (
          <section className="card loading-card">
            <div className="loading-animation">
              <div className="pulse-ring"></div>
              <div className="pulse-dot"></div>
            </div>
            <div className="loading-text">
              <h3 className="highlighted-stage">{jobStatus?.stage || "Starting run..."}</h3>
              <p>Time elapsed: {elapsedSeconds}s</p>
              {elapsedSeconds > 30 && <p className="warning-text" style={{color: "orange"}}>taking longer than usual</p>}
              <button className="cancel-btn" onClick={handleCancel} style={{marginTop: 10}}>Cancel</button>
            </div>
          </section>
        )}"""

app_jsx = app_jsx.replace(loading_old, loading_new)


# Fix the Dangerously Set Inner HTML for error
# In React, you can't just put HTML in strings. I'll need to parse or use elements.
# Wait, I used a string with a button tag in error.
# Let's fix that error setting to not use strings with HTML.

app_jsx = app_jsx.replace(
    "`Quota exhausted. Try again in ${errorData.retry_after}s. <button onClick={() => alert('Demo mode activated!')}>Try demo mode</button>`",
    """<div className="quota-error">
               <p>Quota exhausted. Try again in {errorData.retry_after}s.</p>
               <button onClick={() => alert('Demo mode activated!')}>Try demo mode</button>
             </div>"""
)

# And render error
error_old = """            <div className="error-body">{error}</div>"""
error_new = """            <div className="error-body">{typeof error === "string" ? error : error}</div>"""
app_jsx = app_jsx.replace(error_old, error_new)

with open("frontend/src/App.jsx", "w", encoding="utf-8") as f:
    f.write(app_jsx)

