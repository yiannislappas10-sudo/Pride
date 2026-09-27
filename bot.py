from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import aiohttp
from aiohttp import web
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

import database

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")
PRIDE_API_KEY = os.getenv("PRIDE_API_KEY", "")
ENVY_API_URL = os.getenv("ENVY_API_URL", "").rstrip("/")
ENVY_API_KEY = os.getenv("ENVY_API_KEY", "")

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

TITLE_REQUIREMENTS = {
    "Rising Name": 0,
    "Recognized": 50,
    "Renowned": 100,
    "Proud": 250,
    "Icon": 500,
    "Unforgettable": 1000,
}

ACHIEVEMENT_INFO = {
    "FIRST_STEP": ("First Step", "Your first recorded accomplishment."),
    "RECOGNIZED": ("Recognized", "Reach 50 reputation."),
    "RENOWNED": ("Renowned", "Reach 100 reputation."),
    "PROUD": ("Proud", "Reach 250 reputation."),
    "ICON": ("Icon", "Reach 500 reputation."),
    "UNFORGETTABLE": ("Unforgettable", "Reach 1,000 reputation."),
    "VETERAN": ("Veteran", "Record 100 events."),
    "LEGACY": ("Legacy", "Record 500 events."),
}

SOURCE_DEFAULTS = {
    "envy": {"command": 1, "daily": 5, "weekly": 10, "work": 3, "beg": 1, "level_up": 10},
    "greed": {"command": 1, "buckshot_win": 10, "buckshot_loss": 0},
    "sloth": {"command": 1, "warn": 0, "jail": 0, "mute": 0, "ban": 0},
    "wraith": {"command": 1, "rules_view": 0},
}


def rank_for(rep: int) -> str:
    for threshold, rank in (
        (1000, "Unforgettable"),
        (500, "Icon"),
        (250, "Proud"),
        (100, "Renowned"),
        (50, "Recognized"),
    ):
        if rep >= threshold:
            return rank
    return "Rising Name"


def points_for(source_bot: str, event_name: str, requested: int | None) -> int:
    if requested is not None:
        return max(-10000, min(10000, int(requested)))
    source = SOURCE_DEFAULTS.get(source_bot.lower(), {})
    if event_name.startswith("command:"):
        command = event_name.split(":", 1)[1]
        return int(source.get(command, source.get("command", 0)))
    return int(source.get(event_name, 0))


async def event_endpoint(request: web.Request) -> web.Response:
    if not PRIDE_API_KEY or request.headers.get("X-Pride-Key") != PRIDE_API_KEY:
        return web.json_response({"ok": False, "error": "unauthorized"}, status=401)

    try:
        data: dict[str, Any] = await request.json()
        guild_id = int(data["guild_id"])
        user_id = int(data["user_id"])
        source_bot = str(data["source_bot"]).lower().strip()
        event_name = str(data["event"]).strip()
        if event_name.startswith("command:"):
            minute_bucket = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
            event_id = f"command:{source_bot}:{guild_id}:{user_id}:{minute_bucket}"
        else:
            event_id = str(
                data.get("event_id")
                or f"{source_bot}:{guild_id}:{user_id}:{event_name}:{data.get('reference_id', '')}"
            )
    except (KeyError, TypeError, ValueError):
        return web.json_response({"ok": False, "error": "invalid payload"}, status=400)

    points = points_for(source_bot, event_name, data.get("points"))
    user, created = await database.record_event(
        event_id,
        guild_id,
        user_id,
        source_bot,
        event_name,
        points,
        data.get("metadata") if isinstance(data.get("metadata"), dict) else {},
    )

    print(
        f"[PRIDE] Event received: source={source_bot} event={event_name} "
        f"guild={guild_id} user={user_id} points={points} created={created} "
        f"reputation={user['reputation']}"
    )

    return web.json_response({
        "ok": True,
        "created": created,
        "reputation": user["reputation"],
        "event_count": user["event_count"],
        "newly_unlocked": user.get("newly_unlocked", []),
    })


async def profile_endpoint(request: web.Request) -> web.Response:
    try:
        guild_id = int(request.match_info["guild_id"])
        user_id = int(request.match_info["user_id"])
    except ValueError:
        return web.json_response({"ok": False, "error": "invalid ids"}, status=400)

    user = await database.get_user(guild_id, user_id)
    return web.json_response({
        "ok": True,
        "profile": {
            **user,
            "rank": rank_for(user["reputation"]),
            "achievement_count": len(user["achievements"]),
        },
    })


async def health_endpoint(_: web.Request) -> web.Response:
    return web.json_response({"ok": True, "service": "pride"})


