FROM node:26-alpine3.23

WORKDIR /app

COPY package*.json ./
RUN npm ci --omit-dev

COPY src ./src

ENV NODE_ENV=production
ENV HOST=0.0.0.0
ENV PORT=3000

EXPOSE 3000

CMD ["npm", "start"]