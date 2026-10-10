import random
import discord

from database import (
    create_narrator_template,
    get_narrator_templates,
    get_narrator_template,
    get_episode,
    get_episode_cast,
    get_character,
    save_episode_message,
)

PRESETS = {
    "Scary": ("SCARY", "none", "The atmosphere suddenly changes. Something feels very wrong."),
    "Happy": ("HAPPY", "none", "For the first time in a while, everything feels peaceful."),
    "Warning": ("WARNING", "system", "Something has changed. Everyone should stay alert."),
    "Mystery": ("MYSTERY", "whisper", "A strange silence falls over the area."),
    "Emergency": ("EMERGENCY", "system", "An emergency has changed the situation."),
    "Reveal": ("REVEAL", "none", "The truth is finally revealed."),
    "Suspense": ("SUSPENSE", "static", "The room goes quiet. Then... something moves."),
    "System Error": ("SYSTEM ERROR", "glitch", "SYSTEM ERROR // SCENE DATA CORRUPTED"),
}


def effect_text(text, effect):
    text = (text or "").strip()[:1900]
    if effect == "glitch":
        return "".join(
            ch + (random.choice(["̷", "̸", "̶"]) if ch.isalnum() and random.random() < .2 else "")
            for ch in text
        )
    if effect == "static":
        return "// STATIC // " + text + " // STATIC //"
    if effect == "whisper":
        return "*" + text.lower() + "*"
    if effect == "redacted":
        return " ".join(
            "[REDACTED]" if i % 3 == 1 else word
            for i, word in enumerate(text.split())
        )
    if effect == "system":
        return "[ SYSTEM ] " + text
    if effect == "corrupt":
        return "CORRUPTED // " + text
    return text


def _resolve_speaker(episode, user_id):
    if int(episode.get("narrator_id") or 0) == int(user_id):
        return {
            "user_id": int(user_id),
            "character_id": 0,
            "name": "Narrator",
            "avatar_url": None,
            "message_type": "narrator",
        }

    for entry in get_episode_cast(episode["episode_id"]):
        if int(entry["user_id"]) != int(user_id):
            continue
        character = get_character(entry["character_id"])
        if not character or int(character.get("user_id") or 0) != int(user_id):
            return None
        return {
            "user_id": int(user_id),
            "character_id": int(character["character_id"]),
            "name": character["name"],
            "avatar_url": character.get("avatar_url"),
            "message_type": "character",
        }
    return None


async def publish(interaction, episode, content, effect="none", title=None):
    """Send a template as the speaker's OC or Narrator, without a public banner."""
    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel):
        return False

    speaker = _resolve_speaker(episode, interaction.user.id)
    if not speaker:
        return False

    payload = effect_text(content, effect).strip()
    if not payload:
        return False
    payload = payload[:2000]

    narrator = speaker["message_type"] == "narrator"
    cache_key = -channel.id if narrator else channel.id
    hook_name = "Episode Narrator Relay" if narrator else "OC Roleplay Relay"
    cache = getattr(interaction.client, "rp_webhook_cache", {})
    webhook = cache.get(cache_key)

    try:
        if webhook is None:
            hooks = await channel.webhooks()
            webhook = next((hook for hook in hooks if hook.name == hook_name), None)
            if webhook is None:
                webhook = await channel.create_webhook(
                    name=hook_name,
                    reason="Relay roleplay templates as the speaking OC or narrator",
                )
            cache[cache_key] = webhook

        kwargs = {
            "content": payload,
            "username": speaker["name"][:80],
            "allowed_mentions": discord.AllowedMentions.none(),
            "wait": True,
        }
        if speaker.get("avatar_url"):
            kwargs["avatar_url"] = speaker["avatar_url"]
        sent = await webhook.send(**kwargs)
    except (discord.Forbidden, discord.HTTPException) as exc:
        cache.pop(cache_key, None)
        print(f"Template relay failed for episode #{episode['episode_id']}: {exc}")
        return False

    save_episode_message(
        episode["episode_id"],
        interaction.guild.id,
        speaker["user_id"],
        speaker["character_id"],
        speaker["name"],
        channel.id,
        sent.id,
        payload,
        speaker["message_type"],
    )
    if hasattr(interaction.client, "record_episode_activity"):
        await interaction.client.record_episode_activity(episode["episode_id"], channel)
    return True


