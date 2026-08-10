"""Framework-independent Discord economy service example.

Use this service from discord.py/py-cord/nextcord commands. The bot never receives database credentials
and never constructs SQL. It only holds a narrowly scoped API key.
"""
from __future__ import annotations
from clients.python.json_api_forge_client import ForgeClient
class EconomyService:
    def __init__(self, api_base: str, api_key: str): self.api = ForgeClient(api_base.rstrip("/") + "/api/app1/v1", api_key)
    async def balance(self, discord_user_id: str): return await self.api.request("GET", f"/rpc/economy.balance/{discord_user_id}")
    async def transfer(self, from_user: str, to_user: str, amount: int, *, interaction_id: str):
        return await self.api.rpc("economy.transfer", {"from_user": from_user, "to_user": to_user, "amount": amount}, idempotency_key=f"discord:{interaction_id}")
    async def grant(self, user_id: str, amount: int, reason: str): return await self.api.rpc("economy.grant", {"user_id": user_id, "amount": amount, "reason": reason})
    async def close(self): await self.api.close()
