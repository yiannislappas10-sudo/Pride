import os
import re

import discord
from discord import app_commands
from discord.ext import commands
from openai import AsyncOpenAI

from database import (
    init_db,
    get_characters,
    get_character,
    save_character,
    update_character,
    delete_character,
    get_roleplay_settings,
    save_roleplay_settings,
    get_active_character_id,
    save_active_character_id,
    get_player_roleplay_active,
    save_player_roleplay_active,
    get_player_auto_rp_format,
    save_player_auto_rp_format,
    get_rp_learning_examples,
    save_rp_learning_example,
)

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing.")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PRIDE_AI_MODEL = os.getenv("PRIDE_AI_MODEL", "gpt-6-astra")
ai_client = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

DEV_GUILD_ID = 1529246492332920872

intents = discord.Intents.default()
intents.message_content = True


def clean(value: str, limit: int) -> str:
    return (value or "").strip()[:limit]


def display(value: str) -> str:
    return value.strip() if value and value.strip() else "Not set"


def trim(value: str, limit: int = 1024) -> str:
    value = display(value)
    return value if len(value) <= limit else value[: limit - 1] + "…"


async def ai_format_rp_message(
    character: dict,
    content: str,
    examples: list[dict],
) -> str:
    text = (content or "").strip()
    if not text:
        return text

    character_name = character.get("name", "Character").strip() or "Character"
    if ai_client is None:
        return f"{character_name}: {text}"

    memory = "\n".join(
        f"- User: {item['input_text']}\n  RP: {item['output_text']}"
        for item in examples[:8]
    )

    profile = (
        f"Name: {character_name}\n"
        f"Personality: {trim(character.get('personality', ''), 700)}\n"
        f"Appearance: {trim(character.get('appearance', ''), 400)}\n"
        f"Backstory: {trim(character.get('backstory', ''), 500)}"
    )

    prompt = f"""You are Pride's RP message formatter.

Character profile:
{profile}

Previous style examples:
{memory if memory else "(none yet)"}

User's new message:
{text}

Return ONLY the finished Discord RP message.

Rules:
- Start with the exact character name.
- Decide whether plain dialogue, a delivery cue, or a small action fits.
- Natural examples include: Character Name: hello, Character Name (whispers): hello, Character Name *smiles*: hello, and Character Name: hello *smiles*
- Use cues like whispers, murmurs, shouts, laughs, sighs, gasps, and similar cues only when the message actually suggests them.
- Use actions like *looks around*, *smiles*, *steps closer*, *pauses*, etc. only when reasonably implied.
- Do not force an action or cue onto every message.
- Never invent facts, emotions, actions, lore, or extra dialogue.
- Preserve the user's meaning and wording as much as possible.
- Do not mention AI, formatting, instructions, or these examples.
- Do not use code fences."""

    try:
        response = await ai_client.responses.create(
            model=PRIDE_AI_MODEL,
            instructions=(
                "Only format the user's message as roleplay dialogue. "
                "Do not become the character or continue the conversation."
            ),
            input=prompt,
            max_output_tokens=120,
        )
        result = (response.output_text or "").strip()
        if not result:
            return f"{character_name}: {text}"

        if not result.lower().startswith(character_name.lower()):
            result = f"{character_name}: {result}"

        return result[:2000]
    except Exception as exc:
        print(f"AI RP formatting failed: {exc}")
        return f"{character_name}: {text}"


class CoreModal(discord.ui.Modal):
    def __init__(
        self,
        user_id: int,
        character_id: int | None = None,
        existing: dict | None = None,
    ):
        self.user_id = user_id
        self.character_id = character_id
        self.existing = existing or {}

        title = "Create Your OC" if character_id is None else "Edit OC"
        super().__init__(title=title)

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
        data = {
            **self.existing,
            "name": clean(self.name.value, 80),
            "age": clean(self.age.value, 20),
            "pronouns": clean(self.pronouns.value, 40),
            "occupation": clean(self.occupation.value, 80),
            "faction": clean(self.faction.value, 80),
        }

        new_id = save_character(
            self.user_id,
            data,
            character_id=self.character_id,
        )

        if interaction.guild is not None:
            save_active_character_id(
                interaction.guild.id,
                self.user_id,
                new_id,
            )

        await interaction.response.edit_message(
            view=CharacterDashboard(self.user_id, new_id)
        )


