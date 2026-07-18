# Clean-container environment for the pilot 10-point validation (SPEC 2.8).
# Build from the repository root:
#   docker build -f tasks/pilot-realworld/Dockerfile -t pilot-validate .
# Run the full validation end-to-end (needs network to clone the subject repo):
#   docker run --rm --network=host pilot-validate
#
# The image carries only the tooling and the pilot harness; the subject repo is
# cloned fresh at the pinned commit inside the container, so the run proves
# reproducibility from scratch rather than baking in a pre-built tree.
FROM node:20-bookworm-slim

# git (clone the subject repo) + python3/pyyaml (read the delivery manifest).
RUN apt-get update -qq \
    && apt-get install -y --no-install-recommends git ca-certificates python3 python3-yaml \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /lab

# Copy only what the validator needs (see .dockerignore for exclusions).
COPY manifest/ /lab/manifest/
COPY tasks/ /lab/tasks/

# Work outside the copied tree; keep the image's /lab pristine.
ENV PILOT_WORKDIR=/tmp/pilot-work
ENV NX_DAEMON=false CI=true PILOT_IN_CONTAINER=1

ENTRYPOINT ["bash", "/lab/tasks/pilot-realworld/validate.sh"]
