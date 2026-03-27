import json
import os
import socket
import sys
import time
from typing import Any, Dict, Optional

DEFAULT_PROJECT_ROOT = os.environ.get("GH_AUTODEBUG_PROJECT_ROOT", os.getcwd())
DEFAULT_LAST_ERROR_JSON_PATH = os.path.join(DEFAULT_PROJECT_ROOT, "_gh_debug", "last_error.json")
DEFAULT_RECOMPUTE_TCP_PORT = 17666


def _get_mtime(path: str) -> Optional[float]:
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def _tcp_recompute(port: int = DEFAULT_RECOMPUTE_TCP_PORT, timeout_s: float = 2.0) -> Dict[str, Any]:
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=float(timeout_s)) as sock:
            sock.settimeout(float(timeout_s))
            sock.sendall(b'{"type":"recompute"}\n')
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


def recompute_and_read(
    port: int = DEFAULT_RECOMPUTE_TCP_PORT,
    timeout_s: float = 2.0,
    wait_timeout_s: float = 10.0,
    last_error_path: str = DEFAULT_LAST_ERROR_JSON_PATH,
    poll_interval_s: float = 0.2,
) -> Dict[str, Any]:
    old_mtime = _get_mtime(last_error_path)
    tcp_result = _tcp_recompute(port=int(port), timeout_s=float(timeout_s))
    if tcp_result.get("success") is False:
        return {
            "success": False,
            "error": "tcp_recompute_failed",
            "port": int(port),
            "last_error_path": last_error_path,
            "tcp_result": tcp_result,
        }

    deadline = time.time() + float(wait_timeout_s)
    new_mtime = _get_mtime(last_error_path)
    while time.time() < deadline:
        if new_mtime is not None and (old_mtime is None or new_mtime > old_mtime):
            break
        time.sleep(float(poll_interval_s))
        new_mtime = _get_mtime(last_error_path)

    if new_mtime is None or (old_mtime is not None and new_mtime <= old_mtime):
        return {
            "success": False,
            "error": "wait_timeout",
            "port": int(port),
            "last_error_path": last_error_path,
            "last_error_updated": False,
            "tcp_result": tcp_result,
        }

    last_error_payload = _read_last_error_payload(path=last_error_path)
    if last_error_payload.get("success") is False:
        return {
            "success": False,
            "error": "read_last_error_failed",
            "port": int(port),
            "last_error_path": last_error_path,
            "last_error_updated": True,
            "last_error_mtime": new_mtime,
            "tcp_result": tcp_result,
            "detail": last_error_payload,
        }

    if not isinstance(last_error_payload, dict):
        return {
            "success": False,
            "error": "invalid_last_error_payload",
            "port": int(port),
            "last_error_path": last_error_path,
            "last_error_updated": True,
            "last_error_mtime": new_mtime,
            "tcp_result": tcp_result,
        }

    result = dict(last_error_payload)
    result["success"] = True
    result["port"] = int(port)
    result["last_error_path"] = last_error_path
    result["last_error_updated"] = True
    result["last_error_mtime"] = new_mtime
    result["tcp_result"] = tcp_result
    return result


def _read_last_error_payload(
    path: str = DEFAULT_LAST_ERROR_JSON_PATH,
) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {"success": False, "error": "file_not_found", "path": path}

    try:
        with open(path, "r", encoding="utf-8") as f:
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
                        "wait_timeout_s": {"type": "number", "default": 10.0},
                        "last_error_path": {"type": "string", "default": DEFAULT_LAST_ERROR_JSON_PATH},
                        "poll_interval_s": {"type": "number", "default": 0.2},
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
            wait_timeout_s=float(arguments.get("wait_timeout_s", 10.0)),
            last_error_path=arguments.get("last_error_path", DEFAULT_LAST_ERROR_JSON_PATH),
            poll_interval_s=float(arguments.get("poll_interval_s", 0.2)),
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
