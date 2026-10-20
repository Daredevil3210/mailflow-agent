# MailFlow Agent：Gmail 后续手工测试步骤

适用版本：MailFlow Agent v0.5.0 发布代码。所有邮箱、正文和参数均为通用测试模板，不包含真实账号或执行记录。整理日期：2026-10-20，时区 Asia/Shanghai。

你已经完成“读取真实邮件 → 生成回复 → 人工接受 → 发送 → 标为已读”。下面按顺序测试修改、反馈、记忆、提问、会议、通知和忽略。**不要一次把所有邮件都发出；完成一项，再开始下一项。**

这些是待你执行的测试用例，不代表已经通过。模型分类和偏好提取存在波动；实际结果与预期不同，就记录为需要排查的问题。

## 一、固定两个邮箱和运行方式

- 发件测试邮箱示例：`sender@example.com`，使用你自己的另一个邮箱替换。
- 助手 Gmail 示例：`assistant@example.com`，使用你完成 OAuth 授权的 Gmail 替换。
- 每项都用“写邮件”新建邮件，使用下面唯一的主题；不要回复上一项测试邮件。
- 所有测试都可以在 Studio 完成，不必同时操作 Agent Inbox。
- 测试期间使用同一个本地服务。新线程会独立保存消息，但仍读取同一份 Store 中的偏好。
- 服务是否重启过不是判断记忆是否清空的依据；以 Memory 或下面的 `memory` 命令为准。不要删除本地数据目录来重置。

这次准备了 `src/email_assistant/tools/gmail/manual_test.py`，只精确提交指定主题的一封测试邮件。它不自动 Accept、不自动填写反馈、不删除旧运行。重复提交同一主题时会返回原线程，不会再创建运行。需要重新做某项时，在主题后加 `-R2`，同时把下面命令的主题也改掉。

原来的 `run_ingest.py` 保留，但这组测试不用它：它的查询较宽、没有完成去重检查，而且存在删除旧运行的逻辑。

### 1. 确认服务

在 PowerShell 执行：

```powershell
# 在克隆后的项目根目录执行
Invoke-RestMethod http://127.0.0.1:2024/ok
```

显示 `ok: True` 就继续。服务已经在运行时不要再启动一份。如果连接被拒绝，在一个单独终端运行下面命令，并保持终端打开：

```powershell
# 在克隆后的项目根目录执行
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe -X utf8 -m langgraph_cli dev --config langgraph.gmail.local.json --no-browser --no-reload --allow-blocking --host 127.0.0.1 --port 2024
```

### 2. 在另一个 PowerShell 窗口定义快捷命令

先替换下面两个邮箱变量，再整段执行一次。正文及 JSON 中的示例邮箱也必须替换为自己的真实地址；示例签名 Alex 可改成自己的名字。这些定义只对当前终端有效，重开终端需要再执行。

```powershell
# 在克隆后的项目根目录执行
$testPython = (Resolve-Path '.\.venv\Scripts\python.exe').Path
$testHelper = (Resolve-Path '.\src\email_assistant\tools\gmail\manual_test.py').Path
$senderEmail = 'sender@example.com'       # 改为自己的发件测试邮箱
$assistantEmail = 'assistant@example.com' # 改为已授权的 Gmail
function Test-Submit([string]$Subject) { & $testPython -X utf8 $testHelper submit --subject $Subject --sender $senderEmail --recipient $assistantEmail }
function Test-Status([string]$Subject) { & $testPython -X utf8 $testHelper status --subject $Subject }
function Test-Verify([string]$Subject) { & $testPython -X utf8 $testHelper verify --subject $Subject }
function Test-Memory([string]$Label) { & $testPython -X utf8 $testHelper memory --save $Label }
Test-Memory '00-before-tests'
```

`Test-Submit` 会打印本次线程的 Studio 链接。每次必须打开对应链接，不能一直在之前已经结束的线程点击 Resume。

`Test-Status` 用来查看运行状态、待审核工具和工具结果。若仍是 pending/running，稍后再查；`success` 也可能表示本轮已正常停在中断处，必须同时检查待审核请求和 next 节点。

