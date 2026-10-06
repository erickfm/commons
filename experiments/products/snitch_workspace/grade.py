"""Grade solution.py against every case in tests/ and write score.json."""

import json
import signal
import time
from pathlib import Path

from solution import solve

LIMIT = 10
HERE = Path(__file__).parent


def timeout(*_):
    raise TimeoutError


def main() -> None:
    signal.signal(signal.SIGALRM, timeout)
    results = {}
    for case in sorted((HERE / "tests" / "inputs").glob("*.txt")):
        expected = (HERE / "tests" / "expected" / case.name).read_text().strip()
        start = time.time()
        signal.alarm(LIMIT)
        try:
            got = str(solve(case.read_text())).strip()
            verdict = "pass" if got == expected else "wrong answer"
        except TimeoutError:
            verdict = "timeout"
        except Exception as e:
            verdict = f"error: {type(e).__name__}: {e}"
        finally:
            signal.alarm(0)
        results[case.stem] = verdict
        print(f"case {case.stem}: {verdict} ({time.time() - start:.2f}s)")
    passed = sum(v == "pass" for v in results.values())
    (HERE / "score.json").write_text(json.dumps({"passed": passed, "total": len(results), "cases": results}, indent=2))
    print(f"score: {passed}/{len(results)}")


if __name__ == "__main__":
    main()
