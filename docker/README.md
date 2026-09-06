# Production API Container

This deployment runs the Research API only. Build and run from the repository
root:

```powershell
docker compose -f docker/compose.production.yml build
docker compose -f docker/compose.production.yml up -d
docker compose -f docker/compose.production.yml ps
```

Create `.env` from `.env.example` first and replace every placeholder secret.
The compose file binds the API to loopback, runs as a non-root user, drops Linux
capabilities, uses a read-only root filesystem, and defaults to 1 GiB RAM, 1 CPU,
128 processes, and a 128 MiB temporary filesystem. Numeric library threads are
also limited to one by default to avoid RAM and CPU oversubscription.

Adjust the allocation in the root `.env` only after measuring the workload:

```env
JAYA_CONTAINER_MEMORY=1g
JAYA_CONTAINER_MEMORY_RESERVATION=512m
JAYA_CONTAINER_CPUS=1.0
JAYA_CONTAINER_PIDS=128
JAYA_CONTAINER_TMPFS=128m
JAYA_OMP_THREADS=1
JAYA_OPENBLAS_THREADS=1
JAYA_MKL_THREADS=1
JAYA_NUMBA_THREADS=1
```

Increase one value at a time. Do not remove the limits or set unlimited values.
If the container reaches its memory limit, Docker may terminate the process;
that is preferable to allowing an uncontrolled host-level memory exhaustion.

The UI must be built separately with `npm ci` and `npm run build` in
`packages/jaya-research/ui`. Put the resulting static files behind an
authenticated TLS reverse proxy that forwards `/api` to the API container.
Do not expose port 8000 directly to the public internet.

The container is a deployment baseline, not proof of production readiness.
Backups, TLS termination, secret rotation, monitoring, and rollback must be
verified by the operator before handling real user data.
