[简体中文](./README.md) | [English](./README.en.md)

# Myna

Myna is a local toolchain that lets Codex/Agents automatically write, run, and debug Grasshopper Python 3 Script components.

You can think of it like this:

- You prepare inputs, outputs, and a Python 3 Script component in Grasshopper.
- The Agent writes the Python algorithm in the local project.
- The Agent triggers a Grasshopper recompute.
- Grasshopper writes inputs, outputs, errors, and validation results back to JSON.
- The Agent reads the result and keeps fixing the code until it passes.

Good fit for:

- Writing new Python algorithms in Grasshopper.
- Automatically debugging an existing Python 3 Script.
- Letting an Agent iteratively fix code based on GH inputs and outputs.
- Returning Python tracebacks, GH runtime messages, and input/output snapshots to the Agent in one place.

![](<./00assets/README_2026-04-23-22-58-07.png>)

## What You Need

Software:

- Rhino 8
- Grasshopper
- A Grasshopper `Python 3 Script` component
- Codex, or another environment that can run the Agent workflow in this repository
- Python and `uv` for the Agent-side tools; regular Grasshopper users usually do not need to manage this directly

Project components:

- `Myna.gha`: the recompute server component inside Grasshopper.
- `local_bridge.py`: the Agent-side script that triggers Grasshopper recompute and reads the result.
- `gh_entry_template.py`: the entry script template pasted into the GH Python 3 Script component.
- `mymodules/*.py`: your actual algorithm code.

## Project Layout

Recommended structure for each project:

```text
<PROJECT_ROOT>/
  .agents/
    skills/
      gh-auto-debug/
  _gh_debug/
  gh_scripts/
  mymodules/
  .venv/             # optional, only needed when third-party Python packages are required
```

Folder purpose:

- `_gh_debug/`: Myna writes request data, runtime state, errors, and debug JSON here.
- `gh_scripts/`: stores entry scripts that are pasted into the GH Python 3 Script component.
- `mymodules/`: stores the real algorithm modules.
- `.venv/`: optional project dependency environment; only needed when the algorithm requires extra Python packages.

## Installation

### 1. Install Myna.gha

Copy `Myna.gha` into the Grasshopper Libraries folder:

```text
C:\Users\<your-user-name>\AppData\Roaming\Grasshopper\Libraries\
```

Restart Rhino and Grasshopper after copying it.

### 2. Python and dependencies

The bridge script in this project only needs a Python interpreter to run `local_bridge.py`.

If there is no local or global Python interpreter on the machine, you can ask the Agent:

```text
Please help me check and install the local Python environment required to run Myna local_bridge.py.
```

The algorithm script itself runs inside Grasshopper's Python 3 Script component. If you only use Rhino/Grasshopper built-in functionality, you do not need a virtual environment.

You only need a local virtual environment when the algorithm depends on extra third-party libraries, for example:

- `numpy`
- `scipy`
- `shapely`
- other pip packages

When third-party packages are required, you can ask the Agent to create a local `.venv` and install dependencies:

```text
This algorithm needs scipy. Please help me install the dependencies in the current project and continue debugging with Myna.
```

The GH entry script will automatically load `<PROJECT_ROOT>\mymodules`; if `.venv` exists, its dependencies will also be added automatically.

### 3. Open the project folder

Open this project folder directly in Codex or VS Code.

The project folder should contain:

- `.agents/skills/gh-auto-debug/`
- `mymodules/`
- `gh_scripts/`
- `_gh_debug/`

## Grasshopper Setup

![](<./00assets/README_2026-04-23-22-11-13.png>)

### 1. Place the components

Place at least these two components on the Grasshopper canvas:

1. `Myna Recompute Server`
2. `Python 3 Script`

It is recommended to put these two components into the same Group, and keep only these two core components inside that Group. This makes it easier for Myna to reliably locate the target Python component.

### 2. Configure Myna Recompute Server

The default configuration is usually fine:

- `Run = True`
- `Port = 17666`

The status output should look similar to:

```text
listening 127.0.0.1:17666 target=Py3
```

Here, `target=Py3` means the target `Python 3 Script` component has been found. If it shows `target=no-group`, `target=group-no-target`, or `target=not-found:...`, Myna has not located the Python component to recompute yet.

