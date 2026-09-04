# Oracle Cloud Ampere A1 24/7 Capacity Catcher

Automated GitHub Actions runner that continuously monitors and claims an **Oracle Cloud Always Free Ampere A1 instance (2 OCPU, 12 GB RAM)** in `ap-batam-1`.

### How It Works:
1. Runs in the cloud via GitHub Actions on a 30-minute schedule (even when your laptop is turned off).
2. Repeatedly attempts to provision the instance.
3. Once successful, it creates an issue with your server's Public IP and sends an email notification.
4. Auto-terminates once the instance is running to avoid duplicate instances.
