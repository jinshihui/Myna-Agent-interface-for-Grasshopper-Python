---
name: myna
description: "Myna 是 Grasshopper Python 的 agent interface。用 Myna.gha + recompute_and_read 驱动 GH Python Script 的编写、重算、回读与迭代。"
---

# Myna

Agent interface for Grasshopper Python。

## 何时使用

- 用户要在 Grasshopper Python 3 Script 中新写算法。
- 用户要让 Agent 自动调试 GH Python 脚本。
- 用户已经安装或准备安装 `Myna.gha`，并希望形成“改算法 -> 触发 GH 重算 -> 回读结果 -> 继续迭代”的闭环。

## 目录与模板约定

项目根目录默认为 `<PROJECT_ROOT>`，由 `GH_AUTODEBUG_PROJECT_ROOT`、GH 文档路径或当前工作目录自动推断。GH 入口、bridge、算法代码必须指向同一个项目根目录。

默认目录和文件：

- `<PROJECT_ROOT>/mymodules/*.py`：真实算法模块位置。
- `<PROJECT_ROOT>/gh_scripts/*.py`：GH Python 入口脚本默认位置。
- `<PROJECT_ROOT>/_gh_debug/`：自动调试运行文件与最终反馈文件目录。
- `<PROJECT_ROOT>/.venv`：项目依赖环境，默认依赖安装位置。
- `templates/gh_entry_template.py`：GH 入口脚本模板。
- `templates/mymodule_template.py`：算法模块模板。

默认修改范围：

- 优先修改 `<PROJECT_ROOT>/mymodules/*.py`。
- 需要接线时，只修改 `<PROJECT_ROOT>/gh_scripts/*.py` 的 Agent 改动区。
- 不要把具体算法塞进 GH 入口脚本。
- 不要破坏 `.venv` 注入、`mymodules` 注入、`request_id` / heartbeat、Python sidecar 写入和 `validation` / `python_debug` 回写。

依赖约定：

- 依赖默认安装到 `<PROJECT_ROOT>/.venv`，优先使用 `uv`。
- 不要安装到系统全局 Python。
- 当前默认开发链路不使用 Rhino `# venv:`。

如果 `.venv` 尚未准备好，先运行：

```powershell
python <skill_path>/local_project_env.py --project-root <PROJECT_ROOT>
```

安装额外依赖时运行：

```powershell
python <skill_path>/local_project_env.py --project-root <PROJECT_ROOT> <package...>
```

## 前置条件

Agent 开始工作前，默认假设用户已完成这些准备：

1. 安装 `Myna.gha`。
2. 在 GH 画布放置 `Myna Recompute Server`。
3. 在 Python 3 Script 组件粘贴或导入入口脚本；入口脚本默认位置为 `<PROJECT_ROOT>/gh_scripts/*.py`，以 `templates/gh_entry_template.py` 为模板。
4. `Myna Recompute Server` 与目标 Python 组件放在同一个 Group，且该 Group 最好只放这两者。
5. 设置 `GH_AUTODEBUG_PROJECT_ROOT`，使 GH 入口与 MCP bridge 指向同一个项目根目录。
6. `<PROJECT_ROOT>` 至少包含 `mymodules/` 和 `_gh_debug/`。

## 链路职责

当前只使用 `Myna.gha` TCP 重算 + `recompute_and_read(...)` 这条链路。

bridge 负责：

- 每轮生成 `request_id`。
- 通过 TCP 向 `.gha` 发送 `recompute`。
- 默认等待本轮终态结果 `60s`。
- 只认 `request_id` 匹配且 `terminal=true` 的 `last_error.json`。
- 若等待上限内没有本轮终态，则补写结构化终态：
  - 宿主仍可 `ping`：`phase=timeout`
  - 宿主不可 `ping`：`phase=host_unreachable`

`.gha` 负责：

