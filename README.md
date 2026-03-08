# arxiv_cast

Self-hosted dashboard: system stats, Pi-hole, and **ArxivCast** (arXiv fetch + AI podcast in `intel-stack/`).

## Git

One repo, one remote (`origin` → arxiv_cast). Push and pull the whole project.

```bash
cd /home/rishav/weblogger
git remote remove intel-stack   # if you added it earlier
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
