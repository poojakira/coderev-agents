import json
import subprocess
from typing import Any, Dict, List


class BanditTool:
    """Wrapper for Bandit static analysis tool."""

    def run_scan(self, path: str) -> List[Dict[str, Any]]:
        """Runs bandit on the provided path and returns findings."""
        try:
            result = subprocess.run(
                ["bandit", "-r", path, "-f", "json"], capture_output=True, text=True
            )
            # Bandit returns 1 if issues found, so we don't check returncode == 0
            if not result.stdout:
                return []

            data = json.loads(result.stdout)
            return data.get("results", [])
        except Exception as e:
            return [{"error": str(e)}]

    def format_findings(self, findings: List[Dict[str, Any]]) -> str:
        """Formats findings for the LLM agent."""
        if not findings:
            return "No obvious security issues found by Bandit."

        report = ["Static Analysis (Bandit) Findings:"]
        for f in findings:
            report.append(
                f"- [{f['issue_severity']}] {f['issue_text']} in {f['filename']}:{f['line_number']}"
            )
            report.append(f"  Code: {f['code'].strip()}")
        return "\n".join(report)