def embed(title: str, description: str, color: int = 0x8A2BE2) -> discord.Embed:
    return discord.Embed(title=title, description=description, color=color)


async def get_target_profile(interaction: discord.Interaction, member: discord.Member | None):
    target = member or interaction.user
    return target, await database.get_user(interaction.guild_id, target.id)


class CombinedProfileView(discord.ui.LayoutView):
    def __init__(self, owner_id: int, guild_id: int, target: discord.Member, envy: dict, pride: dict):
        super().__init__(timeout=300)
        self.owner_id = owner_id
        self.guild_id = guild_id
        self.target = target
        self.envy = envy
        self.pride = pride
        self.section = "overview"
        self.build()

    def _box(self, *children: discord.ui.Item):
        return discord.ui.Container(*children, accent_color=0x000000)

    def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            return False
        return True

    def build(self):
        self.clear_items()
        envy = self.envy
        pride = self.pride
        achievements = envy.get("achievements") or []
        pride_achievements = pride.get("achievements") or []
        businesses = envy.get("businesses") or []
        holdings = envy.get("market_holdings") or []
        court = envy.get("court_record") or {}
        shop = envy.get("shop")
        body = (
            f"# {self.target.display_name.upper()} — PROFILE\n\n"
            f"**Wallet**\n{int(envy.get('wallet', 0)):,}\n\n"
            f"**Bank**\n{int(envy.get('bank', 0)):,}\n\n"
            f"**Net Worth**\n{int(envy.get('net_worth', 0)):,}\n\n"
            f"**Level**\n{int(envy.get('level', 0))}\n\n"
            f"**Achievements**\n{len(achievements) + len(pride_achievements)} unlocked\n\n"
            f"**Businesses**\n{len(businesses)} active\n\n"
            f"**Shop**\n{shop.get('name') if shop else 'No player shop'}\n\n"
            f"**Market Holdings**\n{len(holdings)} position(s)\n\n"
            f"**Court Record**\n{int(court.get('total', 0) or 0)} case(s)\n\n"
            f"**Pride**\n{pride.get('rank', 'Rising Name')} · {int(pride.get('reputation', 0))} reputation"
        )
        if self.section == "achievements":
            body = (
                "# ACHIEVEMENTS\n\n"
                + ("\n".join(achievements) if achievements else "No Envy achievements.")
                + "\n\n**Pride achievements**\n"
                + (", ".join(pride_achievements) if pride_achievements else "None")
            )
        elif self.section == "businesses":
            body = "# BUSINESSES\n\n" + (
                "\n".join(
                    f"**#{b['business_id']}** {b['business_type'].title()} · Level {b['level']} · {int(b['investment']):,}"
                    for b in businesses
                ) if businesses else "No businesses."
            )
        elif self.section == "shop":
            body = "# SHOP\n\n" + (
                f"**{shop['name']}**\n{shop.get('description') or 'Player storefront.'}"
                if shop else "No player shop."
            )
        elif self.section == "holdings":
            body = "# MARKET HOLDINGS\n\n" + (
                "\n".join(
                    f"**{h['symbol']}** · {int(h['quantity']):,} units · {int(h['value']):,}"
                    for h in holdings
                ) if holdings else "No market holdings."
            )
        elif self.section == "court":
            body = (
                "# COURT RECORD\n\n"
                f"**Total:** {int(court.get('total', 0) or 0)}\n"
                f"**As lawyer:** {int(court.get('plaintiff_cases', 0) or 0)}\n"
                f"**As defendant:** {int(court.get('defendant_cases', 0) or 0)}"
            )

        def nav(label, action):
            button = discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.secondary,
                custom_id=f"pride:profile:{action}",
            )
            async def callback(interaction: discord.Interaction):
                if action == "close":
                    self.stop()
                    await interaction.response.edit_message(content=None, view=None)
                    return
                self.section = action
                if action == "refresh":
                    fresh = await fetch_envy_profile(self.guild_id, self.target.id)
                    self.envy = fresh or self.envy
                    self.section = "overview"
                self.build()
                await interaction.response.edit_message(content=None, embeds=[], view=self)
            button.callback = callback
            return button

        self.add_item(
            self._box(
                discord.ui.TextDisplay(body),
                discord.ui.Separator(visible=True),
                discord.ui.ActionRow(
                    nav("Overview", "overview"),
                    nav("Achievements", "achievements"),
                    nav("Businesses", "businesses"),
                    nav("Shop", "shop"),
                ),
                discord.ui.ActionRow(
                    nav("Market Holdings", "holdings"),
                    nav("Court Record", "court"),
                    nav("Refresh", "refresh"),
                    nav("Close", "close"),
                ),
            )
        )


