# GSB A/B Runner

这个仓库用于 Pair-wise GSB 的题目、初始快照、A/B 两轮产物和轨迹管理。

## 目录结构

```text
record1/
  tools/
    config/                 # CLI 模板配置（不含真实 key，真实 key 放 .env.local）
    new-task.ps1            # 根据初始快照创建一个新任务
    open-run.ps1            # 启动 A 或 B，并强制重置工作区
    collect-run.ps1         # 提取 SessionID、轨迹文件、产物 commit
    reset-run.ps1           # 清理 A 或 B
    push-run.ps1            # 推送产物分支并校验远端 SHA
  tasks/
    <task-id>/
      prompt.md             # 两次跑共用的 prompt 原文
      meta.json             # 初始快照、语言框架、分支信息
      baseline.bundle       # 初始环境快照的 Git bundle
      open-A.cmd
      open-B.cmd
      collect-A.cmd
      collect-B.cmd
      reset-A.cmd
      reset-B.cmd
      results/
        A/
          <session-id>.jsonl
          prompt.md
          summary.json
        B/
          <session-id>.jsonl
          prompt.md
          summary.json
```

运行时的 `A/`、`B/` 和 `.codex-home/` 不会提交到主分支；它们会在每次启动时被删除并重新创建。

## 第一次配置

在 `tools/config/.env.local` 中填写：

```text
SUPER_RELAY_KEY=你的_relay_key
```

这个文件已被 `.gitignore` 忽略，不会提交。

## 创建一个新任务

空项目快照（适合从零实现的题目）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "D:\北京中强实习\record1\tools\new-task.ps1" `
  -TaskId "my-task" `
  -PromptPath "D:\path\to\prompt.md" `
  -LanguageFramework "TypeScript, React, Node.js"
```

已有项目快照：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "D:\北京中强实习\record1\tools\new-task.ps1" `
  -TaskId "my-task" `
  -PromptPath "D:\path\to\prompt.md" `
  -SourceDir "D:\path\to\source-project" `
  -LanguageFramework "Go, Gin, PostgreSQL"
```

脚本会生成一个只有 root commit 的 `baseline.bundle`，并把 40 位初始 SHA 写入 `meta.json`。

## 跑 A / B

在任务目录下分别双击或运行：

```text
open-A.cmd
open-B.cmd
```

每次启动都会：

1. 删除旧的 `A/` 或 `B/` 工作区；
2. 从 `baseline.bundle` 重新克隆；
3. 删除旧的 `.codex-home/A` 或 `.codex-home/B`；
4. 新建一份独立的 CLI 会话目录；
5. 以全自动模式启动 Codex CLI。

这样上一轮的产物、会话历史和未提交文件都不会被下一轮读到。

## 采集结果

每轮结束后运行：

```text
collect-A.cmd
collect-B.cmd
```

它会：

- 找到该轮最新的 `rollout-*.jsonl`；
- 提取 `session_meta.payload.session_id`；
- 把轨迹复制到 `results/A/` 或 `results/B/`；
- 生成 `summary.json`；
- 把当前产物做成一个 parent 为初始快照的 commit；
- 校验这一轮是否合法（只有一条 prompt、以 `task_complete` 结束、没有 `turn_aborted`），把结果写入 `summary.json` 的 `run_valid` / `validity_note`，不合法时会直接告警。

## 自动录屏

`run-A.cmd` / `run-B.cmd` 会在拉起 CLI 之前自动开始录屏，CLI 退出后停止，
视频落到 `tasks\<task-id>\results\<A|B>\<A|B>.mp4`（已加入 `.gitignore`，不进 Git），
路径会写进 `summary.json` 的 `video_path` 并出现在 `submission.md` 的「运行录屏」一行。

- 参数在 `tools/config/record.json`：`ffmpegPath` / `framerate` / `crf` / `preset`。
  默认 10fps + crf 26，整屏录制（gdigrab），3840x1080 大约 200 KB/s，跑 10 分钟约 120 MB；
  想更小就调低 `framerate` 或调高 `crf`。
- `ffmpegPath` 是本机路径，换机器或走 PATH 都能用：脚本会依次尝试配置路径、同目录的 ffprobe、
  裸命令 `ffmpeg`。
- 没装 ffmpeg、或把 `enabled` 改成 `false` 时，自动跳过录屏，任务照常跑。
- 只开窗口不采集结果：`open-A.cmd`（要顺便录屏就 `open-A.cmd -Record`）。
- 这一轮不想录：`run-A.cmd -NoRecord`。

单独检查某一轮是否合法：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\verify-run.ps1 -Path tasks\my-task\results\A
```

## 生成提交字段

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\make-submission.ps1 -TaskDir tasks\my-task
```

会读取 `meta.json` 和 `results/A|B/summary.json`，按飞书表格要求输出
「语言/框架、初始环境快照、A/B-SessionID、A/B-轨迹文件、A/B-产物快照」等字段，
同时写入 `tasks\<task-id>\submission.md`。

## 推送到 GitHub

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\push-all.ps1
```

它会把 `main`（工具 + 轨迹）和所有 `task/<id>/base`、`task/<id>/A`、`task/<id>/B`
分支推到 `https://github.com/lucky-people/gsb-test`，推送后逐个比对远端 SHA，
失败会按间隔重试。GitHub 直连不稳定时，先启动本地代理再执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\push-all.ps1 -ProxyUrl http://127.0.0.1:7897
```

## 重置

如果某一轮失败，可以直接运行：

```text
reset-A.cmd
reset-B.cmd
```

下一次启动也会自动重置。

## 安全说明

启动器使用 `--dangerously-bypass-approvals-and-sandbox` 来实现全自动运行。它不会弹出 yes/no，但也意味着 Codex 可以读写当前用户有权限访问的文件。请只在专门的 A/B 工作区里使用，不要在包含重要未备份数据的目录里运行。
