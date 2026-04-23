# 更新日志

## 2026-04-23

### 新增

- 更新 `.agents/skills/gh-auto-debug/local_bridge.py`，为每轮重算生成 `request_id`，默认等待时间提升到 `60s`，并在超时或宿主失联时兜底回写结构化 `last_error.json`。
- 更新 `gh_components/myna/GH_RecomputeServerComponent.cs`，增加 `run_in_progress` 单飞保护、`request_context_<component-guid>.json` 写入，以及 `request_id` / `phase` / `terminal` 等终态字段合并。
- 更新 `.agents/skills/gh-auto-debug/templates/gh_entry_template.py` 与 `gh_scripts/gh_entry_template_20260403.py`，增加 `run_status_<request-id>.json` heartbeat、`request_id` / `phase` / `terminal` 回写。
- 精简最终 `last_error.json`，移除 `python_payload`、`out_text`、`inputs_debug.script`、`outputs_debug.out`。
- 更新 `.agents/skills/gh-auto-debug/SKILL.md`，同步当前链路的 `request_id`、heartbeat、`timeout` / `host_unreachable` / `run_in_progress` 协议与默认入口脚本路径说明。
- 完成当前 Myna 调试链路验证。验证链路可在正常运行、输入接错、脚本语言错误、脚本文本/编码错误、Python 算法报错、算法长时间运行、重复触发重算、Grasshopper solver 关闭、Rhino/Myna Server 关闭等情况下返回有用反馈。
- 更新 `.agents/skills/gh-auto-debug/README.md`，补充面向普通用户的安装、配置和排错说明。

### 说明

- `local_bridge.py` 只需要本地 Python 解释器。
- 算法脚本默认在 Grasshopper Python 3 Script 中运行。
- 只有算法需要 `numpy`、`scipy` 等第三方库时，才需要配置项目 `.venv`。


## 2026-04-03

### 链路重构

- 将 Myna 调试链路从“入口脚本单点负责”重构为“`.gha` 负责 GH/Rhino 侧采集，Python 入口只负责 Python 内部调试信息”的分层闭环。
- 打通 `recompute_and_read(...)` → `local_bridge.py` → `Myna.gha` → GH Python 入口脚本 → 算法模块 → sidecar → `last_error.json` 的主链路，稳定支持端到端回传。
- `.gha` 侧补齐目标组件定位、输入输出摘要、runtime message、GH/Rhino 环境采集与 sidecar 合并；Python 入口侧收敛为导入算法、记录 traceback、分类 `error_category`、写 `validation` / `python_debug`。
- 统一采用 `project_root + last_error_relpath` 路径协议，固定 sidecar 位置，并处理 UTF-8/BOM 与摘要裁剪问题，降低路径漂移、时序抖动和上下文污染。