class DetailsModal(discord.ui.Modal, title="OC Details"):
    def __init__(self, user_id: int, character_id: int, existing: dict):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.character_id = character_id

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

        for item in (
            self.appearance,
            self.personality,
            self.backstory,
        ):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        update_character(
            self.character_id,
            appearance=clean(self.appearance.value, 1000),
            personality=clean(self.personality.value, 1000),
            backstory=clean(self.backstory.value, 2000),
        )

        await interaction.response.edit_message(
            view=CharacterDashboard(self.user_id, self.character_id)
        )


class AvatarModal(discord.ui.Modal, title="Set OC Avatar"):
    avatar = discord.ui.TextInput(
        label="Image URL",
        placeholder="https://...",
        max_length=500,
        required=True,
    )

    def __init__(self, user_id: int, character_id: int):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.character_id = character_id

    async def on_submit(self, interaction: discord.Interaction):
        url = self.avatar.value.strip()

        if not re.match(r"^https?://\S+$", url):
            await interaction.response.send_message(
                "That doesn't look like a valid image URL.",
                ephemeral=True,
            )
            return

        update_character(self.character_id, avatar_url=url)

        await interaction.response.edit_message(
            view=CharacterDashboard(self.user_id, self.character_id)
        )


class DeleteConfirmView(discord.ui.LayoutView):
    def __init__(self, user_id: int, character_id: int, stage: int = 1):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.character_id = character_id
        self.stage = stage

        character = get_character(character_id)
        name = character["name"] if character else "this OC"

        if stage == 1:
            text = (
                "## Delete OC?\n"
                f'You are about to delete **"{name}"**.\n\n'
                "This is confirmation **1 of 2**. "
                "Nothing has been deleted yet."
            )
        else:
            text = (
                "## Final Confirmation\n"
                f'Are you absolutely sure you want to delete **"{name}"**?\n\n'
                "This is confirmation **2 of 2**. "
                "The next confirmation permanently removes this OC."
            )

        self.add_item(discord.ui.TextDisplay(text))
        self.add_item(discord.ui.Separator())

        actions = discord.ui.ActionRow()

        cancel = discord.ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.secondary,
        )
        confirm = discord.ui.Button(
            label=(
                "Confirm Delete"
                if stage == 1
                else "Permanently Delete"
            ),
            style=discord.ButtonStyle.danger,
        )

        cancel.callback = self.cancel_callback
        confirm.callback = self.confirm_callback

        actions.add_item(cancel)
        actions.add_item(confirm)
        self.add_item(actions)

    async def allowed(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This confirmation panel belongs to someone else.",
                ephemeral=True,
            )
            return False
        return True

    async def cancel_callback(self, interaction: discord.Interaction):
        if not await self.allowed(interaction):
            return

        await interaction.response.edit_message(
            view=CharacterDashboard(self.user_id, self.character_id)
        )

    async def confirm_callback(self, interaction: discord.Interaction):
        if not await self.allowed(interaction):
            return

        character = get_character(self.character_id)
        if not character:
            await interaction.response.edit_message(
                view=CharacterDashboard(self.user_id)
            )
            return

        if self.stage == 1:
            await interaction.response.edit_message(
                view=DeleteConfirmView(
                    self.user_id,
                    self.character_id,
                    stage=2,
                )
            )
            return

        delete_character(self.character_id)

        await interaction.response.edit_message(
            view=CharacterDashboard(self.user_id)
        )


