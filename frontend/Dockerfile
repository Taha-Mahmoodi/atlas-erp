FROM node:22-alpine AS build

WORKDIR /app

# Dependency layer first so source edits do not invalidate the npm cache.
COPY package.json package-lock.json ./
RUN npm ci

# BOTH entries: index.html is the Atlas console, website.html the property's guest-facing site.
# One build produces both (vite.config.ts), and the two final stages below serve one each.
COPY index.html website.html vite.config.ts tsconfig.json vitest.setup.ts ./
COPY src ./src
RUN npm run build

# The guest website, on its own origin because its nginx holds the machine API key the site
# authenticates to Atlas with (website-nginx.conf.template). Built with --target website.
FROM nginx:alpine AS website

COPY website-nginx.conf.template /etc/nginx/templates/default.conf.template
# Read before the template is rendered: puts the two keys in the environment (see the file).
COPY website-keys.envsh /docker-entrypoint.d/05-website-keys.envsh
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

# The Atlas console. LAST on purpose: it is what a bare `docker build ./frontend` produces, which
# is what the compose file, the docs and every existing script already do.
FROM nginx:alpine AS console

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