- 接收 `recompute`。
- 定位目标组件。
- 写 `request_context_<component-guid>.json`。
- 采集 `runtime_messages`、`inputs_debug`、`outputs_debug`、GH/Rhino 环境信息。
- 合并 Python sidecar。
- 写最终 `_gh_debug/last_error.json`。
- 提供单飞保护：上一轮尚未结束时，新一轮 `recompute` 返回 `run_in_progress`。

GH 入口脚本负责：

- 注入 `.venv` 与 `mymodules`。
- 读取 `request_context_<component-guid>.json`。
- 写 `run_status_<request-id>.json` 并每秒 heartbeat。
- 导入并调用算法模块。
- 捕获 Python traceback。
- 写 `python_payload_<component-guid>.json`，其中包含 `validation`、`python_debug`、`request_id`、`phase`、`terminal` 等 Python 侧反馈。

## 运行文件

当前链路里有 4 个关键文件：

- `request_context_<component-guid>.json`
- `run_status_<request-id>.json`
- `python_payload_<component-guid>.json`
- `last_error.json`

默认时序：

1. bridge 生成 `request_id`。
2. `.gha` 接收 `recompute`，写 `request_context`。
3. 入口脚本读取 `request_context`，立刻写 `run_status`，`phase=running`。
4. 入口脚本后台 heartbeat 每秒更新一次 `run_status`。
5. 算法结束后，入口脚本写 `python_payload`，其中带 `request_id`、`phase=succeeded|failed`、`terminal=true`。
6. `.gha` 在 `SolutionEnd` 合并 GH 反馈与 `python_payload`，写最终 `last_error.json`。
7. 若 bridge 在等待上限内没等到匹配本轮 `request_id` 的终态，由 bridge 兜底写 `timeout` 或 `host_unreachable`。

## Agent 工作流程

把用户目标翻译成 4 件事：

- `mymodules/<algo>.py`：真实算法。
- `gh_scripts/*.py`：GH 入口脚本接线。
- `VALIDATION_REPORT` / `DEBUG_PAYLOAD`：验证与调试反馈。
- 必要依赖：安装到 `<PROJECT_ROOT>/.venv`。

默认实现方式：

- 算法模块从 `templates/mymodule_template.py` 起步。
- 入口脚本从 `templates/gh_entry_template.py` 起步。
- 每次只做当前最小改动。
- 根据反馈只修一个当前最关键的问题。

当用户说“请编写某某算法，输入为 x/y/z，输出为 a/b/c”时，Agent 默认应：

- 在 `<PROJECT_ROOT>/mymodules` 新建或修改算法脚本。
- 修改 GH 入口脚本的 Agent 改动区接入算法。
- 同时补正式自检与交叉验算。
- 写入 `VALIDATION_REPORT` / `DEBUG_PAYLOAD`。
- 用 `recompute_and_read(...)` 依据 `phase`、`validation` 和 `outputs_debug` 持续迭代直到通过。

## 执行循环

每轮默认执行：

1. 只做当前最小改动。
2. 调 `recompute_and_read(wait_timeout_s=60)`；若用户明确知道算法更慢，可按需调大。
3. 读取返回的 `_gh_debug/last_error.json`。
4. 优先判断 `request_id`、`phase`、`terminal`、`ok`、`error_category`。
5. 再判断 `error_location`、`traceback_tail`、`runtime_messages`、`inputs_debug`、`outputs_debug`、`validation`、`python_debug`、`python_payload_fresh`。
6. 根据反馈只修一个当前最关键的问题。

长耗时与并发约束：

- 当前默认支持 `<60s` 的长计算；若算法更慢，应显式提高 `wait_timeout_s`。
- 当前 heartbeat 主要用于运行可见性和 timeout 上下文，不会自动无限续命等待。
- 若上一轮还没结束，新的 `recompute` 会返回 `run_in_progress`。
- Agent 在长任务场景下应遵循“单轮串行”：先消费本轮结果，再触发下一轮。

停止条件：

- `phase=succeeded`
- `ok=true`
- `validation.passed=true`，或存在等价的明确通过信号
- `outputs_debug` 与用户目标一致
- 交叉验算通过
- 本轮没有新增回归

