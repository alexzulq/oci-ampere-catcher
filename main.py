#!/usr/bin/env python3
"""
Oracle Cloud Infrastructure (OCI) Ampere Always Free 24/7 Continuous Provisioner
Runs uninterrupted in GitHub Actions (Public Repo - Unlimited Free Minutes).
Pings Oracle continuously every 45-60 seconds.
"""

import os
import sys
import time
import subprocess
from datetime import datetime
import oci

def log(msg):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {msg}", flush=True)

def main():
    log("=== Starting OCI Ampere A1 Continuous 24/7 Cloud Provisioner ===")
    
    # Required environment variables from GitHub Secrets
    user_ocid = os.environ.get("OCI_USER")
    fingerprint = os.environ.get("OCI_FINGERPRINT")
    tenancy_ocid = os.environ.get("OCI_TENANCY")
    region = os.environ.get("OCI_REGION", "ap-batam-1")
    key_content = os.environ.get("OCI_KEY_CONTENT")
    ssh_pubkey = os.environ.get("OCI_SSH_PUBKEY")
    subnet_id = os.environ.get("OCI_SUBNET_ID")
    
    if not all([user_ocid, fingerprint, tenancy_ocid, key_content, ssh_pubkey, subnet_id]):
        log("Error: Missing required environment variables.")
        sys.exit(1)

    # Write private key file for OCI SDK
    key_path = os.path.expanduser("~/.oci_api_key.pem")
    with open(key_path, "w") as f:
        f.write(key_content.strip() + "\n")
    os.chmod(key_path, 0o600)

    config = {
        "user": user_ocid,
        "fingerprint": fingerprint,
        "tenancy": tenancy_ocid,
        "region": region,
        "key_file": key_path
    }
    oci.config.validate_config(config)

    compute = oci.core.ComputeClient(config)
    network = oci.core.VirtualNetworkClient(config)

    # Check if instance already exists to prevent duplicate instances
    existing_instances = compute.list_instances(tenancy_ocid, display_name="solar-fleet-server").data
    for inst in existing_instances:
        if inst.lifecycle_state in ["PROVISIONING", "RUNNING", "STARTING"]:
            log(f"Instance already exists and is {inst.lifecycle_state}! Halting runner.")
            
            # Fetch public IP
            vnic_attachments = compute.list_vnic_attachments(tenancy_ocid, instance_id=inst.id).data
            if vnic_attachments:
                vnic = network.get_vnic(vnic_attachments[0].vnic_id).data
                log(f"Public IP: {vnic.public_ip}")
            sys.exit(0)

    ad_name = "lGbf:AP-BATAM-1-AD-1"
    image_id = "ocid1.image.oc1.ap-batam-1.aaaaaaaa3tnngyx7pvxtq6utczzc4gb2wl6d3kghs42fqyy5lqxz5q4atrjq" # Ubuntu 24.04 Minimal ARM

    launch_details = oci.core.models.LaunchInstanceDetails(
        compartment_id=tenancy_ocid,
        availability_domain=ad_name,
        display_name="solar-fleet-server",
        shape="VM.Standard.A1.Flex",
        shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(
            ocpus=2.0,
            memory_in_gbs=12.0
        ),
        image_id=image_id,
        metadata={
            "ssh_authorized_keys": ssh_pubkey.strip()
        },
        create_vnic_details=oci.core.models.CreateVnicDetails(
            subnet_id=subnet_id,
            assign_public_ip=True,
            display_name="solar-primary-vnic"
        )
    )

    # Run for up to 5 hours (300 minutes) per runner job
    max_duration_seconds = 5 * 3600
    start_time = time.time()
    attempt = 0

    log(f"Continuous loop active in {region} ({ad_name}). Shape: 2 OCPU, 12 GB RAM.")
    log(f"Will continuously retry every 45 seconds for up to 5 hours, then auto-relay to the next run.")

    while (time.time() - start_time) < max_duration_seconds:
        attempt += 1
        try:
            log(f"[Attempt #{attempt}] Requesting Ampere A1 allocation from Oracle...")
            response = compute.launch_instance(launch_details)
            instance = response.data
            log("🎉🎉🎉 SUCCESS! Instance provisioned successfully!")
            log(f"Instance ID: {instance.id}")
            log("Waiting for instance to reach RUNNING status...")

            # Wait for running state
            oci.wait_until(
                compute,
                compute.get_instance(instance.id),
                'lifecycle_state',
                'RUNNING',
                max_wait_seconds=300
            )

            # Retrieve Public IP
            public_ip = "Pending"
            vnic_attachments = compute.list_vnic_attachments(tenancy_ocid, instance_id=instance.id).data
            if vnic_attachments:
                vnic = network.get_vnic(vnic_attachments[0].vnic_id).data
                public_ip = vnic.public_ip

            summary_md = f"""# 🚀 Oracle Always Free Server Provisioned!

- **Public IP:** `{public_ip}`
- **Username:** `ubuntu`
- **Instance ID:** `{instance.id}`
- **Shape:** `VM.Standard.A1.Flex` (2 OCPU, 12 GB RAM)
- **Region:** `{region}`

### Connect via SSH from your Mac:
```bash
ssh -i ~/Downloads/ssh-key-2026-09-04.key ubuntu@{public_ip}
```
"""
            log(summary_md)

            # Write to GitHub Actions summary if available
            step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
            if step_summary:
                with open(step_summary, "a") as f:
                    f.write(summary_md + "\n")

            # Create GitHub Issue to send instant email alert
            repo = os.environ.get("GITHUB_REPOSITORY")
            token = os.environ.get("GITHUB_TOKEN")
            if repo and token:
                try:
                    subprocess.run([
                        "gh", "issue", "create",
                        "--repo", repo,
                        "--title", f"🚀 Oracle Server Ready: {public_ip}",
                        "--body", summary_md
                    ], check=False)
                    log("Created GitHub Issue (email notification sent to alex.zulq@gmail.com).")
                except Exception as e:
                    log(f"Failed to create notification issue: {e}")

            sys.exit(0)

        except oci.exceptions.ServiceError as e:
            if "Out of host capacity" in str(e.message) or e.status in [429, 500]:
                log(f"Capacity full in Batam AD-1. Retrying in 45 seconds...")
            else:
                log(f"OCI Service Notice [{e.code}]: {e.message.strip()}. Retrying in 45s...")
            time.sleep(45)
        except Exception as err:
            log(f"Temporary error: {err}. Retrying in 45 seconds...")
            time.sleep(45)

    log("5-hour relay window reached. Triggering next continuous workflow run...")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if repo:
        try:
            subprocess.run(["gh", "workflow", "run", "catcher.yml", "--repo", repo], check=False)
            log("Next continuous relay workflow successfully triggered!")
        except Exception as e:
            log(f"Relay trigger notice: {e}")

    sys.exit(0)

if __name__ == "__main__":
    main()
