# LangGraph Email Agent · DeepSeek 学习复现

基于 [LangChain agents-from-scratch](https://github.com/langchain-ai/agents-from-scratch) 的学习复现。此仓库仅整理已学习的基础 Agent、评测和人工介入（HITL）三个章节，以及它们运行需要的公共模块与测试。保留上游 MIT 版权声明。

## 本次公开范围

- `notebooks/agent.ipynb`：邮件分类、工具调用与回复子图。
- `notebooks/evaluation.ipynb`：工具检查、分类评测、LLM-as-Judge。
- `notebooks/hitl.ipynb`：人工介入章节文件；当前学习到批准工具调用，并开始学习编辑参数。
- `src/email_assistant/email_assistant.py` 与 `email_assistant_hitl.py`：上述助手的 Python 实现。
- 运行必需的模型适配、提示词、状态结构、工具、格式化函数、示例数据和测试。
- 三个 Notebook 引用的上游课程插图。

记忆章节、Gmail 集成、定时任务、独立 LangGraph 101 教程、上游自动化工作流和无关测试未纳入此次发布。公共模块中可能保留未使用的上游辅助定义；它们不代表本学习版已实现或验证对应扩展功能。HITL 中的检查点用于保存执行状态，属于本次学习范围。

## 本学习版改动

- `models.py` 集中加载项目根目录 `.env`，使用 DeepSeek 的 OpenAI 兼容接口。
- 适配结构化输出和工具调用；当前模型配置关闭 thinking。
- 提供 `run_demo.py` 普通脚本入口。
- 使用 DeepSeek 作为回复质量评测的裁判。
- 配置仅包含基础版和 HITL 版的 Studio 图。
- Notebook 清除运行输出，环境变量加载不依赖本机绝对路径。

## 安装与 PyCharm

需要 Python `>=3.11,<3.14`，建议使用 Python 3.11。克隆仓库后，在项目根目录的 PowerShell 终端执行：

```powershell
py -m pip install uv
py -m uv python install 3.11
py -m uv sync --python 3.11 --extra dev --locked
```

在 PyCharm 中打开项目，选择已有解释器 `.venv\Scripts\python.exe`；Notebook 内核也选择此环境。锁文件沿用已安装验证的课程依赖集合，其中可能包含未使用的扩展依赖。

## 配置与演示

首次使用时复制空模板，已有 `.env` 时不要覆盖：

```powershell
Copy-Item .env.deepseek.example .env
```

在本地填写：

```dotenv
DEEPSEEK_API_KEY=your_private_deepseek_key
DEEPSEEK_MODEL=deepseek-flash
LANGSMITH_TRACING=false
LANGSMITH_PROJECT=agents-from-scratch-learning
LANGSMITH_API_KEY=
```

进行 LangSmith 追踪、数据集和评测时，需要独立的 LangSmith 密钥；填写后启用 `LANGSMITH_TRACING=true`。如账户使用其他区域，配置相应 `LANGSMITH_ENDPOINT`，必要时设置 `LANGSMITH_WORKSPACE_ID`。

`DEEPSEEK_MODEL` 可按账户支持的模型配置，但所选模型必须兼容本项目的工具调用和模型参数。

```powershell
.\.venv\Scripts\python.exe -X utf8 run_demo.py
```

基础邮件与日历工具为模拟实现，运行不会真实发送邮件或创建会议。

## 学习与评测

按 `agent.ipynb` → `evaluation.ipynb` → `hitl.ipynb` 顺序逐格运行。HITL 使用 `InMemorySaver` 保存执行状态；恢复时使用同一图实例及 `thread_id`。重启内核会丢失内存状态。

先检查测试能否加载：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest notebooks/test_tools.py tests/test_response.py --agent-module email_assistant --collect-only -q
```

基础工具检查共 2 项：

```powershell
$env:LANGSMITH_TEST_SUITE = "Email assistant: Test Tools"
.\.venv\Scripts\python.exe -X utf8 -m pytest notebooks/test_tools.py -v
```

完整回复测试选取 8 封需要回复的邮件，分别检查工具调用和回复质量，共 16 项：

```powershell
$env:LANGSMITH_TEST_SUITE = "Email assistant: Full Response"
.\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_response.py --agent-module email_assistant -v
```

实际评测会调用模型，并将测试记录上传到你的 LangSmith 账户。自动化回复测试支持基础版 `email_assistant`；HITL 通过 Notebook 中的暂停与恢复流程学习验证。

历史学习运行观察到：分类评测 13/16 正确，完整回复测试 14/16 通过。这是特定运行结果，两个指标含义不同，也不能保证后续运行一致。工具检查尚未完整覆盖参数、调用顺序和次数；模型裁判结果需要结合样例人工核查。

## Studio

在项目根目录执行并保持终端开启：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m langgraph_cli dev --no-browser
```

打开命令输出的 Studio 链接，选择 `email_assistant` 或 `email_assistant_hitl`。`langgraph.local.json` 另保留仅加载基础版的配置。

## 发布说明

- 本仓库是按学习范围导出的独立快照，未复制上游 Git 历史。
- 未包含真实密钥、个人实验结果、Notebook 输出、本地路径、IDE 配置、虚拟环境、运行缓存和本地备份。
- 样例数据与课程插图来自上游。使用模拟日历，会议日期与参数仍需核查。
- 多工具并发、恢复时的副作用幂等性、持久化和生产部署仍需后续完善。

## 来源与许可

原项目：[langchain-ai/agents-from-scratch](https://github.com/langchain-ai/agents-from-scratch)。配套课程：[Ambient Agents with LangGraph](https://academy.langchain.com/courses/ambient-agents)。

遵循 [MIT License](LICENSE)，保留上游 `Copyright (c) 2026 LangChain, Inc.` 声明。
