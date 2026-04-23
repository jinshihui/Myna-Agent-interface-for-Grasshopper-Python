[简体中文](./README.md) | [English](./README.en.md)

# Myna

Myna 是一个让 Codex/Agent 自动编写、运行、调试 Grasshopper Python 3 Script 的本地工具链。

你可以把它理解成：

- 你在 Grasshopper 里准备输入、输出和一个 Python 3 Script 组件。
- Agent 在本地项目里写 Python 算法。
- Agent 触发 Grasshopper 重算。
- Grasshopper 把输入、输出、报错、验证结果写回 JSON。
- Agent 读取结果，继续修代码，直到结果通过。

适合场景：

- 在 Grasshopper 里新写 Python 算法。
- 自动调试已有 Python 3 Script。
- 让 Agent 根据 GH 输入输出反复修正代码。
- 需要把 Python traceback、GH runtime message、输入输出快照统一回传给 Agent。

![](<./00assets/README_2026-04-23-22-58-07.png>)

## 你需要准备什么

软件：

- Rhino 8
- Grasshopper
- Grasshopper `Python 3 Script` 组件
- Codex 或其他能运行本仓库 Agent workflow 的环境
- Python 与 `uv`，用于 Agent 侧工具运行；普通 Grasshopper 用户通常不需要手动操作

本项目组件：

- `Myna.gha`：Grasshopper 里的重算服务器组件。
- `local_bridge.py`：Agent 侧触发 Grasshopper 重算并读取结果的脚本。
- `gh_entry_template.py`：粘贴到 GH Python 3 Script 里的入口脚本模板。
- `mymodules/*.py`：你的真实算法代码。

## 项目目录

推荐每个项目使用下面结构：

```text
<PROJECT_ROOT>/
  .agents/
    skills/
      gh-auto-debug/
  _gh_debug/
  gh_scripts/
  mymodules/
  .venv/             # 可选，需要第三方 Python 包时才需要
```

目录用途：

- `_gh_debug/`：Myna 写入请求、运行状态、错误和调试 JSON。
- `gh_scripts/`：保存粘贴到 GH Python 3 Script 的入口脚本。
- `mymodules/`：保存真实算法模块。
- `.venv/`：可选的项目依赖环境；只在算法需要额外 Python 包时使用。

## 安装

### 1. 安装 Myna.gha

把 `Myna.gha` 复制到 Grasshopper Libraries 目录：

```text
C:\Users\<你的用户名>\AppData\Roaming\Grasshopper\Libraries\
```

复制后重启 Rhino 和 Grasshopper。

### 2. Python 与依赖环境

本项目的桥接脚本只需要一个 Python 解释器，用来运行 `local_bridge.py`。

如果电脑没有本地或全局 Python 解释器，可以对 Agent 说：

```text
请帮我检查并安装运行 Myna local_bridge.py 所需的本地 Python 环境。
```

算法脚本会在 Grasshopper 的 Python 3 Script 组件里运行。只使用 Rhino/Grasshopper 自带功能时，不需要安装虚拟环境。

只有当算法需要额外第三方库时，才需要配置本地虚拟环境，例如：

- `numpy`
- `scipy`
- `shapely`
- 其他 pip 包

需要第三方库时，可以让 Agent 配置本地 `.venv` 并安装依赖：

```text
这个算法需要 scipy。请帮我在当前项目里安装依赖，并继续用 Myna 调试。
```

GH 入口脚本会自动加载 `<PROJECT_ROOT>\mymodules`；如果存在 `.venv`，也会自动加载其中的依赖。

### 3. 打开项目文件夹

在 Codex 或 VS Code 里直接打开本项目文件夹即可。

项目文件夹里应包含：

- `.agents/skills/gh-auto-debug/`
- `mymodules/`
- `gh_scripts/`
- `_gh_debug/`


## Grasshopper 配置

![](<./00assets/README_2026-04-23-22-11-13.png>)

### 1. 放置组件

在 Grasshopper 画布中至少放两个组件：

1. `Myna Recompute Server`
2. `Python 3 Script`

建议把这两个组件放到同一个 Group，并且这个 Group 里只放这两个核心组件。这样 Myna 能稳定找到目标 Python 组件。

### 2. 配置 Myna Recompute Server

默认配置为，一般不需要改动：

- `Run = True`
- `Port = 17666`

状态输出应类似：

```text
listening 127.0.0.1:17666 target=Py3
```