class CharacterDashboard(discord.ui.LayoutView):
    def __init__(
        self,
        user_id: int,
        selected_character_id: int | None = None,
    ):
        super().__init__(timeout=1200)
        self.user_id = user_id

        characters = get_characters(user_id)

        character = None
        if selected_character_id is not None:
            candidate = get_character(selected_character_id)
            if candidate and candidate["user_id"] == user_id:
                character = candidate

        if character is None and characters:
            character = characters[0]

        selected_id = character["character_id"] if character else None

        if character:
            position = next(
                (
                    index + 1
                    for index, item in enumerate(characters)
                    if item["character_id"] == selected_id
                ),
                1,
            )

            identity = (
                f"## ⟐ {character['name']}\n"
                f"*Original Character • OC {position} of {len(characters)}*\n"
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
                "Create your first OC. You can make multiple characters "
                "and switch between them here."
            )

        self.add_item(discord.ui.TextDisplay(identity))
        self.add_item(discord.ui.Separator())
        self.add_item(discord.ui.TextDisplay(profile))
        self.add_item(discord.ui.Separator())

        actions = discord.ui.ActionRow()

        self.create_button = discord.ui.Button(
            label="Create OC",
            style=discord.ButtonStyle.primary,
        )
        self.edit_button = discord.ui.Button(
            label="Edit Current",
            style=discord.ButtonStyle.secondary,
            disabled=character is None,
        )
        self.details_button = discord.ui.Button(
            label="Details",
            style=discord.ButtonStyle.secondary,
            disabled=character is None,
        )
        self.avatar_button = discord.ui.Button(
            label="Avatar",
            style=discord.ButtonStyle.secondary,
            disabled=character is None,
        )
        self.delete_button = discord.ui.Button(
            label="Delete OC",
            style=discord.ButtonStyle.danger,
            disabled=character is None,
        )

        self.create_button.callback = self.create_callback
        self.edit_button.callback = self.edit_callback
        self.details_button.callback = self.details_callback
        self.avatar_button.callback = self.avatar_callback
        self.delete_button.callback = self.delete_callback

        actions.add_item(self.create_button)
        actions.add_item(self.edit_button)
        actions.add_item(self.details_button)
        actions.add_item(self.avatar_button)
        actions.add_item(self.delete_button)
        self.add_item(actions)

        if characters:
            switch_row = discord.ui.ActionRow()

            options = [
                discord.SelectOption(
                    label=trim(item["name"], 100),
                    description=(
                        f"OC #{index + 1}"
                        if len(characters) <= 25
                        else "Character"
                    ),
                    value=str(item["character_id"]),
                    default=item["character_id"] == selected_id,
                )
                for index, item in enumerate(characters[:25])
            ]

            self.switch_select = discord.ui.Select(
                placeholder="Switch character",
                options=options,
                min_values=1,
                max_values=1,
            )
            self.switch_select.callback = self.switch_callback
            switch_row.add_item(self.switch_select)
            self.add_item(switch_row)

            if len(characters) > 25:
                self.add_item(
                    discord.ui.TextDisplay(
                        "*Only the first 25 OCs are shown in the switcher.*"
                    )
                )

    async def allowed(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This character panel belongs to someone else.",
                ephemeral=True,
            )
            return False
        return True

    async def create_callback(self, interaction: discord.Interaction):
        if await self.allowed(interaction):
            await interaction.response.send_modal(
                CoreModal(self.user_id)
            )

    async def edit_callback(self, interaction: discord.Interaction):
        if not await self.allowed(interaction):
            return

        character = self.current_character()

        if not character:
            await interaction.response.send_message(
                "Create an OC first.",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(
            CoreModal(
                self.user_id,
                character["character_id"],
                character,
            )
        )

    async def details_callback(self, interaction: discord.Interaction):
        if not await self.allowed(interaction):
            return

        character = self.current_character()
        if not character:
            await interaction.response.send_message(
                "Create an OC first.",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(
            DetailsModal(
                self.user_id,
                character["character_id"],
                character,
            )
        )

    async def avatar_callback(self, interaction: discord.Interaction):
        if not await self.allowed(interaction):
            return

        character = self.current_character()
        if not character:
            await interaction.response.send_message(
                "Create an OC first.",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(
            AvatarModal(
                self.user_id,
                character["character_id"],
            )
        )

    async def refresh_callback(self, interaction: discord.Interaction):
        if not await self.allowed(interaction):
            return

        current = self.current_character()
        current_id = current["character_id"] if current else None

        await interaction.response.edit_message(
            view=CharacterDashboard(self.user_id, current_id)
        )

    async def delete_callback(self, interaction: discord.Interaction):
        if not await self.allowed(interaction):
            return

        character = self.current_character()
        if not character:
            await interaction.response.send_message(
                "Create an OC first.",
                ephemeral=True,
            )
            return

        await interaction.response.edit_message(
            view=DeleteConfirmView(
                self.user_id,
                character["character_id"],
                stage=1,
            )
        )

    async def switch_callback(self, interaction: discord.Interaction):
        if not await self.allowed(interaction):
            return

        character_id = int(self.switch_select.values[0])
        character = get_character(character_id)

        if not character or character["user_id"] != self.user_id:
            await interaction.response.send_message(
                "That character no longer exists.",
                ephemeral=True,
            )
            return

        if interaction.guild is not None:
            save_active_character_id(
                interaction.guild.id,
                self.user_id,
                character_id,
            )

        await interaction.response.edit_message(
            view=CharacterDashboard(self.user_id, character_id)
        )

    def current_character(self) -> dict | None:
        characters = get_characters(self.user_id)
        if not characters:
            return None

        # The dashboard's switcher stores the selected item in its select default.
        if hasattr(self, "switch_select"):
            selected = next(
                (
                    option.value
                    for option in self.switch_select.options
                    if option.default
                ),
                None,
            )
            if selected is not None:
                character = get_character(int(selected))
                if character and character["user_id"] == self.user_id:
                    return character

        return characters[0]


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


class PublicCharacterPicker(discord.ui.LayoutView):
    def __init__(
        self,
        member: discord.Member,
        characters: list[dict],
    ):
        super().__init__(timeout=300)
        self.member = member

        self.add_item(
            discord.ui.TextDisplay(
                f"## ⟐ {member.display_name}'s Characters\n"
                "Select an OC to view its profile."
            )
        )
        self.add_item(discord.ui.Separator())

        row = discord.ui.ActionRow()
        options = [
            discord.SelectOption(
                label=trim(character["name"], 100),
                value=str(character["character_id"]),
                description=f"OC #{index + 1}",
            )
            for index, character in enumerate(characters[:25])
        ]

        select = discord.ui.Select(
            placeholder="Select an OC",
            options=options,
            min_values=1,
            max_values=1,
        )
        select.callback = self.select_callback

        row.add_item(select)
        self.select = select
        self.add_item(row)

        if len(characters) > 25:
            self.add_item(
                discord.ui.TextDisplay(
                    "*Only the first 25 OCs are available in this picker.*"
                )
            )

    async def select_callback(self, interaction: discord.Interaction):
        character_id = int(self.select.values[0])
        character = get_character(character_id)

        if not character or character["user_id"] != self.member.id:
            await interaction.response.send_message(
                "That character no longer exists.",
                ephemeral=True,
            )
            return

        await interaction.response.edit_message(
            view=CharacterProfile(character, self.member)
        )


async def ensure_roleplay_channel(
    interaction: discord.Interaction,
) -> bool:
    if interaction.guild is None:
        await interaction.response.send_message(
            "The roleplay system can only be used inside a server.",
            ephemeral=True,
        )
        return False

    settings = get_roleplay_settings(interaction.guild.id)

    if not settings["enabled"]:
        await interaction.response.send_message(
            "The roleplay system is currently OFF in this server.\n"
            "An administrator can configure it with /oc admin.",
            ephemeral=True,
        )
        return False

    channel_ids = settings["channel_ids"]

    if not channel_ids:
        await interaction.response.send_message(
            "No roleplay channels have been configured yet.\n"
            "An administrator can choose them with /oc admin.",
            ephemeral=True,
        )
        return False

    if interaction.channel_id not in channel_ids:
        allowed = ", ".join(f"<#{channel_id}>" for channel_id in channel_ids)
        await interaction.response.send_message(
            "This is not a roleplay channel.\n"
            f"Use one of the configured channels: {allowed}",
            ephemeral=True,
        )
        return False

    return True


class RoleplaySettingsView(discord.ui.LayoutView):
    def __init__(
        self,
        guild_id: int,
        *,
        enabled: bool | None = None,
        selected_channel_ids: list[int] | None = None,
    ):
        super().__init__(timeout=900)
        self.guild_id = guild_id

        saved = get_roleplay_settings(guild_id)
        self.enabled = saved["enabled"] if enabled is None else enabled
        self.selected_channel_ids = (
            list(saved["channel_ids"])
            if selected_channel_ids is None
            else list(selected_channel_ids)
        )

        status = "ON" if self.enabled else "OFF"
        saved_channels = saved["channel_ids"]
        selected_text = (
            ", ".join(f"<#{channel_id}>" for channel_id in self.selected_channel_ids)
            if self.selected_channel_ids
            else "None selected"
        )

        saved_text = (
            ", ".join(f"<#{channel_id}>" for channel_id in saved_channels)
            if saved_channels
            else "None configured"
        )

        selection_matches_saved = set(self.selected_channel_ids) == set(saved_channels)
        selection_status = (
            "Matches saved settings"
            if selection_matches_saved
            else "UNSAVED CHANGES — press Save Channels"
        )

        panel = (
            "## ⟐ Roleplay Settings\\n"
            "*Server-wide controls for the RP system*\\n\\n"
            f"**Status:** {status}\\n"
            f"**Saved RP channels:** {saved_text}\\n"
            f"**Selection:** {selected_text}\\n"
            f"**Selection status:** {selection_status}\\n\\n"
            "Choose the channels in the selector, then press Save Channels. "
            "When server RP is ON, messages are relayed as the author's active OC "
            "in saved RP channels, provided the player has personal RP turned ON."
        )

        self.add_item(discord.ui.TextDisplay(panel))
        self.add_item(discord.ui.Separator())

        channel_row = discord.ui.ActionRow()
        self.channel_select = discord.ui.ChannelSelect(
            placeholder="Select RP channels",
            min_values=1,
            max_values=25,
            channel_types=[discord.ChannelType.text],
        )
        self.channel_select.callback = self.channel_select_callback
        channel_row.add_item(self.channel_select)
        self.add_item(channel_row)

        actions = discord.ui.ActionRow()

        stop = discord.ui.Button(
            label="Stop Server RP",
            style=discord.ButtonStyle.danger,
            disabled=not self.enabled,
        )
        start = discord.ui.Button(
            label="Open Server RP",
            style=discord.ButtonStyle.success,
            disabled=self.enabled,
        )
        save = discord.ui.Button(
            label="Save Channels",
            style=discord.ButtonStyle.primary,
        )
        clear = discord.ui.Button(
            label="Clear Channels",
            style=discord.ButtonStyle.secondary,
        )
        close = discord.ui.Button(
            label="Close",
            style=discord.ButtonStyle.secondary,
        )

        stop.callback = self.stop_callback
        start.callback = self.start_callback
        save.callback = self.save_callback
        clear.callback = self.clear_callback
        close.callback = self.close_callback

        actions.add_item(stop)
        actions.add_item(start)
        actions.add_item(save)
        actions.add_item(clear)
        actions.add_item(close)
        self.add_item(actions)

    async def allowed(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None or interaction.guild.id != self.guild_id:
            await interaction.response.send_message(
                "This settings panel is no longer valid here.",
                ephemeral=True,
            )
            return False

        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "You need Manage Server to change roleplay settings.",
                ephemeral=True,
            )
            return False

        return True

    async def channel_select_callback(self, interaction: discord.Interaction):
        if not await self.allowed(interaction):
            return

        self.selected_channel_ids = [channel.id for channel in self.channel_select.values]

        await interaction.response.edit_message(
            view=RoleplaySettingsView(
                self.guild_id,
                enabled=self.enabled,
                selected_channel_ids=self.selected_channel_ids,
            )
        )

    async def stop_callback(self, interaction: discord.Interaction):
        if not await self.allowed(interaction):
            return

        self.enabled = False
        save_roleplay_settings(
            self.guild_id,
            False,
            self.selected_channel_ids,
        )

        await interaction.response.edit_message(
            view=RoleplaySettingsView(
                self.guild_id,
                enabled=False,
                selected_channel_ids=self.selected_channel_ids,
            )
        )

    async def start_callback(self, interaction: discord.Interaction):
        if not await self.allowed(interaction):
            return

        if not self.selected_channel_ids:
            await interaction.response.send_message(
                "Select at least one RP channel before opening server RP.",
                ephemeral=True,
            )
            return

        self.enabled = True
        save_roleplay_settings(
            self.guild_id,
            True,
            self.selected_channel_ids,
        )

        await interaction.response.edit_message(
            view=RoleplaySettingsView(
                self.guild_id,
                enabled=True,
                selected_channel_ids=self.selected_channel_ids,
            )
        )

    async def save_callback(self, interaction: discord.Interaction):
        if not await self.allowed(interaction):
            return

        save_roleplay_settings(
            self.guild_id,
            self.enabled,
            self.selected_channel_ids,
        )

        await interaction.response.edit_message(
            view=RoleplaySettingsView(
                self.guild_id,
                enabled=self.enabled,
                selected_channel_ids=self.selected_channel_ids,
            )
        )

    async def clear_callback(self, interaction: discord.Interaction):
        if not await self.allowed(interaction):
            return

        self.selected_channel_ids = []
        save_roleplay_settings(
            self.guild_id,
            self.enabled,
            [],
        )

        await interaction.response.edit_message(
            view=RoleplaySettingsView(
                self.guild_id,
                enabled=self.enabled,
                selected_channel_ids=[],
            )
        )

    async def close_callback(self, interaction: discord.Interaction):
        if not await self.allowed(interaction):
            return

        self.stop()
        # V2 LayoutView messages cannot be reliably cleared with view=None.
        # Delete the original (including ephemeral) settings panel instead.
        await interaction.response.defer()
        await interaction.delete_original_response()


class PlayerSettingsView(discord.ui.LayoutView):
    def __init__(
        self,
        guild_id: int,
        user_id: int,
        selected_character_id: int | None = None,
    ):
        super().__init__(timeout=900)
        self.guild_id = guild_id
        self.user_id = user_id

        characters = get_characters(user_id)
        saved_id = get_active_character_id(guild_id, user_id)
        self.roleplay_active = get_player_roleplay_active(guild_id, user_id)

        if selected_character_id is None:
            selected_character_id = saved_id

        if selected_character_id is None and characters:
            selected_character_id = characters[0]["character_id"]

        valid_ids = {item["character_id"] for item in characters}
        if selected_character_id not in valid_ids:
            selected_character_id = (
                characters[0]["character_id"] if characters else None
            )

        self.selected_character_id = selected_character_id

        active = (
            get_character(self.selected_character_id)
            if self.selected_character_id
            else None
        )
        active_name = active["name"] if active else "No OC selected"

        player_status = "ON" if self.roleplay_active else "OFF"

        panel = (
            "## ⟐ Roleplay Settings\n"
            "*Your personal roleplay controls*\n\n"
            f"**Personal RP:** {player_status}\n"
            f"**Active OC:** {active_name}\n"
            "Choose the OC you want to use, then save it. "
            "You can also stop or start your own RP participation here."
        )

        self.add_item(discord.ui.TextDisplay(panel))
        self.add_item(discord.ui.Separator())

        row = discord.ui.ActionRow()
        options = [
            discord.SelectOption(
                label=trim(character["name"], 100),
                description=f"OC #{index + 1}",
                value=str(character["character_id"]),
                default=character["character_id"] == self.selected_character_id,
            )
            for index, character in enumerate(characters[:25])
        ]

        if options:
            self.character_select = discord.ui.Select(
                placeholder="Choose your active OC",
                options=options,
                min_values=1,
                max_values=1,
            )
        else:
            self.character_select = discord.ui.Select(
                placeholder="No OCs available",
                options=[
                    discord.SelectOption(
                        label="No OCs available",
                        value="none",
                        default=True,
                    )
                ],
                min_values=1,
                max_values=1,
                disabled=True,
            )

        self.character_select.callback = self.select_callback
        row.add_item(self.character_select)
        self.add_item(row)

        actions = discord.ui.ActionRow()

        save = discord.ui.Button(
            label="Save Active OC",
            style=discord.ButtonStyle.primary,
            disabled=not bool(options),
        )
        toggle = discord.ui.Button(
            label="Stop My RP" if self.roleplay_active else "Start My RP",
            style=(
                discord.ButtonStyle.danger
                if self.roleplay_active
                else discord.ButtonStyle.success
            ),
        )
        dashboard = discord.ui.Button(
            label="OC Dashboard",
            style=discord.ButtonStyle.secondary,
        )
        close = discord.ui.Button(
            label="Close",
            style=discord.ButtonStyle.secondary,
        )

        save.callback = self.save_callback
        toggle.callback = self.toggle_callback
        dashboard.callback = self.dashboard_callback
        close.callback = self.close_callback

        actions.add_item(save)
        actions.add_item(toggle)
        actions.add_item(dashboard)
        actions.add_item(close)
        self.add_item(actions)

        if len(characters) > 25:
            self.add_item(
                discord.ui.TextDisplay(
                    "*Only the first 25 OCs are shown here.*"
                )
            )

    async def allowed(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None or interaction.guild.id != self.guild_id:
            await interaction.response.send_message(
                "This settings panel is no longer valid here.",
                ephemeral=True,
            )
            return False

        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This settings panel belongs to someone else.",
                ephemeral=True,
            )
            return False

        return True

    async def select_callback(self, interaction: discord.Interaction):
        if not await self.allowed(interaction):
            return

        selected = self.character_select.values[0]
        if selected == "none":
            await interaction.response.send_message(
                "Create an OC first.",
                ephemeral=True,
            )
            return

        self.selected_character_id = int(selected)

        await interaction.response.edit_message(
            view=PlayerSettingsView(
                self.guild_id,
                self.user_id,
                self.selected_character_id,
            )
        )

    async def save_callback(self, interaction: discord.Interaction):
        if not await self.allowed(interaction):
            return

        if self.selected_character_id is None:
            await interaction.response.send_message(
                "Create an OC first.",
                ephemeral=True,
            )
            return

        character = get_character(self.selected_character_id)
        if not character or character["user_id"] != self.user_id:
            await interaction.response.send_message(
                "That OC no longer exists.",
                ephemeral=True,
            )
            return

        save_active_character_id(
            self.guild_id,
            self.user_id,
            self.selected_character_id,
        )

        await interaction.response.edit_message(
            view=PlayerSettingsView(
                self.guild_id,
                self.user_id,
                self.selected_character_id,
            )
        )

    async def toggle_callback(self, interaction: discord.Interaction):
        if not await self.allowed(interaction):
            return

        self.roleplay_active = not self.roleplay_active
        save_player_roleplay_active(
            self.guild_id,
            self.user_id,
            self.roleplay_active,
        )

        await interaction.response.edit_message(
            view=PlayerSettingsView(
                self.guild_id,
                self.user_id,
                self.selected_character_id,
            )
        )

    async def dashboard_callback(self, interaction: discord.Interaction):
        if not await self.allowed(interaction):
            return

        await interaction.response.edit_message(
            view=CharacterDashboard(
                self.user_id,
                self.selected_character_id,
            )
        )

    async def close_callback(self, interaction: discord.Interaction):
        if not await self.allowed(interaction):
            return

        self.stop()
        # V2 LayoutView messages cannot be reliably cleared with view=None.
        # Delete the original (including ephemeral) settings panel instead.
        await interaction.response.defer()
        await interaction.delete_original_response()


class RPBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rp_webhook_cache: dict[int, discord.Webhook] = {}

    async def on_message(self, message: discord.Message):
        # Only relay ordinary human messages in explicitly configured RP channels.
        if message.guild is None or message.author.bot or message.webhook_id:
            return

        if message.content.startswith("!"):
            return

        settings = get_roleplay_settings(message.guild.id)
        if not settings["enabled"] or message.channel.id not in settings["channel_ids"]:
            return

        if not get_player_roleplay_active(message.guild.id, message.author.id):
            return

        character_id = get_active_character_id(message.guild.id, message.author.id)
        character = get_character(character_id) if character_id else None
        if not character or character["user_id"] != message.author.id:
            return

        channel = message.channel
        if not isinstance(channel, discord.TextChannel):
            return

        me = message.guild.me
        if me is None:
            return
        permissions = channel.permissions_for(me)
        if not permissions.manage_webhooks or not permissions.manage_messages:
            print(
                f"Cannot relay RP message in channel {channel.id}: "
                "bot needs Manage Webhooks and Manage Messages."
            )
            return

        webhook = self.rp_webhook_cache.get(channel.id)
        try:
            if webhook is None:
                hooks = await channel.webhooks()
                webhook = next(
                    (hook for hook in hooks if hook.name == "OC Roleplay Relay"),
                    None,
                )
                if webhook is None:
                    webhook = await channel.create_webhook(
                        name="OC Roleplay Relay",
                        reason="Relay roleplay messages using saved OC profiles",
                    )
                self.rp_webhook_cache[channel.id] = webhook

            payload = (message.content or "").strip()
            if message.attachments:
                attachment_links = "\\n".join(item.url for item in message.attachments)
                payload = f"{payload}\\n{attachment_links}".strip()
            if not payload:
                return
            if len(payload) > 2000:
                payload = payload[:1997] + "..."

            send_kwargs = {
                "content": payload,
                "username": character["name"][:80],
                "allowed_mentions": discord.AllowedMentions.none(),
                "wait": True,
            }
            avatar_url = character.get("avatar_url")
            if avatar_url:
                send_kwargs["avatar_url"] = avatar_url

            await webhook.send(**send_kwargs)
            # Delete only after the OC relay succeeded, so a failed relay never eats a message.
            await message.delete()
        except discord.Forbidden:
            print(
                f"RP relay permission failure in channel {channel.id}; "
                "original message was kept if relay could not be sent."
            )
            self.rp_webhook_cache.pop(channel.id, None)
        except discord.HTTPException as exc:
            print(f"RP relay failed in channel {channel.id}: {exc}")
            self.rp_webhook_cache.pop(channel.id, None)
        except Exception as exc:
            print(f"Unexpected RP relay error in channel {channel.id}: {exc}")
            self.rp_webhook_cache.pop(channel.id, None)

    async def setup_hook(self):
        init_db()

        guild = discord.Object(id=DEV_GUILD_ID)

        # Remove all old global commands, including the previous /pride command.
        self.tree.clear_commands(guild=None)
        await self.tree.sync()

        # Register only the current /oc command group in the development guild.
        self.tree.clear_commands(guild=guild)
        self.tree.add_command(
            oc_group,
            guild=guild,
            override=True,
        )
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
    description="Create and manage your roleplay characters.",
)


@oc_group.command(
    name="dashboard",
    description="Open your OC dashboard.",
)
async def oc_dashboard(interaction: discord.Interaction):
    if not await ensure_roleplay_channel(interaction):
        return

    active_id = get_active_character_id(
        interaction.guild.id,
        interaction.user.id,
    )

    await interaction.response.send_message(
        view=CharacterDashboard(interaction.user.id, active_id),
        ephemeral=True,
    )


@oc_group.command(
    name="view",
    description="View a member's OC.",
)
@app_commands.describe(
    member="The member whose OC you want to view."
)
async def oc_view(
    interaction: discord.Interaction,
    member: discord.Member | None = None,
):
    if not await ensure_roleplay_channel(interaction):
        return

    target = member or interaction.user
    characters = get_characters(target.id)

    if not characters:
        await interaction.response.send_message(
            f"{target.display_name} doesn't have an OC yet.",
            ephemeral=True,
        )
        return

    if len(characters) == 1:
        await interaction.response.send_message(
            view=CharacterProfile(characters[0], target)
        )
        return

    await interaction.response.send_message(
        view=PublicCharacterPicker(target, characters)
    )


@oc_group.command(
    name="settings",
    description="Open your personal roleplay settings.",
)
async def oc_settings(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message(
            "This command can only be used inside a server.",
            ephemeral=True,
        )
        return

    await interaction.response.send_message(
        view=PlayerSettingsView(
            interaction.guild.id,
            interaction.user.id,
        ),
        ephemeral=True,
    )


@oc_group.command(
    name="admin",
    description="Open the roleplay administrator panel.",
)
async def oc_admin(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message(
            "This command can only be used inside a server.",
            ephemeral=True,
        )
        return

    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message(
            "You need Manage Server to use the roleplay admin panel.",
            ephemeral=True,
        )
        return

    await interaction.response.send_message(
        view=RoleplaySettingsView(interaction.guild.id),
        ephemeral=True,
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
