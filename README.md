# GPS Fleet Backend

Custom GPS backend for Teltonika FMB920 and CONCOX V5/GT06 devices. Traccar is intentionally not used.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

HTTP API: `http://localhost:8000/docs`

Additional APIs include driver and trip registration, circular geofences, alert acknowledgement, and a tenant-scoped live WebSocket at `/api/v1/ws/live?token=<JWT>`.

TCP listeners:

- Teltonika Codec 8/8E: `0.0.0.0:5001`
- GT06 / CONCOX V5: `0.0.0.0:5002`

Set `DATABASE_URL` for PostgreSQL in production. The default SQLite database is only for local development.

## Device flow

1. Create an organization and admin through `POST /api/v1/auth/register`.
2. Create a vehicle and register its IMEI with `POST /api/v1/vehicles`.
3. Point the tracker at the appropriate TCP port.
4. The server authenticates the IMEI, decodes packets, deduplicates them, stores raw packets and normalized positions, and raises normalized alerts.

The TCP server is intentionally limited to GPS transport and decoding. Business APIs stay in FastAPI, which keeps protocol code isolated and testable.

## Production deployment

```bash
docker compose up --build
```

Expose TCP ports 5001 and 5002 directly to the internet or through a TCP load balancer. Put the HTTP API behind TLS and replace `JWT_SECRET` and the database password before deployment.

## Frontend

```bash
cd apps/web-console
npm install
npm run dev
```

Open `http://localhost:3000`. The Next.js console proxies `/api` to the FastAPI service when run through Docker Compose.

## AWS deployment

Use the Terraform stack in `infra/terraform` to provision an EC2 instance, Elastic IP, security group, and Docker bootstrap for the custom GPS gateway.
