# Gmail 与 Google Calendar 集成

我在这一阶段把模拟工具换成真实 API，完成了读取、模型生成回复、人工批准、发送和标为已读的闭环。Calendar 代码已接入，但真实会议与邀请通知仍按手工用例验证。

## 文件职责

- setup_gmail.py：桌面 OAuth 授权，保存本地令牌。
- check_gmail_read.py：专用测试主题的邮件头读取检查，不调用模型。
- gmail_tools.py：凭据加载、正文提取、邮件读取/发送、日程查询/创建、标为已读。
- prompt_templates.py：可用工具的文字说明。
- ../../email_assistant_hitl_memory_gmail.py：分类、问答、审核、偏好更新和工具执行。
- run_ingest.py：查询 Gmail，转换输入，通过 SDK 提交运行。
- manual_test.py：精确提交单封测试邮件、查看状态/记忆、核实发送。
- setup_cron.py 与 ../../cron.py：定时获取参考入口，本次没有创建或启用任务。

## Google 授权

1. 在 Google Cloud 同一项目启用 Gmail API 和 Calendar API。
2. 配置 OAuth 受众与测试用户，创建 Desktop app 客户端。
3. 下载客户端 JSON，在本目录创建 .secrets/，保存为 .secrets/secrets.json。
4. 在项目根目录运行：

```powershell
.\.venv\Scripts\python.exe -X utf8 src/email_assistant/tools/gmail/setup_gmail.py
```

授权成功后生成 .secrets/token.json。脚本申请 gmail.modify 和 calendar 权限，本身不处理邮件。应用配置与用户令牌均留在本地。

官方参考：[Gmail Python 快速入门](https://developers.google.com/workspace/gmail/api/quickstart/python)、[Calendar Python 快速入门](https://developers.google.com/workspace/calendar/api/quickstart/python)。

## 读取检查

给授权邮箱发主题为 MailFlow-Read-Test 的邮件，然后执行：

```powershell
.\.venv\Scripts\python.exe -X utf8 src/email_assistant/tools/gmail/check_gmail_read.py
```

默认查询最近七天该主题的邮件，最多显示三封邮件头。没有匹配结果时连接也可能成功；脚本不调用模型、不发送邮件、不创建会议、不修改标签。刷新时会更新本地令牌。

## 启动与逐封提交

项目根目录配置自己的 DeepSeek .env 后，保持服务终端开启：

```powershell
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe -X utf8 -m langgraph_cli dev --config langgraph.gmail.local.json --no-browser --no-reload --allow-blocking
```

检查 http://127.0.0.1:2024/ok ，打开终端提供的 Studio 链接。图名 email_assistant_hitl_memory_gmail，当前是本地开发服务。

从另一个自己的邮箱发测试邮件，主题以 MailFlow-Test- 开头。先替换两个示例地址，在另一终端执行：

```powershell
$senderEmail = 'sender@example.com'
$assistantEmail = 'assistant@example.com'
.\.venv\Scripts\python.exe -X utf8 src/email_assistant/tools/gmail/manual_test.py submit --subject MailFlow-Test-01-Edit --sender $senderEmail --recipient $assistantEmail
```

只处理最近七天收件箱中主题、发件人和收件人准确匹配的唯一邮件。输出新线程链接；同一主题重复提交不会创建新运行。重做时使用新主题，如 MailFlow-Test-01-Edit-R2。

在 Studio 当前线程的 Resume 输入框填写：

```json
[{"type":"accept"}]
```

这会执行当前动作。edit 提交完整修改参数并执行；response 反馈后重新生成，等待下一次审核；Question 用 response 回答。发布版 Gmail 工作流复用了审核输入校验，非法输入时再次暂停。

```powershell
.\.venv\Scripts\python.exe -X utf8 src/email_assistant/tools/gmail/manual_test.py status --subject MailFlow-Test-01-Edit
.\.venv\Scripts\python.exe -X utf8 src/email_assistant/tools/gmail/manual_test.py verify --subject MailFlow-Test-01-Edit
.\.venv\Scripts\python.exe -X utf8 src/email_assistant/tools/gmail/manual_test.py memory --save after-first-test
```

这些检查命令不恢复执行、不自动接受。运行记录与记忆快照保存在 .local-backups/，输出也可能含自己的邮件内容，均保留在本地。

完整模板见 [11 组手工测试指南](../../../../docs/GMAIL_MANUAL_TEST_GUIDE.md)。

## 输入、线程和采集入口

Gmail 输入为 from、to、subject、body、id，与 Notebook 的 author/email_thread 不同。message ID 用于回复和标为已读；Gmail thread 表示邮件往来会话；LangGraph thread 表示工作流状态。

run_ingest.py 将 Gmail 会话 ID 转成固定 UUID，并尝试删除旧运行；去重仍是 TODO，skip-filters 未在当前处理流程中使用。手工入口使用独立线程，避免依赖这些未完成逻辑。服务端 Store 与 Notebook 内存对象不共享。

## 已知限制

- 默认背景与部分指令仍含课程人物及旧工具名称，实际使用前需统一。
- Calendar 时区混用可能报错并返回 mock due to error，不能当作真实空闲结果。
- sendUpdates 当前放在 event body 中；Google 将其定义为请求参数，事件和邀请通知需分别验证：[官方说明](https://developers.google.com/workspace/calendar/api/v3/reference/events/insert)。
- 找不到原邮件时回退占位收件人的逻辑不适合真实发送；不能据此声称支持任意新邮件。
- 部分工具缺少依赖或凭据时返回模拟内容，成功字符串不能代替真实邮箱/日历核验。
- 多工具审核重放、重复发送/建会防护、账号隔离和常驻部署仍需完善。
- 邮件会进入配置的模型服务，开启追踪后也可能进入 LangSmith；仓库只含通用模板，不含私人执行数据。

来源与 MIT 许可见根目录 README 和 LICENSE。
