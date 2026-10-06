# Container image for the manual GUI in hosted mode (ADR-0023).
# Standard library only: nothing is installed beyond the interpreter.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY . .

# Configuration comes from the environment at start:
#   FRAMESHIFT_PASSWORD   required, at least 16 characters
#   FRAMESHIFT_OPERATOR   the actor id approvals record (default user_local)
#   FRAMESHIFT_PUBLIC_HOST or the platform's RAILWAY_PUBLIC_DOMAIN
#   PORT                  injected by the platform
#   RAILWAY_VOLUME_MOUNT_PATH or FRAMESHIFT_STORE, where event logs persist
CMD ["python", "-m", "frameshift.bootstrap", "gui", "--hosted"]
