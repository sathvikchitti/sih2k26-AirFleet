FROM node:22-alpine AS build

WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN VITE_API_BASE= npm run build

FROM nginx:1.27-alpine
ENV API_PROXY_TARGET=http://backend:8000 \
    NGINX_ENVSUBST_FILTER=^API_PROXY_TARGET$

COPY frontend/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
