import json
import os
import socket
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple


def _resolve_project_root() -> str:
    project_root = os.environ.get("GH_AUTODEBUG_PROJECT_ROOT", "").strip()
    if project_root:
        return os.path.abspath(project_root)

    current_dir = os.getcwd()
    candidate_dir = current_dir
    while True:
        if os.path.isdir(os.path.join(candidate_dir, "mymodules")) and os.path.isdir(os.path.join(candidate_dir, "_gh_debug")):
            return candidate_dir
        parent_dir = os.path.dirname(candidate_dir)
        if parent_dir == candidate_dir:
            return current_dir
        candidate_dir = parent_dir


DEFAULT_PROJECT_ROOT = _resolve_project_root()
DEFAULT_LAST_ERROR_JSON_PATH = os.path.join(DEFAULT_PROJECT_ROOT, "_gh_debug", "last_error.json")
DEFAULT_RECOMPUTE_TCP_PORT = 17666
DEFAULT_WAIT_TIMEOUT_S = 60.0
DEFAULT_POLL_INTERVAL_S = 0.2


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_last_error_path(last_error_path: str) -> Tuple[str, str]:
    normalized_project_root = os.path.abspath(DEFAULT_PROJECT_ROOT)
    if os.path.isabs(last_error_path):
        normalized_input_path = os.path.abspath(last_error_path)
    else:
        normalized_input_path = os.path.abspath(os.path.join(normalized_project_root, last_error_path))
    try:
        relative_path = os.path.relpath(normalized_input_path, normalized_project_root)
        if relative_path.startswith(".."):
            normalized_project_root = os.path.dirname(normalized_input_path)
            relative_path = os.path.basename(normalized_input_path)
    except ValueError:
        normalized_project_root = os.path.dirname(normalized_input_path)
        relative_path = os.path.basename(normalized_input_path)
    return normalized_project_root, relative_path.replace("\\", "/")


def _resolve_last_error_path(last_error_path: str) -> str:
    project_root, relative_path = _normalize_last_error_path(last_error_path)
    normalized_relative_path = relative_path.replace("/", os.sep).replace("\\", os.sep)
    return os.path.abspath(os.path.join(project_root, normalized_relative_path))


def _run_status_path(project_root: str, request_id: str) -> str:
    return os.path.join(project_root, "_gh_debug", f"run_status_{request_id}.json")


def _get_mtime(path: str) -> Optional[float]:
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def _read_json_payload(path: str) -> Optional[Dict[str, Any]]:
    if not os.path.exists(path):
        return None

    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None

    return payload if isinstance(payload, dict) else None


def _write_json_atomic(path: str, payload: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def _payload_matches_request(payload: Optional[Dict[str, Any]], request_id: str) -> bool:
    return isinstance(payload, dict) and payload.get("request_id") == request_id


def _payload_is_terminal(payload: Optional[Dict[str, Any]], request_id: str) -> bool:
    return _payload_matches_request(payload, request_id) and bool(payload.get("terminal") is True)


def _tcp_ping(port: int = DEFAULT_RECOMPUTE_TCP_PORT, timeout_s: float = 2.0) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=float(timeout_s)) as sock:
            sock.settimeout(float(timeout_s))
            sock.sendall(b'{"type":"ping"}\n')
            response_line = b""
            while b"\n" not in response_line:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response_line += chunk
    except OSError:
        return False

    response_text = response_line.decode("utf-8", errors="replace").strip()
    if not response_text:
        return False

    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError:
        return False

    return bool(isinstance(payload, dict) and payload.get("success") is True)


def _tcp_recompute(
    port: int = DEFAULT_RECOMPUTE_TCP_PORT,
    timeout_s: float = 2.0,
    last_error_path: str = DEFAULT_LAST_ERROR_JSON_PATH,
    request_id: str = "",
) -> Dict[str, Any]:
    project_root, last_error_relpath = _normalize_last_error_path(last_error_path)
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=float(timeout_s)) as sock:
            sock.settimeout(float(timeout_s))
            request_text = json.dumps(
                {
                    "type": "recompute",
                    "project_root": project_root,
                    "last_error_relpath": last_error_relpath,
                    "request_id": request_id,
                },
                ensure_ascii=False,
            )
            sock.sendall((request_text + "\n").encode("utf-8"))
            response_line = b""
            while b"\n" not in response_line:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response_line += chunk
    except OSError as e:
        return {"success": False, "error": "tcp_connect_failed", "port": int(port), "detail": str(e)}

    response_text = response_line.decode("utf-8", errors="replace").strip()
    if not response_text:
        return {"success": False, "error": "empty_response", "port": int(port)}

    try:
        parsed = json.loads(response_text)
    except json.JSONDecodeError as e:
        return {
            "success": False,
            "error": "invalid_response_json",
            "port": int(port),
            "detail": str(e),
            "response_text": response_text,
        }

    if not isinstance(parsed, dict):
        return {"success": False, "error": "invalid_response_type", "port": int(port)}

    parsed["port"] = int(port)
    return parsed


