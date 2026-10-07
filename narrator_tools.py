import random
import discord

from database import create_narrator_template, get_narrator_templates, get_episode, save_episode_message

PRESETS = {
    "Scary": ("SCARY", "none", "The atmosphere suddenly changes. Something feels very wrong."),
    "Happy": ("HAPPY", "none", "For the first time in a while, everything feels peaceful."),
    "Warning": ("WARNING", "system", "WARNING — Something has changed."),
    "Mystery": ("MYSTERY", "whisper", "A strange silence falls over the area."),
    "Emergency": ("EMERGENCY", "system", "EMERGENCY — Everyone needs to stay alert."),
    "Reveal": ("REVEAL", "none", "The truth is finally revealed."),
    "Suspense": ("SUSPENSE", "static", "The room goes quiet. Then... something moves."),
    "System Error": ("SYSTEM ERROR", "glitch", "SYSTEM ERROR // SCENE DATA CORRUPTED"),
}

def effect_text(text, effect):
    text = (text or "").strip()[:1900]
    if effect == "glitch":
        return "".join(ch + (random.choice(["̷","̸","̶"]) if ch.isalnum() and random.random() < .2 else "") for ch in text)
    if effect == "static": return "// STATIC // " + text + " // STATIC //"
    if effect == "whisper": return "*" + text.lower() + "*"
    if effect == "redacted": return " ".join("[REDACTED]" if i % 3 == 1 else word for i, word in enumerate(text.split()))
    if effect == "system": return "[ SYSTEM ] " + text
    if effect == "corrupt": return "CORRUPTED // " + text
    return text

async def publish(interaction, episode, content, effect="none", title=None):
    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel): return
    payload = effect_text(content, effect)
    if title: payload = "## ⟐ " + title + "\n" + payload
    sent = await channel.send(payload[:2000], allowed_mentions=discord.AllowedMentions.none())
    save_episode_message(episode["episode_id"], interaction.guild.id, interaction.user.id, 0, "Narrator", channel.id, sent.id, payload[:2000], "narrator")
    if hasattr(interaction.client, "record_episode_activity"):
        await interaction.client.record_episode_activity(episode["episode_id"], channel)

class MessageModal(discord.ui.Modal):
    def __init__(self, episode_id, title, effect="none"):
        super().__init__(title=title[:45])
        self.episode_id, self.effect, self.title_text = episode_id, effect, title
        self.message = discord.ui.TextInput(label="Narrator Message", style=discord.TextStyle.paragraph, max_length=1800, required=True)
        self.add_item(self.message)
    async def on_submit(self, interaction):
        episode = get_episode(self.episode_id)
        if not episode or episode.get("narrator_id") != interaction.user.id or episode.get("status") not in {"active","paused"}:
            await interaction.response.send_message("Only the assigned narrator can use this.", ephemeral=True); return
        await publish(interaction, episode, self.message.value, self.effect, self.title_text.upper())
        await interaction.response.send_message("Published.", ephemeral=True)

class TemplateModal(discord.ui.Modal, title="Create Narrator Template"):
    def __init__(self, episode_id):
        super().__init__(timeout=600)
        self.episode_id = episode_id
        self.name = discord.ui.TextInput(label="Template Name", max_length=80, required=True)
        self.message = discord.ui.TextInput(label="Template Message", style=discord.TextStyle.paragraph, max_length=1800, required=True)
        self.add_item(self.name); self.add_item(self.message)
    async def on_submit(self, interaction):
        episode = get_episode(self.episode_id)
        if not episode or episode.get("narrator_id") != interaction.user.id or episode.get("status") not in {"active","paused"}:
            await interaction.response.send_message("Only the assigned narrator can create templates.", ephemeral=True); return
        create_narrator_template(interaction.guild.id, interaction.user.id, self.name.value, "custom", "none", self.message.value)
        await interaction.response.send_message("Template saved.", ephemeral=True)

