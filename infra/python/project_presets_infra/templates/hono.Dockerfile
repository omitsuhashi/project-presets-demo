FROM node:24.21.0-bookworm-slim@sha256:0e0ff40c39bc087845bfb27465a0df4ea419520094bc35842ff83dd8cbe6f9b6
WORKDIR /app
COPY . .
RUN npm install --global --ignore-scripts "$(node -p "require('./package.json').packageManager")" \
    && pnpm install --frozen-lockfile --ignore-scripts
ENV NODE_ENV=production
EXPOSE 3000
USER node
CMD ["node", "server.ts"]