`Test-Verify` 只核实 Gmail 原邮件的已读标签，以及同一邮件会话中有没有已发送回复。它不验证 Calendar 中的事件。

`Test-Memory` 读取本地服务的 Store，并将当前偏好保存到 `.local-backups/memory-标签.json`（本地私有目录，不提交）。这里读的是服务中的记忆，不是 Notebook 里的 `store` 变量。

### 3. Studio 审核输入的共同规则

在右侧下方 `Provide a value to resume execution...` 输入框中，**完整替换**默认的 `""`，然后点击右下角 **Resume**。不要用左侧 Input 的 Submit 来提交审核结果。

接受当前动作：

```json
[{"type":"accept"}]
```

给文字反馈，要求模型重新生成：

```json
[{"type":"response","args":"这里填写反馈"}]
```

忽略当前请求：

```json
[{"type":"ignore"}]
```

直接修改参数并执行：

```json
[{"type":"edit","args":{"args":{"这里必须填写当前工具的完整参数":"不是只填修改字段"}}}]
```

**edit 会按修改后的参数直接执行工具；response 才是先反馈、重新生成、再审核。** 每次 Resume 后都要重新看当前 action，不能对已经发送的动作重复 Resume。

## 二、测试 1：直接修改邮件回复（edit）

目标：修改后的正文被真实发送，且邮件风格偏好有针对性更新。

从 发件测试邮箱新建邮件，收件人填 助手邮箱：

**主题：** `MailFlow-Test-01-Edit`

**正文：**

```text
Hi,

I have sent you the draft API checklist. Please reply to confirm receipt and let me know that you will review it.

No meeting is needed.

Thanks!
```

1. 发送邮件；保持未读即可，若已经打开也能被这个辅助脚本找到。
2. 执行：

```powershell
Test-Submit 'MailFlow-Test-01-Edit'
Test-Status 'MailFlow-Test-01-Edit'
```

3. 打开输出的 Studio 链接。预期分类为 respond，停在 `send_email_tool`。
4. 从当前 action_request.args 复制真实 `email_id`。把下面的 `从当前请求复制的真实ID` 替换掉，其他字段保留。注意 JSON 字符串中的换行写成 `\n`。

```json
[{"type":"edit","args":{"args":{"email_id":"从当前请求复制的真实ID","response_text":"Thanks, received. I'll review the API checklist.\n\nCheers,\nAlex","email_address":"assistant@example.com","additional_recipients":[]}}}]
```

5. 点击 Resume。这里会发送修改后的邮件，不需要再 Accept 一次。
6. 执行：

```powershell
Test-Status 'MailFlow-Test-01-Edit'
Test-Verify 'MailFlow-Test-01-Edit'
Test-Memory '01-after-edit'
```

7. 到 发件测试邮箱查看回复，正文应与你修改的一致。原邮件应已读，工作流应结束。
8. 查看 `response_preferences`：可能提取简洁、轻松语气、签名等特征；具体措辞不固定。必须保留其他无冲突偏好，不能把整份配置意外删掉。一次 edit 不保证每个细节都变成长期规则，下一项用明确反馈补充。

## 三、测试 2：用文字反馈调整回复（response）

目标：反馈后不立刻发送；先更新偏好，再生成新回复供审核。

**主题：** `MailFlow-Test-02-Feedback`

**正文：**

```text
Hi,

The deployment checklist is ready for your review. Could you confirm receipt and say that you will review it?

No meeting is needed.

Thanks!
```

1. 从发件测试邮箱发到助手邮箱，执行：

```powershell
Test-Submit 'MailFlow-Test-02-Feedback'
Test-Memory '02-before-feedback'
```

2. 在 `send_email_tool` 审核处填写并 Resume：

```json
[{"type":"response","args":"For this reply and future routine work acknowledgments, use at most two short sentences in the body, keep the tone friendly and informal, and sign off exactly as Cheers, followed by Alex on the next line. Do not use the name Lance in my replies. Please revise this draft accordingly."}]
```

3. 等待再次出现 `send_email_tool`。新正文应简短，并使用你指定的签名。
4. 在 Accept 之前执行：

```powershell
Test-Verify 'MailFlow-Test-02-Feedback'
Test-Memory '02-after-feedback-before-accept'
```

