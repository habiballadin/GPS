FROM node:20-alpine AS deps
WORKDIR /workspace
COPY apps/web-console/package.json ./package.json
RUN npm install --no-audit --no-fund

FROM node:20-alpine AS builder
WORKDIR /workspace
COPY --from=deps /workspace/node_modules ./node_modules
COPY apps/web-console ./
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /workspace ./
EXPOSE 3000
CMD ["npm", "run", "start"]
