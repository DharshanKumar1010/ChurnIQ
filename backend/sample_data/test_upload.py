"""Test script: login, upload CSV, print result."""

import asyncio
import sys
from pathlib import Path

import httpx

BASE_URL = "http://localhost:8000"
CSV_PATH = Path(__file__).parent / "customers_sample.csv"


async def main() -> None:
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        # Register (ignore 400 if already exists)
        await client.post(
            "/api/v1/auth/register",
            json={"full_name": "Test User", "email": "test@churniq.dev", "password": "password123"},
        )

        # Login
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "test@churniq.dev", "password": "password123"},
        )
        if resp.status_code != 200:
            print(f"Login failed {resp.status_code}: {resp.text}")
            sys.exit(1)
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print(f"Logged in OK, token: {token[:40]}...")

        # Upload CSV
        with CSV_PATH.open("rb") as f:
            upload_resp = await client.post(
                "/api/v1/customers/bulk-import",
                headers=headers,
                files={"file": ("customers_sample.csv", f, "text/csv")},
            )

        if upload_resp.status_code != 200:
            print(f"Upload failed {upload_resp.status_code}: {upload_resp.text}")
            sys.exit(1)

        data = upload_resp.json()
        print(f"\nBulk import result:")
        print(f"  created : {data['created']}")
        print(f"  skipped : {data['skipped']}")
        print(f"  errors  :")
        for e in data["errors"]:
            print(f"    row {e['row']:>3}: {e['error']}")

        # Verify via list endpoint
        list_resp = await client.get(
            "/api/v1/customers/",
            headers=headers,
            params={"limit": 5},
        )
        total = list_resp.json()["total"]
        print(f"\nCustomers now in DB for this user: {total}")


asyncio.run(main())
