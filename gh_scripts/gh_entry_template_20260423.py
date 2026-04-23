#! python 3
# pyright: reportUnboundVariable=false
# pyright: reportPossiblyUnboundVariable=false
# pyright: reportUndefinedVariable=false

import contextlib
import glob
import importlib
import io
import json
import os
import re
import sys
import threading
import time
import traceback
from datetime import datetime, timezone


def _find_project_root_from(start_dir):
    if not start_dir:
        return None

    candidate_dir = os.path.abspath(start_dir)
    while True:
        if os.path.isdir(os.path.join(candidate_dir, "mymodules")) and os.path.isdir(os.path.join(candidate_dir, "_gh_debug")):
            return candidate_dir
        parent_dir = os.path.dirname(candidate_dir)
        if parent_dir == candidate_dir:
            return None
        candidate_dir = parent_dir


def _resolve_project_root():
    project_root = os.environ.get("GH_AUTODEBUG_PROJECT_ROOT", "").strip()
    if project_root:
        return os.path.abspath(project_root)

    gh_env = globals().get("ghenv", None)
    component = getattr(gh_env, "Component", None)
    document = component.OnPingDocument() if component is not None else None
    document_path = getattr(document, "FilePath", None)
    document_root = _find_project_root_from(os.path.dirname(document_path)) if document_path else None
    if document_root:
        return document_root

    cwd_root = _find_project_root_from(os.getcwd())
    if cwd_root:
        return cwd_root

    return os.getcwd()


def _utc_now_text():
    return datetime.now(timezone.utc).isoformat()


def _read_json_payload(path):
    if not os.path.exists(path):
        return None

    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None

    return payload if isinstance(payload, dict) else None


def _write_json_atomic(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


PROJECT_ROOT = _resolve_project_root()
MYMODULES_DIR = os.path.join(PROJECT_ROOT, "mymodules")
COMPONENT_GUID = str(getattr(getattr(globals().get("ghenv", None), "Component", None), "InstanceGuid", "unknown_component"))
PYTHON_PAYLOAD_JSON_PATH = os.path.join(PROJECT_ROOT, "_gh_debug", f"python_payload_{COMPONENT_GUID}.json")
REQUEST_CONTEXT_JSON_PATH = os.path.join(PROJECT_ROOT, "_gh_debug", f"request_context_{COMPONENT_GUID}.json")

REQUEST_CONTEXT = _read_json_payload(REQUEST_CONTEXT_JSON_PATH) or {}
REQUEST_ID = str(REQUEST_CONTEXT.get("request_id", "")).strip()
REQUEST_STARTED_AT_UTC = str(REQUEST_CONTEXT.get("started_at_utc") or _utc_now_text())
RUN_STATUS_JSON_PATH = os.path.join(PROJECT_ROOT, "_gh_debug", f"run_status_{REQUEST_ID}.json") if REQUEST_ID else ""

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

RUN_STATE_LOCK = threading.Lock()
HEARTBEAT_STOP_EVENT = threading.Event()
RUN_STATE = {
    "request_id": REQUEST_ID,
    "component_guid": COMPONENT_GUID,
    "started_at_utc": REQUEST_STARTED_AT_UTC,
    "heartbeat_at_utc": _utc_now_text(),
    "heartbeat_ts": time.time(),
    "phase": "running",
    "terminal": False,
    "module_name": None,
}


def _update_run_state(**updates):
    with RUN_STATE_LOCK:
        RUN_STATE.update(updates)


def _write_run_status():
    if not RUN_STATUS_JSON_PATH or not REQUEST_ID:
        return

    with RUN_STATE_LOCK:
        payload = dict(RUN_STATE)

    try:
        _write_json_atomic(RUN_STATUS_JSON_PATH, payload)
    except OSError:
        pass


def _heartbeat_loop():
    while not HEARTBEAT_STOP_EVENT.wait(1.0):
        _update_run_state(
            heartbeat_at_utc=_utc_now_text(),
            heartbeat_ts=time.time(),
        )
        _write_run_status()


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
    elif isinstance(error_exc, ValueError):
        error_text = str(error_exc)
        if error_text.startswith("POINT_INPUT_") or error_text.startswith("SURFACE_INPUT_") or error_text.startswith("INPUT_"):
            error_category = "input_error"
        elif error_text.startswith("VALIDATION_FAIL"):
            error_category = "validation_error"
        else:
            error_category = "value_error"
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
module_name = None
heartbeat_thread = None

if REQUEST_ID:
    _write_run_status()
    heartbeat_thread = threading.Thread(target=_heartbeat_loop, daemon=True)
    heartbeat_thread.start()

try:
    with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stderr_buffer):
        simulate_timeout_seconds = float(os.environ.get("MYNA_SIMULATE_TIMEOUT_SECONDS", "0") or "0")
        simulate_timeout_path = os.path.join(PROJECT_ROOT, "_gh_debug", "myna_simulate_timeout_seconds.txt")
        if simulate_timeout_seconds <= 0.0 and os.path.exists(simulate_timeout_path):
            with open(simulate_timeout_path, "r", encoding="utf-8-sig") as f:
                simulate_timeout_seconds = float((f.read() or "0").strip() or "0")
        if simulate_timeout_seconds > 0.0:
            time.sleep(simulate_timeout_seconds)

        # Agent edit area 1/2: algorithm module
        module_name = "surface_geodesic_20260423"
        _update_run_state(module_name=module_name)
        mymodule = importlib.import_module(module_name)
        importlib.reload(mymodule)

        # Agent edit area 2/2: algorithm call
        calculator = mymodule.SurfaceGeodesicCalculator(x, y)
        a = calculator.compute()
    ok = True