此时通常还没有已发送回复，原邮件也还未被完成节点标为已读；`response_preferences` 应已经包含新的明确偏好。若出现真实发送，说明审核流程与预期不一致。

5. 确认当前工具仍是 `send_email_tool` 且内容正确，再填写 `[{"type":"accept"}]` 并 Resume。
6. 执行 `Test-Status`、`Test-Verify`，并到 发件测试邮箱查看实际收到的回复。

## 四、测试 3：新邮件复用旧偏好

目标：在不同 LangGraph 线程中复用上一项学到的风格。邮件本身不能再提示“简短”“Cheers”等规则。

**主题：** `MailFlow-Test-03-Memory-Reuse`

**正文：**

```text
Hi,

The release notes are ready. Could you confirm that you received them and will review them?

Thanks!
```

1. 新建邮件从发件测试邮箱发到助手邮箱，执行：

```powershell
Test-Submit 'MailFlow-Test-03-Memory-Reuse'
Test-Memory '03-before-accept'
```

2. 确认新输出的 Thread ID 与测试 2 不同。
3. 检查首次生成的 `response_text`，在没有再次反馈的情况下，是否已简短、友好，签名是 `Cheers,` / `Alex`。
4. 在 Studio 的 Trace 中展开本次回复生成的模型调用，查看输入的 system 内容，确认其中确实注入了这些已保存偏好。如果界面不方便找，先以 Store 内容和首次生成结果作为初步观察，不要只凭回复恰好简短就断言因果。
5. 可接受并用 `Test-Verify 'MailFlow-Test-03-Memory-Reuse'` 检查真实发送。
6. 再保存 `Test-Memory '03-after-accept'`。本实现的 accept 分支没有主动更新偏好；已有 profile 的内容应不因单纯接受而变化，更新时间等元数据不属于内容变化。

这证明的是“跨线程可读取共享偏好”，还不是严格的无记忆对照实验。不要通过新建 thread_id 来假装清空 Store。

## 五、测试 4：缺少信息时向你提问（Question）

目标：模型不知道的具体事实，先问你，不凭空给出答案。

**主题：** `MailFlow-Test-04-Question`

**正文：**

```text
Hi,

Which exact build ID have you approved for our next test deployment, and what is the approved deployment window? I need your decision before proceeding.

No meeting or calendar event is needed.

Thanks!
```

1. 发送、执行 `Test-Submit 'MailFlow-Test-04-Question'`。
2. 预期停在 `Question`。先看它是否确实询问 build ID 和部署窗口。
3. 如果模型直接编造答案，不接受发送，记录失败；用 response 指出“这些信息没有提供，请先询问我”，再观察后续行为。若它只发送“稍后确认”而不提问，也不能算 Question 分支通过。
4. 在 Question 审核输入框填：

```json
[{"type":"response","args":"For this test deployment only, the approved build ID is mailflow-test-build-007. The approved window is 2026-10-23 from 20:00 to 20:30 in Asia/Shanghai. Reply with these facts. Do not schedule a meeting or create a calendar event."}]
```

5. Resume 后预期生成 `send_email_tool`，回复应包含准确的 build ID、日期、时间和时区。
6. 这项没有请求创建会议，不应出现 `schedule_meeting_tool`。
7. 检查后 accept，再用 `Test-Verify 'MailFlow-Test-04-Question'` 验证。

当前代码的 Question-response 分支本身没有调用 update_memory；不能预期这次答案自动成为长期记忆。若执行时 2026-10-23 已过，请将答案日期换成未来日期。

## 六、会议测试前先了解当前限制

下面的会议测试会在 助手邮箱对应的真实 Google Calendar 中创建事件。只邀请上述两个测试邮箱。

1. 默认时区是 `America/Los_Angeles`，审核时必须检查并使用 `Asia/Shanghai`。
2. `get_calendar_events()` 当前混用了 UTC 查询范围、带时区事件和不带时区的工作时间。有已有定时事件时可能抛出时间比较异常，随后返回 `mock due to error`。**看到 mock 就暂停会议用例，记录问题，不能拿模拟空闲时间当真实查询结果。**
3. 日历查询只查授权账号的主日历，不代表同时确认了所有参会人的空闲时间。
4. 创建事件的代码把 `sendUpdates` 放在 event body 中，而 Google 官方文档将它定义为请求参数。因此“事件创建成功”和“邀请通知成功送达”要分别验证，不能认为所有邀请邮件一定发出。
5. 本组不自动修复这些业务实现；若遇到异常，把工具结果和操作步骤保留下来，再定位修复。邮件部分通过不代表日历部分已经通过。

