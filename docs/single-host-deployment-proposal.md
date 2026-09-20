# Proposal: preprod + prod on one host

## The problem

`deploy/deploy.sh` already separates the two environments well: distinct Compose
projects (`apartment103-preprod` / `apartment103-prod`), distinct remote paths
(`/opt/apartment103-<env>`), and therefore distinct networks, volumes and image
names. Two things stop them coexisting on one machine:

| Host resource | preprod.env | prod.env |
| --- | --- | --- |
| `HTTP_PORT` | 80 | 80 |
| `HTTPS_PORT` | 443 | 443 |
| `BACKEND_PORT` | 8000 | 8000 |
| `FRONTEND_PORT` | 3000 | 3000 |

Whichever stack comes up second fails with `address already in use`. Renumbering
the ports is not a fix on its own: only one process can own 443, and both
`bergseehome.ch` and `preprod.bergseehome.ch` resolve to the same IP, so
something has to terminate TLS for all four hostnames in one place and fan out
by `Host` / SNI.

## Proposed topology

Introduce a third Compose project — an **edge proxy** — that owns 80/443 and
knows only one thing: which environment a hostname belongs to. Each environment
keeps its own nginx, which keeps doing what it does today (frontend vs. API
split, serving `/images/` off its own volume), minus TLS.

```
                      host :80  :443
                            │
              ┌─────────────┴──────────────┐
              │  apartment103-edge          │   TLS termination for all 4 names
              │  nginx (edge)               │   default_server → 444
              └──────┬───────────────┬──────┘
   apartment103-      │               │      apartment103-
   preprod-edge net   │               │      prod-edge net
              ┌───────▼──────┐ ┌──────▼───────┐
              │ preprod-edge │ │  prod-edge   │  alias of each env's nginx
              │   (nginx)    │ │   (nginx)    │
              ├──────────────┤ ├──────────────┤
              │ frontend     │ │ frontend     │
              │ backend      │ │ backend      │
              │ mongo        │ │ mongo        │
              │ image_data   │ │ image_data   │
              └──────────────┘ └──────────────┘
    project: apartment103-preprod   project: apartment103-prod
```

Routing:

| Hostname | Edge sends to | Env nginx sends to |
| --- | --- | --- |
| `bergseehome.ch` | `prod-edge` | `frontend:3000` |
| `api.bergseehome.ch` | `prod-edge` | `backend:8000`, `/images/*` from volume |
| `preprod.bergseehome.ch` | `preprod-edge` | `frontend:3000` |
| `api-preprod.bergseehome.ch` | `preprod-edge` | `backend:8000`, `/images/*` from volume |
| anything else | — | `444` (connection closed, no response) |

### Why keep a per-environment nginx instead of one big nginx

A single nginx could route all four names directly to `frontend`/`backend`
containers, which is one less hop and two fewer containers. I'm not proposing it
because:

- It would have to mount both projects' `image_data` volumes as external
  volumes, so the edge would hard-code the internals of both stacks — volume
  names, service names, networks. Deploying preprod would mean touching a file
  that prod also serves from.
- The `location ~ ^/images/([^/.]+\.[^/.]+)$` block in
  [default.conf.template](deploy/nginx/templates/default.conf.template) is
  carefully anchored to avoid shadowing FastAPI's own `/images/*` routes. That
  logic belongs next to the backend it describes, versioned with it, not in a
  shared file where a preprod change can break prod.
- Each environment stays independently bootable and testable: `curl` the env
  nginx on its loopback debug port and you have exercised the whole stack
  without the edge existing at all.

The cost is one extra in-Docker hop per request, which is not measurable next to
the Next.js render.

## Two traps this design has to avoid

These are the parts that quietly produce a *wrong* result rather than an error,
so they drive most of the config below.

### 1. Service-name DNS collisions across projects

Both projects have services literally named `nginx`, `frontend`, `backend`.
Compose registers the service name as a network alias on **every** network a
service joins. A container attached to both env networks — the edge — that looks
up `nginx` gets an ambiguous answer and may be handed either project's address.
That is prod traffic landing on preprod, intermittently, with no error anywhere.

The fix is to never use a bare service name from the edge. Each env's nginx gets
a unique alias on the shared network (`preprod-edge`, `prod-edge`), and the edge
config refers only to those. The ambiguous `nginx` entry still exists; we simply
never ask for it.

