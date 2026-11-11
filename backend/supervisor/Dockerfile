FROM node:26-bookworm-slim

WORKDIR /app
COPY --chown=node:node package.json ./
# Dependency is prepared at image build time. Offline execution requires a
# pre-built image; the running container makes no external package requests.
RUN npm install --omit=dev --ignore-scripts --no-audit --no-fund \
    && npm cache clean --force
COPY --chown=node:node src ./src
# A named Docker volume inherits the directory ownership on first creation.
RUN mkdir -p /var/lib/devknowledge-supervisor && chown node:node /var/lib/devknowledge-supervisor

USER node
EXPOSE 9109
CMD ["node", "src/server.js"]
