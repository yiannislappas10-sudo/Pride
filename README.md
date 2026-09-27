# Pride

Pride is the shared reputation, achievement, title, and recognition bot for the seven-sin Discord system.

Features:
- /pride
- /reputation
- /achievements
- /titles
- /title
- /leaderboard
- /hall
- /pride-award
- /pride-revoke
- Authenticated POST /event API
- Profile API
- Persistent SQLite storage
- Cross-bot event system for Envy, Greed, Sloth, Wraith, and future sins

Every connected bot uses PRIDE_API_URL and PRIDE_API_KEY. Pride remains the source of truth for reputation values and achievements.

Combined profile integration:
- Set ENVY_API_URL to Envy's Railway public URL.
- Set ENVY_API_KEY to the same value as Envy's ENVY_API_KEY.
- /profile on Pride reads Envy wallet, bank, net worth, level, achievements, businesses, shop, market holdings, and court record, then adds Pride reputation and achievements.