### 2. nginx resolves `proxy_pass` targets once, at startup

With a literal name (`proxy_pass http://prod-edge;`) nginx resolves at config
load and caches the address for the life of the process. On a single host where
the two environments are deployed *independently*, that breaks twice over:

- Redeploying preprod gives its nginx a fresh container IP. The edge keeps
  proxying to the dead address until someone reloads it.
- If either environment is down when the edge starts, nginx refuses to start at
  all (`host not found in upstream`). A broken preprod would take prod offline.

So the edge uses Docker's embedded DNS explicitly and puts the target in a
variable, which forces per-request resolution:

```nginx
resolver 127.0.0.11 valid=10s ipv6=off;
set $upstream prod-edge;
proxy_pass http://$upstream$request_uri;
```

`$request_uri` is required: once `proxy_pass` contains a variable, nginx stops
passing the URI through implicitly. Using `$request_uri` (rather than `$uri`)
also passes the original, un-normalised path, which is what a pass-through edge
should do.

With this, a down environment is a 502 on its own hostnames only, and no reload
step is needed after an env deploy.

## Files

### New: `deploy/edge/docker-compose.yml`

```yaml
# The shared edge proxy: the only thing on this host that binds :80 and :443.
# It terminates TLS for all four hostnames and decides one thing — which
# ENVIRONMENT a request belongs to — then hands the request, Host header
# intact, to that environment's own nginx, which does the frontend/API split.
#
# Deployed as its own Compose project (apartment103-edge) so that either
# environment can be redeployed without restarting the other's ingress.
services:
  nginx:
    image: nginx:1.27-alpine
    restart: always
    environment:
      PROD_FRONTEND_DOMAIN: ${PROD_FRONTEND_DOMAIN:?must be set in env/edge.env}
      PROD_API_DOMAIN: ${PROD_API_DOMAIN:?must be set in env/edge.env}
      PREPROD_FRONTEND_DOMAIN: ${PREPROD_FRONTEND_DOMAIN:?must be set in env/edge.env}
      PREPROD_API_DOMAIN: ${PREPROD_API_DOMAIN:?must be set in env/edge.env}
      PROD_SSL_CERT_FILE: ${PROD_SSL_CERT_FILE:?must be set in env/edge.env}
      PROD_SSL_KEY_FILE: ${PROD_SSL_KEY_FILE:?must be set in env/edge.env}
      PREPROD_SSL_CERT_FILE: ${PREPROD_SSL_CERT_FILE:?must be set in env/edge.env}
      PREPROD_SSL_KEY_FILE: ${PREPROD_SSL_KEY_FILE:?must be set in env/edge.env}
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./templates:/etc/nginx/templates:ro
      - ./snippets:/etc/nginx/snippets:ro
      - ../../.secrets/certs:/etc/nginx/certs:ro
    networks:
      preprod: {}
      prod: {}
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

# Created out-of-band by deploy.sh (docker network create), NOT by either
# project, so the edge and the environments can be brought up in any order and
# `docker compose down` on one environment cannot delete a network the edge is
# still attached to.
networks:
  preprod:
    external: true
    name: apartment103-preprod-edge
  prod:
    external: true
    name: apartment103-prod-edge
```

### New: `deploy/edge/templates/default.conf.template`