## 验证要求

这是本 skill 的核心要求。`ok=true` 只表示“运行成功”，不表示“算法正确”。

`VALIDATION_REPORT` 推荐至少包含：

- `passed`
- `checks`
- `tolerance`
- `max_error` 或其他关键误差值
- `method_summary`

`DEBUG_PAYLOAD` 适合包含：

- 中间量摘要
- 误差统计
- 参考实现结果摘要
- 关键样本对比

禁止只用主算法自己的中间量做同源自证。Agent 默认应尽量构造另一条验证路径，至少满足下面之一：

- 用另一种数学公式、推导或实现方式交叉验算。
- 用更朴素但可信的基线算法交叉验算。
- 用解析解、简单特例、极限情形做验算。
- 用守恒量、不变量、反算或残差检查做验算。
- 用采样回代验证输出是否真的满足输入约束。

优先级：

1. 独立算法或独立公式
2. 朴素基线算法
3. 特例/不变量/残差

若主算法是几何或数值算法，Agent 默认应优先做这些事：

- 为简单输入构造可手算或可预期的特例。
- 额外写一个更慢但更直接的参考实现，用于少量样本比对。
- 比较主算法输出与参考实现输出的误差。
- 明确误差容限，并解释该容限为何合理。

若无法构造完全独立的参考实现，Agent 也不能跳过验证；应退而求其次组合使用：

- 特例检查
- 边界输入检查
- 量纲/结构检查
- 残差检查
- 输出回代检查

只有同时满足下面条件，才算“算法正确到可接受”：

- 运行不报错。
- `validation.passed = true`。
- `outputs_debug` 与用户要求一致。
- 交叉验算没有发现算法性错误。
- 关键误差在明确给出的合理容差内。

如果自检或交叉验算失败，应优先抛出异常，例如：

```python
raise ValueError("VALIDATION_FAIL: max_error exceeds tolerance")
```

这会让入口把本轮归类为 `validation_error`。如果交叉验算失败，即使 `ok=true`，Agent 也不能停止，应继续修复算法。

## last_error.json 反馈字段

Agent 应默认把这些字段视为主反馈源：

- `request_id`
- `phase`
- `terminal`
- `ok`
- `error_category`
- `error_location`
- `traceback_tail`
- `runtime_messages`
- `inputs_debug`
- `outputs_debug`
- `validation`
- `python_debug`
- `python_payload_fresh`

反馈源总表：

