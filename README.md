# Web logger

Self-hosted Raspberry Pi dashboard: system stats, Pi-hole, and **ArxivCast** (arXiv fetch + AI podcast) in `intel-stack/`.

## Git: one repo, push/pull only intel-stack (no clones)

- **weblogger** is one local repo. You add **one remote**, which is your intel-stack repo. Push and pull only the `intel-stack/` folder via **git subtree** — no separate clone.

**One-time setup:**

```bash
cd /home/rishav/weblogger
git init
git add .
git commit -m "Initial commit: dashboard + intel-stack"
git remote add intel-stack git@github.com:rishavsen1/arxiv_cast.git
```

**Publish intel-stack** (push only the `intel-stack/` folder to that remote):

```bash
./scripts/push_intel_stack.sh
```

(Uses `git subtree push --prefix=intel-stack intel-stack main` under the hood.)

**Pull intel-stack** (if you changed it on GitHub and want those changes locally):

```bash
git subtree pull --prefix=intel-stack intel-stack main
```

So: commits are local for the whole weblogger tree; push and pull only affect the intel-stack remote and the `intel-stack/` prefix. No clones.

## Systemd

After editing the service file:

```bash
sudo cp /home/rishav/weblogger/pi_dashboard.service /etc/systemd/system/pi_dashboard.service
sudo systemctl daemon-reload
sudo systemctl restart pi_dashboard.service
```
