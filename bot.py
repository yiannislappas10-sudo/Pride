import asyncio
import datetime
import os
import re

import discord
from discord import app_commands
from discord.ext import commands
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
    create_episode,
    get_episode,
    get_episodes,
    update_episode,
    delete_episode,
    get_episode_cast,
    add_episode_cast,
    remove_episode_cast,
    get_active_episode,
    save_episode_message,
    get_episode_message_count,
    get_episode_messages,
    get_episode_preparation_remaining,
    lock_episode_player_settings,
    set_episode_narrator,
    add_episode_narrator_request,
    get_episode_narrator_requests,
    delete_episode_narrator_request,
    clear_episode_narrator_requests,
)

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing.")

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


def smart_rp_format(character_name: str, content: str) -> str:
    """Local, zero-cost RP formatter with many contextual RP cues."""
    text = re.sub(r"\s+", " ", (content or "").strip())
    if not text:
        return text

    name = character_name.strip() or "Character"
    lower = text.lower()

    explicit = bool(re.search(
        r"(^|\s)(\*[^*]+\*|_[^_]+_|\([^)]{2,80}\))($|\s)",
        text,
    ))

    cue = None
    action = None

    cue_patterns = [
        (r"\b(whisper|whispers|whispering|quietly|under (?:their|his|her) breath|keep your voice down|lower your voice)\b", "whispers"),
        (r"\b(shout|shouts|shouting|yell|yells|yelling|scream|screams|screaming)\b", "shouts"),
        (r"\b(laugh|laughs|laughing|chuckle|chuckles|giggling|giggles)\b", "laughs"),
        (r"\b(sigh|sighs|sighing|exhales|exhale)\b", "sighs"),
        (r"\b(groan|groans|groaning|grumble|grumbles)\b", "grumbles"),
        (r"\b(mutters|mutter|muttering|mumbles|mumble)\b", "murmurs"),
        (r"\b(gasp|gasps|gasping)\b", "gasps"),
        (r"\b(cry|cries|crying|sob|sobs|sobbing)\b", "voice cracks"),
        (r"\b(angry|furious|enraged)\b|!{2,}", "angrily"),
        (r"\b(nervous|worried|anxious|uneasy)\b|\.{3,}", "nervously"),
    ]

    for pattern, label in cue_patterns:
        if re.search(pattern, lower):
            cue = label
            break

    if not explicit and cue is None:
        action_patterns = [
            (r"\b(is anyone here|anyone here|anybody here)\b", "looks around"),
            (r"\b(hello\??|hey\??|anyone there\??)\b", "looks around"),
            (r"\b(are you there|can you hear me)\b", "looks around"),
            (r"\b(wait|hold on|one second|give me a second)\b", "pauses"),
            (r"\b(come here|over here|follow me|come with me)\b", "gestures for them to come closer"),
            (r"\b(look at this|look here|check this out)\b", "gestures toward it"),
            (r"\b(i['’]?m leaving|i should go|gotta go|have to go|i have to leave)\b", "turns to leave"),
            (r"\b(come in|enter|you can come in)\b", "motions toward the entrance"),
            (r"\b(sit down|take a seat)\b", "gestures toward a seat"),
            (r"\b(stand up|get up)\b", "straightens up"),
            (r"\b(what happened|what's going on|what is happening)\b", "looks around, confused"),
            (r"\b(what do you mean|why did you do that|why are you)\b", "raises an eyebrow"),
            (r"\b(really|seriously|are you serious)\??$", "raises an eyebrow"),
            (r"\b(thank you|thanks)\b", "gives a small nod"),
            (r"\b(sorry|i'm sorry|im sorry)\b", "looks apologetic"),
            (r"\b(i don't know|idk|no idea)\b", "shrugs"),
            (r"\b(maybe|i guess|i suppose)\b", "shrugs slightly"),
            (r"\b(yes|yeah|yep|sure|okay|ok)\b$", "nods"),
            (r"\b(no|nope|nah)\b$", "shakes their head"),
            (r"\b(be careful|watch out|look out)\b", "glances around cautiously"),
            (r"\b(i'm scared|im scared|i'm afraid|im afraid)\b", "takes a nervous step back"),
            (r"\b(i'm tired|im tired|i'm exhausted|im exhausted)\b", "rubs their eyes"),
            (r"\b(i'm cold|im cold)\b", "pulls their arms closer"),
            (r"\b(i'm hungry|im hungry)\b", "glances toward the nearest food"),
            (r"\b(where is|where's)\b", "looks around"),
            (r"\b(come on|hurry up)\b", "motions impatiently"),
            (r"\b(leave me alone|get away from me)\b", "steps back"),
            (r"\b(i love you|love you)\b", "softens their expression"),
            (r"\b(i hate you|hate you)\b", "glares"),
            (r"\b(shut up|be quiet)\b", "glares sharply"),
            (r"\b(what the hell|what the fuck|wtf)\b", "stares in disbelief"),
            (r"\b(good morning|good night|good evening)\b", "offers a small nod"),
        ]

        for pattern, act in action_patterns:
            if re.search(pattern, lower):
                action = act
                break

    # Strongly differentiate generated RP cues without creating a second message.
    if explicit:
        formatted = text
    elif cue:
        formatted = f"**({cue})** {text}"
    elif action:
        formatted = f"**✶ {action}** {text}"
    else:
        formatted = text

    return f"{name}: {formatted}"[:2000]


