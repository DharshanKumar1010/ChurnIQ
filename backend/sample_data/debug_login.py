import asyncio
import httpx


async def main() -> None:
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=10) as c:
        r = await c.post(
            "/api/v1/auth/login",
            json={"email": "test@churniq.dev", "password": "password123"},
        )
        print(r.status_code)
        print(r.text)


asyncio.run(main())
