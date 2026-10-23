import asyncio
from datetime import datetime, timedelta, timezone
import httpx
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram.request import HTTPXRequest

BOT_TOKEN = "8635865754:AAFsjhRGQheMKNHQ3ksjOQ4VwbSc2YihadM"
CHAT_ID = "1127823264"

IS_SCANNING = False


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🤖 **Sports Anomaly Scanner Bot'a Hoş Geldiniz!**\n\n"
        "Kullanabileceğiniz Komutlar:\n"
        "▶ `/tara` - Futbol, Tenis, Basketbol ve Voleybol taramasını başlatır\n"
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
        "🚀 **Çoklu Spor Canlı Maç Taraması Başlatıldı!**\n"
        "⚽ Futbol, 🎾 Tenis, 🏀 Basketbol, 🏐 Voleybol taranıyor..."
    )

    asyncio.create_task(run_scanner_loop(context))


async def send_telegram_alert(context, item):
    text = (
        f"🚨 **CANLI MAÇ YAKALANDI!**\n\n"
        f"📌 **Kaynak:** {item['kaynak']}\n"
        f"🏆 **Spor:** {item['spor']}\n"
        f"⚔️ **Maç:** {item['ev']} vs {item['dep']}\n"
        f"⏰ **Başlama Saati:** {item['saat']} (Türkiye Saati)\n"
        f"📊 **Anlık Skor:** {item['skor']}"
    )
    try:
        await context.bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="Markdown")
    except Exception:
        pass


async def tara_sofascore_multi_sport(client, simdiki_zaman):
    anomaliler = []
    spor_sayilari = {}
    
    sports = {
        "football": "⚽ FUTBOL",
        "tennis": "🎾 TENİS",
        "basketball": "🏀 BASKETBOL",
        "volleyball": "🏐 VOLEYBOL"
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Origin": "https://www.sofascore.com",
        "Referer": "https://www.sofascore.com/"
    }

    toplam_mac = 0
    for sport_slug, sport_name in sports.items():
        url = f"https://api.sofascore.com/api/v1/sport/{sport_slug}/events/live"
        count = 0
        try:
            res = await client.get(url, headers=headers)
            print(f"SPOR: {sport_slug} | HTTP: {res.status_code}", flush=True)
            print(f"YANIT: {res.text[:300]}")
            if res.status_code == 200:
                data = res.json()
                events = data.get("events", [])
                count = len(events)
                toplam_mac += count

                for ev in events:
                    home_score = ev.get("homeScore", {}).get("current")
                    away_score = ev.get("awayScore", {}).get("current")
                    start_timestamp = ev.get("startTimestamp")

                    # Canlı olan ve skoru bulunan tüm maçları doğrudan yakala
                    if home_score is not None and away_score is not None and start_timestamp:
                        match_time = datetime.fromtimestamp(start_timestamp) + timedelta(hours=3)
                        
                        anomaliler.append({
                            "kaynak": "Sofascore API",
                            "spor": sport_name,
                            "ev": ev.get("homeTeam", {}).get("name", "Ev Sahibi"),
                            "dep": ev.get("awayTeam", {}).get("name", "Deplasman"),
                            "saat": match_time.strftime("%H:%M"),
                            "skor": f"{home_score} - {away_score}"
                        })
        except Exception as e:
            print(f"Sofascore {sport_name} Hatası: {e}")
        
        spor_sayilari[sport_name] = count

    return anomaliler, toplam_mac, spor_sayilari


async def run_scanner_loop(context):
    global IS_SCANNING

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        while IS_SCANNING:
            simdiki_zaman = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=3)

            sofa_anom, toplam_mac, spor_sayilari = await tara_sofascore_multi_sport(client, simdiki_zaman)

            if sofa_anom:
                for item in sofa_anom:
                    await send_telegram_alert(context, item)

            rapor_metni = (
                f"✅ **Tarama Döngüsü Tamamlandı!** ({simdiki_zaman.strftime('%H:%M')})\n\n"
                f"📊 **Branşlara Göre Canlı Maçlar:**\n"
                f"• {spor_sayilari.get('⚽ FUTBOL', 0)} Futbol\n"
                f"• {spor_sayilari.get('🎾 TENİS', 0)} Tenis\n"
                f"• {spor_sayilari.get('🏀 BASKETBOL', 0)} Basketbol\n"
                f"• {spor_sayilari.get('🏐 VOLEYBOL', 0)} Voleybol\n\n"
                f"📈 **Toplam Taranan:** {toplam_mac} müsabaka\n"
                f"🚨 **Yakalanan Maç/Anomali:** {len(sofa_anom)} adet"
            )

            try:
                await context.bot.send_message(
                    chat_id=CHAT_ID,
                    text=rapor_metni,
                    parse_mode="Markdown"
                )
            except Exception:
                pass

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

    print("🤖 Çoklu Spor Botu Aktif ve Komut Bekliyor...")
    app.run_polling(drop_pending_updates=True)