async def _authorize(interaction, episode_id, owner_id, allow_paused=False):
    episode = get_episode(episode_id)
    if not episode:
        await interaction.response.send_message(
            "This episode no longer exists.",
            ephemeral=True,
        )
        return None

    if owner_id is not None and interaction.user.id != owner_id:
        await interaction.response.send_message(
            "This template panel belongs to someone else.",
            ephemeral=True,
        )
        return None

    allowed_statuses = {"active", "paused"} if allow_paused else {"active"}
    if episode.get("status") not in allowed_statuses:
        await interaction.response.send_message(
            "Templates can only be published while the episode is live. Resume it first if it is paused.",
            ephemeral=True,
        )
        return None

    if not _resolve_speaker(episode, interaction.user.id):
        await interaction.response.send_message(
            "Only the episode's cast and assigned narrator can use chat templates.",
            ephemeral=True,
        )
        return None
    return episode


class MessageModal(discord.ui.Modal):
    def __init__(self, episode_id, title, effect="none", owner_id=None):
        super().__init__(title=title[:45], timeout=600)
        self.episode_id = episode_id
        self.effect = effect
        self.owner_id = owner_id
        self.message = discord.ui.TextInput(
            label="Message",
            style=discord.TextStyle.paragraph,
            max_length=1800,
            required=True,
        )
        self.add_item(self.message)

    async def on_submit(self, interaction):
        episode = await _authorize(interaction, self.episode_id, self.owner_id)
        if not episode:
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        success = await publish(interaction, episode, self.message.value, self.effect)
        await interaction.followup.send(
            "Message sent in the episode chat."
            if success else
            "I couldn't publish the message. Check my Manage Webhooks permission.",
            ephemeral=True,
        )


class TemplateModal(discord.ui.Modal, title="Create Chat Template"):
    def __init__(self, episode_id, owner_id):
        super().__init__(timeout=600)
        self.episode_id = episode_id
        self.owner_id = owner_id
        self.name = discord.ui.TextInput(label="Template Name", max_length=80, required=True)
        self.message = discord.ui.TextInput(
            label="Template Message",
            style=discord.TextStyle.paragraph,
            max_length=1800,
            required=True,
        )
        self.add_item(self.name)
        self.add_item(self.message)

    async def on_submit(self, interaction):
        episode = await _authorize(interaction, self.episode_id, self.owner_id)
        if not episode:
            return

        create_narrator_template(
            interaction.guild.id,
            interaction.user.id,
            self.name.value,
            "custom",
            "none",
            self.message.value,
        )
        await interaction.response.send_message(
            "Template saved to your personal template list.",
            ephemeral=True,
        )


