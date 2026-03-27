#! python 3
# pyright: reportUnboundVariable=false
# pyright: reportPossiblyUnboundVariable=false
# pyright: reportUndefinedVariable=false

import os
import sys
import time
import traceback
import importlib
import glob
import io
import json
import contextlib
import re

PROJECT_ROOT = os.environ.get("GH_AUTODEBUG_PROJECT_ROOT", r"F:\ghscriptuv")
MYMODULES_DIR = os.path.join(PROJECT_ROOT, "mymodules")
LAST_ERROR_JSON_PATH = os.path.join(PROJECT_ROOT, "_gh_debug", "last_error.json")
TRACEBACK_TAIL_CHARS = 4000
STDOUT_TAIL_CHARS = 4000
STDERR_TAIL_CHARS = 4000


def _summarize_gh_input(value, *, name="x", tag="INPUT", max_items=3, max_repr=120) -> str:
    def _clip(text: str) -> str:
        return text if len(text) <= max_repr else text[:max_repr] + "..."

    if value is None:
        return f"[{tag}] {name}=None"

    value_type = type(value)
    if isinstance(value, (list, tuple)):
        items = []
        for item in value[:max_items]:
            if item is None:
                items.append("None")
                continue
            if all(hasattr(item, a) for a in ("X", "Y", "Z")):
                x0, y0, z0 = getattr(item, "X"), getattr(item, "Y"), getattr(item, "Z")
                if all(isinstance(v, (int, float)) for v in (x0, y0, z0)):
                    items.append(f"{type(item).__name__}({x0:.3f},{y0:.3f},{z0:.3f})")
                    continue
            items.append(_clip(repr(item)))
        return f"[{tag}] {name}.type={value_type!r} len={len(value)} head={items}"

    if all(hasattr(value, a) for a in ("X", "Y", "Z")):
        x0, y0, z0 = getattr(value, "X"), getattr(value, "Y"), getattr(value, "Z")
        if all(isinstance(v, (int, float)) for v in (x0, y0, z0)):
            return f"[{tag}] {name}.type={value_type!r} value={type(value).__name__}({x0:.3f},{y0:.3f},{z0:.3f})"

    return f"[{tag}] {name}.type={value_type!r} value={_clip(repr(value))}"


def _gh_value_debug_json(value, *, max_paths=6, max_items=20, max_repr=160):
    def _clip(text: str) -> str:
        return text if len(text) <= max_repr else text[:max_repr] + "..."

    if value is None:
        return None
    if isinstance(value, (int, float, str, bool)):
        return value

    if all(hasattr(value, a) for a in ("X", "Y", "Z")):
        x0, y0, z0 = getattr(value, "X"), getattr(value, "Y"), getattr(value, "Z")
        if all(isinstance(v, (int, float)) for v in (x0, y0, z0)):
            return {"__type__": type(value).__name__, "xyz": [float(x0), float(y0), float(z0)]}

    if isinstance(value, (list, tuple)):
        head = []
        for item in value[:max_items]:
            head.append(_gh_value_debug_json(item, max_paths=max_paths, max_items=max_items, max_repr=max_repr))
        return {"__type__": repr(type(value)), "len": len(value), "head": head}

    if hasattr(value, "Paths") and hasattr(value, "Branches"):
        paths = list(value.Paths)
        branches = list(value.Branches)
        path_previews = []
        for p, br in list(zip(paths, branches))[:max_paths]:
            items = []
            for item in list(br)[:max_items]:
                items.append(_gh_value_debug_json(item, max_paths=max_paths, max_items=max_items, max_repr=max_repr))
            path_previews.append({"path": str(p), "count": len(br), "items": items})
        return {
            "__type__": repr(type(value)),
            "paths_total": len(paths),
            "paths_preview": path_previews,
            "data_count": int(getattr(value, "DataCount", -1)),
            "branch_count": int(getattr(value, "BranchCount", -1)),
        }

    return {"__type__": repr(type(value)), "repr": _clip(repr(value))}


