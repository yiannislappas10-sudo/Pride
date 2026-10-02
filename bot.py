import os
import re

import discord
from discord import app_commands
from discord.ext import commands

from database import (
    init_db,
    get_character,
    save_character,
    update_character,
    delete_character,
)

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
    return value if len(value) <= limit else value[: limit - 1] + "…"


class CoreModal(discord.ui.Modal):
    def __init__(self, user_id: int, existing=None):
        self.user_id = user_id
        self.existing = existing or {}
        super().__init__(title="Create Your OC" if not existing else "Edit OC")

        def val(key: str) -> str:
            return self.existing.get(key, "")

        self.name = discord.ui.TextInput(
            label="Character Name",
            placeholder="Name other players will see",
            default=val("name"),
            max_length=80,
            required=True,
        )
        self.age = discord.ui.TextInput(
            label="Age",
            default=val("age"),
            max_length=20,
            required=False,
        )
        self.pronouns = discord.ui.TextInput(
            label="Pronouns",
            default=val("pronouns"),
            max_length=40,
            required=False,
        )
        self.occupation = discord.ui.TextInput(
            label="Occupation",
            default=val("occupation"),
            max_length=80,
            required=False,
        )
        self.faction = discord.ui.TextInput(
            label="Faction",
            default=val("faction"),
            max_length=80,
            required=False,
        )

        for item in (
            self.name,
            self.age,
            self.pronouns,
            self.occupation,
            self.faction,
        ):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        save_character(
            self.user_id,
            {
                **self.existing,
                "name": clean(self.name.value, 80),
                "age": clean(self.age.value, 20),
                "pronouns": clean(self.pronouns.value, 40),
                "occupation": clean(self.occupation.value, 80),
                "faction": clean(self.faction.value, 80),
            },
        )
        await interaction.response.edit_message(
            view=CharacterDashboard(self.user_id)
        )


class DetailsModal(discord.ui.Modal, title="OC Details"):
    def __init__(self, user_id: int, existing: dict):
        super().__init__(timeout=600)
        self.user_id = user_id

        self.appearance = discord.ui.TextInput(
            label="Appearance",
            style=discord.TextStyle.paragraph,
            default=existing.get("appearance", ""),
            max_length=1000,
            required=False,
        )
        self.personality = discord.ui.TextInput(
            label="Personality",
            style=discord.TextStyle.paragraph,
            default=existing.get("personality", ""),
            max_length=1000,
            required=False,
        )
        self.backstory = discord.ui.TextInput(
            label="Backstory",
            style=discord.TextStyle.paragraph,
            default=existing.get("backstory", ""),
            max_length=2000,
            required=False,
        )

        for item in (self.appearance, self.personality, self.backstory):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        update_character(
            self.user_id,
            appearance=clean(self.appearance.value, 1000),
            personality=clean(self.personality.value, 1000),
            backstory=clean(self.backstory.value, 2000),
        )
        await interaction.response.edit_message(
            view=CharacterDashboard(self.user_id)
        )


class AvatarModal(discord.ui.Modal, title="Set OC Avatar"):
    avatar = discord.ui.TextInput(
        label="Image URL",
        placeholder="https://...",
        max_length=500,
        required=True,
    )

    def __init__(self, user_id: int):
        super().__init__(timeout=300)
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):
        url = self.avatar.value.strip()

        if not re.match(r"^https?://\S+$", url):
            await interaction.response.send_message(
                "That doesn't look like a valid image URL.",
                ephemeral=True,
            )
            return

        update_character(self.user_id, avatar_url=url)
        await interaction.response.edit_message(
            view=CharacterDashboard(self.user_id)
        )


