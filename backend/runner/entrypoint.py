"""Runs ONLY inside the disposable restricted container; never import in the backend."""
import json
import sys

request = json.load(sys.stdin)
proposals = []
warnings = []
output = None


def set_output(value):
    global output
    encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
    if len(encoded.encode("utf-8")) > 256 * 1024:
        raise ValueError("Output exceeds 256 KiB")
    output = json.loads(encoded)



def emit(field, value, block_ids):
    proposals.append({"field": field, "value": value, "block_ids": block_ids})


try:
    # Isolation is provided by Docker, not by restricting Python builtins.
    context = {"document": request["document"], "params": request["params"], "emit": emit, "warnings": warnings, "previous_results": request.get("previous_results", {"fields": {}, "steps": [], "conflicts": []}), "set_output": set_output}
    exec(compile(request["code"], "user_step.py", "exec"), context)
    json.dump({"proposals": proposals, "warnings": warnings, "output": output}, sys.stdout, ensure_ascii=False, allow_nan=False)
except BaseException:
    # Tracebacks may contain document fragments; return a bounded diagnostic instead.
    sys.stderr.write("Python step failed. Check code and input document.\n")
    sys.exit(1)