官方参数说明：https://developers.google.com/workspace/calendar/api/v3/reference/events/insert

## 七、测试 5：直接修改会议参数（edit）

目标：按审核后的时间创建真实事件，并从修改中提取日历偏好。

以下用 `2026-10-23` 作为未来测试日期；若你执行时日期已过，或当天 15:00—15:30 已有真实安排，统一替换为另一段确认可用的未来时间。开始时间与结束时间必须一起修改。

**主题：** `MailFlow-Test-05-Meeting-Edit`

**正文：**

```text
Hi,

Could we schedule a 45-minute MailFlow test review on 2026-10-23? I am available from 15:00 to 17:00 in Asia/Shanghai.

Please check your calendar, schedule one available slot, and email me the confirmed date, time, and duration. This is only a test meeting between sender@example.com and assistant@example.com.

Thanks!
```

1. 发送后执行：

```powershell
Test-Submit 'MailFlow-Test-05-Meeting-Edit'
Test-Memory '05-before-meeting-edit'
Test-Status 'MailFlow-Test-05-Meeting-Edit'
```

2. 检查 `check_calendar_tool` 的结果，不能是 mock。它的日期格式是 `DD-MM-YYYY`，本例是 `23-10-2026`；创建会议的 ISO 日期格式则是 `YYYY-MM-DD`。
3. 预期停在 `schedule_meeting_tool`。模型可能已经提出 30 分钟，也可能按来信提出 45 分钟；记录原参数，不要求必须是 45 才能继续。
4. 确认 15:00—15:30 在真实日历中可用，再填写：

```json
[{"type":"edit","args":{"args":{"attendees":["sender@example.com","assistant@example.com"],"title":"MailFlow Test Review","start_time":"2026-10-23T15:00:00+08:00","end_time":"2026-10-23T15:30:00+08:00","organizer_email":"assistant@example.com","timezone":"Asia/Shanghai"}}}]
```

5. 点击 Resume，此时会尝试真实创建事件，不必再接受同一个会议请求。
6. 进入 https://calendar.google.com/ ，登录 助手邮箱，检查标题、日期、上海时间 15:00—15:30、参会人。必须实际看到事件才算创建通过。
7. 执行 `Test-Memory '05-after-meeting-edit'`，检查 `cal_preferences` 是否保留原规则并反映修改。15:00 属于一次具体安排，不应无依据地固化为“永远只在15:00开会”。
8. 工作流随后通常会停在 `send_email_tool`。检查回复内容是否与**已创建事件**的日期、时间、时区、时长一致；若不一致，先用 response 要求只修正文案、不要再创建会议，再审核新草稿。
9. 接受邮件回复，用 `Test-Verify 'MailFlow-Test-05-Meeting-Edit'` 核实。Calendar 事件与回复邮件都正确才算本项通过。

## 八、测试 6：文字反馈调整会议（response）

目标：表达长期偏好后，重新提案；未接受前不创建这项会议。

**主题：** `MailFlow-Test-06-Meeting-Feedback`

**正文：**

```text
Hi,

Could we schedule a 45-minute follow-up for the MailFlow test on 2026-10-26? I can attend any available slot between 14:00 and 17:00 in Asia/Shanghai.

Please check your calendar, arrange the meeting, and send me a confirmation. The attendees are sender@example.com and assistant@example.com.

Thanks!
```

1. 发送并执行 `Test-Submit 'MailFlow-Test-06-Meeting-Feedback'`。
2. 在 `schedule_meeting_tool` 审核处使用：

```json
[{"type":"response","args":"For this and future meetings, prefer 30 minutes and a start time strictly later than 14:00 in Asia/Shanghai. Exactly 14:00 is not acceptable. For this meeting, choose 16:00 to 16:30 on 2026-10-26 if it is free. Keep the meeting title concise. Please revise the proposal; do not create it until I approve."}]
```

