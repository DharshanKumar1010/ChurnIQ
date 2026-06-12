"""Import customers_realistic.csv via the bulk-import endpoint."""
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))
import httpx

BASE = "http://localhost:8000"
CSV  = Path(__file__).parent / "customers_realistic.csv"


async def main() -> None:
    async with httpx.AsyncClient(base_url=BASE, timeout=60) as c:
        # Register (ignore 400 if exists)
        await c.post("/api/v1/auth/register",
                     json={"full_name":"Test User","email":"test@churniq.dev","password":"password123"})
        r = await c.post("/api/v1/auth/login",
                         json={"email":"test@churniq.dev","password":"password123"})
        if r.status_code != 200:
            sys.exit(f"Login failed: {r.text}")
        headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

        with CSV.open("rb") as f:
            resp = await c.post("/api/v1/customers/bulk-import", headers=headers,
                                files={"file": (CSV.name, f, "text/csv")})
        if resp.status_code != 200:
            sys.exit(f"Import failed {resp.status_code}: {resp.text}")

        d = resp.json()
        print(f"created={d['created']}  skipped={d['skipped']}")

        total = (await c.get("/api/v1/customers/", headers=headers,
                             params={"limit":1})).json()["total"]
        print(f"Total customers in DB: {total}")

asyncio.run(main())