```nginx
# Rendered by nginx's docker-entrypoint (envsubst) at container start from the
# environment set in deploy/edge/docker-compose.yml.
#
# This file knows about environments, not about the application. It never
# mentions frontend, backend or /images — the per-environment nginx owns all
# of that (deploy/nginx/templates/default.conf.template).

# Docker's embedded DNS. The proxy_pass targets below go through a variable on
# purpose so that names are re-resolved per request instead of being cached for
# the process lifetime — see "Two traps" in
# docs/single-host-deployment-proposal.md. Without it, redeploying one
# environment silently 502s until the edge is reloaded, and an environment that
# is down at edge-start time prevents nginx from starting at all, taking the
# other environment with it.
resolver 127.0.0.11 valid=10s ipv6=off;
resolver_timeout 5s;

map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

# Both hostnames share one IP, so anything that does not match a known
# server_name below — raw-IP port scans, stale DNS, Host-header probing —
# would otherwise fall through to whichever server block happens to be first
# and get served a real environment. Close the connection instead.
server {
    listen 80 default_server;
    server_name _;
    return 444;
}

server {
    listen 443 ssl default_server;
    server_name _;
    # Refuse the TLS handshake outright rather than presenting a certificate
    # for a name the client did not ask for (nginx >= 1.19.4).
    ssl_reject_handshake on;
}

server {
    listen 80;
    server_name ${PROD_FRONTEND_DOMAIN} ${PROD_API_DOMAIN}
                ${PREPROD_FRONTEND_DOMAIN} ${PREPROD_API_DOMAIN};
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    http2 on;
    server_name ${PROD_FRONTEND_DOMAIN} ${PROD_API_DOMAIN};

    ssl_certificate     /etc/nginx/certs/${PROD_SSL_CERT_FILE};
    ssl_certificate_key /etc/nginx/certs/${PROD_SSL_KEY_FILE};
    ssl_protocols TLSv1.2 TLSv1.3;

    # Matches _MAX_UPLOAD_BYTES in app/api/routes/images.py. Both this proxy
    # and the per-environment nginx buffer the body, so both need the cap
    # raised or the upload is rejected here with a 413 before it ever reaches
    # the environment.
    client_max_body_size 20m;

    location / {
        include /etc/nginx/snippets/proxy.conf;
        set $upstream prod-edge;
        proxy_pass http://$upstream$request_uri;
    }
}

server {
    listen 443 ssl;
    http2 on;
    server_name ${PREPROD_FRONTEND_DOMAIN} ${PREPROD_API_DOMAIN};

    ssl_certificate     /etc/nginx/certs/${PREPROD_SSL_CERT_FILE};
    ssl_certificate_key /etc/nginx/certs/${PREPROD_SSL_KEY_FILE};
    ssl_protocols TLSv1.2 TLSv1.3;

    client_max_body_size 20m;

    # preprod is a public hostname on the same IP as prod; keep it out of
    # search results so it cannot compete with or leak ahead of the real site.
    add_header X-Robots-Tag "noindex, nofollow, noarchive" always;

    location / {
        include /etc/nginx/snippets/proxy.conf;
        set $upstream preprod-edge;
        proxy_pass http://$upstream$request_uri;
    }
}
```

### New: `deploy/edge/snippets/proxy.conf`

```nginx
# Not a .template — no envsubst, mounted at /etc/nginx/snippets.
proxy_http_version 1.1;
proxy_set_header Host              $host;
proxy_set_header X-Real-IP         $remote_addr;
proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
# Hard-coded rather than $scheme: this snippet is only included from the 443
# blocks, and TLS ends here, so the hop inward is plain HTTP.
proxy_set_header X-Forwarded-Proto https;
proxy_set_header X-Forwarded-Host  $host;
proxy_set_header Upgrade           $http_upgrade;
proxy_set_header Connection        $connection_upgrade;
proxy_read_timeout 60s;
```

### New: `deploy/edge/env/edge.env` (+ `.example`)

```sh
PROD_FRONTEND_DOMAIN=bergseehome.ch
PROD_API_DOMAIN=api.bergseehome.ch
PREPROD_FRONTEND_DOMAIN=preprod.bergseehome.ch
PREPROD_API_DOMAIN=api-preprod.bergseehome.ch

# Both currently point at the same file. Split them if preprod ever gets its
# own certificate; the config already reads them independently.
PROD_SSL_CERT_FILE=bergseehome_ch_chain.crt
PROD_SSL_KEY_FILE=bergseehome_ch.key
PREPROD_SSL_CERT_FILE=bergseehome_ch_chain.crt
PREPROD_SSL_KEY_FILE=bergseehome_ch.key
```

Certificates move from `.secrets/certs/<env>/` to `.secrets/certs/edge/`, since
the environments no longer terminate TLS. The existing certificate needs all
four names as SANs; a `*.bergseehome.ch` + `bergseehome.ch` certificate covers
all of them (every name is single-level).

## Changes to existing files

### `deploy/docker-compose.yml`

**nginx** — stop binding 80/443, drop TLS, join the shared network under a
unique alias:

```yaml
  nginx:
    image: nginx:1.27-alpine
    depends_on:
      - frontend
      - backend
    environment:
      FRONTEND_DOMAIN: ${FRONTEND_DOMAIN:?FRONTEND_DOMAIN must be set in the deploy env file}
      API_DOMAIN: ${API_DOMAIN:?API_DOMAIN must be set in the deploy env file}
    # Loopback only, and a different port per environment. This is the
    # debugging handle: curl it and you have exercised the whole stack without
    # involving the edge proxy or DNS.
    ports:
      - "127.0.0.1:${DEBUG_PORT:?DEBUG_PORT must be set in the deploy env file}:80"
    volumes:
      - ./nginx/templates:/etc/nginx/templates:ro
      - image_data:/data/images:ro
    networks:
      default: {}
      edge:
        aliases:
          # Unique per environment: the edge proxy is attached to BOTH
          # environments' networks, so the bare service name "nginx" resolves
          # ambiguously from there.
          - ${ENV_SLUG:?ENV_SLUG must be set in the deploy env file}-edge

networks:
  default: {}
  edge:
    external: true
    name: apartment103-${ENV_SLUG}-edge
```

**backend / frontend** — delete their `ports:` blocks entirely. Nothing outside
the Compose network needs them: nginx reaches them over the project network, and
`DEBUG_PORT` above covers manual poking. This removes the 8000/3000 collision by
removing the bind rather than renumbering it, and shrinks the host's listening
surface.

**mongo** — cap the WiredTiger cache. This is the one that will bite otherwise:
mongod defaults to `max(0.5 × (RAM − 1GB), 256MB)` and has no idea another
mongod is doing the same. Two unbounded instances will try to claim the whole
machine.

```yaml
  mongo:
    image: mongo:7
    command: ["mongod", "--wiredTigerCacheSizeGB", "${MONGO_CACHE_GB:-0.5}"]
    mem_limit: ${MONGO_MEM_LIMIT:-1g}
```

### `deploy/nginx/templates/default.conf.template`

TLS moves to the edge, so: delete the port-80 redirect block, and in the two
remaining blocks change `listen 443 ssl; http2 on;` to `listen 80;` and drop the
three `ssl_*` lines. Everything else — the `server_name` split, the `/images/`
regex, `client_max_body_size 20m` — stays exactly as it is.

Add at the top so logs and rate-limiting see the real client rather than the
edge container:

```nginx
# The edge proxy is the only thing that talks to us, from the Docker bridge
# range; trust its X-Forwarded-For so $remote_addr is the real client.
set_real_ip_from 172.16.0.0/12;
real_ip_header X-Forwarded-For;
real_ip_recursive on;
```

### `deploy/env/preprod.env` / `prod.env`

Remove `HTTP_PORT`, `HTTPS_PORT`, `BACKEND_PORT`, `FRONTEND_PORT`,
`SSL_CERT_FILE`, `SSL_KEY_FILE`. Add:

```sh
# preprod.env
ENV_SLUG=preprod
DEBUG_PORT=8081
MONGO_CACHE_GB=0.25
MONGO_MEM_LIMIT=512m
```
```sh
# prod.env
ENV_SLUG=prod
DEBUG_PORT=8082
MONGO_CACHE_GB=1
MONGO_MEM_LIMIT=2g
```

`FRONTEND_DOMAIN` / `API_DOMAIN` stay — the per-env nginx still uses them to
split frontend from API.

### `deploy/docker-compose.preprod.yml`

Give preprod the same log caps as prod. Unbounded json-file logs were fine when
preprod had its own machine; on a shared host a chatty preprod can fill the disk
out from under prod.

### `deploy/deploy.sh`

1. Create the shared network idempotently before `up`, so ordering between the
   three projects never matters:
   ```sh
   docker network inspect "apartment103-$ENVIRONMENT-edge" >/dev/null 2>&1 \
     || docker network create "apartment103-$ENVIRONMENT-edge"
   ```
2. Drop the `SSL_CERT_FILE`/`SSL_KEY_FILE` lookup and the certificate scp
   (lines 118–129, 177–181) — those move to the edge deploy.
3. Keep the `stop nginx` / `rm -f nginx` / `up -d nginx` dance; it is still the
   only reliable way to re-render a bind-mounted template.
4. No edge reload needed after an env deploy — that is what the `resolver`
   change buys.

### New: `deploy/deploy-edge.sh`

Same shape as `deploy.sh` but much smaller: rsync `deploy/edge/`, scp the certs
from `.secrets/certs/edge/` to `/opt/apartment103-edge/.secrets/certs/` at mode
600, create both networks if absent, then
`docker compose -p apartment103-edge --env-file env/edge.env up -d` followed by
`stop`/`rm`/`up -d` for the template re-render. No secrets export loop and no
migrations, so most of the complexity in `deploy.sh` drops away.

