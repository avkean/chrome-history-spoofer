---
created: 2025-12-03
tags:
  - vps
  - tech
---
# VPS Usage Guide

## 1. Overview
* How to create webapp with docker compose & git
* Using caddy for reverse proxy
* Decommissioning an app

### 1.1 SSH Command
```bash
ssh -p 22 avner@96.9.231.27
```

## 2. Adding a new app

This is the most important section: **how to add a new app correctly**.

### 2.1 Decide the basics

For each new app, decide:

- App folder name (e.g. `/srv/apps/blog`).
- Domain/subdomain (e.g. `+[6]+).
- Internal port the app will listen on (e.g. `3000`).
- Service name in Compose (e.g. `web`).

### 2.2 Create app folder in /srv/apps

```bash
cd /srv/apps
mkdir blog
cd blog
```

If code lives in Git, git clone it into its directory in /srv/apps:

```bash
git clone git@github.com:<user>/<blog-repo>.git .
```


### 5.3 Add `Dockerfile`

Example Node/Next.js style `Dockerfile`:

```dockerfile
FROM node:24-alpine AS build
WORKDIR /app

COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:24-alpine AS runtime
WORKDIR /app

ENV NODE_ENV=production
COPY --from=build /app/package*.json ./
RUN npm ci --omit=dev
COPY --from=build /app/.next ./.next
COPY --from=build /app/public ./public
COPY --from=build /app/next.config.mjs ./next.config.mjs

EXPOSE 3000
CMD ["npm", "start"]
```

Adapt commands and paths for your stack (Express, Laravel, etc.).

### 5.4 Add `.env`

Create `/srv/apps/blog/.env`:

```env
NODE_ENV=production
PORT=3000
DATABASE_URL=...
SOME_SECRET=...
```

### 5.5 Create docker-compose.yml for the app

Example:

```yaml
services:
  web:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: your_container_name
    restart: unless-stopped
    env_file:
      - .env
    networks:
      - proxy_net

networks:
  proxy_net:
    external: true
```

Notes:
- Service name is `web`.
- Container name is your_container_name (will be referenced in Caddyfile)
- Joined to external `proxy_net`, same network as Caddy.

### 5.6 Bring the app up

```bash
cd /srv/apps/blog
docker compose build
docker compose up -d
```

Check:

```bash
docker ps                 # web container should be Up
docker logs web           # app logs
```

The app should now be reachable inside Docker at `web:3000`.

---

## 6. Expose the new app via Caddy

### 6.1 DNS

Add A record:

```text
Type: A
Name: blog
Value: <VPS IPv4>
```

### 6.2 Update Caddyfile

Edit `/srv/infra/Caddyfile` and add:

```text
blog.akean.dev {
    reverse_proxy your_container_name:3000
}
```

### 6.3 Reload Caddy

```bash
cd /srv/infra
docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile
```

Then you're set to go, test your website on that URL.

---

## 7. Managing Portainer via subdomain

Portainer is also exposed via Caddy.

### 7.1 Accessing Portainer

Portainer is running on port 9000 (publicaly exposed), and can be accessed at:
https://portainer.avkean.com

---

## 8. Decommissioning an app

To remove an app properly:

1. Stop and remove containers:
    
    ```bash
    cd /srv/apps/<app>
    docker compose down
    ```
    
2. Remove its Caddy entry (Caddyfile) and reload:
    
    ```bash
    cd /srv/infra
    docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile
    ```
    
3. Optionally remove DNS records (A record for that subdomain).
    
4. Optionally archive the folder:
    
    ```bash
    cd /srv/apps
    tar czf <app>-archive-YYYYMMDD.tar.gz <app>
    rm -rf <app>        # only if sure
    ```
5. Commit changes (if app config is in Git) so the repo reflects the fact it is gone.

## 9. Connections
* Related to: [[VPS Info]], [[VPS Setup]], [[VPS Maintenance]], [[VPS Backup]]