async def fetch_envy_profile(guild_id: int, user_id: int) -> dict:
    if not ENVY_API_URL or not ENVY_API_KEY:
        return {}
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                f"{ENVY_API_URL}/v1/profile/{guild_id}/{user_id}",
                headers={"Authorization": f"Bearer {ENVY_API_KEY}"},
            ) as response:
                if response.status != 200:
                    return {}
                payload = await response.json()
                return payload.get("profile", {}) if payload.get("ok") else {}
    except (aiohttp.ClientError, TimeoutError):
        return {}


@bot.tree.command(name="pride", description="View a Pride profile.")
@app_commands.describe(member="The member to inspect.")
async def pride(interaction: discord.Interaction, member: discord.Member | None = None):
    target, profile = await get_target_profile(interaction, member)
    names = [ACHIEVEMENT_INFO.get(key, (key, ""))[0] for key in profile["achievements"]]
    equipped = profile["title"] or rank_for(profile["reputation"])
    description = (
        f"**Title:** {equipped}\n"
        f"**Rank:** {rank_for(profile['reputation'])}\n"
        f"**Reputation:** {profile['reputation']}\n"
        f"**Events:** {profile['event_count']}\n"
        f"**Achievements:** {len(profile['achievements'])}\n\n"
        f"**Unlocked:** {', '.join(names) if names else 'None yet'}"
    )
    await interaction.response.send_message(
        embed=embed(f"{target.display_name}'s Pride", description)
    )


@bot.tree.command(name="profile", description="View a combined Envy + Pride profile.")
@app_commands.describe(member="The member to inspect.")
async def profile(interaction: discord.Interaction, member: discord.Member | None = None):
    target = member or interaction.user
    pride_profile = await database.get_user(interaction.guild_id, target.id)
    envy_profile = await fetch_envy_profile(interaction.guild_id, target.id)
    if not envy_profile:
        await interaction.response.send_message(
            "Envy profile data is currently unavailable. Check ENVY_API_URL and ENVY_API_KEY.",
            ephemeral=True,
        )
        return
    view = CombinedProfileView(interaction.user.id, interaction.guild_id, target, envy_profile, pride_profile)
    await interaction.response.send_message(view=view)


@bot.tree.command(name="reputation", description="View a member's reputation.")
@app_commands.describe(member="The member to inspect.")
async def reputation(interaction: discord.Interaction, member: discord.Member | None = None):
    target, profile = await get_target_profile(interaction, member)
    await interaction.response.send_message(
        f"{target.mention} has **{profile['reputation']} reputation** and holds the rank **{rank_for(profile['reputation'])}**."
    )


@bot.tree.command(name="achievements", description="View earned Pride achievements.")
@app_commands.describe(member="The member to inspect.")
async def achievements(interaction: discord.Interaction, member: discord.Member | None = None):
    target, profile = await get_target_profile(interaction, member)
    lines = []
    for key, (name, desc) in ACHIEVEMENT_INFO.items():
        state = "UNLOCKED" if key in profile["achievements"] else "LOCKED"
        lines.append(f"**{name}** — {state}\n{desc}")
    await interaction.response.send_message(
        embed=embed(f"{target.display_name}'s Achievements", "\n\n".join(lines))
    )


@bot.tree.command(name="titles", description="View Pride titles and their requirements.")
async def titles(interaction: discord.Interaction):
    profile = await database.get_user(interaction.guild_id, interaction.user.id)
    lines = []
    for title_name, requirement in TITLE_REQUIREMENTS.items():
        state = "UNLOCKED" if profile["reputation"] >= requirement else f"{requirement} reputation needed"
        equipped = " [EQUIPPED]" if profile["title"] == title_name else ""
        lines.append(f"**{title_name}** — {state}{equipped}")
    await interaction.response.send_message(embed=embed("Pride Titles", "\n".join(lines)))


@bot.tree.command(name="title", description="Equip an unlocked Pride title.")
@app_commands.describe(title_name="Exact title to equip.")
async def title(interaction: discord.Interaction, title_name: str):
    profile = await database.get_user(interaction.guild_id, interaction.user.id)
    requirement = TITLE_REQUIREMENTS.get(title_name)
    if requirement is None:
        await interaction.response.send_message("That title does not exist.", ephemeral=True)
        return
    if profile["reputation"] < requirement:
        await interaction.response.send_message(
            f"You need **{requirement} reputation** to equip **{title_name}**.",
            ephemeral=True,
        )
        return
    await database.set_title(interaction.guild_id, interaction.user.id, title_name)
    await interaction.response.send_message(f"Your Pride title is now **{title_name}**.")


