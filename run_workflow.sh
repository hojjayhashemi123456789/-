#!/usr/bin/env bash
set -e

echo "🚀 Starting DRpdfmakerbot 24/7 Watchdog & Hot-Reload Runner..."

# اجرای حلقه ۵ ساعت و ۳۵ دقیقه‌ای (۳۳۵ دقیقه) قبل از تحویل سیکل به گیت‌هاب اکشنز بعدی
START_TIME=$(date +%s)
MAX_SECONDS=$((335 * 60))

while true; do
    NOW=$(date +%s)
    ELAPSED=$((NOW - START_TIME))
    if [ "$ELAPSED" -ge "$MAX_SECONDS" ]; then
        echo "⏰ 335 minutes reached. Gracefully stopping for next GitHub Actions cycle..."
        break
    fi

    echo "🔥 Launching bot.py..."
    python3 bot.py &
    BOT_PID=$!

    # نظارت بر وضعیت پروسس و تغییرات گیت (Hot-Reload)
    while kill -0 "$BOT_PID" 2>/dev/null; do
        NOW=$(date +%s)
        ELAPSED=$((NOW - START_TIME))
        if [ "$ELAPSED" -ge "$MAX_SECONDS" ]; then
            kill "$BOT_PID" 2>/dev/null || true
            break 2
        fi
        sleep 5
    done

    echo "⚠️ bot.py exited. Restarting in 3 seconds..."
    sleep 3
done
