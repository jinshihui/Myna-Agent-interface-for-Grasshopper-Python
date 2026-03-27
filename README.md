# Myna

Agent interface for Grasshopper Python

`Myna` 让 Grasshopper 可以直接接入 Agent。

安装 `Myna.gha` 和 `gh-auto-debug` skill 之后，你可以把一个 GH Python 组件交给 Agent，让 Agent 负责：

- 编写算法
- 接入 Grasshopper
- 触发运行
- 发现错误并继续修复
- 做自检并反复迭代

你不需要自己处理桥接脚本、调试循环或算法模板对齐。

![](<./00assets/README_2026-03-28-00-03-22.png>)

## 适合做什么

- 在 Grasshopper 中快速生成新的 Python 算法
- 把现有 GH Python 脚本交给 Agent 自动调试
- 让 Agent 根据输入输出约束反复修正结果

## 安装

### 1. 安装 `Myna.gha`

把 `Myna.gha` 复制到你的 Grasshopper `Libraries` 目录，然后重启 Rhino 和 Grasshopper。

### 2. 安装 skill

把 `gh-auto-debug` 目录放到你的 Agent skill 目录中。

### 3. 配置 GH 文件

在 GH 画布中：

1. 放置 `Myna Recompute Server`
2. 放置一个 `Python 3 Script` 组件
3. 把 Myna 提供的入口模板粘贴到这个 Python 组件中
4. 把这个 GH 文件保存到你的项目工作流中

完成后，你就可以直接让 Agent 接手算法开发。

## 如何使用

你只需要告诉 Agent：

- 你要什么算法
- GH 输入端口 `x/y/z/...` 分别代表什么
- GH 输出端口 `a/b/c/...` 应该返回什么
- 结果需要满足什么要求

剩下的事情默认由 Agent 负责：

- 在 `mymodules` 中生成或修改算法脚本
- 在需要时配置当前项目的 `.venv` 并安装依赖，优先使用 `uv`
- 把算法接到 GH 入口脚本
- 运行并读取结果
- 做自检
- 持续修复直到结果达标

## 典型 Prompt

### 示例 1

```text
请使用 myna skill。
请编写一个曲线采样算法。
输入：
x = 一组 Rhino 曲线
y = 每条曲线上的采样参数列表
输出：
a = 每个采样点的切向量
b = 每个采样点的曲率
要求：
输出应保持与输入曲线数量一致，结果结构适合直接在 Grasshopper 中查看。
```

### 示例 2

```text
请使用 myna skill。
请编写一个点集包围盒分析算法。
输入：
x = 点列表
y = 是否输出中心点
z = 是否输出尺寸
输出：
a = 包围盒
b = 中心点
c = 长宽高
要求：
空输入时不要报错，输出应保持稳定。
```

### 示例 3

```text
请使用 myna skill。
请修改当前算法。
输入：
x = 基础曲线
y = 偏移距离
输出：
a = 偏移后的曲线
b = 失败信息
要求：
偏移失败时应给出清晰反馈，成功时结果应可直接用于后续 GH 组件。
```

## 适合普通用户的理解方式

`Myna` 的作用不是替代 Grasshopper，而是把 GH Python 组件变成一个可以被 Agent 持续迭代的工作目标。

你定义输入、输出和目标，Agent 负责实现、运行、检查和修复。