def _terminal_feedback_payload(
    *,
    request_id: str,
    last_error_path: str,
    phase: str,
    error_category: str,
    run_status: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "captured_at_utc": _utc_now_text(),
        "request_id": request_id,
        "phase": phase,
        "terminal": True,
        "ok": False,
        "error_category": error_category,
        "error_location": None,
        "traceback_tail": "",
        "stdout_tail": "",
        "stderr_tail": "",
        "runtime_messages": [],
        "inputs_debug": [],
        "outputs_debug": [],
        "validation": None,
        "python_debug": None,
        "python_payload_fresh": False,
        "last_error_path": last_error_path,
        "host_status": "unreachable" if phase == "host_unreachable" else "alive",
        "timeout_reason": error_category if phase in {"timeout", "host_unreachable"} else None,
    }
    if run_status:
        for key in ("started_at_utc", "heartbeat_at_utc", "component_guid", "module_name"):
            if key in run_status:
                payload[key] = run_status.get(key)
    return payload


def _write_terminal_feedback(
    *,
    request_id: str,
    last_error_path: str,
    phase: str,
    error_category: str,
    run_status: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    payload = _terminal_feedback_payload(
        request_id=request_id,
        last_error_path=last_error_path,
        phase=phase,
        error_category=error_category,
        run_status=run_status,
    )
    _write_json_atomic(last_error_path, payload)
    return payload


def _build_result(
    *,
    payload: Dict[str, Any],
    port: int,
    last_error_path: str,
    tcp_result: Dict[str, Any],
) -> Dict[str, Any]:
    result = dict(payload)
    result["success"] = True
    result["port"] = int(port)
    result["last_error_path"] = last_error_path
    result["last_error_updated"] = True
    result["last_error_mtime"] = _get_mtime(last_error_path)
    result["tcp_result"] = tcp_result
    return result


def recompute_and_read(
    port: int = DEFAULT_RECOMPUTE_TCP_PORT,
    timeout_s: float = 2.0,
    wait_timeout_s: float = DEFAULT_WAIT_TIMEOUT_S,
    last_error_path: str = DEFAULT_LAST_ERROR_JSON_PATH,
    poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
) -> Dict[str, Any]:
    normalized_last_error_path = _resolve_last_error_path(last_error_path)
    project_root, _ = _normalize_last_error_path(normalized_last_error_path)
    request_id = str(uuid.uuid4())
    run_status_path = _run_status_path(project_root, request_id)

    tcp_result = _tcp_recompute(
        port=int(port),
        timeout_s=float(timeout_s),
        last_error_path=normalized_last_error_path,
        request_id=request_id,
    )
    if tcp_result.get("success") is False:
        phase = "host_unreachable" if tcp_result.get("error") in {"tcp_connect_failed", "empty_response"} else "failed"
        error_category = "host_unreachable" if phase == "host_unreachable" else str(tcp_result.get("error") or "schedule_failed")
        payload = _write_terminal_feedback(
            request_id=request_id,
            last_error_path=normalized_last_error_path,
            phase=phase,
            error_category=error_category,
            run_status=None,
        )
        return _build_result(
            payload=payload,
            port=int(port),
            last_error_path=normalized_last_error_path,
            tcp_result=tcp_result,
        )

    deadline = time.time() + float(wait_timeout_s)
    last_run_status = None

    while time.time() < deadline:
        last_error_payload = _read_last_error_payload(path=normalized_last_error_path)
        if _payload_is_terminal(last_error_payload, request_id):
            return _build_result(
                payload=last_error_payload,
                port=int(port),
                last_error_path=normalized_last_error_path,
                tcp_result=tcp_result,
            )

        run_status = _read_json_payload(run_status_path)
        if _payload_matches_request(run_status, request_id):
            last_run_status = run_status

        time.sleep(float(poll_interval_s))

    last_error_payload = _read_last_error_payload(path=normalized_last_error_path)
    if _payload_is_terminal(last_error_payload, request_id):
        return _build_result(
            payload=last_error_payload,
            port=int(port),
            last_error_path=normalized_last_error_path,
            tcp_result=tcp_result,
        )

    host_reachable = _tcp_ping(port=int(port), timeout_s=float(timeout_s))
    phase = "timeout" if host_reachable else "host_unreachable"
    error_category = "timeout" if host_reachable else "host_unreachable"
    payload = _write_terminal_feedback(
        request_id=request_id,
        last_error_path=normalized_last_error_path,
        phase=phase,
        error_category=error_category,
        run_status=last_run_status,
    )
    return _build_result(
        payload=payload,
        port=int(port),
        last_error_path=normalized_last_error_path,
        tcp_result=tcp_result,
    )


def _read_last_error_payload(
    path: str = DEFAULT_LAST_ERROR_JSON_PATH,
) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {"success": False, "error": "file_not_found", "path": path}

    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except OSError as e:
        return {"success": False, "error": "read_failed", "path": path, "detail": str(e)}
    except json.JSONDecodeError as e:
        return {"success": False, "error": "json_decode_failed", "path": path, "detail": str(e)}


def _write_response(message: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _tool_definitions() -> Dict[str, Any]:
    return {
        "tools": [
            {
                "name": "recompute_and_read",
                "description": "Trigger GH recompute via TCP and return fresh `_gh_debug/last_error.json` in one call.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "port": {"type": "integer", "default": DEFAULT_RECOMPUTE_TCP_PORT},
                        "timeout_s": {"type": "number", "default": 2.0},
                        "wait_timeout_s": {"type": "number", "default": DEFAULT_WAIT_TIMEOUT_S},
                        "last_error_path": {"type": "string", "default": DEFAULT_LAST_ERROR_JSON_PATH},
                        "poll_interval_s": {"type": "number", "default": DEFAULT_POLL_INTERVAL_S},
                    },
                    "additionalProperties": False,
                },
            },
        ],
    }


