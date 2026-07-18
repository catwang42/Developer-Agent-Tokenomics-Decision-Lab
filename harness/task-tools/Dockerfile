# Clean-container environment for the parameterized task 10-point validation
# (SPEC 2.8). Build from the repository root:
#   docker build -f harness/task-tools/Dockerfile -t task-validate .
# Run a task's validation end-to-end (needs network to clone the subject repo):
#   docker run --rm --network=host -e TASK_DIR=/lab/tasks/pilot-realworld task-validate
#   docker run --rm --network=host -e TASK_DIR=/lab/tasks/suite/W4-complex-bugfix task-validate
#
# The image carries only the tooling and the task harness; the subject repo is
# cloned fresh at the pinned commit inside the container, proving reproducibility
# from scratch rather than baking in a pre-built tree.
FROM node:20-bookworm-slim

RUN apt-get update -qq \
    && apt-get install -y --no-install-recommends git ca-certificates python3 python3-yaml \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /lab

COPY manifest/ /lab/manifest/
COPY tasks/ /lab/tasks/
COPY harness/task-tools/ /lab/harness/task-tools/

ENV TASK_WORKDIR=/tmp/task-work
ENV NX_DAEMON=false CI=true TASK_IN_CONTAINER=1
ENV TASK_DIR=/lab/tasks/pilot-realworld

ENTRYPOINT ["bash", "/lab/harness/task-tools/validate.sh"]
