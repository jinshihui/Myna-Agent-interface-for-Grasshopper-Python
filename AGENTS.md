# AGENTS.md — Grasshopper Python Bridge Projects

## 1. 适用范围
- 本类项目本质上只在 Rhino + Grasshopper + Python 3 Script 内运行。
- 可以直接使用 RhinoCommon / Grasshopper / ghpythonlib；不要为了脱离 GH 运行而额外加隔离层、mock 或外部适配架构。

## 2. 目录约定
- `mymodules/`：真实算法脚本。核心计算、自检、验证都放这里。
- `gh_scripts/`：GH 接口脚本。只做输入读取、导入算法、调用算法、组织输出、写 `_gh_debug/last_error.json`。
- `_gh_debug/last_error.json`：Agent 自动调试的主反馈源。
- 禁止把具体算法逻辑或算法测试塞进 `gh_scripts/`。

## 3. 默认工作流
- 用户提出需求后，Agent 默认按 Myna 桥接流程工作，不需要用户反复说明。
- Agent 默认职责：
  - 在 `mymodules/` 新建或修改算法脚本
  - 在 `gh_scripts/` 新建或修改接口脚本
  - 补最小但有效的自检
  - 必要时配置本项目 `.venv` 和依赖
- 依赖只安装到本项目 `.venv`，优先使用 `uv`。

## 4. 自动调试闭环
- 优先通过 `recompute_and_read(...)` 触发 GH 重算并读取最新 `_gh_debug/last_error.json`。
- 每轮至少检查：
  - `ok`
  - `traceback_tail`
  - `inputs_debug`
  - `outputs_debug`
  - `validation`
- 循环规则：
  - `ok=false`：按 traceback 做最小修复后继续
  - `ok=true` 但 `validation` 未通过：继续修算法
  - `ok=true` 且 `validation` 通过，但 `outputs_debug` 不符合用户目标：继续修算法或接口输出
- 只有 `ok=true`、`validation` 通过、`outputs_debug` 符合用户要求时才停止。

## 5. 自检标准
- 自检不能只等于“不报错”。
- 自检应尽量从数学、几何或结构层面验证结果是否满足用户要求。
- 自检结果写入算法模块的 `VALIDATION_REPORT`。
- 若结果不达标，应抛出明确错误或标记失败，不要把失败结果伪装成成功。

## 6. 编码约定
- 保持最小改动；一次只解决当前目标，不顺手重构。
- `gh_scripts/` 保持直线代码；复杂逻辑进入 `mymodules/`。
- 命名使用 Python 常规风格：
  - 变量/函数/方法：`snake_case`
  - 类名：`CamelCase`
  - 常量：全大写下划线
- 输出优先使用 GH 易识别的数据类型：RhinoCommon 几何、扁平列表或 `DataTree`。
- 不要把 GH 输出做成嵌套 Python 列表，除非用户明确要求。

## 7. 新会话默认行为
- 新会话进入本项目后，默认遵守以上规则。
- 除非用户明确改规则，否则不需要再次解释这套基础流程。
