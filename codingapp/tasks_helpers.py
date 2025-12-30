# codingapp/tasks_helpers.py
"""
Small, safe (for local/dev) check_test_cases implementation.

It only supports Python submissions for now. It executes each test case
in a subprocess using the system python executable with a timeout,
feeds the test input on stdin, collects stdout, and compares to expected output.

Expected `test_cases` format (list of dicts):
    [{"input": "1\n2\n", "expected_output": ["3"]}, ... ]

Return value:
    {
        "score": <int passed_count>,
        "results": [
            {"input": "...", "expected_output": [...], "actual_output": [...], "status": "Accepted"/"Rejected", "error_message": "..."},
            ...
        ],
        "error": "",           # execution-level error string if any
        "status": "Accepted" or "Rejected" or "Error"
    }
"""

from subprocess import run, PIPE, TimeoutExpired
import tempfile
import sys
import os
import json
import re
from typing import Tuple, List, Dict, Any

PYTHON_EXECUTABLE = sys.executable  # uses the same Python interpreter

# Safety/time limits — adjust if necessary
PER_TEST_TIMEOUT = 5  # seconds per test input
TOTAL_TIMEOUT = 30    # overall cap (not strictly enforced here)


def _safe_normalize_newlines(s: str) -> str:
    """
    Convert escaped newline sequences '\\n' and '\\r\\n' to real newlines if it looks like
    the incoming string uses escaped sequences (heuristic: more escaped sequences than real newlines).
    If the string already contains real newlines, do not ruin them.
    """
    if s is None:
        return ""
    try:
        # Quick heuristic: convert only when escaped sequences seem more numerous than actual newlines.
        if "\\r\\n" in s or "\\n" in s:
            if s.count("\\n") >= s.count("\n"):
                s = s.replace("\\r\\n", "\r\n").replace("\\n", "\n")
    except Exception:
        return s
    return s


def _ensure_trailing_newline(s: str) -> str:
    if s is None:
        s = ""
    if not s.endswith("\n"):
        s = s + "\n"
    return s


def _run_python_code(code: str, stdin_data: str, timeout: int = PER_TEST_TIMEOUT) -> Tuple[str, str, int, bool]:
    """
    Run python code in a subprocess using a temporary file.

    Returns:
      (stdout_text, stderr_text, returncode, timed_out_bool)
    """
    if code is None:
        return ("", "No code provided", 1, False)

    # Normalize escaped newline sequences in code and stdin
    try:
        code = _safe_normalize_newlines(code)
    except Exception:
        pass

    # Ensure the code file ends with a newline
    code_src = code if code.endswith("\n") else code + "\n"

    # Normalize stdin and ensure it has enough lines for input() calls
    stdin_data = "" if stdin_data is None else str(stdin_data)
    stdin_data = _safe_normalize_newlines(stdin_data)

    # Heuristic: count input() occurrences so we can ensure stdin has enough lines
    try:
        input_calls = len(re.findall(r'\binput\s*\(', code_src))
    except Exception:
        input_calls = 0

    stdin_lines = stdin_data.splitlines()
    if stdin_data.strip() == "":
        stdin_lines = []

    if len(stdin_lines) < input_calls:
        needed = input_calls - len(stdin_lines)
        stdin_lines += [""] * needed

    stdin_fixed = "\n".join(stdin_lines)
    if not stdin_fixed.endswith("\n"):
        stdin_fixed += "\n"
    # ensure at least a newline
    if stdin_fixed == "":
        stdin_fixed = "\n"

    tmp_path = None
    try:
        # Write to a temporary file and execute via the same interpreter
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(code_src)
            tmp_path = f.name

        proc = run(
            [PYTHON_EXECUTABLE, tmp_path],
            input=stdin_fixed.encode("utf-8"),
            stdout=PIPE,
            stderr=PIPE,
            timeout=timeout,
        )
        stdout = proc.stdout.decode("utf-8", errors="replace")
        stderr = proc.stderr.decode("utf-8", errors="replace")
        return (stdout, stderr, proc.returncode, False)
    except TimeoutExpired:
        return ("", f"Timed out after {timeout}s", -1, True)
    except Exception as exc:
        # Return runner-level error message, don't raise (Celery worker shouldn't die)
        return ("", f"Runner error: {str(exc)}", -1, False)
    finally:
        try:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass


def _normalize_output_to_lines(s: str) -> List[str]:
    """
    Clean stdout into list of lines for comparison:
    - normalize CRLF to LF
    - strip leading/trailing whitespace per line
    - remove empty lines
    """
    if s is None:
        return []
    s = s.replace("\r\n", "\n").rstrip("\n")
    lines = s.split("\n")
    lines = [ln.strip() for ln in lines]
    return [ln for ln in lines if ln != ""]


def check_test_cases(code: str, language: str, test_cases) -> Dict[str, Any]:
    """
    Primary exported function expected by the Celery task.
    Only 'python' language is supported here (local/dev).
    """
    if language is None:
        language = "python"

    results: List[Dict[str, Any]] = []
    passed = 0
    overall_error = ""

    if language.lower() != "python":
        return {
            "score": 0,
            "results": [],
            "error": f"Language {language} not supported by this runner.",
            "status": "Error"
        }

    try:
        # test_cases expected to be list-like of dicts
        for tc in test_cases or []:
            # TC input and expected may come as different shapes in your DB; handle gracefully
            tc_input = tc.get("input", "") if isinstance(tc, dict) else ""
            expected = tc.get("expected_output", []) if isinstance(tc, dict) else []

            # Normalize inputs (convert escaped newlines if present)
            tc_input = "" if tc_input is None else str(tc_input)

            # Run the code for a single test case
            stdout, stderr, rc, timed_out = _run_python_code(code, tc_input, timeout=PER_TEST_TIMEOUT)

            actual_lines = _normalize_output_to_lines(stdout)

            # Normalize expected output to list of strings
            if isinstance(expected, str):
                expected_lines = [expected.strip()] if expected.strip() != "" else []
            else:
                expected_lines = [str(x).strip() for x in (expected or []) if str(x).strip() != ""]

            status = "Accepted"
            error_message = ""

            # If timed out or non-zero return code with stderr, mark rejected with reason
            if timed_out:
                status = "Rejected"
                error_message = f"Timed out after {PER_TEST_TIMEOUT}s"
            elif rc != 0 and stderr:
                status = "Rejected"
                error_message = stderr.strip()
            else:
                # Compare expected_lines vs actual_lines
                if len(expected_lines) == 0:
                    # If expected empty, accept as long as program produced something
                    status = "Accepted" if actual_lines else "Rejected"
                    if status == "Rejected":
                        error_message = f"No output produced; expected something."
                else:
                    if actual_lines == expected_lines:
                        status = "Accepted"
                    else:
                        # tolerant compare: compare joined whitespace-stripped strings
                        if " ".join(actual_lines).strip() == " ".join(expected_lines).strip():
                            status = "Accepted"
                        else:
                            status = "Rejected"
                            exp_preview = json.dumps(expected_lines[:3], ensure_ascii=False)
                            act_preview = json.dumps(actual_lines[:3], ensure_ascii=False)
                            error_message = f"Expected {exp_preview}, got {act_preview}"

            if status == "Accepted":
                passed += 1

            results.append({
                "input": tc_input,
                "expected_output": expected_lines,
                "actual_output": actual_lines,
                "status": status,
                "error_message": error_message,
            })

        final_status = "Accepted" if (passed == len(test_cases or []) and len(test_cases or []) > 0) else "Rejected"
        return {
            "score": passed,
            "results": results,
            "error": overall_error,
            "status": final_status
        }
    except Exception as e:
        return {
            "score": 0,
            "results": [],
            "error": str(e),
            "status": "Error"
        }
