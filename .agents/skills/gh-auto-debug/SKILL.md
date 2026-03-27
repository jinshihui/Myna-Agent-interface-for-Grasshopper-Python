---
name: myna
description: "Myna 是 Grasshopper Python 的 agent interface。用 Myna.gha + recompute_and_read 驱动 GH Python Script 的编写、重算、回读与迭代。"
---

# Myna

Agent interface for Grasshopper Python

## 何时使用

- 用户要在 Grasshopper Python 3 Script 中新写算法。
- 用户要让 Agent 自动调试 GH Python 脚本。
- 用户已经安装或准备安装 `Myna.gha`，并希望形成稳定的“修改算法 -> 触发 GH 重算 -> 回读结果 -> 继续迭代”闭环。

## 目标

- Agent 只通过一次 MCP 工具调用 `recompute_and_read(...)` 触发本轮 GH 重算并回读 `_gh_debug/last_error.json`。
- 真正的算法放在 `<PROJECT_ROOT>/mymodules/*.py`。
- GH 入口脚本只负责导入算法、调用算法、组织输出、写 `last_error.json`。
- 每轮结束后，Agent 必须同时检查：
 - `ok`
 - `validation`
 - `outputs_debug`
- 只有当运行不报错、算法自检通过、`outputs_debug` 与用户目标一致时才停止。

## 内置文件

- `local_bridge.py`
 - stdio MCP server
 - 提供 `recompute_and_read`
- `local_project_env.py`
 - 为 `<PROJECT_ROOT>` 创建与 Rhino Python 版本一致的 `.venv`
 - 优先 `uv`
- `templates/gh_entry_template.py`
 - GH Python 组件入口模板
 - 默认由 Agent 修改其中的“Agent 改动区”
- `templates/mymodule_template.py`
 - `mymodules/*.py` 算法模板
 - 默认由 Agent 复制后改成具体算法
- `local_gh_entry_20251229.py`
 - 完整参考入口
 - 用于查看更完整的 `last_error.json` 字段组织方式

## 默认约束

- 不保留旧的 Timer / 命令文件触发逻辑。
- 只使用 `Myna.gha` TCP 重算 + `recompute_and_read(...)` 这一条当前链路。
- 依赖默认安装到 `<PROJECT_ROOT>/.venv`，不要装到系统全局 Python。
- 不使用 Rhino `# venv:` 作为当前默认开发链路。
- 不把具体算法写进 GH 入口脚本。

## 前置条件

Agent 开始工作前，默认假设用户已经或将会完成这些准备：

1. 安装 `Myna.gha`。
2. 在 GH 画布放置 `Myna Recompute Server`。
3. 在 Python 3 Script 组件粘贴 `templates/gh_entry_template.py`。
4. 设置 `GH_AUTODEBUG_PROJECT_ROOT`，使 GH 入口与 MCP bridge 指向同一个项目根目录。
5. `<PROJECT_ROOT>` 至少包含：
 - `mymodules/`
 - `_gh_debug/`

如果 `.venv` 尚未准备好，先运行：

```powershell
python <skill_path>/local_project_env.py --project-root <PROJECT_ROOT>
```

## Agent 工作流

### 1. 接收用户目标

用户通常会描述：

- 要实现什么算法
- GH 输入端口 `x/y/z/...` 分别代表什么
- GH 输出端口 `a/b/c/...` 应该返回什么
- 结果应满足什么几何、数值或结构要求

Agent 应把这些要求翻译成：

- 一个 `mymodules/<algo>.py`
- 一段 GH 入口脚本接线
- 一组最小自检
- 必要的本地 `.venv` 和依赖安装动作

### 2. 新建或修改算法脚本

默认从 `templates/mymodule_template.py` 起步，在 `<PROJECT_ROOT>/mymodules` 新建算法文件。

算法脚本应遵守：

- 提供清晰稳定的入口
 - 类入口，例如 `YourCalculator(...)`
 - 或函数入口，例如 `solve(...)`
- 把真实算法逻辑放在算法脚本内
- 不依赖 GH 入口脚本承载算法细节
- 默认提供：
 - `ENABLE_VALIDATION`
 - `VALIDATION_REPORT`

参考完整示例：

- [freeform_curve_curvature_20251229.py](/f:/ghscriptuv/mymodules/freeform_curve_curvature_20251229.py)

### 2.5 配置项目 `.venv` 与依赖

当算法需要第三方依赖时，这也是 Agent 的默认职责，不需要用户手工处理。

默认策略：

