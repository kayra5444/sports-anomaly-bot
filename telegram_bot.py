import asyncio
from datetime import datetime
import os
import re
import httpx
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram.request import HTTPXRequest

BOT_TOKEN = "8635865754:AAHcSQcfbJjce64v3ISJZMSX1wcYzuVTvig"
CHAT_ID = "1127823264"

IS_SCANNING = False


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🤖 **Sports Anomaly Scanner Bot'a Hoş Geldiniz!**\n\n"
        "Kullanabileceğiniz Komutlar:\n"
        "▶ `/tara` - Canlı anomali taramasını başlatır\n"
        "⏹ `/dur` - Taramayı durdurur\n"
        "📊 `/durum` - Botun durumunu gösterir"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def durum_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    durum = "🟢 TARAMA AKTİF" if IS_SCANNING else "🔴 DURDURULDU"
    await update.message.reply_text(f"Bot Durumu: {durum}")


async def dur_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global IS_SCANNING
    IS_SCANNING = False
    await update.message.reply_text("⏹ Tarama durduruldu.")


async def tara_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global IS_SCANNING
    if IS_SCANNING:
        await update.message.reply_text("⚠️ Tarama zaten aktif olarak çalışıyor!")
        return

    IS_SCANNING = True
    await update.message.reply_text(
        "🚀 **Hızlı API Tabanlı Canlı Anomali Taraması Başlatıldı!**\n"
        "Sofascore canlı verileri taranıyor..."
    )

    asyncio.create_task(run_scanner_loop(context))


async def send_telegram_alert(context, item):
    text = (
        f"🚨 **ANOMALİ MAÇ YAKALANDI!**\n\n"
        f"📌 **Kaynak:** {item['kaynak']}\n"
        f"🏆 **Spor:** {item['spor']}\n"
        f"⚔️ **Maç:** {item['ev']} vs {item['dep']}\n"
        f"⏰ **Planlanan Saat:** {item['saat']} (İleriki Saat!)\n"
        f"📊 **Girilen Skor:** {item['skor']}"
    )
    try:
        await context.bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="Markdown")
    except Exception:
        pass


async def tara_sofascore_api(simdiki_zaman):
    anomaliler, toplam = [], 0
    url = "https://api.sofascore.com/api/v1/sport/football/events/live"
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.sofascore.com/"
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            res = await client.get(url, headers=headers)
            if res.status_code == 200:
                data = res.json()
                events = data.get("events", [])
                toplam = len(events)

                for ev in events:
                    home_score = ev.get("homeScore", {}).get("current")
                    away_score = ev.get("awayScore", {}).get("current")
                    start_timestamp = ev.get("startTimestamp")

                    if home_score is not None and away_score is not None and start_timestamp:
                        match_time = datetime.fromtimestamp(start_timestamp)
                        
                        # İleriki saate skor girilip girilmediğinin kontrolü (Anomali)
                        if match_time > simdiki_zaman:
                            anomaliler.append({
                                "kaynak": "Sofascore API",
                                "spor": "⚽ FUTBOL",
                                "ev": ev.get("homeTeam", {}).get("name", "Ev Sahibi"),
                                "dep": ev.get("awayTeam", {}).get("name", "Deplasman"),
                                "saat": match_time.strftime("%H:%M"),
                                "skor": f"{home_score} - {away_score}"
                            })
        except Exception as e:
            print(f"Sofascore API hatası: {e}")

    return anomaliler, toplam


async def run_scanner_loop(context):
    global IS_SCANNING

    while IS_SCANNING:
        simdiki_zaman = datetime.now()

        # Doğrudan engelsiz API Taraması
        sofa_anom, sofa_cnt = await tara_sofascore_api(simdiki_zaman)

        if sofa_anom:
            for item in sofa_anom:
                await send_telegram_alert(context, item)

        rapor_metni = (
            f"✅ **Tarama Döngüsü Tamamlandı!** ({simdiki_zaman.strftime('%H:%M')})\n\n"
            f"📊 **Taranan Maç Sayıları:**\n"
            f"• 🔵 **Sofascore Live API:** {sofa_cnt} canlı maç\n\n"
            f"🚨 **Yakalanan Anomali:** {len(sofa_anom)} adet"
        )

        try:
            await context.bot.send_message(
                chat_id=CHAT_ID,
                text=rapor_metni,
                parse_mode="Markdown"
            )
        except Exception:
            pass

        # 60 saniyede bir yeniden tara
        for _ in range(60):
            if not IS_SCANNING:
                break
            await asyncio.sleep(1)


if __name__ == "__main__":
    request = HTTPXRequest(connect_timeout=60.0, read_timeout=60.0)
    app = ApplicationBuilder().token(BOT_TOKEN).request(request).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("tara", tara_command))
    app.add_handler(CommandHandler("dur", dur_command))
    app.add_handler(CommandHandler("durum", durum_command))

    print("🤖 Telegram Botu Aktif (Ultra Hızlı API Modu) ve Komut Bekliyor...")
    app.run_polling()
