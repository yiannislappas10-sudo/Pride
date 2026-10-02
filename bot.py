import os
import re
import discord
from discord import app_commands
from discord.ext import commands

from database import init_db, get_character, save_character, update_character, delete_character

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing.")

DEV_GUILD_ID = 1529246492332920872
intents = discord.Intents.default()

def clean(value: str, limit: int) -> str:
    return (value or "").strip()[:limit]

def display(value: str) -> str:
    return value.strip() if value and value.strip() else "Not set"

def trim(value: str, limit: int = 1024) -> str:
    value = display(value)
    return value if len(value) <= limit else value[:limit - 1] + "…"

def character_embed(character: dict, owner=None) -> discord.Embed:
    embed = discord.Embed(title=f"⟐ {character['name']}", description="**Original Character**")
    avatar = character.get("avatar_url") or (owner.display_avatar.url if owner else None)
    if avatar:
        embed.set_thumbnail(url=avatar)
    embed.add_field(name="Age", value=display(character["age"]), inline=True)
    embed.add_field(name="Pronouns", value=display(character["pronouns"]), inline=True)
    embed.add_field(name="Occupation", value=display(character["occupation"]), inline=True)
    embed.add_field(name="Faction", value=display(character["faction"]), inline=True)
    embed.add_field(name="Appearance", value=trim(character["appearance"]), inline=False)
    embed.add_field(name="Personality", value=trim(character["personality"]), inline=False)
    embed.add_field(name="Backstory", value=trim(character["backstory"]), inline=False)
    embed.set_footer(text="RP Prototype • Persistent OC")
    return embed

class CoreModal(discord.ui.Modal):
    def __init__(self, user_id: int, existing=None):
        self.user_id = user_id
        self.existing = existing or {}
        super().__init__(title="Create Your OC" if not existing else "Edit OC")
        def val(key):
            return self.existing.get(key, "")
        self.name = discord.ui.TextInput(label="Character Name", placeholder="Name other players will see", default=val("name"), max_length=80, required=True)
        self.age = discord.ui.TextInput(label="Age", default=val("age"), max_length=20, required=False)
        self.pronouns = discord.ui.TextInput(label="Pronouns", default=val("pronouns"), max_length=40, required=False)
        self.occupation = discord.ui.TextInput(label="Occupation", default=val("occupation"), max_length=80, required=False)
        self.faction = discord.ui.TextInput(label="Faction", default=val("faction"), max_length=80, required=False)
        for item in (self.name, self.age, self.pronouns, self.occupation, self.faction):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        save_character(self.user_id, {**(self.existing or {}), "name": clean(self.name.value, 80), "age": clean(self.age.value, 20), "pronouns": clean(self.pronouns.value, 40), "occupation": clean(self.occupation.value, 80), "faction": clean(self.faction.value, 80)})
        character = get_character(self.user_id)
        await interaction.response.edit_message(embed=character_embed(character, interaction.user), view=CharacterDashboard(self.user_id))

class DetailsModal(discord.ui.Modal, title="OC Details"):
    def __init__(self, user_id: int, existing: dict):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.appearance = discord.ui.TextInput(label="Appearance", style=discord.TextStyle.paragraph, default=existing.get("appearance", ""), max_length=1000, required=False)
        self.personality = discord.ui.TextInput(label="Personality", style=discord.TextStyle.paragraph, default=existing.get("personality", ""), max_length=1000, required=False)
        self.backstory = discord.ui.TextInput(label="Backstory", style=discord.TextStyle.paragraph, default=existing.get("backstory", ""), max_length=2000, required=False)
        for item in (self.appearance, self.personality, self.backstory):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        update_character(self.user_id, appearance=clean(self.appearance.value, 1000), personality=clean(self.personality.value, 1000), backstory=clean(self.backstory.value, 2000))
        character = get_character(self.user_id)
        await interaction.response.edit_message(embed=character_embed(character, interaction.user), view=CharacterDashboard(self.user_id))

class AvatarModal(discord.ui.Modal, title="Set OC Avatar"):
    avatar = discord.ui.TextInput(label="Image URL", placeholder="https://...", max_length=500, required=True)

    def __init__(self, user_id: int):
        super().__init__(timeout=300)
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):
        url = self.avatar.value.strip()
        if not re.match(r"^https?://\S+$", url):
            await interaction.response.send_message("That doesn't look like a valid image URL.", ephemeral=True)
            return
        character = update_character(self.user_id, avatar_url=url)
        await interaction.response.edit_message(embed=character_embed(character, interaction.user), view=CharacterDashboard(self.user_id))

class CharacterDashboard(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=1200)
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This character panel belongs to someone else.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Create / Edit", style=discord.ButtonStyle.primary, row=0)
    async def edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CoreModal(self.user_id, get_character(self.user_id)))

    @discord.ui.button(label="Details", style=discord.ButtonStyle.secondary, row=0)
    async def details(self, interaction: discord.Interaction, button: discord.ui.Button):
        character = get_character(self.user_id)
        if not character:
            await interaction.response.send_message("Create your OC first.", ephemeral=True)
            return
        await interaction.response.send_modal(DetailsModal(self.user_id, character))

    @discord.ui.button(label="Avatar", style=discord.ButtonStyle.secondary, row=0)
    async def avatar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not get_character(self.user_id):
            await interaction.response.send_message("Create your OC first.", ephemeral=True)
            return
        await interaction.response.send_modal(AvatarModal(self.user_id))

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary, row=1)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        character = get_character(self.user_id)
        if character:
            await interaction.response.edit_message(embed=character_embed(character, interaction.user), view=self)
        else:
            await interaction.response.edit_message(embed=discord.Embed(title="⟐ OC Dashboard", description="You don't have an OC yet. Press **Create / Edit** to begin."), view=self)

    @discord.ui.button(label="Delete OC", style=discord.ButtonStyle.danger, row=1)
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        delete_character(self.user_id)
        await interaction.response.edit_message(embed=discord.Embed(title="⟐ OC Dashboard", description="Your OC has been deleted."), view=self)

class RPBot(commands.Bot):
    async def setup_hook(self):
        init_db()
        guild = discord.Object(id=DEV_GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        synced = await self.tree.sync(guild=guild)
        print(f"Synced {len(synced)} commands to guild {DEV_GUILD_ID}")

bot = RPBot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"RP Bot online as {bot.user} ({bot.user.id})")

oc_group = app_commands.Group(name="oc", description="Create and manage your roleplay character.")

@oc_group.command(name="dashboard", description="Open your OC dashboard.")
async def oc_dashboard(interaction: discord.Interaction):
    character = get_character(interaction.user.id)
    if character:
        embed = character_embed(character, interaction.user)
    else:
        embed = discord.Embed(title="⟐ OC Dashboard", description="You don't have an OC yet.\n\nCreate your character to begin building your roleplay identity.")
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
    await interaction.response.send_message(embed=embed, view=CharacterDashboard(interaction.user.id), ephemeral=True)

@oc_group.command(name="view", description="View an OC.")
@app_commands.describe(member="The member whose OC you want to view.")
async def oc_view(interaction: discord.Interaction, member: discord.Member | None = None):
    target = member or interaction.user
    character = get_character(target.id)
    if not character:
        await interaction.response.send_message(f"{target.display_name} hasn't created an OC yet.", ephemeral=True)
        return
    await interaction.response.send_message(embed=character_embed(character, target))

bot.tree.add_command(oc_group)

if __name__ == "__main__":
    bot.run(TOKEN)