Deploy order on a fresh machine: `deploy-edge.sh` creates the networks, so any
order works; the edge will 502 for an environment that is not up yet.

## Cutover

Doing this on the live host means prod ingress moves. Sequence that keeps the
window short:

1. Deploy preprod with the new layout first. It no longer binds 80/443, so it
   can run alongside the current prod stack untouched. Verify through the
   loopback debug port:
   `curl -H 'Host: preprod.bergseehome.ch' http://127.0.0.1:8081/`
2. Deploy prod with the new layout. Both stacks are now up and nothing owns
   80/443 — this is the outage window, and it is as long as a prod deploy.
3. Deploy the edge. It grabs 80/443 and both sites come back.
4. Verify all four names plus the negative case:
   ```sh
   for h in bergseehome.ch api.bergseehome.ch \
            preprod.bergseehome.ch api-preprod.bergseehome.ch; do
     curl -sS -o /dev/null -w "$h -> %{http_code}\n" "https://$h/"
   done
   curl -sS -o /dev/null -w "raw IP -> %{http_code}\n" https://<host-ip>/ ; # expect 000
   ```
5. Confirm the two environments are actually isolated. This is the check that
   catches the DNS-alias trap, and because that trap is *intermittent* it has
   to be a loop, not a single request. Run it after every deploy of either
   environment, not just at cutover.

   The frontend bakes `NEXT_PUBLIC_API_URL` into its bundle at build time
   (`frontend/Dockerfile`), so the served HTML already identifies which build
   answered — no code change needed:
   ```sh
   # each must print exactly one line, twenty times out of twenty
   for i in $(seq 20); do curl -s https://preprod.bergseehome.ch/ \
     | grep -o 'api-preprod\.bergseehome\.ch' | head -1; done | sort -u
   for i in $(seq 20); do curl -s https://bergseehome.ch/ \
     | grep -o 'api\.bergseehome\.ch' | head -1; done | sort -u
   ```

   The API side has no such discriminator: `/health` returns a constant
   `{"status": "ok"}` (`backend/app/api/routes/health.py`), which is identical
   in both environments and therefore cannot detect misrouting at all. Worth
   fixing as part of this work — `settings.environment` is already populated
   from the `ENVIRONMENT` var the compose file sets:
   ```python
   @router.get("/health")
   def health() -> dict[str, str]:
       return {"status": "ok", "environment": settings.environment}
   ```
   which makes the API check the same shape as the frontend one:
   ```sh
   for i in $(seq 20); do curl -s https://api-preprod.bergseehome.ch/health; done | sort -u
   ```

To roll back, stop the edge and revert one environment's compose + env file to
the current version; it will re-take 80/443 on its own.

## Loose ends worth deciding now

- **HSTS.** If `bergseehome.ch` ever sends `Strict-Transport-Security` with
  `includeSubDomains`, it pins `preprod.bergseehome.ch` too. That is fine while
  preprod has a valid certificate and actively harmful the day it does not.
  Either omit `includeSubDomains` or accept that preprod must always have valid
  TLS.
- **preprod access control.** preprod is a public hostname serving real-looking
  content. `X-Robots-Tag` above is the minimum; HTTP basic auth at the edge on
  the preprod block is a two-line addition and worth it unless someone needs
  anonymous access.
- **Stripe webhooks.** Both environments have a `STRIPE_WEBHOOK_SECRET`. Confirm
  the two Stripe endpoints point at `api.` and `api-preprod.` respectively —
  once they share an IP, a misconfigured endpoint silently delivers preprod
  events to prod.
- **Disk.** Two full Next.js builds plus two image histories on one box. Add
  `docker image prune -f` at the end of `deploy.sh`, and watch
  `/var/lib/docker`.
- **Backups.** Two `mongo_data` volumes now share one failure domain. Whatever
  backs up prod's volume should exclude preprod's, and restore procedures need
  to name the volume explicitly (`apartment103-prod_mongo_data`).

## Validation

Per `AGENTS.md`, implementing this requires an end-to-end pass with the
visual-eval skill against both hostnames — the routing change touches every
request path, and a misrouted environment renders as a perfectly healthy page,
so screenshots of prod and preprod side by side are the check that matters.
