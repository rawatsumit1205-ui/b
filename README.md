# BlueSMS Auto OTP Telegram Bot

Auto-fetches incoming OTPs from Blue-SMS (Simple API v2) and forwards them directly to Telegram Channels with 1-click copy buttons.

## Features
- **Format Match:** Identical to MySMSPortal format:
  `🇾🇪 YE | 🟢 9639*****968 #EN`
  `🔥 Google - 123456`
- **1-Click Copy Button:** Tap on `[🛡️ OTP]` button to copy code directly.
- **Auto Dedup:** Never sends duplicate OTPs.
- **100% Free Hosting:** Zero VPS required. Deploy on Render, Koyeb, or run in Termux.

## Environment Variables
- `BOT_TOKEN`: Your Telegram Bot Token from @BotFather
- `CHANNEL_ID`: Your channel ID (e.g. `-1001234567890`)
- `CHANNEL_URL`: Your Telegram channel link (e.g. `https://t.me/your_channel`)
- `GET_NUMBER_URL`: Your Get Number link
- `BLUESMS_TOKEN`: Simple API v2 token (pre-configured)
- `ADMIN_ID`: Your Telegram User ID