def _error_category_and_location(error_exc: Exception, traceback_text: str):
    if isinstance(error_exc, ModuleNotFoundError):
        error_category = "import_error"
    elif isinstance(error_exc, AttributeError):
        error_category = "attribute_error"
    elif isinstance(error_exc, TypeError):
        error_category = "type_error"
    elif isinstance(error_exc, (IndexError, KeyError)):
        error_category = "index_error"
    elif (
        type(error_exc).__name__.endswith("Exception")
        and "Rhino.Runtime" in getattr(type(error_exc), "__module__", "")
    ):
        error_category = "geometry_error"
    else:
        error_category = "unknown"

    error_location = None
    match_list = re.findall(r'File "([^"]*mymodules[\\/][^"]+)", line (\d+)', traceback_text)
    if match_list:
        file_path, line_text = match_list[-1]
        error_location = {"file": os.path.basename(file_path), "line": int(line_text)}

    return error_category, error_location

project_site_packages_dirs = [os.path.join(PROJECT_ROOT, ".venv", "Lib", "site-packages")]
project_site_packages_dirs.extend(
    glob.glob(os.path.join(PROJECT_ROOT, ".venv", "lib", "python*", "site-packages"))
)
for _path in reversed(project_site_packages_dirs + [MYMODULES_DIR]):
    if os.path.isdir(_path) and _path not in sys.path:
        sys.path.insert(0, _path)

a = None
b = None
c = None
d = None
e = None
out = None

input_summaries = []
for _name in ("x", "y", "z", "u", "v", "w"):
    if _name in globals() and globals()[_name] is not None:
        input_summaries.append(_summarize_gh_input(globals()[_name], name=_name))

run_started = time.time()
ok = False
traceback_text = ""
stdout_buf = io.StringIO()
stderr_buf = io.StringIO()
mymodule = None
error_category = None
error_location = None

try:
    with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
        # ==============================
        # Agent 改动区 1/2：选择并热重载算法模块
        MODULE_NAME = "freeform_curve_curvature_20251229"
        mymodule = importlib.import_module(MODULE_NAME)
        importlib.reload(mymodule)
        # ==============================

        # ==============================
        # Agent 改动区 2/2：算法入口调用
        curve_calculator = mymodule.CurveCauculator(x, y)
        a, b = curve_calculator.curvatures_and_local_bending_energies()
        # ==============================
    ok = True
except Exception as error_exc:
    traceback_text = traceback.format_exc()
    error_category, error_location = _error_category_and_location(error_exc, traceback_text)
finally:
    output_summaries = []
    for _name in ("a", "b", "c", "d", "e"):
        output_summaries.append(_summarize_gh_input(globals().get(_name, None), name=_name, tag="OUTPUT"))
    elapsed_ms = int((time.time() - run_started) * 1000)

    def _tail_text(text: str, max_chars: int) -> str:
        if not text:
            return ""
        return text if len(text) <= max_chars else text[-max_chars:]

    stdout_tail = _tail_text(stdout_buf.getvalue(), STDOUT_TAIL_CHARS)
    stderr_tail = _tail_text(stderr_buf.getvalue(), STDERR_TAIL_CHARS)
    traceback_tail = _tail_text(traceback_text, TRACEBACK_TAIL_CHARS)

    out_text = "ok"
    if not ok:
        error_text_parts = []
        if stdout_tail:
            error_text_parts.append(stdout_tail.rstrip())
        if stderr_tail:
            error_text_parts.append(stderr_tail.rstrip())
        if traceback_tail:
            error_text_parts.append(traceback_tail.rstrip())
        out_text = "\n".join(error_text_parts) if error_text_parts else "error"

    out = out_text
    print(out_text)

    last_error_payload = {
        "ok": ok,
        "elapsed_ms": elapsed_ms,
        "traceback_tail": traceback_tail,
        "error_category": error_category,
        "error_location": error_location,
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail,
        "out_text": out_text,
        "input_summaries": input_summaries,
        "output_summaries": output_summaries,
        "inputs_debug": {
            k: _gh_value_debug_json(globals().get(k, None))
            for k in ("x", "y", "z", "u", "v", "w")
            if k in globals()
        },
        "outputs_debug": {k: _gh_value_debug_json(globals().get(k, None)) for k in ("a", "b", "c", "d", "e")},
        "validation": getattr(mymodule, "VALIDATION_REPORT", None) if mymodule is not None else None,
    }

    try:
        os.makedirs(os.path.dirname(LAST_ERROR_JSON_PATH), exist_ok=True)
        tmp_path = LAST_ERROR_JSON_PATH + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(last_error_payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, LAST_ERROR_JSON_PATH)
    except OSError:
        pass
