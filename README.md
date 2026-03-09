# arxiv_cast

Self-hosted dashboard: system stats, Pi-hole, and **ArxivCast** (arXiv fetch + AI podcast in `arxvicast/`).

## Git

One repo, one remote (`origin` → arxiv_cast). Push and pull the whole project.

```bash
cd /home/rishav/weblogger
git remote remove intel-stack   # optional, if you had it as a remote
git remote add origin git@github.com:rishavsen1/arxiv_cast.git
git push -u origin main
```

Then: `git push`, `git pull` as usual.

## Systemd

```bash
sudo cp /home/rishav/weblogger/pi_dashboard.service /etc/systemd/system/pi_dashboard.service
sudo systemctl daemon-reload
sudo systemctl restart pi_dashboard.service
```
