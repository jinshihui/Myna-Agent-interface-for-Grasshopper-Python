#! python 3
# pyright: reportUnboundVariable=false
# pyright: reportPossiblyUnboundVariable=false
# pyright: reportUndefinedVariable=false

import contextlib
import importlib
import io
import json
import os
import glob
import re
import sys
import time
import traceback

PROJECT_ROOT = os.environ.get("GH_AUTODEBUG_PROJECT_ROOT", r"F:\ghscriptuv")
MYMODULES_DIR = os.path.join(PROJECT_ROOT, "mymodules")
LAST_ERROR_JSON_PATH = os.path.join(PROJECT_ROOT, "_gh_debug", "last_error.json")

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


def _gh_value_debug_json(value, *, max_paths=6, max_items=20, max_repr=160):
    def _clip(text: str) -> str:
        return text if len(text) <= max_repr else text[:max_repr] + "..."

    if value is None:
        return None
    if isinstance(value, (int, float, str, bool)):
        return value

    if all(hasattr(value, attr_name) for attr_name in ("X", "Y", "Z")):
        x0, y0, z0 = getattr(value, "X"), getattr(value, "Y"), getattr(value, "Z")
        if all(isinstance(axis_value, (int, float)) for axis_value in (x0, y0, z0)):
            return {"__type__": type(value).__name__, "xyz": [float(x0), float(y0), float(z0)]}

    if isinstance(value, (list, tuple)):
        return {
            "__type__": repr(type(value)),
            "len": len(value),
            "head": [
                _gh_value_debug_json(item, max_paths=max_paths, max_items=max_items, max_repr=max_repr)
                for item in value[:max_items]
            ],
        }

    if hasattr(value, "Paths") and hasattr(value, "Branches"):
        path_previews = []
        for path, branch in list(zip(list(value.Paths), list(value.Branches)))[:max_paths]:
            path_previews.append(
                {
                    "path": str(path),
                    "count": len(branch),
                    "items": [
                        _gh_value_debug_json(item, max_paths=max_paths, max_items=max_items, max_repr=max_repr)
                        for item in list(branch)[:max_items]
                    ],
                }
            )
        return {
            "__type__": repr(type(value)),
            "paths_total": len(list(value.Paths)),
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


run_started = time.time()
ok = False
traceback_text = ""
error_category = None
error_location = None
stdout_buffer = io.StringIO()
stderr_buffer = io.StringIO()
mymodule = None

try:
    with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stderr_buffer):
        # Agent 改动区 1/2：算法模块
        module_name = "your_module_name"
        mymodule = importlib.import_module(module_name)
        importlib.reload(mymodule)

        # Agent 改动区 2/2：算法调用
        calculator = mymodule.YourCalculator(x, y)
        a = calculator.compute()
    ok = True
except Exception as error_exc:
    traceback_text = traceback.format_exc()
    error_category, error_location = _error_category_and_location(error_exc, traceback_text)
    # 自动调试流程固定不向上抛异常，始终写 last_error.json 供 Agent 回读。
finally:
    elapsed_ms = int((time.time() - run_started) * 1000)
    stdout_tail = stdout_buffer.getvalue()[-4000:]
    stderr_tail = stderr_buffer.getvalue()[-4000:]
    traceback_tail = traceback_text[-4000:]

    out_text = "ok"
    if not ok:
        error_text_list = [part.rstrip() for part in (stdout_tail, stderr_tail, traceback_tail) if part]
        out_text = "\n".join(error_text_list) if error_text_list else "error"

    out = out_text
    print(out_text)

    payload = {
        "ok": ok,
        "elapsed_ms": elapsed_ms,
        "traceback_tail": traceback_tail,
        "error_category": error_category,
        "error_location": error_location,
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail,
        "out_text": out_text,
        "inputs_debug": {
            key: _gh_value_debug_json(globals().get(key, None))
            for key in ("x", "y", "z", "u", "v", "w")
            if key in globals()
        },
        "outputs_debug": {key: _gh_value_debug_json(globals().get(key, None)) for key in ("a", "b", "c", "d", "e")},
        "validation": getattr(mymodule, "VALIDATION_REPORT", None) if mymodule is not None else None,
    }

    try:
        os.makedirs(os.path.dirname(LAST_ERROR_JSON_PATH), exist_ok=True)
        tmp_path = LAST_ERROR_JSON_PATH + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, LAST_ERROR_JSON_PATH)
    except OSError:
        pass