3. 点击 Resume，等新会议请求。执行 `Test-Memory '06-after-feedback-before-accept'`，检查日历偏好是否已更新。
4. 此时到 助手邮箱日历检查，不应已经创建本次会议。
5. 新参数应是上海时间 16:00—16:30，日期正确。尤其检查 `start_time` 不能仍是 14:00；记忆写对但工具参数错，仍算未通过。
6. 如果原提案已经满足这些条件，也可以提交该反馈，用它确认显式偏好保存和再次审核流程。
7. 确认无冲突后 accept 会议；到 Calendar 查看事件；再审核并 accept 确认邮件。
8. `Test-Status` 中若再次出现同一会议创建请求，不要反复接受；先检查是否已经建成，防止重复事件。

## 九、测试 7：新线程复用会议偏好

目标：不在来信里重复 30 分钟或 14 点之后的规则，观察首次提案是否读取已有偏好。

**主题：** `MailFlow-Test-07-Calendar-Memory`

**正文：**

```text
Hi,

Could we arrange a MailFlow results discussion on 2026-10-27? I can attend between 13:00 and 17:00 in Asia/Shanghai. Please choose an available time and a suitable duration, then send me a confirmation.

The attendees are sender@example.com and assistant@example.com.

Thanks!
```

1. 发送并执行 `Test-Submit 'MailFlow-Test-07-Calendar-Memory'`。
2. 确认 Thread ID 与测试 6 不同，且服务 Store 中仍有测试 6 的规则。
3. 首次会议提案应优先 30 分钟、开始时间严格晚于上海时间 14:00，并符合真实空闲时间。
4. 若为 14:00、时区不对、时长错误，记录失败；不要先通过 edit 修正后再声称“自动复用成功”。可以修正来继续验证工具，但要区分“第一次是否正确”和“修正后是否正确”。
5. 查看模型调用的 system 输入，确认 cal_preferences 被注入。默认偏好本来就有 30 分钟，因此“开始时间严格晚于14:00”比单看30分钟更有辨别力。
6. 如要验证第三个真实事件，可继续 accept 会议和确认邮件，再检查日历。若只想观察提案而不创建，停在审核处即可；不要为了结束而用 ignore，因为当前代码会据此修改 triage_preferences，影响后面的分类测试。

## 十、测试 8：重要但无需回复（notify），再主动要求回复

目标：进入通知审核；你的反馈能改变本次处理路径并更新分流偏好。

**主题：** `MailFlow-Test-08-Notify`

**正文：**

```text
Hi,

FYI: the MailFlow staging deployment completed successfully. All health checks passed and no action is required. This update is for your awareness only; no reply is needed.

Thanks!
```

1. 执行 `Test-Submit 'MailFlow-Test-08-Notify'`，预期分类 notify，停在 `Email Assistant: notify`。
2. 这一处没有要发送的草稿，不能用 accept。填写：

```json
[{"type":"response","args":"Please reply to thank the sender for this deployment update. For future successful MailFlow staging deployment updates, I also want to send a short acknowledgment rather than only receive a notification."}]
```

3. Resume 后预期进入回复流程，生成 `send_email_tool` 并再次等待审核。
4. 执行 `Test-Memory '08-after-notify-response'`，查看 `triage_preferences` 是否增加了针对 MailFlow staging 部署成功更新的规则，而不是把所有 FYI 邮件都变成必须回复。
5. 检查草稿后 accept，执行 `Test-Verify 'MailFlow-Test-08-Notify'`。
6. 若一开始没有分类 notify，先记录实际分类和当前 triage_preferences；不要反复提交同一邮件试到通过，也不能把模型误分类当作通知分支已验证。

## 十一、测试 9：新邮件复用分流偏好

目标：与测试 8 同类的新邮件，首次分类是否从 notify 转向 respond。

**主题：** `MailFlow-Test-09-Triage-Memory`

**正文：**

```text
Hi,

FYI: another MailFlow staging deployment completed successfully. All health checks passed. No action is required and no reply is needed; this is just a deployment status update.

Thanks!
```

