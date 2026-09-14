# Deployment runbook

This app has two independent hosting options: Streamlit Community Cloud and Docker on AWS EC2. Updating one does not update the other. Merging a PR does **not** deploy the EC2 container; there is no deployment workflow in this repository.

## Current AWS setup

Recorded on 2026-09-14. Recheck live state before making changes.

| Setting | Value |
| --- | --- |
| Repository directory | `/home/ubuntu/gs-excel-transformation` |
| Container | `gs-excel-transformation` |
| Initial application commit | `1295f66d4e8667555438f798c73d067d8a98253b`, includes PR #3 |
| Initial image tag | `gs-excel-transformation:1295f66` |
| Host binding | `0.0.0.0:8880` to container TCP `8501` |
| Protocol | HTTP, not HTTPS |
| Restart policy | `unless-stopped` |
| Limits | 1 CPU, 1 GiB memory, 256 processes; no additional swap allowance |
| Docker logs | `max-size=10m`, `max-file=3` |
| Runtime user | Non-root UID/GID `10001:10001` |
| Health check | `/_stcore/health` every 30 seconds |
| Hostnames and instance addresses | Obtain from the deployment owner; do not assume an EC2 public address is permanent |

The host also runs calculator, chatbot, and optimiser containers on ports `8501`, `8502`, and `8503`. Do not stop, replace, or prune those containers or their images.

The initial Docker build files were created directly on the server before this documentation PR. When adopting the tracked Docker files, review and move the existing untracked copies outside the checkout before pulling. Do not use `git reset --hard`, `git clean`, or overwrite local files to resolve a pull conflict.

## Access and security

Public IPv4 access to host port `8880` was explicitly enabled for initial testing. The app currently has no built-in authentication. Public access is not an endorsement for sending confidential spreadsheets over HTTP.

- Use non-sensitive files until HTTPS and access controls are configured.
- Container limits reduce resource contention, but large uploads and concurrent processing can still exhaust the app's memory. This deployment has not been load-tested.
- Uploads and processed data are held in the app session. Restarting the container interrupts users and loses those sessions. There is no persistent data volume in this setup.
- Do not bake credentials, `.env` files, or Streamlit secrets into an image. The Docker build copies only requirements and application code.
- Do not open additional ports or change shared security groups as part of a routine code update.

### Cloudflare handoff

Give the Cloudflare administrator the current origin address and **HTTP port `8880`**. Ask them to configure a company hostname, HTTPS, WebSocket support, and authentication if needed.

Cloudflare supports `8880` as an HTTP proxy port. A proxied DNS record alone does not translate a normal HTTPS request on `443` to HTTP origin port `8880`. The administrator must choose and verify an appropriate origin-port and TLS setup. Do not assume `https://hostname:8880` works.

After standard proxying works, restrict origin ingress to Cloudflare's current published address ranges, coordinating the change with the AWS owner. Otherwise direct access to the origin can bypass Cloudflare protections. Restricting the source is not itself application authentication.

Alternatively, a tunnel connector running directly on this host can reach `http://localhost:8880`. Confirm its configuration and health with its owner. With a verified tunnel, the app can bind to localhost and public inbound access to `8880` can be removed as a separate approved change.

## Prerequisites

Run the commands below in a Linux shell on the **verified target EC2 host**, not on your Windows machine or an unrelated server.

Required: Git, Docker, permission to use Docker, and network access to GitHub, the container registry, and the Python package index. The Dockerfile installs Python dependencies inside the image; do not install them globally on the host.

Before deploying:

```bash
hostname
date -Is
free -m
df -h /
docker ps --format '{{.Names}}\t{{.Image}}\t{{.Status}}'
ss -ltn
```

Verify host identity, available capacity, and port ownership. If permissions fail, ask the operator; do not escalate privileges or change IAM automatically.

The Dockerfile sets `TZ=UTC`. Keep the container in UTC because `calculate_adjusted_datetime()` adds 9 hours for GS SGV1 and 8 hours for other selections. Running the same code on a local machine already in Singapore time adds those offsets again. The README's local-testing warning still applies; do not change the host timezone to compensate.

## First deployment

Skip cloning if the repository already exists. Inspect that checkout instead.

```bash
git clone --branch main https://github.com/SIMPPLE-AI/gs-excel-transformation.git /home/ubuntu/gs-excel-transformation
cd /home/ubuntu/gs-excel-transformation
git status --short
REV=$(git rev-parse HEAD)
IMAGE="gs-excel-transformation:$REV"
docker build -t "$IMAGE" .
```

Stop if the build fails. A build does not replace a running container. Record the commit, image ID, and deployment time in your change record. Commit tags identify source, but the mutable base image means rebuilding later is not guaranteed to produce identical image bytes. Keep the previous image for rollback.

Once the image builds and host port `8880` and the container name are available:

```bash
docker run -d \
  --name gs-excel-transformation \
  --restart unless-stopped \
  --memory 1g --memory-swap 1g --cpus 1 --pids-limit 256 \
  --cap-drop ALL --security-opt no-new-privileges \
  --log-opt max-size=10m --log-opt max-file=3 \
  -p 0.0.0.0:8880:8501 \
  "$IMAGE"
```

