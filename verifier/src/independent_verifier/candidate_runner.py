"""Local SOURCE_TEST candidate runner; supplies no OS security isolation."""

import importlib.util
import json
import sys
from pathlib import Path


def main():
    if len(sys.argv) < 2:
        sys.stderr.write("CANDIDATE_PATH_REQUIRED\n")
        sys.stderr.flush()
        sys.exit(2)

    cand_path = Path(sys.argv[1]).resolve()
    if not cand_path.is_file():
        sys.stderr.write("CANDIDATE_NOT_FOUND\n")
        sys.stderr.flush()
        sys.exit(3)

    # -I excludes user packages; retain the standard library for normal candidates.
    # Neither -I nor sys.path is a filesystem security boundary.

    try:
        spec = importlib.util.spec_from_file_location("candidate_title_eval", cand_path)
        if spec is None or spec.loader is None:
            sys.stderr.write("SPEC_LOAD_FAILED\n")
            sys.stderr.flush()
            sys.exit(4)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception as exc:
        sys.stderr.write(f"IMPORT_ERROR: {type(exc).__name__}: {exc}\n")
        sys.stderr.flush()
        sys.exit(5)

    func = getattr(mod, "normalize_title", None)
    if not callable(func):
        sys.stderr.write("NORMALIZE_TITLE_NOT_CALLABLE\n")
        sys.stderr.flush()
        sys.exit(6)

    # Signal ready
    sys.stdout.write("READY\n")
    sys.stdout.flush()

    # Read binary stream of lines safely
    in_stream = sys.stdin.buffer
    out_stream = sys.stdout.buffer

    while True:
        line = in_stream.readline()
        if not line:
            break
        line_str = line.decode("utf-8", errors="replace").strip()
        if not line_str:
            continue
        if line_str == "DONE":
            break

        try:
            req = json.loads(line_str)
            val = req.get("value")
            request_id = req["id"]
            res = func(val)
            resp = {"id": request_id, "status": "SUCCESS", "value": res}
        except Exception as exc:
            resp = {"id": req.get("id"), "status": "ERROR", "error_type": type(exc).__name__}

        out_data = json.dumps(resp, ensure_ascii=False).encode("utf-8") + b"\n"
        out_stream.write(out_data)
        out_stream.flush()


if __name__ == "__main__":
    main()
