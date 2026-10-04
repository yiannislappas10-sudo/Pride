# Pride RP Bot

Pride has been replaced by the first prototype of the new roleplay bot.

## Current system

- Persistent original-character creation
- OC dashboard and personal RP settings
- Local zero-cost RP dialogue/action formatting
- Detailed episode creation wizard
- Episode recruitment lobby with configurable 1–25 player cap
- Players join using a selected OC
- Start button unlocks only when the cast is full
- Private episode preparation tickets visible only to the creator and selected cast
- Begin RP turns the preparation ticket into the live RP channel
- Episode cast and transcript persistence
- Compound-style Discord UI

## Commands

- `/oc dashboard` — manage OCs
- `/oc view [member]` — view an OC
- `/oc settings` — personal RP controls
- `/oc admin` — server-wide RP controls
- `/episode create` — create a detailed episode and post its recruitment lobby
- `/episode dashboard` — view episode status

## Environment

- `DISCORD_TOKEN`
- `DATABASE_PATH` (recommended: `/data/rp.db` on a Railway volume)