This binding exposes the port on host IPv4 interfaces, subject to network controls. It reproduces the initial public-access deployment. For a local tunnel connector, use `127.0.0.1:8880:8501` instead, only after agreeing the routing change. `unless-stopped` requires the Docker daemon to start after a host reboot; it does not restart a manually stopped container.

## Updating an existing deployment

Coordinate a maintenance window. Replacing the container causes brief downtime and clears upload sessions. Review this runbook against the running container's settings before using it.

1. Inspect the checkout and fetch the approved code:

   ```bash
   cd /home/ubuntu/gs-excel-transformation
   git status --short
   git fetch origin
   git log -5 --oneline origin/main
   ```

   Resolve unexpected local changes with the owner first. In particular, review the initial untracked Docker files before the first pull of this PR. Never discard them blindly.

2. Fast-forward `main` and build before stopping the current app:

   ```bash
   git switch main
   git pull --ff-only origin main
   REV=$(git rev-parse HEAD)
   IMAGE="gs-excel-transformation:$REV"
   docker build -t "$IMAGE" .
   ```

   Confirm the resulting commit is approved. Stop on any failed command. Do not deploy a different commit merely because `main` advanced.

3. Preserve the current container and its configuration for rollback:

   ```bash
   BACKUP="gs-excel-transformation-backup-$(date -u +%Y%m%dT%H%M%SZ)"
   docker inspect --format '{{.Config.Image}} {{.Image}}' gs-excel-transformation
   docker stop --time 30 gs-excel-transformation
   docker rename gs-excel-transformation "$BACKUP"
   ```

   Record `$BACKUP` in the change record. Check each command succeeded before continuing. Run the `docker run` command from **First deployment**, using the new `$IMAGE` and preserving the agreed binding and runtime settings.

4. Verify the app below. If verification fails, roll back rather than changing unrelated services.

## Verification

```bash
curl --fail --max-time 5 http://127.0.0.1:8880/_stcore/health
docker inspect --format '{{.State.Status}} {{.State.Health.Status}}' gs-excel-transformation
docker ps --format '{{.Names}}\t{{.Status}}'
```

Allow startup time. HTTP `200` and Docker `healthy` confirm the health endpoint responds, not that spreadsheet processing is correct. Verify the other three apps remain running.

In a browser using the intended access path:

1. Confirm the upload form and Process button load. This also exercises the Streamlit WebSocket connection.
2. Upload a non-sensitive representative CSV or XLSX, select the intended server, and enter a cutoff time older than the sample's receive-task-report times. The filter is strictly greater than the cutoff.
3. For GS SGV2, check `loop_count` after `pause_time`, and the `lat` and `lng` columns. PR #3 adds these automatically.
4. Verify whole-number formatting, fractional values, row count, and generated timestamps against expected output.
5. Download the XLSX and inspect it. Test the copy button separately; browser clipboard access may be unavailable on a plain HTTP origin.

Do not treat a successful empty result as proof of processing correctness. Keep real user data out of logs and screenshots.

## Rollback

Use the exact backup name recorded during the update. Do not guess a container to stop or remove.

```bash
# Replace the value with the recorded name of the previous app container.
BACKUP='gs-excel-transformation-backup-<recorded-timestamp>'
docker container inspect --format '{{.Name}} {{.Config.Image}}' "$BACKUP"
```

Confirm the backup is the intended previous version. If the replacement container exists, stop it and rename it to preserve failure evidence:

```bash
FAILED="gs-excel-transformation-failed-$(date -u +%Y%m%dT%H%M%SZ)"
docker stop --time 30 gs-excel-transformation
docker rename gs-excel-transformation "$FAILED"
```

If creation failed before a replacement container existed, skip those two commands. Then restore the original container:

```bash
docker rename "$BACKUP" gs-excel-transformation
docker start gs-excel-transformation
```

Repeat verification. The restored container retains its previous image, port bindings, restart policy, and limits. The repository checkout may still be at the newer revision; it does not determine the code inside the restored image.

Keep backups until the change is accepted. Cleanup must target explicitly identified app containers/images. Never run a host-wide Docker prune on this shared server.

## Troubleshooting

- **Local health succeeds, public access times out:** check the intended source address, EC2 security groups, network ACLs, and host firewall. Do not open the port to everyone as an automatic fix.
- **Page shell loads but the form does not:** inspect app startup errors and WebSocket/proxy routing. A health response alone is insufficient.
- **Container exits:** check its exit state and a bounded log sample. Avoid copying raw logs containing uploads or credentials into tickets.
- **Changes do not appear:** confirm the running image, not only `git log`. Source edits on the host do not alter a built image.
- **Wrong timestamps locally:** review the UTC assumption above. The displayed Singapore clock and generated output timestamps use different functions.
- **Cloudflare hostname fails:** confirm DNS proxy status, allowed origin sources, origin protocol/port, TLS configuration, and WebSocket handling with its administrator.

No GitHub Actions deployment, DNS changes, or security-group changes are performed by this runbook or the included Dockerfile.