def _call_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    if name == "recompute_and_read":
        result = recompute_and_read(
            port=int(arguments.get("port", DEFAULT_RECOMPUTE_TCP_PORT)),
            timeout_s=float(arguments.get("timeout_s", 2.0)),
            wait_timeout_s=float(arguments.get("wait_timeout_s", DEFAULT_WAIT_TIMEOUT_S)),
            last_error_path=arguments.get("last_error_path", DEFAULT_LAST_ERROR_JSON_PATH),
            poll_interval_s=float(arguments.get("poll_interval_s", DEFAULT_POLL_INTERVAL_S)),
        )
    else:
        result = {"success": False, "error": "unknown_tool", "name": name}

    return {
        "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
        "isError": bool(result.get("success") is False),
    }


def main() -> None:
    server_info = {"name": "myna-recompute", "version": "0.1.0"}

    for raw_line in sys.stdin:
        raw_line = raw_line.strip()
        if not raw_line:
            continue

        try:
            req = json.loads(raw_line)
        except json.JSONDecodeError:
            continue

        req_id = req.get("id", None)
        method = req.get("method", "")
        params = req.get("params", {}) or {}

        if method == "initialize":
            protocol_version = params.get("protocolVersion", "2024-11-05")
            _write_response(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": protocol_version,
                        "capabilities": {"tools": {"listChanged": False}},
                        "serverInfo": server_info,
                    },
                }
            )
            continue

        if method == "notifications/initialized":
            continue

        if method == "tools/list":
            _write_response({"jsonrpc": "2.0", "id": req_id, "result": _tool_definitions()})
            continue

        if method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {}) or {}
            _write_response(
                {"jsonrpc": "2.0", "id": req_id, "result": _call_tool(tool_name, arguments)}
            )
            continue

        if method == "ping":
            _write_response({"jsonrpc": "2.0", "id": req_id, "result": {}})
            continue

        if req_id is not None:
            _write_response(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": "Method not found"},
                }
            )


if __name__ == "__main__":
    main()
