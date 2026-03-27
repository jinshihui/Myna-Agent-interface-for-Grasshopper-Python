import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def _run(command):
    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def detect_rhino_python():
    base_dir = Path.home() / ".rhinocode"
    candidates = []
    if base_dir.is_dir():
        for child in base_dir.iterdir():
            if not child.is_dir():
                continue
            match = re.fullmatch(r"py(\d)(\d+)-rh(\d+)", child.name)
            python_exe = child / "python.exe"
            if match and python_exe.is_file():
                major = int(match.group(1))
                minor = int(match.group(2))
                rhino_major = int(match.group(3))
                candidates.append(
                    {
                        "runtime_dir": str(child),
                        "python_exe": str(python_exe),
                        "python_version": f"{major}.{minor}",
                        "rhino_major": rhino_major,
                    }
                )

    if not candidates:
        raise RuntimeError("No Rhino Python runtime found under ~/.rhinocode")

    candidates.sort(key=lambda item: (item["rhino_major"], item["python_version"]), reverse=True)
    selected = candidates[0]
    version_result = _run([selected["python_exe"], "--version"])
    selected["python_version_full"] = version_result["stdout"] or selected["python_version"]
    return selected


def ensure_project_env(project_root, packages):
    project_root = Path(project_root).resolve()
    venv_dir = project_root / ".venv"
    rhino_python = detect_rhino_python()
    uv_exe = shutil.which("uv")

    if uv_exe:
        create_result = _run([uv_exe, "venv", "--python", rhino_python["python_exe"], str(venv_dir)])
        manager = "uv"
    else:
        create_result = _run([rhino_python["python_exe"], "-m", "venv", str(venv_dir)])
        manager = "venv"

    if create_result["returncode"] != 0:
        return {
            "success": False,
            "step": "create_venv",
            "manager": manager,
            "project_root": str(project_root),
            "venv_dir": str(venv_dir),
            "rhino_python": rhino_python,
            "detail": create_result,
        }

    venv_python = venv_dir / "Scripts" / "python.exe"
    install_result = None
    if packages:
        if uv_exe:
            install_result = _run([uv_exe, "pip", "install", "--python", str(venv_python), *packages])
            install_manager = "uv"
        else:
            install_result = _run([str(venv_python), "-m", "pip", "install", *packages])
            install_manager = "pip"
        if install_result["returncode"] != 0:
            return {
                "success": False,
                "step": "install_packages",
                "manager": install_manager,
                "project_root": str(project_root),
                "venv_dir": str(venv_dir),
                "rhino_python": rhino_python,
                "packages": packages,
                "detail": install_result,
            }

    return {
        "success": True,
        "project_root": str(project_root),
        "venv_dir": str(venv_dir),
        "venv_python": str(venv_python),
        "rhino_python": rhino_python,
        "create_manager": manager,
        "install_manager": ("uv" if uv_exe else "pip") if packages else None,
        "packages": packages,
        "install_result": install_result,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=os.environ.get("GH_AUTODEBUG_PROJECT_ROOT", os.getcwd()))
    parser.add_argument("--detect-only", action="store_true")
    parser.add_argument("packages", nargs="*")
    args = parser.parse_args()

    if args.detect_only:
        print(json.dumps(detect_rhino_python(), ensure_ascii=False, indent=2))
        return

    result = ensure_project_env(args.project_root, args.packages)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result.get("success"):
        sys.exit(1)


if __name__ == "__main__":
    main()