- 依赖安装到 `<PROJECT_ROOT>/.venv`
- 优先 `uv`
- 若本机无 `uv`，退回 `python -m venv` / `pip`
- `.venv` 的 Python 版本尽量与 Rhino Python 一致

推荐顺序：

1. 先运行：

```powershell
python <skill_path>/local_project_env.py --project-root <PROJECT_ROOT>
```

2. 需要安装包时优先运行：

```powershell
python <skill_path>/local_project_env.py --project-root <PROJECT_ROOT> <package...>
```

3. 仅在 `local_project_env.py` 不能满足时，再手动使用 `uv` / `pip`

Agent 不应默认把依赖装到：

- 系统全局 Python
- Rhino 安装目录
- 其他与当前项目无关的环境

### 3. 给算法补自检

Agent 在新建或修改算法脚本时，默认要同时补最小自检。

自检要求：

- 直接围绕本轮输出写
- 能回答“结果是否真的达标”
- 不写空壳测试

常见方式：

- 与 RhinoCommon 或参考实现做数值对照
- 检查几何合法性
- 检查输出尺寸、树结构、分支数
- 检查误差是否落在阈值内
- 检查是否满足用户明确要求的目标值或目标形态

自检结果应优先写入 `VALIDATION_REPORT`，推荐结构至少包含：

- `passed`
- `checks`
- 关键误差值或统计量
- 容差信息

如果自检失败代表本轮结果不可接受，优先直接抛出异常，让 `ok=false`。

### 4. 修改 GH 入口脚本

默认以 `templates/gh_entry_template.py` 作为 GH 入口模板。

Agent 只改模板中的“Agent 改动区”：

- 选择算法模块名
- 导入并热重载算法模块
- 调用算法入口
- 将结果接到 `a/b/c/d/e`

不要改掉这些稳定能力：

- `<PROJECT_ROOT>/.venv` 的 `site-packages` 注入
- `<PROJECT_ROOT>/mymodules` 注入
- `_gh_debug/last_error.json` 写入
- `validation` / `outputs_debug` 回写

### 5. 执行循环

每轮默认执行：

1. 只做当前最小改动
2. 调 `recompute_and_read(wait_timeout_s=10)`
3. 读取返回的 `last_error.json`
4. 判断：
 - `ok`
 - `error_category`
 - `error_location`
 - `traceback_tail`
 - `validation`
 - `outputs_debug`
5. 继续下一轮最小修复

### 6. 停止条件

只有全部满足才停止：

- `ok=true`
- `validation` 显示通过，或没有自检失败信号
- `outputs_debug` 与用户目标一致
- 本轮没有新增回归

## last_error.json 约定

Agent 应默认把这些字段视为主反馈源：

- `ok`
- `error_category`
- `error_location`
- `traceback_tail`
- `inputs_debug`
- `outputs_debug`
- `validation`

约定：

- 算法脚本的 `VALIDATION_REPORT` 应写回 `last_error.json["validation"]`
- 关键结果应尽量写进 `outputs_debug`
- 若用户目标是“数值正确”或“结构正确”，Agent 必须优先比对 `outputs_debug` 和 `validation`

## 依赖策略

- 第三方依赖默认安装到 `<PROJECT_ROOT>/.venv`
- 优先：

```powershell
python <skill_path>/local_project_env.py --project-root <PROJECT_ROOT> <package...>
```

- 优先 `uv`
- 若本机无 `uv`，退回 `python -m venv` / `pip`
- 不修改 Rhino 安装目录
- 不修改系统全局 Python

## 安全规则

- 不把具体算法塞进 GH 入口脚本。
- 不移除 `_gh_debug/last_error.json` 写入机制。
- 不改入口脚本“Agent 改动区”之外的稳定逻辑，除非用户明确要求。
- 每轮优先只改一个问题，避免跨文件顺手重构。

## Agent 默认理解

当用户说“请编写某某算法，输入为 x/y/z，输出为 a/b/c”时，Agent 默认应：

1. 在 `<PROJECT_ROOT>/mymodules` 新建算法脚本
2. 从 `templates/mymodule_template.py` 起步
3. 当算法需要时，配置 `<PROJECT_ROOT>/.venv` 并安装必要依赖，优先 `uv`
4. 补最小自检并写 `VALIDATION_REPORT`
5. 修改 GH 入口脚本“Agent 改动区”接入算法
6. 调 `recompute_and_read(...)`
7. 依据 `validation` 和 `outputs_debug` 持续迭代直到通过
