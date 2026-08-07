"""Small HTTP load probe using runtime dependency httpx.

Example:
  python scripts/load_test.py https://localhost:8000/api/app1/v1/rpc/economy.balance/123 \
      --requests 10000 --concurrency 100 --api-key jf2_...

This is a diagnostic probe, not a replacement for distributed load testing tools.
"""
from __future__ import annotations

import argparse
import asyncio
import statistics
import time
from collections import Counter

import httpx


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    idx = min(int(round((len(values) - 1) * p)), len(values) - 1)
    return values[idx]


async def run(args) -> None:
    sem = asyncio.Semaphore(args.concurrency)
    latencies: list[float] = []
    statuses: Counter[int | str] = Counter()
    headers = {"X-API-Key": args.api_key} if args.api_key else {}
    timeout = httpx.Timeout(args.timeout)
    limits = httpx.Limits(max_connections=max(args.concurrency, 10), max_keepalive_connections=max(args.concurrency, 10))

    async with httpx.AsyncClient(timeout=timeout, limits=limits, verify=not args.insecure) as client:
        async def one(i: int):
            async with sem:
                start = time.perf_counter()
                try:
                    response = await client.request(args.method, args.url, headers=headers)
                    statuses[response.status_code] += 1
                except Exception as exc:
                    statuses[type(exc).__name__] += 1
                finally:
                    latencies.append((time.perf_counter() - start) * 1000)

        start_all = time.perf_counter()
        await asyncio.gather(*(one(i) for i in range(args.requests)))
        elapsed = time.perf_counter() - start_all

    print(f"requests={args.requests} concurrency={args.concurrency} elapsed={elapsed:.3f}s rps={args.requests/max(elapsed,1e-9):.2f}")
    print("statuses=", dict(statuses))
    if latencies:
        print(
            "latency_ms "
            f"mean={statistics.fmean(latencies):.2f} "
            f"p50={percentile(latencies,.50):.2f} "
            f"p95={percentile(latencies,.95):.2f} "
            f"p99={percentile(latencies,.99):.2f} "
            f"max={max(latencies):.2f}"
        )


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("url")
    p.add_argument("--requests", type=int, default=1000)
    p.add_argument("--concurrency", type=int, default=50)
    p.add_argument("--method", default="GET")
    p.add_argument("--api-key")
    p.add_argument("--timeout", type=float, default=10.0)
    p.add_argument("--insecure", action="store_true", help="Disable TLS certificate verification for local testing only")
    args = p.parse_args()
    if args.requests < 1 or args.concurrency < 1:
        p.error("requests and concurrency must be >= 1")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
