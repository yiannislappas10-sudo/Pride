# RP Bot Prototype

Pride has been replaced by the first prototype of the new roleplay bot.

## Current prototype

- Persistent original-character creation
- OC dashboard with buttons
- Core character details
- Appearance, personality and backstory
- Custom OC avatar URL
- Public OC viewing
- SQLite persistence for Railway volumes
- Clean Compound-style Discord UI

## Commands

- `/oc dashboard` — open your OC dashboard
- `/oc view [member]` — view a character

## Not implemented yet

The RP activation/identity replacement system is intentionally next. Once designed, RP mode can use the OC name and avatar for RP messages through the appropriate Discord mechanism.

## Environment

- `DISCORD_TOKEN`
- `DATABASE_PATH` (recommended: `/data/rp.db` on a Railway volume)