| 字段/反馈源 | 来源 | 类型 | 意义 |
| --- | --- | --- | --- |
| `request_id` | bridge 发起、入口脚本回写、`.gha` 合并或 bridge 兜底 | 轮次标识 | 标记这次 `recompute` 属于哪一轮。bridge 只认 `request_id` 匹配且 `terminal=true` 的终态结果。 |
| `phase` | Python sidecar、`.gha` 合并或 bridge 兜底 | 运行阶段 | 常见值：`running`、`succeeded`、`failed`、`timeout`、`host_unreachable`。适合先判断这轮到底是正常结束、超时，还是宿主失联。 |
| `terminal` | Python sidecar、`.gha` 合并或 bridge 兜底 | 终态标志 | 为 `true` 表示这轮反馈已经收敛到可消费终态。 |
| `ok` | `.gha` 汇总 GH runtime messages 与 Python sidecar 的 `ok` 后得出，或由 bridge 兜底写 `false` | 合并后的总判断 | 最终是否成功运行。不是算法正确性的充分条件。 |
| `error_category` | Python sidecar、`.gha` 退化分类或 bridge 兜底 | 合并后的错误分类 | 用于快速决定下一步改哪一层：导入、输入、类型、几何、验证失败、组件运行时问题，还是链路级 timeout / 宿主失联。 |
| `error_location` | Python 入口脚本根据 traceback 提取，`.gha` 合并 | Python 错误定位 | 通常是 `mymodules/*.py` 的文件名和行号。 |
| `traceback_tail` | Python 入口脚本写 sidecar，`.gha` 合并 | Python 异常尾部 | Python 组件执行失败时的最后一段 traceback。用于直接定位算法或导入错误。 |
| `runtime_messages` | `.gha` 直接从目标 GH 组件采集 | GH 运行时消息 | 对应组件在 Grasshopper 侧产生的 warning/error/info。适合判断有没有组件级报错。 |
| `inputs_debug` | `.gha` 直接采集目标组件输入端口 | 参数输入快照 | 反映本轮 `x/y/z/...` 实际进到 Python 组件里的数据形态、分支、长度和值预览。当前已过滤 `script` 输入口。 |
| `outputs_debug` | `.gha` 直接采集目标组件输出端口 | 参数输出快照 | 反映本轮 `a/b/c/...` 实际从 Python 组件流出的数据形态、分支、长度和值预览。当前已过滤 `out` 输出口。 |
| `validation` | 算法模块 `VALIDATION_REPORT`，经 Python sidecar 再由 `.gha` 合并 | 正式自检结果 | 判断“结果是否真的正确”的主反馈源。必须包含交叉验算结论，而不只是形式检查。 |
| `python_debug` | 算法模块 `DEBUG_PAYLOAD`，经 Python sidecar 再由 `.gha` 合并 | 调试补充信息 | 适合放中间量、误差统计、参考实现摘要、关键样本对比。 |
| `python_payload_fresh` | `.gha` 读取 sidecar 后写入最终 JSON | sidecar 新鲜度 | 表示本轮是否成功读到了刚生成的 Python sidecar。若为 `false`，说明 Python 反馈可能缺失或过期。 |
| `started_at_utc` / `heartbeat_at_utc` / `finished_at_utc` | 入口脚本写 `run_status` / `python_payload`，再由 `.gha` 合并；timeout 时可由 bridge 兜底带出 | 时间状态 | 用于判断本轮是否真正启动、最近一次活性时间、是否已经结束。 |
| `stdout_tail` | Python 入口脚本写 sidecar，`.gha` 合并 | Python 标准输出 | 算法或入口脚本 `print(...)` 的尾部内容。 |
| `stderr_tail` | Python 入口脚本写 sidecar，`.gha` 合并 | Python 标准错误 | Python 侧错误输出尾部。 |
| `module_name` | Python sidecar 或 bridge 从 `run_status` 带出 | Python 模块信息 | 表示本轮入口脚本实际导入了哪个算法模块。适合排查“改了文件但 GH 没用到”。 |
| `elapsed_ms` | Python sidecar，`.gha` 合并 | Python 执行耗时 | 本轮 Python 侧执行时长。 |
| `gh_environment` | `.gha` 构建 | GH 环境信息 | 描述当前 Grasshopper 文档/组件上下文，用于定位是不是文档、目标组件或画布状态的问题。 |
| `rhino_environment` | `.gha` 构建 | Rhino 环境信息 | 描述 Rhino 运行环境，用于区分宿主环境问题与算法问题。 |

判断约定：

- 不要把 `ok=true` 误判为“算法正确”；算法正确性主要看 `validation`、交叉验算和 `outputs_debug`。
- 若用户目标是“数值正确”或“结构正确”，Agent 必须优先比对 `outputs_debug` 和 `validation`。
- `phase=succeeded` / `phase=failed` 表示本轮已正常结束。
- `phase=timeout` 表示等待上限内未完成，但宿主仍可通信。
- `phase=host_unreachable` 表示 bridge 无法再与宿主通信。
- 若 `phase=timeout` 后立刻再调重算，可能先拿到 `run_in_progress`；这通常表示 GH 内上一轮还没真正释放。

## 安全规则

- 只改 `mymodules/*.py` 和 GH 入口脚本的 Agent 改动区。
- 不要把具体算法塞进 GH 入口脚本。
- 不要移除 `request_id`、`run_status` heartbeat、Python sidecar 写入机制。
- 除非用户明确要求，不改入口脚本稳定逻辑。
- 每轮只修一个当前最关键的问题。