async def ai_format_rp_message(character: dict, content: str, examples: list[dict]) -> str:
    # Kept as a compatibility wrapper so the rest of Pride does not need an API.
    return smart_rp_format(character.get("name", "Character"), content)


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

    # Episode preparation/live channels are private RP spaces and should
    # also allow OC viewing even when they are not part of the saved RP list.
    for episode in get_episodes(interaction.guild.id, 100):
        if episode.get("status") not in {"preparing", "active"}:
            continue
        if interaction.channel_id in {
            episode.get("prep_channel_id"),
            episode.get("channel_id"),
        }:
            return True

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
        archive_channel_id: int | None = None,
        archive_enabled: bool | None = None,
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
        self.archive_channel_id = (
            saved["archive_channel_id"]
            if archive_channel_id is None
            else archive_channel_id
        )
        self.archive_enabled = (
            saved["archive_enabled"]
            if archive_enabled is None
            else archive_enabled
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
            else "UNSAVED CHANGES — press Save RP Channels"
        )
        archive_text = (
            f"<#{self.archive_channel_id}>"
            if self.archive_channel_id
            else "None selected"
        )
        archive_status = "ON" if self.archive_enabled else "OFF"

        panel = (
            "## ⟐ Roleplay Settings\n"
            "*Server-wide controls for the RP system*\n\n"
            f"**Status:** {status}\n"
            f"**Saved RP channels:** {saved_text}\n"
            f"**Selection:** {selected_text}\n"
            f"**Selection status:** {selection_status}\n\n"
            f"### Episode Archive\n"
            f"**Archive Channel:** {archive_text}\n"
            f"**Publish Completed Episodes:** {archive_status}\n\n"
            "Choose RP channels in the first selector. "
            "Choose one public archive channel in the second selector. "
            "Use the archive controls below to save the channel and decide "
            "whether completed episodes are published there."
        )

        # Keep the V2 view within Discord's top-level child limit.
        self.add_item(discord.ui.TextDisplay(panel))

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

        archive_row = discord.ui.ActionRow()
        self.archive_channel_select = discord.ui.ChannelSelect(
            placeholder="Select archive channel",
            min_values=1,
            max_values=1,
            channel_types=[discord.ChannelType.text],
        )
        self.archive_channel_select.callback = self.archive_channel_select_callback
        archive_row.add_item(self.archive_channel_select)
        self.add_item(archive_row)

        rp_actions = discord.ui.ActionRow()
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
            label="Save RP Channels",
            style=discord.ButtonStyle.primary,
        )
        clear = discord.ui.Button(
            label="Clear RP Channels",
            style=discord.ButtonStyle.secondary,
        )
        stop.callback = self.stop_callback
        start.callback = self.start_callback
        save.callback = self.save_callback
        clear.callback = self.clear_callback
        for item in (stop, start, save, clear):
            rp_actions.add_item(item)
        self.add_item(rp_actions)

        archive_actions = discord.ui.ActionRow()
        archive_toggle = discord.ui.Button(
            label=f"Publish Episodes: {archive_status}",
            style=(
                discord.ButtonStyle.success
                if self.archive_enabled
                else discord.ButtonStyle.secondary
            ),
        )
        archive_save = discord.ui.Button(
            label="Save Archive",
            style=discord.ButtonStyle.primary,
        )
        archive_clear = discord.ui.Button(
            label="Clear Archive",
            style=discord.ButtonStyle.secondary,
        )
        close = discord.ui.Button(
            label="Close",
            style=discord.ButtonStyle.secondary,
        )
        archive_toggle.callback = self.archive_toggle_callback
        archive_save.callback = self.archive_save_callback
        archive_clear.callback = self.archive_clear_callback
        close.callback = self.close_callback
        for item in (archive_toggle, archive_save, archive_clear, close):
            archive_actions.add_item(item)
        self.add_item(archive_actions)

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
                archive_channel_id=self.archive_channel_id,
                archive_enabled=self.archive_enabled,
            )
        )

    async def archive_channel_select_callback(self, interaction: discord.Interaction):
        if not await self.allowed(interaction):
            return

        self.archive_channel_id = self.archive_channel_select.values[0].id
        await interaction.response.edit_message(
            view=RoleplaySettingsView(
                self.guild_id,
                enabled=self.enabled,
                selected_channel_ids=self.selected_channel_ids,
                archive_channel_id=self.archive_channel_id,
                archive_enabled=self.archive_enabled,
            )
        )

    async def archive_save_callback(self, interaction: discord.Interaction):
        if not await self.allowed(interaction):
            return

        if self.archive_channel_id is None:
            await interaction.response.send_message(
                "Select an archive channel first.",
                ephemeral=True,
            )
            return

        save_archive_settings(
            self.guild_id,
            self.archive_channel_id,
            self.archive_enabled,
        )
        await interaction.response.edit_message(
            view=RoleplaySettingsView(
                self.guild_id,
                enabled=self.enabled,
                selected_channel_ids=self.selected_channel_ids,
                archive_channel_id=self.archive_channel_id,
                archive_enabled=self.archive_enabled,
            )
        )

    async def archive_toggle_callback(self, interaction: discord.Interaction):
        if not await self.allowed(interaction):
            return

        next_enabled = not self.archive_enabled

        # Publishing can only be turned ON when a destination archive exists.
        # Keep the button clickable so the panel explains the missing setting
        # instead of appearing broken/disabled.
        if next_enabled and self.archive_channel_id is None:
            await interaction.response.send_message(
                "Select an archive channel first, then turn Publish Episodes ON.",
                ephemeral=True,
            )
            return

        self.archive_enabled = next_enabled
        save_archive_settings(
            self.guild_id,
            self.archive_channel_id,
            self.archive_enabled,
        )
        await interaction.response.edit_message(
            view=RoleplaySettingsView(
                self.guild_id,
                enabled=self.enabled,
                selected_channel_ids=self.selected_channel_ids,
                archive_channel_id=self.archive_channel_id,
                archive_enabled=self.archive_enabled,
            )
        )

    async def archive_clear_callback(self, interaction: discord.Interaction):
        if not await self.allowed(interaction):
            return

        self.archive_channel_id = None
        self.archive_enabled = False
        save_archive_settings(
            self.guild_id,
            None,
            False,
        )
        await interaction.response.edit_message(
            view=RoleplaySettingsView(
                self.guild_id,
                enabled=self.enabled,
                selected_channel_ids=self.selected_channel_ids,
                archive_channel_id=None,
                archive_enabled=False,
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
                archive_channel_id=self.archive_channel_id,
                archive_enabled=self.archive_enabled,
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
                archive_channel_id=self.archive_channel_id,
                archive_enabled=self.archive_enabled,
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
                archive_channel_id=self.archive_channel_id,
                archive_enabled=self.archive_enabled,
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
                archive_channel_id=self.archive_channel_id,
                archive_enabled=self.archive_enabled,
            )
        )

    async def close_callback(self, interaction: discord.Interaction):
        if not await self.allowed(interaction):
            return

        self.stop()
        try:
            await interaction.response.defer()
            if interaction.message is not None:
                try:
                    await interaction.message.delete()
                    return
                except (discord.NotFound, discord.HTTPException):
                    pass
            await interaction.delete_original_response()
        except discord.NotFound:
            pass


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
        self.auto_rp_format = get_player_auto_rp_format(
            guild_id,
            user_id,
        )

        active = (
            get_character(self.selected_character_id)
            if self.selected_character_id
            else None
        )
        active_name = active["name"] if active else "No OC selected"

        player_status = "ON" if self.roleplay_active else "OFF"
        ai_status = "ON" if self.auto_rp_format else "OFF"

        panel = (
            "## ⟐ Roleplay Settings\n"
            "*Your personal roleplay controls*\n\n"
            f"**Personal RP:** {player_status}\n"
            f"**Active OC:** {active_name}\n"
            f"**AI RP Format:** {ai_status}\n"
            "When enabled, Pride uses AI to decide when to use "
            "dialogue cues and small RP actions."
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
        ai_format = discord.ui.Button(
            label="Disable AI RP Format" if self.auto_rp_format else "Enable AI RP Format",
            style=(
                discord.ButtonStyle.danger
                if self.auto_rp_format
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
        ai_format.callback = self.auto_format_callback
        dashboard.callback = self.dashboard_callback
        close.callback = self.close_callback

        actions.add_item(save)
        actions.add_item(toggle)
        actions.add_item(ai_format)
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

    async def auto_format_callback(self, interaction: discord.Interaction):
        if not await self.allowed(interaction):
            return

        self.auto_rp_format = not self.auto_rp_format
        save_player_auto_rp_format(
            self.guild_id,
            self.user_id,
            self.auto_rp_format,
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

        try:
            await interaction.response.defer()

            if interaction.message is not None:
                try:
                    await interaction.message.delete()
                    return
                except (discord.NotFound, discord.HTTPException):
                    pass

            await interaction.delete_original_response()
        except discord.NotFound:
            pass



class EpisodeNoticeView(discord.ui.LayoutView):
    def __init__(self, text: str):
        super().__init__(timeout=300)
        self.add_item(discord.ui.TextDisplay(text))


def episode_status_label(status: str) -> str:
    return {
        "planning": "RECRUITING",
        "preparing": "PREPARATION",
        "active": "LIVE",
        "completed": "COMPLETED",
    }.get(status, status.upper())


def episode_lobby_text(episode: dict, cast: list[dict]) -> str:
    status = episode_status_label(episode["status"])
    member_lines = []
    for item in cast:
        character = get_character(item["character_id"])
        name = character["name"] if character else "Deleted OC"
        member_lines.append(f"<@{item['user_id']}> — **{name}**")

    cast_text = "\n".join(member_lines) if member_lines else "*No participants yet.*"
    details = episode.get("details") or "No extra details provided."
    text = (
        f"## ⟐ EPISODE {episode['episode_id']} — {episode['title']}\n"
        f"*{status}*\n\n"
        f"**Players:** {len(cast)}/{episode.get('max_players', 2)}\n"
        f"**Location:** {episode.get('location') or 'Not set'}\n"
        f"**Tone:** {episode.get('tone') or 'Not set'}\n"
        f"**Narrator:** {f"<@{episode['narrator_id']}>" if episode.get('narrator_id') else 'None assigned'}\n\n"
        f"**Premise**\n{trim(episode.get('premise') or 'No premise provided.', 750)}\n\n"
        f"**Additional Details**\n{trim(details, 900)}\n\n"
        f"**Cast**\n{cast_text}"
    )
    return text[:1900]


async def refresh_episode_lobby(bot: "RPBot", episode_id: int):
    episode = get_episode(episode_id)
    if not episode:
        return

    channel_id = episode.get("lobby_channel_id")
    message_id = episode.get("lobby_message_id")
    if not channel_id or not message_id:
        return

    channel = bot.get_channel(channel_id)
    if not isinstance(channel, discord.TextChannel):
        return

    try:
        message = await channel.fetch_message(message_id)
        await message.edit(
            view=EpisodeLobbyView(episode_id),
        )
    except (discord.NotFound, discord.HTTPException):
        pass


class EpisodeDetailsModal(discord.ui.Modal, title="Episode Details — Part II"):
    def __init__(self, base: dict):
        super().__init__(timeout=600)
        self.base = base

        self.lore = discord.ui.TextInput(
            label="Lore / Context",
            placeholder="History, mysteries, factions, secrets, important context...",
            style=discord.TextStyle.paragraph,
            max_length=2000,
            required=False,
        )
        self.objective = discord.ui.TextInput(
            label="Objectives",
            placeholder="What must the characters discover, solve, survive or accomplish?",
            style=discord.TextStyle.paragraph,
            max_length=1500,
            required=False,
        )
        self.key_events = discord.ui.TextInput(
            label="Key Events",
            placeholder="Optional events or beats you want the episode to hit.",
            style=discord.TextStyle.paragraph,
            max_length=1500,
            required=False,
        )
        self.rules = discord.ui.TextInput(
            label="RP Rules / Boundaries",
            placeholder="Things players should or should not do during this episode.",
            style=discord.TextStyle.paragraph,
            max_length=1000,
            required=False,
        )
        self.ending = discord.ui.TextInput(
            label="Ending / Cliffhanger",
            placeholder="How should the episode end or what should it set up?",
            style=discord.TextStyle.paragraph,
            max_length=1200,
            required=False,
        )

        for item in (
            self.lore,
            self.objective,
            self.key_events,
            self.rules,
            self.ending,
        ):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            max_players = int(self.base["max_players"])
        except (TypeError, ValueError):
            max_players = 2

        if max_players < 1 or max_players > 25:
            await interaction.followup.send(
                "Max players must be between 1 and 25.",
                ephemeral=True,
            )
            return

        details_parts = [
            ("Lore / Context", self.lore.value),
            ("Objectives", self.objective.value),
            ("Key Events", self.key_events.value),
            ("RP Rules / Boundaries", self.rules.value),
        ]
        details = "\n\n".join(
            f"**{label}**\n{clean(value, limit)}"
            for label, value, limit in (
                (label, value, 2000 if label == "Lore / Context" else 1500)
                for label, value in details_parts
                if value and value.strip()
            )
        )

        episode = create_episode(
            interaction.guild.id,
            interaction.user.id,
            self.base["title"],
            self.base["premise"],
            self.base["location"],
            self.base["tone"],
            clean(self.ending.value, 1200),
            details,
            max_players,
        )
        if not episode:
            await interaction.followup.send(
                "I couldn't create the episode.",
                ephemeral=True,
            )
            return

        if self.base.get("ping_role"):
            ping_role = interaction.guild.get_role(1555716046919573505)
            if ping_role is not None:
                await interaction.channel.send(
                    f"{ping_role.mention} A new episode is recruiting: **{episode['title']}**",
                    allowed_mentions=discord.AllowedMentions(
                        roles=[ping_role],
                        users=False,
                        everyone=False,
                    ),
                )

        lobby_message = await interaction.channel.send(
            view=EpisodeLobbyView(episode["episode_id"]),
            allowed_mentions=discord.AllowedMentions.none(),
        )

        update_episode(
            episode["episode_id"],
            lobby_channel_id=interaction.channel.id,
            lobby_message_id=lobby_message.id,
        )

        await interaction.followup.send(
            f"Episode **#{episode['episode_id']} — {episode['title']}** created and the recruitment lobby is ready.",
            ephemeral=True,
        )


class EpisodeCreateModal(discord.ui.Modal, title="Create Episode — Part I"):
    def __init__(self):
        super().__init__(timeout=600)

        self.title_input = discord.ui.TextInput(
            label="Episode Title",
            placeholder="The Signal Beneath Haven",
            max_length=100,
            required=True,
        )
        self.premise_input = discord.ui.TextInput(
            label="Premise",
            placeholder="Describe the situation as the episode begins.",
            style=discord.TextStyle.paragraph,
            max_length=2000,
            required=True,
        )
        self.location_input = discord.ui.TextInput(
            label="Location / Setting",
            placeholder="Where does the episode mainly take place?",
            max_length=300,
            required=False,
        )
        self.tone_input = discord.ui.TextInput(
            label="Tone / Genre",
            placeholder="Mystery, horror, action, emotional, calm...",
            max_length=300,
            required=False,
        )
        self.max_players_input = discord.ui.TextInput(
            label="Maximum Players",
            placeholder="4",
            max_length=2,
            required=True,
        )

        for item in (
            self.title_input,
            self.premise_input,
            self.location_input,
            self.tone_input,
            self.max_players_input,
        ):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            max_players = int(self.max_players_input.value.strip())
        except ValueError:
            await interaction.response.send_message(
                "Max players must be a number from 1 to 25.",
                ephemeral=True,
            )
            return

        if not 1 <= max_players <= 25:
            await interaction.response.send_message(
                "Max players must be between 1 and 25.",
                ephemeral=True,
            )
            return

        base = {
            "title": clean(self.title_input.value, 100),
            "premise": clean(self.premise_input.value, 2000),
            "location": clean(self.location_input.value, 300),
            "tone": clean(self.tone_input.value, 300),
            "max_players": max_players,
        }

        base["ping_role"] = False
        await interaction.response.send_message(
            view=EpisodeDetailsPromptView(base),
            ephemeral=True,
        )


class EpisodeDetailsPromptView(discord.ui.LayoutView):
    def __init__(self, base: dict):
        super().__init__(timeout=600)
        self.base = base
        self.render()

    def render(self):
        self.clear_items()
        choice = "ON" if self.base.get("ping_role") else "OFF"
        self.add_item(
            discord.ui.TextDisplay(
                "## ⟐ Episode Setup — Part II\n"
                "Choose whether to notify the episode role before continuing.\n\n"
                f"**Role ping:** {choice}\n"
                "Role: <@1555716046919573505>\n\n"
                "Nothing has been created yet."
            )
        )
        self.add_item(discord.ui.Separator())

        actions = discord.ui.ActionRow()
        ping_button = discord.ui.Button(
            label="Ping Role: ON" if self.base.get("ping_role") else "Ping Role: OFF",
            style=discord.ButtonStyle.success if self.base.get("ping_role") else discord.ButtonStyle.secondary,
        )
        continue_button = discord.ui.Button(
            label="Continue to Details",
            style=discord.ButtonStyle.primary,
        )
        cancel_button = discord.ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.secondary,
        )

        async def toggle_callback(interaction: discord.Interaction):
            self.base["ping_role"] = not self.base.get("ping_role", False)
            self.render()
            await interaction.response.edit_message(view=self)

        async def continue_callback(interaction: discord.Interaction):
            await interaction.response.send_modal(
                EpisodeDetailsModal(self.base)
            )

        async def cancel_callback(interaction: discord.Interaction):
            await interaction.response.edit_message(
                view=EpisodeNoticeView("Episode creation cancelled."),
            )

        ping_button.callback = toggle_callback
        continue_button.callback = continue_callback
        cancel_button.callback = cancel_callback

        actions.add_item(ping_button)
        actions.add_item(continue_button)
        actions.add_item(cancel_button)
        self.add_item(actions)


class EpisodeJoinView(discord.ui.LayoutView):
    def __init__(self, user_id: int, episode_id: int):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.episode_id = episode_id

        characters = get_characters(user_id)
        options = [
            discord.SelectOption(
                label=trim(item["name"], 100),
                description=f"OC #{index + 1}",
                value=str(item["character_id"]),
            )
            for index, item in enumerate(characters[:25])
        ]

        self.add_item(
            discord.ui.TextDisplay(
                "## ⟐ Choose Your OC\n"
                "Select the character you will use for this episode. "
                "Your chosen OC becomes part of the episode cast and the private preparation ticket."
            )
        )
        self.add_item(discord.ui.Separator())

        if options:
            self.character_select = discord.ui.Select(
                placeholder="Choose your OC",
                options=options,
                min_values=1,
                max_values=1,
            )
        else:
            self.character_select = discord.ui.Select(
                placeholder="Create an OC first",
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
        row = discord.ui.ActionRow()
        row.add_item(self.character_select)
        self.add_item(row)

    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This OC selector belongs to someone else.",
                ephemeral=True,
            )
            return

        selected = self.character_select.values[0]
        if selected == "none":
            await interaction.response.send_message(
                "Create an OC first.",
                ephemeral=True,
            )
            return

        episode = get_episode(self.episode_id)
        if not episode or episode["status"] != "planning":
            await interaction.response.send_message(
                "This episode is no longer recruiting.",
                ephemeral=True,
            )
            return

        cast = get_episode_cast(self.episode_id)
        already_joined = next(
            (item for item in cast if item["user_id"] == interaction.user.id),
            None,
        )
        if not already_joined and len(cast) >= episode["max_players"]:
            await interaction.response.send_message(
                "The episode is already full.",
                ephemeral=True,
            )
            return

        add_episode_cast(
            self.episode_id,
            interaction.guild.id,
            interaction.user.id,
            int(selected),
        )

        episode = get_episode(self.episode_id)
        await interaction.response.edit_message(
            view=EpisodeNoticeView(
                f"Joined **{episode['title']}** with **{get_character(int(selected))['name']}**."
            ),
        )
        await refresh_episode_lobby(interaction.client, self.episode_id)


class EpisodeLobbyView(discord.ui.LayoutView):
    def __init__(self, episode_id: int):
        super().__init__(timeout=None)
        self.episode_id = episode_id

        episode = get_episode(episode_id)
        cast = get_episode_cast(episode_id) if episode else []
        if episode:
            self.add_item(discord.ui.TextDisplay(episode_lobby_text(episode, cast)))
            self.add_item(discord.ui.Separator())
        full = bool(episode) and len(cast) >= int(episode.get("max_players") or 2)

        join = discord.ui.Button(
            label="Join with OC",
            custom_id=f"episode:{self.episode_id}:join",
            style=discord.ButtonStyle.success,
            disabled=not episode or episode["status"] != "planning" or full,
        )
        start = discord.ui.Button(
            label="Start Episode",
            custom_id=f"episode:{self.episode_id}:start",
            style=discord.ButtonStyle.primary,
            disabled=(
                not episode
                or episode["status"] != "planning"
                or not full
            ),
        )
        details = discord.ui.Button(
            label="Full Details",
            custom_id=f"episode:{self.episode_id}:details",
            style=discord.ButtonStyle.secondary,
            disabled=not bool(episode),
        )
        leave = discord.ui.Button(
            label="Leave Cast",
            custom_id=f"episode:{self.episode_id}:leave",
            style=discord.ButtonStyle.secondary,
            disabled=not episode or episode["status"] != "planning",
        )
        cancel = discord.ui.Button(
            label="Cancel Episode",
            custom_id=f"episode:{self.episode_id}:cancel",
            style=discord.ButtonStyle.danger,
            disabled=not bool(episode),
        )

        join.callback = self.join_callback
        start.callback = self.start_callback
        details.callback = self.details_callback
        leave.callback = self.leave_callback
        cancel.callback = self.cancel_callback

        row = discord.ui.ActionRow()
        for item in (join, start, details, leave, cancel):
            row.add_item(item)
        self.add_item(row)

        narrator = discord.ui.Button(
            label="Set Narrator",
            style=discord.ButtonStyle.primary,
            disabled=not episode or episode["status"] != "planning",
        )
        request = discord.ui.Button(
            label="Request Narrator",
            style=discord.ButtonStyle.secondary,
            disabled=not episode or episode["status"] != "planning",
        )
        manage = discord.ui.Button(
            label="Manage Requests",
            style=discord.ButtonStyle.secondary,
            disabled=not episode or episode["status"] != "planning",
        )
        narrator.callback = self.narrator_callback
        request.callback = self.request_narrator_callback
        manage.callback = self.manage_narrator_requests_callback
        narrator_row = discord.ui.ActionRow()
        narrator_row.add_item(narrator)
        narrator_row.add_item(request)
        narrator_row.add_item(manage)
        self.add_item(narrator_row)

    async def narrator_callback(self, interaction: discord.Interaction):
        episode = get_episode(self.episode_id)
        if not episode or episode["status"] != "planning":
            await interaction.response.send_message(
                "The narrator can only be assigned while the episode is recruiting.",
                ephemeral=True,
            )
            return
        if interaction.user.id != episode["creator_id"]:
            await interaction.response.send_message(
                "Only the episode creator can assign the narrator.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            view=EpisodeNarratorView(self.episode_id),
            ephemeral=True,
        )

    async def request_narrator_callback(self, interaction: discord.Interaction):
        episode = get_episode(self.episode_id)
        if not episode or episode["status"] != "planning":
            await interaction.response.send_message(
                "Narrator requests are closed once recruitment ends.",
                ephemeral=True,
            )
            return
        if interaction.user.id == episode["creator_id"]:
            await interaction.response.send_message(
                "You're the episode creator. Use **Set Narrator** to choose yourself.",
                ephemeral=True,
            )
            return
        if episode.get("narrator_id"):
            await interaction.response.send_message(
                "A narrator has already been selected.",
                ephemeral=True,
            )
            return
        cast_ids = {item["user_id"] for item in get_episode_cast(self.episode_id)}
        if interaction.user.id in cast_ids:
            await interaction.response.send_message(
                "You are already playing an OC in this episode. A narrator cannot also be a player.",
                ephemeral=True,
            )
            return
        pending = get_episode_narrator_requests(self.episode_id)
        if any(item["user_id"] == interaction.user.id for item in pending):
            await interaction.response.send_message(
                "Your narrator request is already pending.",
                ephemeral=True,
            )
            return
        add_episode_narrator_request(
            self.episode_id,
            interaction.guild.id,
            interaction.user.id,
        )
        await interaction.response.send_message(
            "Your narrator request has been sent to the episode creator.",
            ephemeral=True,
        )

    async def manage_narrator_requests_callback(self, interaction: discord.Interaction):
        episode = get_episode(self.episode_id)
        if not episode or episode["status"] != "planning":
            await interaction.response.send_message(
                "Narrator requests are closed once recruitment ends.",
                ephemeral=True,
            )
            return
        if interaction.user.id != episode["creator_id"]:
            await interaction.response.send_message(
                "Only the episode creator can manage narrator requests.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            view=EpisodeNarratorRequestsView(self.episode_id),
            ephemeral=True,
        )

    async def join_callback(self, interaction: discord.Interaction):
        episode = get_episode(self.episode_id)
        if not episode or episode["status"] != "planning":
            await interaction.response.send_message(
                "This episode is no longer recruiting.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            view=EpisodeJoinView(interaction.user.id, self.episode_id),
            ephemeral=True,
        )

    async def start_callback(self, interaction: discord.Interaction):
        episode = get_episode(self.episode_id)
        if not episode or episode["status"] != "planning":
            await interaction.response.send_message(
                "This episode cannot be started right now.",
                ephemeral=True,
            )
            return

        if interaction.user.id != episode["creator_id"]:
            await interaction.response.send_message(
                "Only the episode creator can start it.",
                ephemeral=True,
            )
            return

        cast = get_episode_cast(self.episode_id)
        if len(cast) < episode["max_players"]:
            await interaction.response.send_message(
                f"The cast is not full yet: **{len(cast)}/{episode['max_players']}**.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        bot_member = guild.me
        if bot_member is None or not guild.me.guild_permissions.manage_channels:
            await interaction.followup.send(
                "I need Manage Channels to create the private episode preparation ticket.",
                ephemeral=True,
            )
            return

        category = discord.utils.get(
            guild.categories,
            name="Episode Preparation",
        )
        if category is None:
            try:
                category = await guild.create_category(
                    "Episode Preparation",
                    reason="Create private preparation tickets for RP episodes",
                )
            except discord.Forbidden:
                await interaction.followup.send(
                    "I couldn't create the Episode Preparation category. Check my Manage Channels permission.",
                    ephemeral=True,
                )
                return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            bot_member: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
                manage_messages=True,
                manage_webhooks=True,
            ),
        }

        allowed_user_ids = {episode["creator_id"]}
        allowed_user_ids.update(item["user_id"] for item in cast)
        if episode.get("narrator_id"):
            allowed_user_ids.add(int(episode["narrator_id"]))
        for user_id in allowed_user_ids:
            # get_member() can miss users who are not currently in cache.
            # Fetch them so every joined cast member receives the overwrite.
            member = guild.get_member(user_id)
            if member is None:
                try:
                    member = await guild.fetch_member(user_id)
                except (discord.NotFound, discord.HTTPException):
                    member = None

            if member:
                overwrites[member] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    attach_files=True,
                    embed_links=True,
                )

        channel = await category.create_text_channel(
            f"episode-{self.episode_id}-preparation",
            overwrites=overwrites,
            topic=f"Private preparation for Episode #{self.episode_id} — {episode['title']}",
            reason="Open private RP episode preparation",
        )

        update_episode(
            self.episode_id,
            status="preparing",
            prep_channel_id=channel.id,
        )

        await interaction.followup.send(
            f"Preparation opened: {channel.mention}",
            ephemeral=False,
        )

        prep_message = await channel.send(
            view=EpisodePrepView(self.episode_id),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        update_episode(
            self.episode_id,
            prep_message_id=prep_message.id,
        )

        cast_mentions = " ".join(f"<@{item['user_id']}>" for item in cast)
        await channel.send(
            (
                "## ⟐ RP SETTINGS — PREP REMINDER\n"
                f"{cast_mentions}\n\n"
                "The bot will automatically take over your OC when the "
                "10-minute preparation timer ends and the episode is ready for RP.\n\n"
                "**Before the timer reaches 0:** use `/oc settings` to check your "
                "active OC and enable **AI RP Format** if you want Pride to add "
                "RP actions/dialogue cues. **Personal RP turns ON automatically "
                "when prep ends.**\n\n"
                "⚠ Your OC and AI RP setting are locked for this episode when "
                "prep ends. You cannot change them afterward."
            ),
            allowed_mentions=discord.AllowedMentions(
                users=True,
                roles=False,
                everyone=False,
            ),
        )
        interaction.client.schedule_episode_prep_timer(self.episode_id)

        await refresh_episode_lobby(interaction.client, self.episode_id)

    async def details_callback(self, interaction: discord.Interaction):
        episode = get_episode(self.episode_id)
        if not episode:
            await interaction.response.send_message(
                "That episode no longer exists.",
                ephemeral=True,
            )
            return

        cast = get_episode_cast(self.episode_id)
        await interaction.response.send_message(
            episode_lobby_text(episode, cast),
            ephemeral=True,
        )

    async def leave_callback(self, interaction: discord.Interaction):
        episode = get_episode(self.episode_id)
        if not episode or episode["status"] != "planning":
            await interaction.response.send_message(
                "You cannot leave this episode anymore.",
                ephemeral=True,
            )
            return

        if interaction.user.id == episode["creator_id"]:
            await interaction.response.send_message(
                "The episode creator cannot leave their own episode.",
                ephemeral=True,
            )
            return

        cast = get_episode_cast(self.episode_id)
        member = next(
            (item for item in cast if item["user_id"] == interaction.user.id),
            None,
        )
        if not member:
            await interaction.response.send_message(
                "You are not currently in the cast.",
                ephemeral=True,
            )
            return

        remove_episode_cast(self.episode_id, interaction.user.id)
        await interaction.response.send_message(
            "You left the episode cast.",
            ephemeral=True,
        )
        await refresh_episode_lobby(interaction.client, self.episode_id)

    async def cancel_callback(self, interaction: discord.Interaction):
        episode = get_episode(self.episode_id)
        if not episode or episode["status"] != "planning":
            await interaction.response.send_message(
                "Only recruiting episodes can be cancelled.",
                ephemeral=True,
            )
            return

        if interaction.user.id != episode["creator_id"]:
            await interaction.response.send_message(
                "Only the episode creator can cancel it.",
                ephemeral=True,
            )
            return

        delete_episode(self.episode_id)
        await interaction.response.edit_message(
            view=EpisodeNoticeView("*This episode was cancelled by its creator.*"),
        )


def episode_prep_text(episode: dict, cast: list[dict], remaining: int) -> str:
    if remaining > 0:
        minutes, seconds = divmod(remaining, 60)
        timer = f"{minutes:02d}:{seconds:02d}"
        prep_status = f"**Prep Time Remaining:** {timer}"
    else:
        prep_status = "**Prep Time:** COMPLETE — the creator can begin the RP."

    cast_lines = []
    for item in cast:
        character = get_character(item["character_id"])
        if character:
            cast_lines.append(
                f"<@{item['user_id']}> — **{character['name']}** "
                f"• {display(character['pronouns'])}"
            )
        else:
            cast_lines.append(f"<@{item['user_id']}> — **Deleted OC**")

    cast_text = "\n".join(cast_lines) if cast_lines else "*No cast recorded.*"
    narrator_text = (
        f"<@{episode['narrator_id']}>"
        if episode.get("narrator_id")
        else "None assigned"
    )

    text = (
        f"## ⟐ EPISODE {episode['episode_id']} — PREPARATION\n"
        f"**{episode['title']}**\n\n"
        f"{prep_status}\n\n"
        f"**Premise**\n{trim(episode.get('premise') or 'No premise provided.', 850)}\n\n"
        f"**Location:** {episode.get('location') or 'Not set'}\n"
        f"**Tone:** {episode.get('tone') or 'Not set'}\n"
        f"**Narrator:** {narrator_text}\n\n"
        f"### Selected Cast\n{cast_text}\n\n"
        "*Everyone in this ticket may inspect the selected OCs before the episode begins.*"
    )
    return text[:1900]


async def publish_episode_archive(
    channel: discord.TextChannel,
    episode: dict,
):
    cast = get_episode_cast(episode["episode_id"])
    messages = get_episode_messages(episode["episode_id"])

    cast_lines = []
    for item in cast:
        character = get_character(item["character_id"])
        cast_lines.append(
            f"<@{item['user_id']}> — **{character['name'] if character else 'Deleted OC'}**"
        )

    cast_text = "\n".join(cast_lines) if cast_lines else "*No cast recorded.*"
    narrator_text = (
        f"<@{episode['narrator_id']}>"
        if episode.get("narrator_id")
        else "None assigned"
    )

    header = (
        f"## ⟐ EPISODE {episode['episode_id']} — {episode['title']}\n"
        f"**Premise**\n{trim(episode.get('premise') or 'No premise provided.', 1200)}\n\n"
        f"**Location:** {episode.get('location') or 'Not set'}\n"
        f"**Tone:** {episode.get('tone') or 'Not set'}\n"
        f"**Narrator:** {narrator_text}\n\n"
        f"### Cast\n{cast_text}\n\n"
        "### Transcript"
    )
    await channel.send(
        header[:2000],
        allowed_mentions=discord.AllowedMentions(
            users=True,
            roles=False,
            everyone=False,
        ),
    )

    current = ""
    for item in messages:
        if item.get("message_type") == "narrator":
            line = f"**Narrator:** {item['content']}"
        else:
            line = f"**{item.get('character_name') or 'Character'}:** {item['content']}"
        line = line.strip()
        if not line:
            continue
        if len(line) > 1800:
            line = line[:1797] + "..."
        if current and len(current) + len(line) + 1 > 1900:
            await channel.send(
                current,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            current = line
        else:
            current = f"{current}\n{line}".strip()

    if current:
        await channel.send(
            current,
            allowed_mentions=discord.AllowedMentions.none(),
        )
    elif not messages:
        await channel.send(
            "*No RP messages were recorded for this episode.*",
            allowed_mentions=discord.AllowedMentions.none(),
        )


class EpisodeCastView(discord.ui.LayoutView):
    def __init__(self, episode_id: int):
        super().__init__(timeout=300)
        self.episode_id = episode_id

        cast = get_episode_cast(episode_id)
        options = []
        for item in cast[:25]:
            character = get_character(item["character_id"])
            if character:
                options.append(
                    discord.SelectOption(
                        label=trim(character["name"], 100),
                        description=f"Played by {item['user_id']}"[:100],
                        value=str(character["character_id"]),
                    )
                )

        self.add_item(
            discord.ui.TextDisplay(
                "## ⟐ Episode Cast\n"
                "Select a character to inspect their full OC profile."
            )
        )
        self.add_item(discord.ui.Separator())

        if options:
            self.character_select = discord.ui.Select(
                placeholder="Select an OC",
                options=options,
                min_values=1,
                max_values=1,
            )
            self.character_select.callback = self.select_callback
            row = discord.ui.ActionRow()
            row.add_item(self.character_select)
            self.add_item(row)
        else:
            self.character_select = None
            self.add_item(
                discord.ui.TextDisplay("*No usable OCs are recorded for this episode.*")
            )

        close = discord.ui.Button(
            label="Close",
            style=discord.ButtonStyle.secondary,
        )
        close.callback = self.close_callback
        row = discord.ui.ActionRow()
        row.add_item(close)
        self.add_item(row)

    async def allowed(self, interaction: discord.Interaction) -> bool:
        episode = get_episode(self.episode_id)
        cast = get_episode_cast(self.episode_id)
        allowed_ids = {episode["creator_id"]} | {
            item["user_id"] for item in cast
        } if episode else set()
        if episode and episode.get("narrator_id"):
            allowed_ids.add(int(episode["narrator_id"]))

        if not episode or interaction.user.id not in allowed_ids:
            await interaction.response.send_message(
                "You are not part of this episode.",
                ephemeral=True,
            )
            return False
        return True

    async def select_callback(self, interaction: discord.Interaction):
        if not await self.allowed(interaction):
            return

        character_id = int(self.character_select.values[0])
        character = get_character(character_id)
        if not character:
            await interaction.response.send_message(
                "That OC no longer exists.",
                ephemeral=True,
            )
            return

        member = interaction.guild.get_member(character["user_id"])
        if member is None:
            try:
                member = await interaction.guild.fetch_member(character["user_id"])
            except (discord.NotFound, discord.HTTPException):
                member = None

        if member is None:
            await interaction.response.send_message(
                "I could not resolve the player for that OC.",
                ephemeral=True,
            )
            return

        await interaction.response.edit_message(
            view=CharacterProfile(character, member)
        )

    async def close_callback(self, interaction: discord.Interaction):
        if not await self.allowed(interaction):
            return

        episode = get_episode(self.episode_id)
        if not episode:
            await interaction.response.edit_message(
                view=EpisodeNoticeView("This episode no longer exists."),
            )
            return

        await interaction.response.edit_message(
            view=EpisodePrepView(self.episode_id),
        )


class EpisodeNarratorRequestsView(discord.ui.LayoutView):
    def __init__(self, episode_id: int):
        super().__init__(timeout=300)
        self.episode_id = episode_id
        requests = get_episode_narrator_requests(episode_id)

        self.add_item(
            discord.ui.TextDisplay(
                "## ⟐ Narrator Requests\n"
                "Approve one member to become the episode narrator, or deny their request.\n\n"
                f"**Pending Requests:** {len(requests)}"
            )
        )
        self.add_item(discord.ui.Separator())

        options = [
            discord.SelectOption(
                label=f"Narrator Request #{index + 1}",
                description=f"From <@{request['user_id']}>"[:100],
                value=str(request["user_id"]),
            )
            for index, request in enumerate(requests[:25])
        ]
        self.request_select = discord.ui.Select(
            placeholder="Select a narrator request",
            options=options or [
                discord.SelectOption(
                    label="No pending requests",
                    value="none",
                    default=True,
                )
            ],
            min_values=1,
            max_values=1,
            disabled=not bool(options),
        )
        self.request_select.callback = self.select_callback
        select_row = discord.ui.ActionRow()
        select_row.add_item(self.request_select)
        self.add_item(select_row)

        actions = discord.ui.ActionRow()
        approve = discord.ui.Button(
            label="Approve",
            style=discord.ButtonStyle.success,
            disabled=not bool(options),
        )
        deny = discord.ui.Button(
            label="Deny",
            style=discord.ButtonStyle.danger,
            disabled=not bool(options),
        )
        close = discord.ui.Button(
            label="Close",
            style=discord.ButtonStyle.secondary,
        )
        approve.callback = self.approve_callback
        deny.callback = self.deny_callback
        close.callback = self.close_callback
        actions.add_item(approve)
        actions.add_item(deny)
        actions.add_item(close)
        self.add_item(actions)
        self.selected_user_id: int | None = None

    async def allowed_creator(self, interaction: discord.Interaction) -> bool:
        episode = get_episode(self.episode_id)
        if not episode:
            await interaction.response.send_message(
                "This episode no longer exists.",
                ephemeral=True,
            )
            return False
        if interaction.user.id != episode["creator_id"]:
            await interaction.response.send_message(
                "Only the episode creator can manage narrator requests.",
                ephemeral=True,
            )
            return False
        if episode["status"] != "planning":
            await interaction.response.send_message(
                "Narrator requests are closed once recruitment ends.",
                ephemeral=True,
            )
            return False
        return True

    async def select_callback(self, interaction: discord.Interaction):
        if not await self.allowed_creator(interaction):
            return
        value = self.request_select.values[0]
        if value == "none":
            await interaction.response.send_message(
                "There are no pending narrator requests.",
                ephemeral=True,
            )
            return
        self.selected_user_id = int(value)
        await interaction.response.edit_message(view=self)

    def selected_request(self) -> int | None:
        if self.selected_user_id is not None:
            return self.selected_user_id
        if self.request_select.values and self.request_select.values[0] != "none":
            return int(self.request_select.values[0])
        return None

    async def approve_callback(self, interaction: discord.Interaction):
        if not await self.allowed_creator(interaction):
            return

        selected = self.selected_request()
        if selected is None:
            await interaction.response.send_message(
                "Select a request first.",
                ephemeral=True,
            )
            return

        episode = get_episode(self.episode_id)
        cast_ids = {item["user_id"] for item in get_episode_cast(self.episode_id)}
        if selected in cast_ids:
            delete_episode_narrator_request(self.episode_id, selected)
            await interaction.response.edit_message(
                view=EpisodeNoticeView(
                    "That requester is already in the cast, so their narrator request was removed."
                ),
            )
            return

        old_id = episode.get("narrator_id") if episode else None
        set_episode_narrator(self.episode_id, selected)
        clear_episode_narrator_requests(self.episode_id)

        narrator_view = EpisodeNarratorView(self.episode_id)
        await narrator_view.apply_channel_access(interaction, old_id, selected)

        await interaction.response.edit_message(
            view=EpisodeNoticeView(
                f"## ⟐ NARRATOR APPROVED\n"
                f"<@{selected}> is now the narrator for **Episode #{self.episode_id}**."
            ),
        )
        await refresh_episode_lobby(interaction.client, self.episode_id)

    async def deny_callback(self, interaction: discord.Interaction):
        if not await self.allowed_creator(interaction):
            return

        selected = self.selected_request()
        if selected is None:
            await interaction.response.send_message(
                "Select a request first.",
                ephemeral=True,
            )
            return

        delete_episode_narrator_request(self.episode_id, selected)
        await interaction.response.edit_message(
            view=EpisodeNoticeView(
                f"Narrator request from <@{selected}> was denied."
            ),
        )
        await refresh_episode_lobby(interaction.client, self.episode_id)

    async def close_callback(self, interaction: discord.Interaction):
        if not await self.allowed_creator(interaction):
            return
        await interaction.response.edit_message(
            view=EpisodeNarratorView(self.episode_id)
        )


class EpisodeNarratorView(discord.ui.LayoutView):
    def __init__(self, episode_id: int):
        super().__init__(timeout=300)
        self.episode_id = episode_id
        episode = get_episode(episode_id)

        narrator_text = (
            f"<@{episode['narrator_id']}>"
            if episode and episode.get("narrator_id")
            else "None assigned"
        )

        self.add_item(
            discord.ui.TextDisplay(
                "## ⟐ Episode Narrator\n"
                "Assign one member to narrate this episode. The narrator can "
                "describe environments, NPCs, discoveries and scene transitions "
                "without taking control of player OCs.\n\n"
                f"**Current Narrator:** {narrator_text}"
            )
        )
        self.add_item(discord.ui.Separator())

        row = discord.ui.ActionRow()
        self.member_select = discord.ui.UserSelect(
            placeholder="Select narrator",
            min_values=1,
            max_values=1,
        )
        self.member_select.callback = self.select_callback
        row.add_item(self.member_select)
        self.add_item(row)

        actions = discord.ui.ActionRow()
        clear = discord.ui.Button(
            label="Disable Narrator",
            style=discord.ButtonStyle.secondary,
        )
        close = discord.ui.Button(
            label="Close",
            style=discord.ButtonStyle.secondary,
        )
        make_me = discord.ui.Button(
            label="Make Me Narrator",
            style=discord.ButtonStyle.primary,
        )
        requests = discord.ui.Button(
            label="Narrator Requests",
            style=discord.ButtonStyle.secondary,
        )
        clear.callback = self.clear_callback
        close.callback = self.close_callback
        make_me.callback = self.make_me_callback
        requests.callback = self.requests_callback
        actions.add_item(make_me)
        actions.add_item(requests)
        actions.add_item(clear)
        actions.add_item(close)
        self.add_item(actions)

    async def allowed_creator(self, interaction: discord.Interaction) -> bool:
        episode = get_episode(self.episode_id)
        if not episode:
            await interaction.response.send_message(
                "This episode no longer exists.",
                ephemeral=True,
            )
            return False
        if interaction.user.id != episode["creator_id"]:
            await interaction.response.send_message(
                "Only the episode creator can control the narrator.",
                ephemeral=True,
            )
            return False
        if episode["status"] != "planning":
            await interaction.response.send_message(
                "The narrator must be selected while the episode is recruiting.",
                ephemeral=True,
            )
            return False
        return True

    async def apply_channel_access(
        self,
        interaction: discord.Interaction,
        old_narrator_id: int | None,
        new_narrator_id: int | None,
    ):
        episode = get_episode(self.episode_id)
        if not episode or not interaction.guild:
            return

        channel_id = episode.get("prep_channel_id") or episode.get("channel_id")
        if not channel_id:
            return

        channel = interaction.guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        protected_ids = {
            episode["creator_id"],
            *(item["user_id"] for item in get_episode_cast(self.episode_id)),
        }

        if old_narrator_id and old_narrator_id not in protected_ids:
            old_member = interaction.guild.get_member(old_narrator_id)
            if old_member is not None:
                try:
                    await channel.set_permissions(
                        old_member,
                        overwrite=None,
                        reason="Remove previous episode narrator",
                    )
                except (discord.Forbidden, discord.HTTPException):
                    pass

        if new_narrator_id and new_narrator_id not in protected_ids:
            member = interaction.guild.get_member(new_narrator_id)
            if member is None:
                try:
                    member = await interaction.guild.fetch_member(new_narrator_id)
                except (discord.NotFound, discord.HTTPException):
                    member = None
            if member is not None:
                try:
                    await channel.set_permissions(
                        member,
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True,
                        attach_files=True,
                        embed_links=True,
                        reason="Grant episode narrator access",
                    )
                except (discord.Forbidden, discord.HTTPException):
                    pass

    async def make_me_callback(self, interaction: discord.Interaction):
        if not await self.allowed_creator(interaction):
            return

        episode = get_episode(self.episode_id)
        old_id = episode.get("narrator_id") if episode else None
        set_episode_narrator(self.episode_id, interaction.user.id)
        clear_episode_narrator_requests(self.episode_id)
        await self.apply_channel_access(interaction, old_id, interaction.user.id)

        await interaction.response.edit_message(
            view=EpisodeNoticeView(
                f"## ⟐ NARRATOR ASSIGNED\n"
                f"You are now the narrator for **Episode #{self.episode_id}**."
            ),
        )
        await refresh_episode_lobby(interaction.client, self.episode_id)

    async def requests_callback(self, interaction: discord.Interaction):
        if not await self.allowed_creator(interaction):
            return
        await interaction.response.edit_message(
            view=EpisodeNarratorRequestsView(self.episode_id)
        )

    async def select_callback(self, interaction: discord.Interaction):
        if not await self.allowed_creator(interaction):
            return

        selected_id = int(self.member_select.values[0])
        episode = get_episode(self.episode_id)
        cast_ids = {item["user_id"] for item in get_episode_cast(self.episode_id)}
        if selected_id in cast_ids:
            await interaction.response.send_message(
                "A narrator cannot also play an OC in the same episode.",
                ephemeral=True,
            )
            return

        old_id = episode.get("narrator_id") if episode else None
        set_episode_narrator(self.episode_id, selected_id)
        await self.apply_channel_access(interaction, old_id, selected_id)

        member = interaction.guild.get_member(selected_id)
        label = member.mention if member else f"<@{selected_id}>"
        await interaction.response.edit_message(
            view=EpisodeNoticeView(
                f"## ⟐ NARRATOR ASSIGNED\n"
                f"{label} is now the narrator for **Episode #{self.episode_id}**."
            ),
        )

    async def clear_callback(self, interaction: discord.Interaction):
        if not await self.allowed_creator(interaction):
            return

        episode = get_episode(self.episode_id)
        old_id = episode.get("narrator_id") if episode else None
        set_episode_narrator(self.episode_id, None)
        await self.apply_channel_access(interaction, old_id, None)

        await interaction.response.edit_message(
            view=EpisodeNoticeView(
                f"Narrator mode is disabled for **Episode #{self.episode_id}**."
            ),
        )

    async def close_callback(self, interaction: discord.Interaction):
        if not await self.allowed_creator(interaction):
            return

        episode = get_episode(self.episode_id)
        if not episode:
            await interaction.response.edit_message(
                view=EpisodeNoticeView("This episode no longer exists."),
            )
            return

        await interaction.response.edit_message(
            view=(
                EpisodeLobbyView(self.episode_id)
                if episode["status"] == "planning"
                else EpisodePrepView(self.episode_id)
            )
        )


class EpisodePrepView(discord.ui.LayoutView):
    def __init__(self, episode_id: int):
        super().__init__(timeout=None)
        self.episode_id = episode_id

        episode = get_episode(episode_id)
        remaining = (
            get_episode_preparation_remaining(episode_id)
            if episode and episode["status"] == "preparing"
            else 0
        )

        if episode:
            if episode["status"] == "preparing":
                panel_text = episode_prep_text(
                    episode,
                    get_episode_cast(episode_id),
                    remaining,
                )
            elif episode["status"] == "active":
                panel_text = (
                    f"## ⟐ EPISODE {episode_id} — LIVE\n"
                    f"**{episode['title']}**\n\n"
                    f"{trim(episode.get('premise') or 'No premise provided.', 1200)}\n\n"
                    "*The episode is live. Stay in character and use your selected OCs.*"
                )
            else:
                panel_text = (
                    f"## ⟐ EPISODE {episode_id} — {episode_status_label(episode['status'])}\n"
                    f"**{episode['title']}**"
                )
            self.add_item(discord.ui.TextDisplay(panel_text))
            self.add_item(discord.ui.Separator())

        begin = discord.ui.Button(
            label="Begin RP",
            custom_id=f"episode:{self.episode_id}:begin",
            style=discord.ButtonStyle.success,
            disabled=(
                not episode
                or episode["status"] != "preparing"
                or remaining > 0
            ),
        )
        end = discord.ui.Button(
            label="End Episode",
            custom_id=f"episode:{self.episode_id}:end",
            style=discord.ButtonStyle.danger,
        )
        cast = discord.ui.Button(
            label="View All OCs",
            custom_id=f"episode:{self.episode_id}:cast",
            style=discord.ButtonStyle.secondary,
        )
        begin.callback = self.begin_callback
        end.callback = self.end_callback
        cast.callback = self.cast_callback

        row = discord.ui.ActionRow()
        row.add_item(begin)
        row.add_item(end)
        row.add_item(cast)
        self.add_item(row)

    async def allowed_creator(self, interaction: discord.Interaction) -> bool:
        episode = get_episode(self.episode_id)
        if not episode:
            await interaction.response.send_message(
                "This episode no longer exists.",
                ephemeral=True,
            )
            return False
        if interaction.user.id != episode["creator_id"]:
            await interaction.response.send_message(
                "Only the episode creator can control this episode.",
                ephemeral=True,
            )
            return False
        return True

    async def narrator_callback(self, interaction: discord.Interaction):
        if not await self.allowed_creator(interaction):
            return
        await interaction.response.send_message(
            view=EpisodeNarratorView(self.episode_id),
            ephemeral=True,
        )

    async def begin_callback(self, interaction: discord.Interaction):
        if not await self.allowed_creator(interaction):
            return

        episode = get_episode(self.episode_id)
        if episode["status"] != "preparing":
            await interaction.response.send_message(
                "This episode is not in preparation.",
                ephemeral=True,
            )
            return

        remaining = get_episode_preparation_remaining(self.episode_id)
        if remaining > 0:
            minutes, seconds = divmod(remaining, 60)
            await interaction.response.send_message(
                f"Preparation is still locked for {minutes:02d}:{seconds:02d}.",
                ephemeral=True,
            )
            return

        # Player settings were locked when the preparation timer ended.
        # Do not re-snapshot here, so changes made afterward cannot affect this episode.

        update_episode(
            self.episode_id,
            status="active",
            channel_id=interaction.channel.id,
        )

        try:
            await interaction.channel.edit(
                name=f"episode-{self.episode_id}-rp",
                topic=f"LIVE RP — Episode #{self.episode_id} — {episode['title']}",
            )
        except discord.HTTPException:
            pass

        await interaction.response.edit_message(
            view=EpisodePrepView(self.episode_id),
        )

    async def end_callback(self, interaction: discord.Interaction):
        if not await self.allowed_creator(interaction):
            return

        episode = get_episode(self.episode_id)
        if episode["status"] not in {"preparing", "active"}:
            await interaction.response.send_message(
                "This episode is already closed.",
                ephemeral=True,
            )
            return

        cleanup_channel_id = episode.get("channel_id") or episode.get("prep_channel_id")

        update_episode(self.episode_id, status="completed")
        episode = get_episode(self.episode_id) or episode

        if cleanup_channel_id:
            interaction.client.schedule_episode_cleanup(
                self.episode_id,
                int(cleanup_channel_id),
                300,
            )

        try:
            await interaction.channel.send(
                "## ⟐ EPISODE CONCLUDED\n"
                "This episode has ended. **This channel will be deleted in 5 minutes.**\n"
                "If Archive Publishing is enabled, the episode and transcript have "
                "been preserved in the archive channel."
            )
        except discord.HTTPException:
            pass

        archive_result = None
        settings = get_roleplay_settings(interaction.guild.id)
        if settings.get("archive_enabled") and settings.get("archive_channel_id"):
            archive_channel = interaction.guild.get_channel(
                settings["archive_channel_id"]
            )
            if isinstance(archive_channel, discord.TextChannel):
                try:
                    await publish_episode_archive(archive_channel, episode)
                    archive_result = f"\n\nArchived in {archive_channel.mention}."
                except discord.HTTPException as exc:
                    print(
                        f"Episode archive failed for #{self.episode_id}: {exc}"
                    )
                    archive_result = (
                        "\n\nThe archive could not be published. "
                        "Check the archive channel permissions."
                    )
            else:
                archive_result = (
                    "\n\nThe configured archive channel could not be found."
                )

        await interaction.response.edit_message(
            view=EpisodeNoticeView(
                f"## ⟐ EPISODE {self.episode_id} — CONCLUDED\n"
                f"**{episode['title']}**\n\n"
                "The episode transcript has been preserved."
                f"{archive_result or ''}"
            ),
        )

    async def cast_callback(self, interaction: discord.Interaction):
        episode = get_episode(self.episode_id)
        cast = get_episode_cast(self.episode_id) if episode else []
        allowed_ids = {episode["creator_id"]} | {
            item["user_id"] for item in cast
        } if episode else set()

        if not episode or interaction.user.id not in allowed_ids:
            await interaction.response.send_message(
                "You are not part of this episode.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            view=EpisodeCastView(self.episode_id),
            ephemeral=True,
        )


class RPBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rp_webhook_cache: dict[int, discord.Webhook] = {}
        self.episode_prep_tasks: dict[int, asyncio.Task] = {}
        self.episode_cleanup_tasks: dict[int, asyncio.Task] = {}

    def schedule_episode_cleanup(
        self,
        episode_id: int,
        channel_id: int,
        delay_seconds: int = 300,
    ):
        task = self.episode_cleanup_tasks.get(episode_id)
        if task and not task.done():
            return

        self.episode_cleanup_tasks[episode_id] = asyncio.create_task(
            self._episode_cleanup_timer(
                episode_id,
                channel_id,
                delay_seconds,
            )
        )

    async def _episode_cleanup_timer(
        self,
        episode_id: int,
        channel_id: int,
        delay_seconds: int,
    ):
        try:
            await asyncio.sleep(max(0, delay_seconds))
            channel = self.get_channel(channel_id)
            if channel is None:
                try:
                    channel = await self.fetch_channel(channel_id)
                except (discord.NotFound, discord.HTTPException):
                    return

            if isinstance(channel, discord.TextChannel):
                try:
                    await channel.delete(
                        reason=f"Episode #{episode_id} ended; automatic 5-minute cleanup"
                    )
                except (discord.NotFound, discord.HTTPException):
                    pass
        finally:
            self.episode_cleanup_tasks.pop(episode_id, None)

    def schedule_episode_prep_timer(self, episode_id: int):
        task = self.episode_prep_tasks.get(episode_id)
        if task and not task.done():
            return
        self.episode_prep_tasks[episode_id] = asyncio.create_task(
            self._episode_prep_timer(episode_id)
        )

    async def _episode_prep_timer(self, episode_id: int):
        while True:
            episode = get_episode(episode_id)
            if not episode or episode["status"] != "preparing":
                return

            remaining = get_episode_preparation_remaining(episode_id)
            channel_id = episode.get("prep_channel_id")
            message_id = episode.get("prep_message_id")

            if channel_id and message_id:
                channel = self.get_channel(channel_id)
                if isinstance(channel, discord.TextChannel):
                    try:
                        message = await channel.fetch_message(message_id)
                        await message.edit(
                            view=EpisodePrepView(episode_id),
                        )
                    except (discord.NotFound, discord.HTTPException):
                        pass

            if remaining <= 0:
                # Prep has ended: automatically activate Personal RP and lock
                # the cast's last saved AI RP choice for this episode.
                lock_episode_player_settings(episode_id)
                return
            await asyncio.sleep(min(30, max(1, remaining)))



    async def relay_episode_narrator(
        self,
        message: discord.Message,
        episode: dict,
    ):
        channel = message.channel
        if not isinstance(channel, discord.TextChannel):
            return

        me = message.guild.me
        if me is None:
            return

        permissions = channel.permissions_for(me)
        if not permissions.manage_webhooks or not permissions.manage_messages:
            print(
                f"Cannot relay narrator message in channel {channel.id}: "
                "bot needs Manage Webhooks and Manage Messages."
            )
            return

        cache_key = -(channel.id)
        webhook = self.rp_webhook_cache.get(cache_key)

        try:
            if webhook is None:
                hooks = await channel.webhooks()
                webhook = next(
                    (hook for hook in hooks if hook.name == "Episode Narrator Relay"),
                    None,
                )
                if webhook is None:
                    webhook = await channel.create_webhook(
                        name="Episode Narrator Relay",
                        reason="Relay episode narrator messages",
                    )
                self.rp_webhook_cache[cache_key] = webhook

            payload = (message.content or "").strip()
            if message.attachments:
                links = "\n".join(item.url for item in message.attachments)
                payload = f"{payload}\n{links}".strip() if payload else links

            if not payload:
                return
            if len(payload) > 2000:
                payload = payload[:1997] + "..."

            relay_message = await webhook.send(
                content=payload,
                username="Narrator",
                allowed_mentions=discord.AllowedMentions.none(),
                wait=True,
            )
            await message.delete()

            save_episode_message(
                episode["episode_id"],
                message.guild.id,
                message.author.id,
                0,
                "Narrator",
                channel.id,
                relay_message.id,
                payload,
                "narrator",
            )
        except discord.Forbidden:
            print(
                f"Narrator relay permission failure in channel {channel.id}; "
                "original message was kept if relay could not be sent."
            )
            self.rp_webhook_cache.pop(cache_key, None)
        except discord.HTTPException as exc:
            print(f"Narrator relay failed in channel {channel.id}: {exc}")
            self.rp_webhook_cache.pop(cache_key, None)
        except Exception as exc:
            print(f"Unexpected narrator relay error in channel {channel.id}: {exc}")
            self.rp_webhook_cache.pop(cache_key, None)

    async def on_interaction(self, interaction: discord.Interaction):
        # Pride is currently restricted to Project Haven while it is in testing.
        if interaction.guild is not None and interaction.guild.id != DEV_GUILD_ID:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "Pride is currently only available in Project Haven.",
                    ephemeral=True,
                )
            return
        await super().on_interaction(interaction)

    async def on_message(self, message: discord.Message):
        # Pride is currently restricted to Project Haven while it is in testing.
        if message.guild is not None and message.guild.id != DEV_GUILD_ID:
            return

        # Only relay ordinary human messages in explicitly configured RP channels.
        if message.guild is None or message.author.bot or message.webhook_id:
            return

        if message.content.startswith("!"):
            return

        active_episode = get_active_episode(
            message.guild.id,
            message.channel.id,
        )
        settings = get_roleplay_settings(message.guild.id)
        in_saved_rp_channel = (
            settings["enabled"]
            and message.channel.id in settings["channel_ids"]
        )

        if not in_saved_rp_channel and not active_episode:
            return

        if active_episode and active_episode.get("narrator_id") == message.author.id:
            await self.relay_episode_narrator(message, active_episode)
            return

        if active_episode:
            cast = get_episode_cast(active_episode["episode_id"])
            if message.author.id not in {item["user_id"] for item in cast}:
                return

        episode_cast_entry = None
        if active_episode:
            episode_cast_entry = next(
                (
                    item
                    for item in get_episode_cast(active_episode["episode_id"])
                    if item["user_id"] == message.author.id
                ),
                None,
            )
            if episode_cast_entry is None:
                return

        if active_episode:
            roleplay_active = bool(episode_cast_entry.get("roleplay_active", 1))
            character_id = episode_cast_entry["character_id"]
            auto_rp_format = bool(episode_cast_entry.get("auto_rp_format", 0))
        else:
            roleplay_active = get_player_roleplay_active(
                message.guild.id,
                message.author.id,
            )
            character_id = get_active_character_id(
                message.guild.id,
                message.author.id,
            )
            auto_rp_format = get_player_auto_rp_format(
                message.guild.id,
                message.author.id,
            )

        if not roleplay_active:
            return

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

            # Send the relay immediately using the user's original wording.
            # AI formatting happens after the relay so Discord never appears to "hang"
            # while waiting for the model.
            original_payload = (message.content or "").strip()

            if message.attachments:
                attachment_links = "\\n".join(item.url for item in message.attachments)
                original_payload = (
                    f"{original_payload}\\n{attachment_links}"
                    if original_payload
                    else attachment_links
                ).strip()

            if not original_payload:
                return
            if len(original_payload) > 2000:
                original_payload = original_payload[:1997] + "..."

            payload = f'{character["name"]}: {message.content.strip()}'
            send_kwargs = {
                "content": payload,
                "username": character["name"][:80],
                "allowed_mentions": discord.AllowedMentions.none(),
                "wait": True,
            }
            avatar_url = character.get("avatar_url")
            if avatar_url:
                send_kwargs["avatar_url"] = avatar_url

            relay_message = await webhook.send(**send_kwargs)

            # Delete the user's message immediately after the relay is safely posted.
            await message.delete()

            if auto_rp_format:
                examples = get_rp_learning_examples(
                    message.guild.id,
                    message.author.id,
                    character["character_id"],
                    limit=8,
                )
                try:
                    payload = await asyncio.wait_for(
                        ai_format_rp_message(
                            character,
                            message.content or "",
                            examples,
                        ),
                        timeout=3.0,
                    )
                except asyncio.TimeoutError:
                    payload = f'{character["name"]}: {message.content.strip()}'

                if message.attachments:
                    attachment_links = "\\n".join(
                        item.url for item in message.attachments
                    )
                    payload = f"{payload}\\n{attachment_links}".strip()

                if len(payload) > 2000:
                    payload = payload[:1997] + "..."

                save_rp_learning_example(
                    message.guild.id,
                    message.author.id,
                    character["character_id"],
                    message.content or "",
                    payload,
                )

                try:
                    await relay_message.edit(
                        content=payload,
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                except (discord.NotFound, discord.HTTPException):
                    pass

            if active_episode:
                # Only cast members reach this point for an episode channel.
                save_episode_message(
                    active_episode["episode_id"],
                    message.guild.id,
                    message.author.id,
                    character["character_id"],
                    character["name"],
                    message.channel.id,
                    relay_message.id,
                    payload,
                )
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

        for episode in get_episodes(DEV_GUILD_ID, 25):
            if episode["status"] == "completed":
                cleanup_channel_id = episode.get("channel_id") or episode.get("prep_channel_id")
                ended_at = episode.get("ended_at")
                if cleanup_channel_id and ended_at:
                    try:
                        ended = datetime.datetime.fromisoformat(
                            ended_at.replace("Z", "+00:00")
                        )
                        if ended.tzinfo is None:
                            ended = ended.replace(tzinfo=datetime.timezone.utc)
                        age = (
                            datetime.datetime.now(datetime.timezone.utc) - ended
                        ).total_seconds()
                        self.schedule_episode_cleanup(
                            episode["episode_id"],
                            int(cleanup_channel_id),
                            max(0, int(300 - age)),
                        )
                    except (TypeError, ValueError):
                        pass
            if episode["status"] == "planning" and episode.get("lobby_message_id"):
                self.add_view(EpisodeLobbyView(episode["episode_id"]))
            if episode["status"] in {"preparing", "active"} and episode.get("prep_channel_id"):
                self.add_view(EpisodePrepView(episode["episode_id"]))
            if episode["status"] == "preparing":
                self.schedule_episode_prep_timer(episode["episode_id"])

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
        self.tree.add_command(
            episode_group,
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

episode_group = app_commands.Group(
    name="episode",
    description="Create and run collaborative RP episodes.",
)


@episode_group.command(
    name="create",
    description="Create a detailed RP episode and open its recruitment lobby.",
)
async def episode_create(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message(
            "This command can only be used inside a server.",
            ephemeral=True,
        )
        return

    await interaction.response.send_modal(EpisodeCreateModal())


@episode_group.command(
    name="dashboard",
    description="Browse the server's RP episodes.",
)
async def episode_dashboard(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message(
            "This command can only be used inside a server.",
            ephemeral=True,
        )
        return

    episodes = get_episodes(interaction.guild.id, 25)
    if not episodes:
        await interaction.response.send_message(
            "No episodes have been created yet. Use /episode create.",
            ephemeral=True,
        )
        return

    lines = []
    for item in episodes:
        cast = get_episode_cast(item["episode_id"])
        lines.append(
            f"**#{item['episode_id']} — {item['title']}** "
            f"• {episode_status_label(item['status'])} "
            f"• {len(cast)}/{item.get('max_players', 2)} players"
        )

    await interaction.response.send_message(
        "## ⟐ Episode Studio\n" + "\n".join(lines),
        ephemeral=True,
    )


@oc_group.command(
    name="dashboard",
    description="Open your OC dashboard.",
)
async def oc_dashboard(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message(
            "This command can only be used inside a server.",
            ephemeral=True,
        )
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