### 3. Configure Python 3 Script

It is recommended to copy the entry script template at `.agents\skills\gh-auto-debug\templates\gh_entry_template.py` into the project directory first.

For example, save it as:

```text
gh_scripts\gh_entry_template_20260423.py
```

Then in Grasshopper:

1. Place a `Read File` component.
2. Make `Read File` load `gh_scripts\gh_entry_template_20260423.py`.
3. Connect the text output of `Read File` to the `script` input of Python 3 Script.
4. Set the `script` input language of Python 3 Script to Python 3.

### 4. Configure input and output ports

Python 3 Script uses these default names:

- Inputs: `x`, `y`, `z`, `u`, `v`, and so on
- Outputs: `a`, `b`, `c`, `d`, `e`, and so on

You only need to tell the Agent what each port means. For example:

```text
x = freeform surface srf
y = two endpoints on the surface
a = geodesic curve on x using y as endpoints
```

## How the Agent Uses It

### Create a new algorithm

A recommended request looks like this:

```text
Please use myna.
Inputs:
x = freeform surface srf
y = two endpoints on the surface
Outputs:
a = geodesic curve on x using y as endpoints
Requirements:
Please create the algorithm script, update the GH entry script, and use Myna to recompute and debug autonomously until the algorithm is correct and the precision is reasonable.
```

The Agent will usually do the following:

1. Create or modify the algorithm script in `mymodules/`.
2. Only modify the Agent-editable section in the `gh_scripts/*.py` entry script.
3. Call `recompute_and_read(...)` to trigger a Grasshopper recompute.
4. Read `_gh_debug/last_error.json`.
5. Keep fixing the code based on errors, input snapshots, output snapshots, and validation results.
6. Stop only when the output matches the requirement.

The entry script is only responsible for wiring, invoking the algorithm, and writing debug information back. The real algorithm should live in `mymodules/*.py`.

### Fix an existing algorithm

```text
Please use myna.
Only modify mymodules\xxx.py and the necessary entry-script wiring.
Current issue:
It crashes when the input is empty.
Requirements:
Empty input should return empty output, and the GH component must not throw an error. Please validate it with Myna autonomously.
```

## File Reference

```text
.agents\skills\gh-auto-debug\local_bridge.py
```

Agent-side script that provides `recompute_and_read(...)`.

```text
.agents\skills\gh-auto-debug\local_project_env.py
```

Optional helper for creating the project `.venv` and installing dependencies when the algorithm requires third-party Python packages.

```text
.agents\skills\gh-auto-debug\templates\gh_entry_template.py
```

GH Python 3 Script entry template.

```text
_gh_debug\last_error.json
```

Final result of each debug round.

```text
_gh_debug\python_payload_<component-guid>.json
```

Sidecar JSON written by the Python entry script.

```text
_gh_debug\request_context_<component-guid>.json
```

Request context for the current round, written by Myna for the Python entry script.

```text
_gh_debug\run_status_<request-id>.json
```

Heartbeat status while the Python entry script is running.

## Currently Verified Flow

This project has already been tested against common debugging scenarios. Under normal conditions, the Agent can trigger Grasshopper recompute, read the result, and continue modifying the algorithm.

Even when the following problems occur, Myna can still return useful information to help the Agent decide the next step:

- Input wires are connected incorrectly.
- The Python component is not reading the entry script correctly.
- The script language or text encoding is configured incorrectly.
- The algorithm fails and raises an error.
- The algorithm takes too long to run.
- A new round is triggered before the previous one has finished.
- The Grasshopper solver is disabled.
- Rhino or the Myna Server is not running.

These cases do not end with a vague "failed" state. Myna tries to return input snapshots, output snapshots, error locations, runtime state, or connection state so the Agent can keep driving the debugging loop.

## Current Constraints

- By default, only `Myna.gha` TCP recompute and `recompute_and_read(...)` are used.
- Algorithm code belongs in `mymodules/*.py`.
- The GH entry script should only handle imports, invocation, exception capture, and debug write-back.
- If third-party Python packages are needed, install them into the project `.venv`.
- Do not write large algorithms directly inside the GH entry script.
