"""Runs ONLY inside the disposable restricted container; never import in the backend."""
import json
import sys

request = json.load(sys.stdin)
proposals = []
warnings = []


def emit(field, value, block_ids):
    proposals.append({"field": field, "value": value, "block_ids": block_ids})


try:
    # Isolation is provided by Docker, not by restricting Python builtins.
    context = {"document": request["document"], "params": request["params"], "emit": emit, "warnings": warnings}
    exec(compile(request["code"], "user_step.py", "exec"), context)
    json.dump({"proposals": proposals, "warnings": warnings}, sys.stdout, ensure_ascii=False, allow_nan=False)
except BaseException:
    # Tracebacks may contain document fragments; return a bounded diagnostic instead.
    sys.stderr.write("Python step failed. Check code and input document.\n")
    sys.exit(1)
