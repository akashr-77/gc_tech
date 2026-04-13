# ─── Stage 1: Build ───────────────────────────────────────────────────────────
FROM node:20-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .
RUN npm run build

# ─── Stage 2: Serve with Nginx ────────────────────────────────────────────────
FROM nginx:1.27-alpine

# Remove default nginx config
RUN rm /etc/nginx/conf.d/default.conf

# Copy our config template (supports EVENTOPS_API_URL env var)
COPY nginx.conf /etc/nginx/templates/default.conf.template

# Copy the built app
COPY --from=build /app/dist /usr/share/nginx/html

# Nginx templates directory is processed automatically on container start:
# every *.template file is run through envsubst and placed in /etc/nginx/conf.d/
# Environment variable used: EVENTOPS_API_URL (default: http://eventops-agent:8000)
ENV EVENTOPS_API_URL=http://eventops-agent:8000

EXPOSE 80

CMD ["/bin/sh", "-c", \
  "envsubst '${EVENTOPS_API_URL}' < /etc/nginx/templates/default.conf.template > /etc/nginx/conf.d/default.conf && nginx -g 'daemon off;'"]