class ToolsView(discord.ui.LayoutView):
    def __init__(self, episode_id, mode):
        super().__init__(timeout=900); self.episode_id=episode_id; self.mode=mode
        title = "NARRATOR TEMPLATES" if mode=="templates" else "NARRATOR EFFECTS"
        desc = "Instant story beats and saved messages." if mode=="templates" else "Transform the next narrator message."
        self.add_item(discord.ui.TextDisplay("## ⟐ "+title+"\n*"+desc+"*")); self.add_item(discord.ui.Separator())
        if mode=="templates": self.add_template_buttons()
        else: self.add_effect_buttons()
        row=discord.ui.ActionRow(); back=discord.ui.Button(label="Back",style=discord.ButtonStyle.secondary); back.callback=self.back; row.add_item(back); self.add_item(row)
    def add_template_buttons(self):
        for labels in (("Scary","Happy","Warning","Mystery"),("Emergency","Reveal","Suspense","System Error")):
            row=discord.ui.ActionRow()
            for label in labels:
                b=discord.ui.Button(label=label,style=discord.ButtonStyle.secondary); b.callback=self.preset(label); row.add_item(b)
            self.add_item(row)
        row=discord.ui.ActionRow(); b=discord.ui.Button(label="Create Custom Template",style=discord.ButtonStyle.primary); b.callback=self.custom; row.add_item(b); self.add_item(row)
        episode=get_episode(self.episode_id)
        if episode:
            saved=get_narrator_templates(episode["guild_id"],episode["narrator_id"])
            if saved:
                self.add_item(discord.ui.Separator()); self.add_item(discord.ui.TextDisplay("### Saved\n"+"\n".join("**"+x["name"]+"**" for x in saved[:8])))
    def add_effect_buttons(self):
        row=discord.ui.ActionRow()
        for label,effect in (("Glitch","glitch"),("Corrupted","corrupt"),("Static","static"),("Whisper","whisper")):
            b=discord.ui.Button(label=label,style=discord.ButtonStyle.secondary); b.callback=self.effect(effect,label); row.add_item(b)
        self.add_item(row)
        row=discord.ui.ActionRow()
        for label,effect in (("Redacted","redacted"),("System","system")):
            b=discord.ui.Button(label=label,style=discord.ButtonStyle.primary if effect=="system" else discord.ButtonStyle.secondary); b.callback=self.effect(effect,label); row.add_item(b)
        self.add_item(row)
    async def allowed(self, interaction):
        episode=get_episode(self.episode_id)
        if not episode or episode.get("narrator_id")!=interaction.user.id or episode.get("status") not in {"active","paused"}:
            await interaction.response.send_message("Only the assigned narrator can use this.",ephemeral=True); return None
        return episode
    def preset(self,label):
        async def cb(interaction):
            episode=await self.allowed(interaction)
            if not episode:return
            title,effect,content=PRESETS[label]; await publish(interaction,episode,content,effect,title); await interaction.response.send_message("Template published.",ephemeral=True)
        return cb
    async def custom(self,interaction):
        if await self.allowed(interaction): await interaction.response.send_modal(TemplateModal(self.episode_id))
    def effect(self,effect,label):
        async def cb(interaction):
            if await self.allowed(interaction): await interaction.response.send_modal(MessageModal(self.episode_id,label+" Narration",effect))
        return cb
    async def back(self,interaction):
        if await self.allowed(interaction): await interaction.response.edit_message(view=self.control_view(self.episode_id))
    control_view = None

def install_narrator_tools(control_view):
    if getattr(control_view,"_tools_installed",False): return
    ToolsView.control_view=control_view
    original=control_view.__init__
    def wrapped(self,episode_id):
        original(self,episode_id)
        row=discord.ui.ActionRow()
        a=discord.ui.Button(label="Templates",style=discord.ButtonStyle.primary)
        b=discord.ui.Button(label="Effects",style=discord.ButtonStyle.secondary)
        async def templates(interaction):
            episode=get_episode(episode_id)
            if episode and episode.get("narrator_id")==interaction.user.id:
                await interaction.response.edit_message(view=ToolsView(episode_id,"templates"))
            else:
                await interaction.response.send_message("Only the assigned narrator can use this.",ephemeral=True)
        async def effects(interaction):
            episode=get_episode(episode_id)
            if episode and episode.get("narrator_id")==interaction.user.id:
                await interaction.response.edit_message(view=ToolsView(episode_id,"effects"))
            else:
                await interaction.response.send_message("Only the assigned narrator can use this.",ephemeral=True)
        a.callback=templates; b.callback=effects; row.add_item(a); row.add_item(b); self.add_item(row)
    control_view.__init__=wrapped
    control_view._tools_installed=True
