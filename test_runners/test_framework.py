"""
test_framework.py
Shared utilities for all maze project test runners.
"""
from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from typing import Callable, List, Optional

# ANSI colours
_GREEN  = "\033[92m"
_RED    = "\033[91m"
_YELLOW = "\033[93m"
_CYAN   = "\033[96m"
_BOLD   = "\033[1m"
_RESET  = "\033[0m"

TYPE_COLOURS = {
    "Unit Testing":        "\033[94m",   # blue
    "Integration Testing": "\033[96m",   # cyan
    "System Testing":      "\033[93m",   # yellow
    "Smoke Testing":       "\033[95m",   # magenta
    "Stress/Load Testing": "\033[91m",   # red
    "Regression Testing":  "\033[97m",   # bright white
}


@dataclass
class TestResult:
    test_id:   str
    test_type: str
    name:      str
    passed:    bool
    duration:  float          # seconds
    error:     Optional[str] = None


@dataclass
class TestSuite:
    module: str
    results: List[TestResult] = field(default_factory=list)

    # ── registration ─────────────────────────────────────────────────
    def run(
        self,
        test_id:   str,
        test_type: str,
        name:      str,
        fn:        Callable[[], None],
    ) -> TestResult:
        type_col = TYPE_COLOURS.get(test_type, _RESET)
        print(
            f"\n{_BOLD}[{test_id}]{_RESET} "
            f"{type_col}[{test_type}]{_RESET}  "
            f"{name}"
        )
        t0 = time.perf_counter()
        error = None
        passed = False
        try:
            fn()
            passed = True
        except AssertionError as e:
            error = f"AssertionError: {e}"
        except Exception as e:
            error = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        duration = time.perf_counter() - t0

        if passed:
            status = f"{_GREEN}✓ PASS{_RESET}"
        else:
            status = f"{_RED}✗ FAIL{_RESET}"

        print(f"  {status}  {_CYAN}{duration*1000:.1f} ms{_RESET}")
        if error:
            for line in error.splitlines():
                print(f"    {_YELLOW}{line}{_RESET}")

        result = TestResult(test_id, test_type, name, passed, duration, error)
        self.results.append(result)
        return result

    # ── summary ───────────────────────────────────────────────────────
    def print_summary(self) -> None:
        total   = len(self.results)
        passed  = sum(1 for r in self.results if r.passed)
        failed  = total - passed
        elapsed = sum(r.duration for r in self.results)

        print(f"\n{'='*65}")
        print(f"{_BOLD}TEST SUMMARY — {self.module}{_RESET}")
        print(f"{'='*65}")
        print(f"  Total : {total}")
        print(f"  {_GREEN}Passed{_RESET}: {passed}")
        print(f"  {_RED}Failed{_RESET}: {failed}")
        print(f"  Time  : {elapsed*1000:.1f} ms")

        if failed:
            print(f"\n{_RED}Failed tests:{_RESET}")
            for r in self.results:
                if not r.passed:
                    print(f"  [{r.test_id}] {r.name}")
                    if r.error:
                        first = r.error.splitlines()[0]
                        print(f"    → {first}")
        print(f"{'='*65}\n")

    def exit_code(self) -> int:
        return 0 if all(r.passed for r in self.results) else 1
