# Tags: docker, verification
# Links: triad/ts_verify/__init__.py, triad/ts_verify/verify-ts
# Queries: "what is inside the exocortex-verify image"
# SH-0 TypeScript verify image (owner decision D12).
# Built on the host with network at build time only; run with --network none.
# The build context is staged by triad.ts_verify.build_ts_verify_image and holds ONLY:
#   package.json, pnpm-workspace.yaml, pnpm-lock.yaml,
#   apps/<ws>/package.json and packages/<ws>/package.json (relative paths preserved),
#   and verify-ts (this directory's script).
# /deps is the installed dependency store. The worktree is bind-mounted at /work
# at run time and copied to a 2g tmpfs by verify-ts; /work itself is never written.
FROM node:24-slim
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
RUN corepack enable && corepack prepare pnpm@11.7.0 --activate
WORKDIR /deps
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY apps ./apps
COPY packages ./packages
RUN pnpm install --frozen-lockfile
COPY verify-ts /usr/local/bin/verify-ts
RUN sed -i 's/\r$//' /usr/local/bin/verify-ts && chmod +x /usr/local/bin/verify-ts