其中 `target=Py3` 表示已经找到目标 `Python 3 Script` 组件。若显示 `target=no-group`、`target=group-no-target` 或 `target=not-found:...`，说明 Myna 还没有定位到要重算的 Python 组件。

### 3. 配置 Python 3 Script

推荐先把入口脚本模板.agents\skills\gh-auto-debug\templates\gh_entry_template.py复制到项目目录：

例如保存为：

```text
gh_scripts\gh_entry_template_20260423.py
```

然后在 Grasshopper 里：

1. 放置 `Read File` 组件。
2. 让 `Read File` 读取 `gh_scripts\gh_entry_template_20260423.py`。
3. 把 `Read File` 的文本输出接到 Python 3 Script 的 `script` 输入。
4. 把 Python 3 Script 的 `script` 输入语言设置为 Python 3。

### 4. 配置输入输出端口

Python 3 Script 默认使用：

- 输入：`x`, `y`, `z`, `u`, `v` 等
- 输出：`a`, `b`, `c`, `d`, `e` 等

你只需要告诉 Agent 每个端口代表什么。例如：

```text
x = 自由曲面 srf
y = 曲面上的两个端点
a = 测地线曲线
```



## Agent 怎么使用

### 新建算法
推荐这样提需求：

```text
请使用 myna。
输入：
x = 自由曲面 srf
y = 曲面上的两个端点
输出：
a = 以 y 为端点、位于 x 上的测地线曲线
要求：
请新建算法脚本，修改 GH 入口脚本，并用 Myna 自主重算调试，直到算法正确、精度合理。
```

Agent 通常会做这些事：

1. 在 `mymodules/` 新建或修改算法脚本。
2. 只修改 `gh_scripts/*.py` 入口脚本里的 Agent 改动区。
3. 调用 `recompute_and_read(...)` 触发 Grasshopper 重算。
4. 读取 `_gh_debug/last_error.json`。
5. 根据错误、输入快照、输出快照和验证结果继续修正。
6. 直到输出符合要求。

入口脚本只负责接线和回写调试信息，真实算法应该放在 `mymodules/*.py`。


### 修已有算法

```text
请使用 myna。
只改 mymodules\xxx.py 和必要的入口脚本接线。
当前问题：
输入为空时报错。
要求：
空输入返回空输出，不要让 GH 组件报错。请用 Myna 自主验证。
```


## 文件说明

```text
.agents\skills\gh-auto-debug\local_bridge.py
```

Agent 侧调用脚本，提供 `recompute_and_read(...)`。

```text
.agents\skills\gh-auto-debug\local_project_env.py
```

可选工具：当算法需要第三方 Python 包时，用来创建项目 `.venv` 和安装依赖。

```text
.agents\skills\gh-auto-debug\templates\gh_entry_template.py
```

GH Python 3 Script 入口模板。

```text
_gh_debug\last_error.json
```

每轮调试的最终结果。

```text
_gh_debug\python_payload_<component-guid>.json
```

Python 入口脚本写出的 sidecar。

```text
_gh_debug\request_context_<component-guid>.json
```

Myna 给 Python 入口脚本写入的本轮请求信息。

```text
_gh_debug\run_status_<request-id>.json
```

Python 入口脚本运行期间的 heartbeat 状态。

## 当前已验证的链路

当前项目已经测试过常见调试场景。正常情况下，Agent 可以触发 Grasshopper 重算、读取结果，并继续修改算法。

即使出现下面这些问题，Myna 也可以返回有用信息，帮助 Agent 判断下一步该做什么：

- 输入线接错。
- Python 组件没有正确读取入口脚本。
- 脚本语言或文本编码设置不对。
- 算法运行失败并报错。
- 算法运行时间太长。
- 上一轮计算还没结束，又触发了下一轮。
- Grasshopper solver 被关闭。
- Rhino 或 Myna Server 没有运行。

这些情况不会只留下一个模糊的“失败”。Myna 会尽量返回输入快照、输出快照、错误位置、运行状态或连接状态，让 Agent 可以继续完成调试链路。

## 当前约束

- 默认只使用 `Myna.gha` TCP 重算和 `recompute_and_read(...)`。
- 算法代码放在 `mymodules/*.py`。
- GH 入口脚本只做导入、调用、异常捕获和调试回写。
- 如果需要第三方 Python 包，依赖安装到项目 `.venv`。
- 不在 GH 入口脚本里直接写大型算法。
