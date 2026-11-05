# Azure event downloader

From the Azure directory, after `docker login` and `az login`:

```bash
bash build_and_push_images.sh
bash container_app_job.sh
```

Both scripts work from any directory. The build uses the repository root as its
context and the root Dockerfile, targeting linux/amd64.

The deployment script sources the project-root `.env` using Bash, then creates or
updates the job directly from `python_container_app_job.yaml` and sets the real
Google Drive API secret using `az containerapp job secret set`. Use shell-compatible
`KEY=value` assignments without spaces around `=`. The YAML contains a bootstrap
secret that is replaced on each deployment. Do not run the YAML directly.

Edit the image tag, environment ID, folder ID, schedule, and storage registration
in the YAML. Keep the image tag consistent with build_and_push_images.sh and
compose.yaml. The folder ID is configured in YAML; the deployment reads the API
key from `.env`. The local Compose service reads both Google Drive settings from
`.env`.

The environment storage registration luckyliquor-file-mount points to the
lucky-rails-public-assets share with ReadWrite access, mounted at /event_img.
The Docker Hub repository must be public for anonymous Azure image pulls.

The job runs every six hours at 00:00, 06:00, 12:00, and 18:00 UTC. Deployment
starts an extra execution only if requested:

```bash
START_JOB=true bash container_app_job.sh
```

One replica per execution does not prevent separate executions from overlapping.
The YAML bootstrap secret is temporarily applied during deployment until the real
secret is set; avoid deploying while an execution is starting.

For local execution from the project root, with the external volume
lucky_rails_public_assets present:

```bash
docker compose -f compose.yaml run --build --rm event-downloader
```

This local Docker volume is separate from Azure Files storage.
