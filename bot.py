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
        await interaction.response.edit_message(content=None, embed=None, embeds=None, attachments=None, view=CharacterDashboard(self.user_id))

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

class CharacterDashboard(discord.ui.LayoutView):
    def __init__(self, user_id: int, owner=None):
        super().__init__(timeout=1200)
        self.user_id = user_id

        character = get_character(user_id)
        avatar = (character.get("avatar_url") if character else None) or (
            owner.display_avatar.url if owner else None
        )

        if character:
            identity = (
                f"## ⟐ {character['name']}\\n"
                f"*Original Character*\\n"
                f"**Age:** {display(character['age'])}  •  "
                f"**Pronouns:** {display(character['pronouns'])}\\n"
                f"**Occupation:** {display(character['occupation'])}  •  "
                f"**Faction:** {display(character['faction'])}"
            )
            profile = (
                f"### Character Profile\\n"
                f"**Appearance**\\n{trim(character['appearance'])}\\n\\n"
                f"**Personality**\\n{trim(character['personality'])}\\n\\n"
                f"**Backstory**\\n{trim(character['backstory'], 1800)}"
            )
        else:
            identity = (
                "## ⟐ OC Dashboard\\n"
                "*Roleplay Character Management*\\n\\n"
                "You don't have an OC yet."
            )
            profile = (
                "**Get started**\\n"
                "Create your OC first, then add your appearance, personality, "
                "backstory, avatar, occupation and faction."
            )

        self.add_item(discord.ui.TextDisplay(identity))
        self.add_item(discord.ui.Separator())
        self.add_item(discord.ui.TextDisplay(profile))
        self.add_item(discord.ui.Separator())

        actions = discord.ui.ActionRow()
        self.edit_button = discord.ui.Button(
            label="Create / Edit", style=discord.ButtonStyle.primary
        )
        self.details_button = discord.ui.Button(
            label="Details", style=discord.ButtonStyle.secondary
        )
        self.avatar_button = discord.ui.Button(
            label="Avatar", style=discord.ButtonStyle.secondary
        )
        self.refresh_button = discord.ui.Button(
            label="Refresh", style=discord.ButtonStyle.secondary
        )
        self.delete_button = discord.ui.Button(
            label="Delete OC", style=discord.ButtonStyle.danger
        )

        self.edit_button.callback = self.edit_callback
        self.details_button.callback = self.details_callback
        self.avatar_button.callback = self.avatar_callback
        self.refresh_button.callback = self.refresh_callback
        self.delete_button.callback = self.delete_callback

        actions.add_item(self.edit_button)
        actions.add_item(self.details_button)
        actions.add_item(self.avatar_button)
        actions.add_item(self.refresh_button)
        actions.add_item(self.delete_button)
        self.add_item(actions)

    async def allowed(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This character panel belongs to someone else.", ephemeral=True
            )
            return False
        return True

    async def edit_callback(self, interaction: discord.Interaction):
        if await self.allowed(interaction):
            await interaction.response.send_modal(
                CoreModal(self.user_id, get_character(self.user_id))
            )

    async def details_callback(self, interaction: discord.Interaction):
        if not await self.allowed(interaction):
            return
        character = get_character(self.user_id)
        if not character:
            await interaction.response.send_message(
                "Create your OC first.", ephemeral=True
            )
            return
        await interaction.response.send_modal(
            DetailsModal(self.user_id, character)
        )

    async def avatar_callback(self, interaction: discord.Interaction):
        if not await self.allowed(interaction):
            return
        if not get_character(self.user_id):
            await interaction.response.send_message(
                "Create your OC first.", ephemeral=True
            )
            return
        await interaction.response.send_modal(AvatarModal(self.user_id))

    async def refresh_callback(self, interaction: discord.Interaction):
        if await self.allowed(interaction):
            await interaction.response.edit_message(
                content=None,
                embed=None,
                embeds=None,
                attachments=None,
                view=CharacterDashboard(self.user_id, interaction.user),
            )

    async def delete_callback(self, interaction: discord.Interaction):
        if not await self.allowed(interaction):
            return
        delete_character(self.user_id)
        await interaction.response.edit_message(
            content=None,
            embed=None,
            embeds=None,
            attachments=None,
            view=CharacterDashboard(self.user_id, interaction.user),
        )


def dashboard_view(user_id: int, owner=None) -> CharacterDashboard:
    return CharacterDashboard(user_id, owner)