class ToolsView(discord.ui.LayoutView):
    control_view = None
    episode_view = None

    def __init__(self, episode_id, mode, owner_id=None, return_to="episode"):
        super().__init__(timeout=900)
        self.episode_id = episode_id
        self.mode = mode
        episode = get_episode(episode_id)
        self.owner_id = owner_id or (episode.get("narrator_id") if episode else None)
        self.return_to = return_to

        title = "CHAT TEMPLATES" if mode == "templates" else "CHAT EFFECTS"
        description = (
            "Send a preset or saved message as your OC or Narrator. "
            "Template labels stay in this private panel instead of becoming public announcements."
            if mode == "templates"
            else "Transform a message and send it as your OC or Narrator."
        )
        self.add_item(discord.ui.TextDisplay(f"## ⟐ {title}\n*{description}*"))
        self.add_item(discord.ui.Separator())

        if mode == "templates":
            self.add_template_buttons()
        else:
            self.add_effect_buttons()

        row = discord.ui.ActionRow()
        back = discord.ui.Button(label="Back", style=discord.ButtonStyle.secondary)
        back.callback = self.back
        row.add_item(back)
        self.add_item(row)

    def add_template_buttons(self):
        for labels in (
            ("Scary", "Happy", "Warning", "Mystery"),
            ("Emergency", "Reveal", "Suspense", "System Error"),
        ):
            row = discord.ui.ActionRow()
            for label in labels:
                button = discord.ui.Button(label=label, style=discord.ButtonStyle.secondary)
                button.callback = self.preset(label)
                row.add_item(button)
            self.add_item(row)

        row = discord.ui.ActionRow()
        custom = discord.ui.Button(
            label="Create Custom Template",
            style=discord.ButtonStyle.primary,
        )
        custom.callback = self.custom
        row.add_item(custom)
        self.add_item(row)

        episode = get_episode(self.episode_id)
        saved = (
            get_narrator_templates(episode["guild_id"], self.owner_id)
            if episode and self.owner_id
            else []
        )
        if saved:
            options = [
                discord.SelectOption(
                    label=(item.get("name") or "Saved Template")[:100],
                    description=(item.get("content") or "Saved message")[:100],
                    value=str(item["template_id"]),
                )
                for item in saved[:25]
            ]
            self.saved_select = discord.ui.Select(
                placeholder="Use one of your saved templates",
                options=options,
                min_values=1,
                max_values=1,
            )
            self.saved_select.callback = self.select_saved_template
            row = discord.ui.ActionRow()
            row.add_item(self.saved_select)
            self.add_item(row)

    def add_effect_buttons(self):
        row = discord.ui.ActionRow()
        for label, effect in (
            ("Glitch", "glitch"),
            ("Corrupted", "corrupt"),
            ("Static", "static"),
            ("Whisper", "whisper"),
        ):
            button = discord.ui.Button(label=label, style=discord.ButtonStyle.secondary)
            button.callback = self.effect(effect, label)
            row.add_item(button)
        self.add_item(row)

        row = discord.ui.ActionRow()
        for label, effect in (("Redacted", "redacted"), ("System", "system")):
            button = discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.primary if effect == "system" else discord.ButtonStyle.secondary,
            )
            button.callback = self.effect(effect, label)
            row.add_item(button)
        self.add_item(row)

    async def allowed(self, interaction):
        return await _authorize(interaction, self.episode_id, self.owner_id)

    def preset(self, label):
        async def callback(interaction):
            episode = await self.allowed(interaction)
            if not episode:
                return

            _, effect, content = PRESETS[label]
            await interaction.response.defer(ephemeral=True, thinking=True)
            success = await publish(interaction, episode, content, effect)
            await interaction.followup.send(
                "Template sent in the episode chat."
                if success else
                "I couldn't publish the template. Check my Manage Webhooks permission.",
                ephemeral=True,
            )
        return callback

    async def select_saved_template(self, interaction):
        episode = await self.allowed(interaction)
        if not episode:
            return

        try:
            template_id = int(self.saved_select.values[0])
        except (ValueError, IndexError, AttributeError):
            await interaction.response.send_message(
                "Choose a saved template first.",
                ephemeral=True,
            )
            return

        template = get_narrator_template(template_id)
        if (
            not template
            or template.get("owner_id") != interaction.user.id
            or template.get("guild_id") != interaction.guild.id
        ):
            await interaction.response.send_message(
                "That saved template is unavailable.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        success = await publish(interaction, episode, template["content"])
        await interaction.followup.send(
            f"**{template['name']}** sent in the episode chat."
            if success else
            "I couldn't publish the template. Check my Manage Webhooks permission.",
            ephemeral=True,
        )

    async def custom(self, interaction):
        if await self.allowed(interaction):
            await interaction.response.send_modal(
                TemplateModal(self.episode_id, self.owner_id)
            )

    def effect(self, effect, label):
        async def callback(interaction):
            if await self.allowed(interaction):
                await interaction.response.send_modal(
                    MessageModal(
                        self.episode_id,
                        label + " Effect",
                        effect,
                        self.owner_id,
                    )
                )
        return callback

    async def back(self, interaction):
        episode = await _authorize(
            interaction,
            self.episode_id,
            self.owner_id,
            allow_paused=True,
        )
        if not episode:
            return

        if self.return_to == "narrator" and self.control_view:
            await interaction.response.edit_message(view=self.control_view(self.episode_id))
        elif self.episode_view:
            await interaction.response.edit_message(view=self.episode_view(self.episode_id))
        else:
            await interaction.response.edit_message(
                content="Template panel closed.",
                view=None,
            )


def install_narrator_tools(control_view):
    if getattr(control_view, "_tools_installed", False):
        return

    ToolsView.control_view = control_view
    original = control_view.__init__

    def wrapped(self, episode_id):
        original(self, episode_id)
        row = discord.ui.ActionRow()
        templates = discord.ui.Button(
            label="Templates",
            style=discord.ButtonStyle.primary,
        )
        effects = discord.ui.Button(
            label="Effects",
            style=discord.ButtonStyle.secondary,
        )

        async def open_templates(interaction):
            episode = get_episode(episode_id)
            if episode and episode.get("narrator_id") == interaction.user.id:
                await interaction.response.edit_message(
                    view=ToolsView(
                        episode_id,
                        "templates",
                        owner_id=interaction.user.id,
                        return_to="narrator",
                    )
                )
            else:
                await interaction.response.send_message(
                    "Only the assigned narrator can use this dashboard.",
                    ephemeral=True,
                )

        async def open_effects(interaction):
            episode = get_episode(episode_id)
            if episode and episode.get("narrator_id") == interaction.user.id:
                await interaction.response.edit_message(
                    view=ToolsView(
                        episode_id,
                        "effects",
                        owner_id=interaction.user.id,
                        return_to="narrator",
                    )
                )
            else:
                await interaction.response.send_message(
                    "Only the assigned narrator can use this dashboard.",
                    ephemeral=True,
                )

        templates.callback = open_templates
        effects.callback = open_effects
        row.add_item(templates)
        row.add_item(effects)
        self.add_item(row)

    control_view.__init__ = wrapped
    control_view._tools_installed = True