except Exception as error_exc:
    traceback_text = traceback.format_exc()
    error_category, error_location = _error_category_and_location(error_exc, traceback_text)
    # Always write the Python sidecar for Myna to merge.
finally:
    HEARTBEAT_STOP_EVENT.set()
    if heartbeat_thread is not None:
        heartbeat_thread.join(timeout=1.0)

    elapsed_ms = int((time.time() - run_started) * 1000)
    stdout_tail = stdout_buffer.getvalue()[-4000:]
    stderr_tail = stderr_buffer.getvalue()[-4000:]
    traceback_tail = traceback_text[-4000:]
    finished_at_utc = _utc_now_text()

    out_text = "ok"
    if not ok:
        error_text_list = [part.rstrip() for part in (stdout_tail, stderr_tail, traceback_tail) if part]
        out_text = "\n".join(error_text_list) if error_text_list else "error"

    out = out_text
    print(out_text)

    phase = "succeeded" if ok else "failed"
    _update_run_state(
        heartbeat_at_utc=finished_at_utc,
        heartbeat_ts=time.time(),
        finished_at_utc=finished_at_utc,
        phase=phase,
        terminal=True,
        module_name=module_name,
        error_category=error_category,
    )
    _write_run_status()

    payload = {
        "request_id": REQUEST_ID,
        "ok": ok,
        "phase": phase,
        "terminal": True,
        "started_at_utc": REQUEST_STARTED_AT_UTC,
        "heartbeat_at_utc": finished_at_utc,
        "finished_at_utc": finished_at_utc,
        "elapsed_ms": elapsed_ms,
        "traceback_tail": traceback_tail,
        "error_category": error_category,
        "error_location": error_location,
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail,
        "out_text": out_text,
        "component_guid": COMPONENT_GUID,
        "module_name": module_name if mymodule is not None else module_name,
        "validation": getattr(mymodule, "VALIDATION_REPORT", None) if mymodule is not None else None,
        "python_debug": _gh_value_debug_json(getattr(mymodule, "DEBUG_PAYLOAD", None)) if mymodule is not None else None,
    }

    try:
        _write_json_atomic(PYTHON_PAYLOAD_JSON_PATH, payload)
    except OSError:
        pass
