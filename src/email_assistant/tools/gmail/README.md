# Gmail 授权与测试邮件读取

这部分记录我从模拟邮件工具走向 Gmail API 的第一步：取得本地授权，然后用独立脚本检查测试邮件读取。当前只发布已经学习的授权和读取准备，Gmail 发送、日历操作及自动采集工作流仍是后续学习内容。

## 文件与授权流程

- `setup_gmail.py`：读取 `.secrets/secrets.json`，通过浏览器完成 OAuth 授权，保存 `.secrets/token.json`。
- `check_gmail_read.py`：读取授权信息，必要时刷新令牌，按专用主题查询最多三封邮件的头部信息。

`secrets.json` 来自 Google Cloud 的桌面 OAuth 客户端，描述应用身份；`token.json` 由用户授权后生成，包含访问令牌、刷新令牌等信息。它们均保留在本地，不提供真实凭据或令牌样例。

## 配置与运行

1. 在 Google Cloud 项目中启用 Gmail API 和 Google Calendar API。
2. 配置 OAuth 同意页面。个人 Gmail 使用 External 受众，在测试用户中加入要授权的账号。
3. 创建 Desktop app 类型的 OAuth 客户端，下载 JSON，保存为本目录 `.secrets/secrets.json`。
4. 在项目根目录运行：

```powershell
.\.venv\Scripts\python.exe -X utf8 src/email_assistant/tools/gmail/setup_gmail.py
```

脚本的 `run_local_server(port=0)` 启动临时授权回调服务，并打开浏览器。此端口由系统分配，与 LangGraph 开发服务的 2024 端口用途不同。授权完成后看到 `Authentication successful!`，本地生成 `token.json`。

课程脚本申请的权限是：

- `https://www.googleapis.com/auth/gmail.modify`
- `https://www.googleapis.com/auth/calendar`

这组权限面向后续邮件与日历功能；当前读取检查只使用邮件查询接口。可结合 [Google Gmail Python 快速入门](https://developers.google.com/workspace/gmail/api/quickstart/python) 和 [Calendar Python 快速入门](https://developers.google.com/workspace/calendar/api/quickstart/python) 核对账户配置。

## 读取测试邮件

给授权邮箱发送主题为 `MailFlow-Read-Test` 的测试邮件，然后运行：

```powershell
.\.venv\Scripts\python.exe -X utf8 src/email_assistant/tools/gmail/check_gmail_read.py
```

默认查询 `subject:MailFlow-Read-Test newer_than:7d`，不要求未读。先通过 `messages.list` 查找邮件 ID，再通过 `messages.get(format="metadata")` 获取 From、To、Subject、Date。最多展示三封；无匹配结果表示连接成功，但还没找到符合条件的邮件。

脚本不启动 Agent、不调用大模型、不发送邮件、不创建日历事件、不标记已读。读取结果和真实账号信息不用提交到 Git。

## 我的学习重点

- 区分应用身份文件与用户授权结果。
- 理解 scopes、访问令牌、刷新令牌及有效期。
- 理解授权脚本的临时回调与 Studio 本地服务的区别。
- 学习从 Gmail 查询 ID 再读取邮件详情的两步调用。
- 授权成功不等于邮件 Agent 已接入 Gmail。下一步学习工具实现和工作流输入字段。

授权脚本来源于上游课程，保留项目来源说明与 MIT 许可。读取检查是本项目新增的学习辅助脚本。