class CharacterDashboard(discord.ui.LayoutView):
    def __init__(self, user_id: int):
        super().__init__(timeout=1200)
        self.user_id = user_id

        character = get_character(user_id)

        if character:
            identity = (
                f"## ⟐ {character['name']}\n"
                "*Original Character*\n"
                f"**Age:** {display(character['age'])}  •  "
                f"**Pronouns:** {display(character['pronouns'])}\n"
                f"**Occupation:** {display(character['occupation'])}  •  "
                f"**Faction:** {display(character['faction'])}"
            )

            profile = (
                "### Character Profile\n"
                f"**Appearance**\n{trim(character['appearance'])}\n\n"
                f"**Personality**\n{trim(character['personality'])}\n\n"
                f"**Backstory**\n{trim(character['backstory'], 1800)}"
            )

            avatar = character.get("avatar_url")
            if avatar:
                profile += f"\n\n[View character image]({avatar})"
        else:
            identity = (
                "## ⟐ OC Dashboard\n"
                "*Roleplay Character Management*\n\n"
                "You don't have an OC yet."
            )

            profile = (
                "### Get Started\n"
                "Create your OC first, then add your appearance, "
                "personality, backstory, avatar, occupation and faction."
            )

        self.add_item(discord.ui.TextDisplay(identity))
        self.add_item(discord.ui.Separator())
        self.add_item(discord.ui.TextDisplay(profile))
        self.add_item(discord.ui.Separator())

        actions = discord.ui.ActionRow()

        self.edit_button = discord.ui.Button(
            label="Create / Edit",
            style=discord.ButtonStyle.primary,
        )
        self.details_button = discord.ui.Button(
            label="Details",
            style=discord.ButtonStyle.secondary,
        )
        self.avatar_button = discord.ui.Button(
            label="Avatar",
            style=discord.ButtonStyle.secondary,
        )
        self.refresh_button = discord.ui.Button(
            label="Refresh",
            style=discord.ButtonStyle.secondary,
        )
        self.delete_button = discord.ui.Button(
            label="Delete OC",
            style=discord.ButtonStyle.danger,
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
                "This character panel belongs to someone else.",
                ephemeral=True,
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
                "Create your OC first.",
                ephemeral=True,
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
                "Create your OC first.",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(
            AvatarModal(self.user_id)
        )

    async def refresh_callback(self, interaction: discord.Interaction):
        if await self.allowed(interaction):
            await interaction.response.edit_message(
                view=CharacterDashboard(self.user_id)
            )

    async def delete_callback(self, interaction: discord.Interaction):
        if not await self.allowed(interaction):
            return

        delete_character(self.user_id)

        await interaction.response.edit_message(
            view=CharacterDashboard(self.user_id)
        )


class CharacterProfile(discord.ui.LayoutView):
    def __init__(self, character: dict, member: discord.Member):
        super().__init__(timeout=300)

        identity = (
            f"## ⟐ {character['name']}\n"
            f"*Played by {member.display_name}*\n"
            f"**Age:** {display(character['age'])}  •  "
            f"**Pronouns:** {display(character['pronouns'])}\n"
            f"**Occupation:** {display(character['occupation'])}  •  "
            f"**Faction:** {display(character['faction'])}"
        )

        profile = (
            "### Character Profile\n"
            f"**Appearance**\n{trim(character['appearance'])}\n\n"
            f"**Personality**\n{trim(character['personality'])}\n\n"
            f"**Backstory**\n{trim(character['backstory'], 1800)}"
        )

        avatar = character.get("avatar_url")
        if avatar:
            profile += f"\n\n[View character image]({avatar})"

        self.add_item(discord.ui.TextDisplay(identity))
        self.add_item(discord.ui.Separator())
        self.add_item(discord.ui.TextDisplay(profile))


class RPBot(commands.Bot):
    async def setup_hook(self):
        init_db()

        guild = discord.Object(id=DEV_GUILD_ID)

        # Remove old global commands such as the former /pride command.
        # Keep the current command tree clean, then register only /oc on the dev guild.
        self.tree.clear_commands(guild=None)
        await self.tree.sync()

        self.tree.clear_commands(guild=guild)
        self.tree.add_command(oc_group, guild=guild, override=True)
        synced = await self.tree.sync(guild=guild)

        print(
            f"Synced {len(synced)} commands to guild {DEV_GUILD_ID}; "
            "global command set cleared."
        )

    async def on_ready(self):
        print(
            f"RP Bot online as {self.user} "
            f"({self.user.id if self.user else 'unknown'})"
        )


bot = RPBot(
    command_prefix="!",
    intents=intents,
)

oc_group = app_commands.Group(
    name="oc",
    description="Create and manage your roleplay character.",
)


@oc_group.command(
    name="dashboard",
    description="Open your OC dashboard.",
)
async def oc_dashboard(interaction: discord.Interaction):
    await interaction.response.send_message(
        view=CharacterDashboard(interaction.user.id),
        ephemeral=True,
    )


@oc_group.command(
    name="view",
    description="View a member's OC.",
)
@app_commands.describe(member="The member whose OC you want to view.")
async def oc_view(
    interaction: discord.Interaction,
    member: discord.Member | None = None,
):
    target = member or interaction.user
    character = get_character(target.id)

    if not character:
        await interaction.response.send_message(
            f"{target.display_name} doesn't have an OC yet.",
            ephemeral=True,
        )
        return

    await interaction.response.send_message(
        view=CharacterProfile(character, target),
    )


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
):
    print(f"Application command error: {error!r}")

    if interaction.response.is_done():
        return

    await interaction.response.send_message(
        "Something went wrong while running that command. Check the bot logs.",
        ephemeral=True,
    )


bot.tree.add_command(oc_group)

if __name__ == "__main__":
    bot.run(TOKEN)
