FROM node:22-bookworm-slim
WORKDIR /runner
COPY package.json package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts && npm cache clean --force
COPY entrypoint.mjs worker.mjs ./
USER 65534:65534
ENTRYPOINT ["node", "/runner/entrypoint.mjs"]
