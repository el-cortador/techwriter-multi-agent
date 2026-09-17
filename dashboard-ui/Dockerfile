FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json tsconfig.json vite.config.ts index.html ./
COPY src ./src
RUN npm ci && npm run build

FROM nginx:1.27-alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
