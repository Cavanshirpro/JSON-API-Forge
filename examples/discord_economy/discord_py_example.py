"""discord.py command example. Replace environment values and guild authorization rules for production."""
from __future__ import annotations
import os, discord
from discord import app_commands
from bot_service import EconomyService
intents=discord.Intents.default(); client=discord.Client(intents=intents); tree=app_commands.CommandTree(client)
economy=EconomyService(os.environ["FORGE_BASE_URL"], os.environ["FORGE_ECONOMY_API_KEY"])
@tree.command(name="balance", description="Show your balance")
async def balance(interaction: discord.Interaction):
    result=await economy.balance(str(interaction.user.id)); await interaction.response.send_message(f"Balance: {result}", ephemeral=True)
@tree.command(name="pay", description="Transfer coins to another member")
async def pay(interaction: discord.Interaction, member: discord.Member, amount: app_commands.Range[int,1,1_000_000]):
    result=await economy.transfer(str(interaction.user.id),str(member.id),amount,interaction_id=str(interaction.id)); await interaction.response.send_message(f"Transfer complete: {result}", ephemeral=True)
@client.event
async def on_ready(): await tree.sync(); print(f"Logged in as {client.user}")
client.run(os.environ["DISCORD_BOT_TOKEN"])
