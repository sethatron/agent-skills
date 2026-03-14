# Anti-Patterns

## ECR Image Forking: Always specify --platform linux/amd64
When pulling images from public ECR to push to private ECR, ALWAYS use `docker pull --platform linux/amd64`. On Apple Silicon (M-series) Macs, Docker defaults to arm64 architecture. EKS nodes run x86_64/amd64. Pushing an arm64 image causes `exec format error` at container startup.

## Don't wait indefinitely for seiji deploys
When using `--executor native`, if a deploy takes >15 minutes, stop waiting and check logs directly in `./work/<label>_targeted_deploy/output/` directory. For airflow executor deploys, retrieve logs from S3 instead.
