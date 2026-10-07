import React from "react";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

export default function Charts({ result }) {
  if (!result || !result.iterations || result.iterations.length === 0) {
    return null;
  }

  // Prepare data for trend charts
  const trendData = result.iterations.map((it) => ({
    iteration: `Iter ${it.iteration}`,
    pylintScore: it.pylint_score,
    totalIssues: it.total_issues_count,
    banditHighMed: it.bandit_high_medium_count,
  }));

  // Prepare data for severity breakdown (before vs after)
  const initialIter = result.iterations[0];
  const finalIter = result.iterations[result.iterations.length - 1];

  // Count issues by severity for initial and final
  const countBySeverity = (issues) => {
    const counts = {
      HIGH: 0,
      MEDIUM: 0,
      LOW: 0,
      ERROR: 0,
      WARNING: 0,
      CONVENTION: 0,
      REFACTOR: 0,
    };
    issues.forEach((issue) => {
      const severity = issue.severity.toUpperCase();
      if (counts.hasOwnProperty(severity)) {
        counts[severity]++;
      }
    });
    return counts;
  };

  const initialSeverity = countBySeverity(initialIter.issues || []);
  const finalSeverity = countBySeverity(finalIter.issues || []);

  const severityData = [
    { name: "High", before: initialSeverity.HIGH, after: finalSeverity.HIGH },
    { name: "Medium", before: initialSeverity.MEDIUM, after: finalSeverity.MEDIUM },
    { name: "Low", before: initialSeverity.LOW, after: finalSeverity.LOW },
    { name: "Error", before: initialSeverity.ERROR, after: finalSeverity.ERROR },
    { name: "Warning", before: initialSeverity.WARNING, after: finalSeverity.WARNING },
    { name: "Convention", before: initialSeverity.CONVENTION, after: finalSeverity.CONVENTION },
    { name: "Refactor", before: initialSeverity.REFACTOR, after: finalSeverity.REFACTOR },
  ].filter((item) => item.before > 0 || item.after > 0);

  return (
    <div className="card charts-card">
      <div className="card-header">
        <h2>Quality Trends & Severity Breakdown</h2>
      </div>

      <div className="charts-grid">
        {/* Pylint Score Trend */}
        <div className="chart-container">
          <h4 className="chart-title">Pylint Score Progress</h4>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={trendData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="iteration" stroke="#94a3b8" fontSize={12} />
              <YAxis stroke="#94a3b8" fontSize={12} domain={[0, 10]} />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#111827",
                  border: "1px solid #374151",
                  borderRadius: "8px",
                }}
                itemStyle={{ color: "#f8fafc" }}
              />
              <Legend />
              <Line
                type="monotone"
                dataKey="pylintScore"
                stroke="#6366f1"
                strokeWidth={2}
                dot={{ fill: "#6366f1", r: 4 }}
                activeDot={{ r: 6 }}
                name="Pylint Score"
              />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Total Issues Trend */}
        <div className="chart-container">
          <h4 className="chart-title">Total Issues Trend</h4>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={trendData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="iteration" stroke="#94a3b8" fontSize={12} />
              <YAxis stroke="#94a3b8" fontSize={12} />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#111827",
                  border: "1px solid #374151",
                  borderRadius: "8px",
                }}
                itemStyle={{ color: "#f8fafc" }}
              />
              <Legend />
              <Line
                type="monotone"
                dataKey="totalIssues"
                stroke="#ef4444"
                strokeWidth={2}
                dot={{ fill: "#ef4444", r: 4 }}
                activeDot={{ r: 6 }}
                name="Total Issues"
              />
              <Line
                type="monotone"
                dataKey="banditHighMed"
                stroke="#f59e0b"
                strokeWidth={2}
                dot={{ fill: "#f59e0b", r: 4 }}
                activeDot={{ r: 6 }}
                name="Bandit High/Med"
              />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Severity Breakdown */}
        {severityData.length > 0 && (
          <div className="chart-container full-width">
            <h4 className="chart-title">Severity Breakdown (Before vs After)</h4>
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={severityData} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis type="number" stroke="#94a3b8" fontSize={12} />
                <YAxis dataKey="name" type="category" stroke="#94a3b8" fontSize={12} width={80} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#111827",
                    border: "1px solid #374151",
                    borderRadius: "8px",
                  }}
                  itemStyle={{ color: "#f8fafc" }}
                />
                <Legend />
                <Bar dataKey="before" fill="#ef4444" name="Before" radius={[0, 4, 4, 0]} />
                <Bar dataKey="after" fill="#10b981" name="After" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );
}
