FROM node:20-slim AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build


FROM node:20-slim

ENV NODE_ENV=production

WORKDIR /app
COPY --from=builder /app/package.json /app/package.json
COPY --from=builder /app/package-lock.json /app/package-lock.json
COPY --from=builder /app/.next /app/.next
COPY --from=builder /app/public /app/public

RUN npm ci --omit=dev

EXPOSE 3000

CMD ["sh", "-c", "npm run start -- --port ${PORT:-3000}"]
