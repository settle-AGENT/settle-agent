# syntax=docker/dockerfile:1

FROM node:22-alpine AS build

WORKDIR /app

COPY frontend-react/package.json frontend-react/package-lock.json ./

RUN npm ci

COPY frontend-react/ ./

ARG VITE_API_BASE_URL=/api
ARG VITE_USE_MOCK=false
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_USE_MOCK=${VITE_USE_MOCK}

RUN npm run build


FROM nginx:stable-alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 3000

CMD ["nginx", "-g", "daemon off;"]
