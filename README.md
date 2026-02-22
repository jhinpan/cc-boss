# cc-boss

Open-source implementation of [胡渊鸣 (Yuanming Hu)](https://www.zhihu.com/people/iterator)'s workflow for [managing 10 Claude Code instances in parallel](https://zhuanlan.zhihu.com/p/2007147036185744607).

Orchestrate multiple Claude Code instances from a mobile-friendly web UI. Dispatch tasks from your phone, watch them execute in real-time.

## Quick Start

```bash
# Clone and install
git clone https://github.com/jhinpan/cc-boss.git
cd cc-boss
uv sync

# Start with 5 parallel workers
uv run cc-boss start --port 8080 --workers 5 --repo /path/to/your/project
```

Open `http://localhost:8080` in your browser.

## Remote Access (iPhone)

```bash
# On the remote node — Cloudflare Tunnel gives you a free HTTPS URL
cloudflared tunnel --url http://localhost:8080
# Prints https://xxx.trycloudflare.com
# Open on iPhone Safari → Share → Add to Home Screen → full-screen PWA
```

## Architecture

```
iPhone / Desktop Browser
       │
  Cloudflare Tunnel (free HTTPS)
       │
   cc-boss (FastAPI)  ←── port 8080
       ├── Task Queue (SQLite)
       ├── Ralph Loop Scheduler (per-worker)
       ├── Plan Mode Manager
       └── CC Runner (subprocess)
           claude -p --dangerously-skip-permissions
                  --output-format stream-json
                  --worktree <name>

       ┌────────┬────────┬────────┐
       │ wt-0   │ wt-1   │ wt-N   │
       │ (CC#0) │ (CC#1) │ (CC#N) │
       └────────┴────────┴────────┘
```

## Features (maps to the 10-step blog)

| Step | Feature | Description |
|------|---------|-------------|
| 1-2 | CC Runner | Spawn `claude -p` subprocesses, parse `stream-json` events in real-time |
| 3 | Ralph Loop | Each worker pulls from a shared SQLite task queue sequentially |
| 4 | Parallel Workers | N workers, each in its own git worktree via `--worktree` |
| 5 | PROGRESS.md | Auto-append lessons learned after each task |
| 6 | Web Manager | FastAPI + htmx, mobile-first dark UI, PWA support |
| 7 | CC monitors CC | Detect errors in stream-json, auto-enqueue fix tasks |
| 8 | Voice Input | Web Speech API — hold mic button to dictate tasks |
| 9 | Plan Mode | Generate plan first, review on phone, approve to execute |
| 10 | CLAUDE.md | Jinja2 template for per-project instructions |

## CLI

```bash
# Add tasks from command line
uv run cc-boss add "fix the failing test in test_auth.py"
uv run cc-boss add --priority 10 "urgent: patch the security hole"

# Check queue status
uv run cc-boss status
```

## Deployment (remote GPU node)

```bash
# One-time setup
bash deploy/setup-node.sh

# Launch
cc-boss start --port 8080 --workers 5 --repo /path/to/project &
bash deploy/cloudflared.sh
```

## Credits

This project is an open-source implementation of the workflow described by [胡渊鸣 (Yuanming Hu)](https://www.zhihu.com/people/iterator) in his [Zhihu post](https://zhuanlan.zhihu.com/p/2007147036185744607) about orchestrating 10 Claude Code instances to work in parallel. The core ideas — Ralph Loop, plan-then-execute, PROGRESS.md accumulation, stream-json monitoring — come from that post.

## License

MIT