1. 新建邮件并执行 `Test-Submit 'MailFlow-Test-09-Triage-Memory'`。
2. 预期受上一项用户偏好影响，首次分类 respond，出现确认回复审核。
3. 用 Trace 中 triage_router 的模型输入确认最新 triage_preferences 已传入。若仍 notify，就记录“偏好未影响本次分类”，不能只因 Store 有记录就算通过。
4. 可以接受确认回复并验证。本项与测试 8 的 Thread ID 必须不同。

## 十二、测试 10：营销邮件自动忽略（ignore）

目标：无须人工审核，也不产生回复或会议。

**主题：** `MailFlow-Test-10-Promotion`

**正文：**

```text
Limited-time promotion!

Save 50% on our generic productivity template bundle. This is a promotional newsletter sent to our mailing list. No personal response or action is requested.

To unsubscribe, use your account preferences.
```

1. 发送并执行 `Test-Submit 'MailFlow-Test-10-Promotion'`。
2. `Test-Status 'MailFlow-Test-10-Promotion'` 应显示分类对应的运行正常结束，没有待审核请求，也没有发送工具结果。
3. 执行 `Test-Verify 'MailFlow-Test-10-Promotion'`，已发送回复列表应为空。
4. 当前代码分类 ignore 会直接 END，不经过 mark_as_read_node，所以原邮件**可能仍未读**。这是当前实现的行为，不等于它偷偷发送了邮件，也不应当按“所有结束都必须已读”来判错。

## 十三、可选测试 11：人工拒绝邮件草稿

这一项放最后，因为当前 ignore 分支会根据你拒绝草稿的行为更新 triage_preferences。

**主题：** `MailFlow-Test-11-Reject-Draft`

**正文：**

```text
Hi,

Please confirm receipt of this optional weekly template review request. No meeting is needed.

Thanks!
```

1. 发送、提交，等 `send_email_tool`。
2. 在接受前执行 `Test-Memory '11-before-ignore'`。
3. 填 `[{"type":"ignore"}]`，点击 Resume。
4. 用 `Test-Verify` 确认没有发出回复，用 `Test-Status` 确认结束。
5. `Test-Memory '11-after-ignore'` 查看 triage_preferences 如何变化。
6. 当前实现把“拒绝这一封草稿”推断成“不想回复这类邮件”。这未必等于你的真实意图，本项也用于观察它是否过度泛化，而不应把任何变化都视为正确学习。

## 十四、如何记录结果和处理异常

每项记录：主题、Thread ID、首次分类、首次工具参数、填写的审核 JSON、发送是否真实发生、日历是否真实创建、记忆变化、最终运行状态。

- 输入 JSON 错误：不要把 JSON 再包成字符串。发布版 Gmail 工作流已复用 request_human_review：格式不合法时会再次暂停，提示修正。按新提示提交合法值，不要将 accept 当作修复格式的通用按钮。若仍失败，保留错误信息并先检查真实副作用，不能直接重复发送或建会。
- 看到 `Question`：先回答，不要把它当成发送审核按 accept。
- “模型已经生成会议方案”不表示事件已建成；看真实 Calendar。
- “工具返回成功”不能代替真实邮箱/Calendar 检查，部分底层分支会使用模拟实现。
- 提交后 pending/running：稍后查状态，不能再次 submit 来催促。
- 发送成功但后续报错：先查已发送邮件，不能重跑 accept。
- memory 里规则正确但提案错：属于执行约束没有落实，记录参数差异。
- 会议邀请没送达：检查事件是否已创建，再排查 sendUpdates 的请求位置；不要重复建会来尝试发邀请。
- 默认背景仍把用户写成 Lance，来自课程默认提示；测试2的偏好可要求改签名，但产品化时应另外配置真实背景，不能把签名变化等同于所有用户身份已替换。

执行完会议测试后，在 Google Calendar 中按标题找到本组测试事件并手动删除，避免影响后续空闲时间判断。若删除时询问是否通知参会人，根据你是否需要清理测试邀请自行选择；不要批量删除其他事件。

完成这组测试后再考虑定时拉取或托管部署。当前重点是确认每条人工审核分支和记忆复用行为，而不是让收件箱自动批量运行。
