FROM node:26-bookworm-slim

WORKDIR /app
COPY --chown=node:node src ./src

USER node
EXPOSE 9109
CMD ["node", "src/server.js"]