@bot.tree.command(name="leaderboard", description="View the Pride reputation leaderboard.")
async def leaderboard(interaction: discord.Interaction):
    rows = await database.leaderboard(interaction.guild_id)
    lines = [
        f"**{index}.** <@{row['user_id']}> — **{row['reputation']}** rep — {rank_for(row['reputation'])}"
        for index, row in enumerate(rows, 1)
    ]
    await interaction.response.send_message(
        embed=embed("PRIDE LEADERBOARD", "\n".join(lines) or "No reputation has been recorded yet.")
    )


@bot.tree.command(name="hall", description="View the Hall of Pride.")
async def hall(interaction: discord.Interaction):
    rows = await database.leaderboard(interaction.guild_id, 5)
    lines = []
    for index, row in enumerate(rows, 1):
        shown_title = row["title"] or rank_for(row["reputation"])
        lines.append(f"**{index}.** <@{row['user_id']}> — **{shown_title}** — {row['reputation']} rep")
    await interaction.response.send_message(
        embed=embed("HALL OF PRIDE", "\n".join(lines) or "The Hall of Pride is empty.")
    )


@bot.tree.command(name="pride-award", description="Award Pride reputation to a member.")
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.describe(member="Member to award.", points="Reputation to add.", reason="Reason for the award.")
async def pride_award(
    interaction: discord.Interaction,
    member: discord.Member,
    points: app_commands.Range[int, 1, 10000],
    reason: str,
):
    user, _ = await database.adjust_reputation(
        interaction.guild_id, member.id, int(points), "pride", reason
    )
    await interaction.response.send_message(
        f"Awarded **{points} reputation** to {member.mention}. They now have **{user['reputation']}** rep."
    )


@bot.tree.command(name="pride-revoke", description="Remove Pride reputation from a member.")
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.describe(member="Member to affect.", points="Reputation to remove.", reason="Reason for removal.")
async def pride_revoke(
    interaction: discord.Interaction,
    member: discord.Member,
    points: app_commands.Range[int, 1, 10000],
    reason: str,
):
    user, _ = await database.adjust_reputation(
        interaction.guild_id, member.id, -int(points), "pride", reason
    )
    await interaction.response.send_message(
        f"Removed **{points} reputation** from {member.mention}. They now have **{user['reputation']}** rep."
    )


@bot.event
async def setup_hook():
    await database.init_db()
    if ENVY_API_URL and ENVY_API_KEY:
        print(f"[ENVY] Combined profile integration configured: {ENVY_API_URL}/v1/profile")
    else:
        print("[ENVY] Combined profile integration not configured.")

    if GUILD_ID:
        try:
            guild_id = int(GUILD_ID)
        except (TypeError, ValueError):
            print("Pride: GUILD_ID is not a valid Discord server ID. Skipping guild command sync.")
        else:
            guild = discord.Object(id=guild_id)
            bot.tree.copy_global_to(guild=guild)
            try:
                await bot.fetch_guild(guild_id)
                synced = await bot.tree.sync(guild=guild)
                print(f"Pride: synced {len(synced)} guild command(s) to GUILD_ID={guild_id}.")
            except discord.Forbidden:
                print(
                    f"Pride: cannot access GUILD_ID={guild_id} (Discord 403 Missing Access). "
                    "Check that this bot is installed in that server and that GUILD_ID matches the server."
                )
            except discord.NotFound:
                print(
                    f"Pride: GUILD_ID={guild_id} was not found. "
                    "Check the server ID configured in Railway."
                )
    else:
        synced = await bot.tree.sync()
        print(f"Pride: synced {len(synced)} global command(s).")

    app = web.Application()
    app.router.add_get("/health", health_endpoint)
    app.router.add_post("/event", event_endpoint)
    app.router.add_get("/profile/{guild_id}/{user_id}", profile_endpoint)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", "8080")))
    await site.start()
    bot._pride_http_runner = runner
    print("Pride API is listening.")


@bot.event
async def on_ready():
    guild_ids = [guild.id for guild in bot.guilds]
    print(f"Logged in as {bot.user} - Pride is online.")
    print(f"Pride can currently see {len(guild_ids)} server(s).")
    if GUILD_ID:
        try:
            configured_guild_id = int(GUILD_ID)
            if configured_guild_id in guild_ids:
                print(f"Pride: configured GUILD_ID={configured_guild_id} is accessible.")
            else:
                print(
                    f"Pride: configured GUILD_ID={configured_guild_id} is NOT in the bot's visible server list."
                )
        except (TypeError, ValueError):
            pass


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        message = "You need Manage Server permission to use that command."
    else:
        print(f"Application command error: {error!r}")
        message = "Something went wrong while running that command."

    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN is not set.")
    if not PRIDE_API_KEY:
        raise RuntimeError("PRIDE_API_KEY is not set.")
    bot.run(TOKEN)
