# Code Review: [DSP-7893] Modernize seiji-dockerbase for py3.11 + uv

**MR:** [!38](https://gitlab.com/abacusinsights/seiji/seiji-dockerbase/-/merge_requests/38)
**Author:** eric.shtivelberg
**Branch:** `py311_upgrade_DSP-7893` -> `master`
**Pipeline:** passed
**Files changed:** 3 (Dockerfile, .gitlab-ci.yml, .gitignore)

---

## Findings

### HIGH

#### 1. Incorrect build-arg name in `build:kaniko_node16_py311` (.gitlab-ci.yml)

The node16 CI variant passes `node_version_15=16.17.1` but the Dockerfile no longer declares a `node_version_15` ARG -- it was removed in this MR. The old Dockerfile had `ARG node_version_15="15.13.0"` which mapped to `NODE_VERSION_15`, but both the ARG and the ENV were deleted.

```yaml
build:kaniko_node16_py311:
  extends: build:kaniko
  variables:
    EXTRA_DOCKER_BUILD_ARGS: "--build-arg python_version_arg=3.11.11 --build-arg node_version_15=16.17.1"
    EXTRA_DOCKER_TAGS: seiji-dockerbase-node16-py3.11
```

This build-arg will be silently ignored by Docker. The resulting image will have Node 20.20.0 (the default), not Node 16.17.1 as intended. The tag `seiji-dockerbase-node16-py3.11` will be misleading.

**Fix:** Either (a) add a new ARG (e.g., `node_version_arg`) to the Dockerfile that overrides the NVM default install/alias, or (b) repurpose the existing `node_version_20` ARG to be generic so callers can override it, or (c) remove this variant entirely if Node 16 is no longer needed (Node 16 is EOL since Sep 2023).

#### 2. Default Python version mismatch between Dockerfile and CI (.gitlab-ci.yml, Dockerfile)

The Dockerfile default `ARG python_version_arg=3.11.15` (patch 15) but the CI jobs all pass `--build-arg python_version_arg=3.11.11` (patch 11). The default Dockerfile image (built without args) would use 3.11.15 while all CI-built variants use 3.11.11. This is inconsistent and could cause confusion if someone builds the image locally without the CI overrides.

**Suggestion:** Align the Dockerfile default to `3.11.11` to match CI, or update CI to `3.11.15`.

#### 3. Shell quoting issue in Docker apt source list (Dockerfile)

The `echo` command that writes the Docker apt source list has nested double quotes that collide with the outer delimiters:

```dockerfile
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "${VERSION_CODENAME}") stable" > /etc/apt/sources.list.d/docker.list
```

The inner `"${VERSION_CODENAME}"` double quotes will terminate the outer `echo "..."` string in some parsing contexts. In practice this may work because Docker's RUN shell handles the subshell nesting, but this is fragile. The canonical Docker docs pattern uses `$VERSION_CODENAME` without inner quotes.

**Suggestion:** Use `$VERSION_CODENAME` without the inner double quotes, or escape them.

### MEDIUM

#### 4. Python build dependencies removed -- downstream C extension compilation will fail (Dockerfile)

The old image installed build-essential, automake, libtool, libffi-dev, libssl-dev, libsqlite3-dev, libreadline-dev, libbz2-dev, zlib1g-dev, libpng-dev, make, and software-properties-common. The new image removes all of them and relies on `uv python install` which downloads prebuilt CPython binaries.

Downstream consumers of this image that `pip install` packages with C extensions (e.g., `cryptography`, `psycopg2`, `Pillow`, `lxml`) will fail at build time because the compiler toolchain and dev headers are gone.

**Action:** Verify that all downstream images (seiji-orchestrator variants, airflow, etc.) do not rely on compiling C extensions in this base image. If they do, a subset of build dependencies needs to be restored (at minimum `build-essential`, `libffi-dev`, `libssl-dev`).

#### 5. `apt-get purge -y wget` on an image that never installed wget (Dockerfile)

The new Dockerfile no longer installs `wget` (replaced with `curl` throughout), but the final security refresh step runs `apt-get purge -y wget`. Not a bug (purge succeeds silently), but dead code that suggests an incomplete cleanup pass.

#### 6. No `node_version_arg` build-arg abstraction (Dockerfile)

The old Dockerfile had two node version ARGs allowing CI to override node versions. The new Dockerfile hardcodes `node_version_20` as the only node ARG but the CI `build:kaniko_node16_py311` variant attempts to use a different node version (see HIGH #1). If multiple node versions are still needed, the Dockerfile should expose a generic `node_version_arg` build-arg.

#### 7. Terraform version bump from 0.13.7 to 1.3.2 default (Dockerfile)

The default Terraform version jumps from 0.13.7 to 1.3.2. The base `build:kaniko_311` variant does not override it, so it will also get Terraform 1.3.2 by default. Confirm that all consumers of the non-terraform-suffixed tag are compatible with Terraform 1.3.2 (or do not use Terraform at all).

### LOW

#### 8. .gitignore includes `.cursor/` with unrelated comment (.gitignore)

The new `.gitignore` has a comment referencing "dispatch-sync" which appears to be tooling unrelated to this repository.

#### 9. Kubernetes 1.33.0 version pin (Dockerfile)

`KUBERNETES_VERSION="1.33.0"` -- verify that kubectl 1.33.0 has been released and is the intended target. The pipeline passed so the download likely succeeded, but worth confirming.

---

## Positive Observations

- **Strong security posture:** Moving from `docker-ce` (full daemon) to `docker-ce-cli` only is a meaningful attack surface reduction. The `dist-upgrade` final layer and helm cache cleanup are good hardening practices.
- **Modern toolchain migration:** pyenv+poetry -> uv is a significant simplification that reduces build time, image layers, and maintenance overhead.
- **wget elimination:** Replacing all `wget` calls with `curl -fsSL` is cleaner and removes a dependency. The `-f` flag ensures HTTP errors are caught.
- **apt-key deprecation fix:** The Docker repo setup correctly migrates from the deprecated `apt-key add` to the `/etc/apt/keyrings/` signed-by pattern required by Ubuntu 24.04.
- **Node 15 removal:** Node 15 has been EOL since June 2021. Defaulting to Node 20 LTS is correct.
- **Poetry removal:** With uv handling Python package management, the poetry dependency and its version pinning are no longer needed.

---

## Recommendation

**Needs changes** -- The `node_version_15` build-arg typo in the CI node16 variant (HIGH #1) means that variant will silently produce an image with the wrong Node version while being tagged as `node16`. This must be fixed before merge. The Python version default mismatch (HIGH #2) and shell quoting fragility (HIGH #3) should also be addressed. The build dependency removal (MEDIUM #4) warrants confirmation from downstream consumers.
