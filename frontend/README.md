# Frontend

Next.js (Pages Router) application for Finance Agent AWS SaaS: portfolio and account management, analysis jobs, and results (report, charts, retirement projection). Authentication is handled by Clerk; data comes from the FastAPI backend in `backend/api`.

## Structure

| Path | Contents |
|---|---|
| `pages/` | Routes: `index`, `dashboard`, `accounts`, `advisor-team`, `analysis`, error pages |
| `components/` | Shared UI components |
| `lib/` | API client and helpers |
| `styles/` | Global styles (Tailwind) |

## Configuration

Create `.env.local` in this directory:

```
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=<clerk publishable key>
CLERK_SECRET_KEY=<clerk secret key>
NEXT_PUBLIC_API_URL=http://localhost:8000
```

The backend needs `CLERK_JWKS_URL` (see the root `.env.example`).

## Development

```bash
npm install
npm run dev        # http://localhost:3000
npm run lint
npm run build      # static export for S3 + CloudFront
```

Run the API alongside it with `uv run run_local.py` from `scripts/`. Deployment is done by `scripts/deploy.py` and `terraform/7_frontend`.
