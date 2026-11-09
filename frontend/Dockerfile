FROM node:22-alpine AS build
WORKDIR /app
COPY package.json ./
# Lockfile generation is pending the first verified dependency resolution.
RUN npm install --no-audit --no-fund
COPY angular.json tsconfig*.json ./
COPY src/ ./src/
RUN npm run build

FROM nginx:stable-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist/devknowledge-frontend/browser/ /usr/share/nginx/html/
EXPOSE 80
HEALTHCHECK --interval=15s --timeout=3s --retries=3 CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
