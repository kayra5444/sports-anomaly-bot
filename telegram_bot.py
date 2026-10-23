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
        "🤖 **Sports Anomaly Scanner Bot (Program Modu) Aktif!**\n\n"
        "Kullanabileceğiniz Komutlar:\n"
        "▶ `/tara` - Günün maç programını ve fikstürünü tarar\n"
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
        "🚀 **Günün Maç Programı ve Fikstür Taraması Başlatıldı!**\n"
        "⚽ Futbol, 🎾 Tenis, 🏀 Basketbol, 🏐 Voleybol taranıyor..."
    )

    asyncio.create_task(run_scanner_loop(context))


async def send_telegram_alert(context, item):
    text = (
        f"📅 **MAÇ PROGRAMI / BİLGİSİ**\n\n"
        f"📌 **Kaynak:** {item['kaynak']}\n"
        f"🏆 **Spor:** {item['spor']}\n"
        f"⚔️ **Maç:** {item['ev']} vs {item['dep']}\n"
        f"⏰ **Saat:** {item['saat']} (TSİ)\n"
        f"📊 **Durum/Skor:** {item['skor']}"
    )
    try:
        await context.bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="Markdown")
    except Exception:
        pass


async def tara_espn_multi_sport(client):
    anomaliler = []
    spor_sayilari = {}
    
    endpoints = {
        "soccer/eng.1": "⚽ FUTBOL",
        "basketball/nba": "🏀 BASKETBOL",
        "tennis/atp": "🎾 TENİS",
        "volleyball": "🏐 VOLEYBOL"
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }

    toplam_mac = 0
    for sport_path, sport_name in endpoints.items():
        url = f"https://site.api.espn.com/apis/site/v2/sports/{sport_path}/scoreboard"
        count = 0
        try:
            res = await client.get(url, headers=headers)
            
            if res.status_code == 200:
                data = res.json()
                events = data.get("events", [])
                count = len(events)
                toplam_mac += count

                for ev in events:
                    # Maç tarihini alıp Türkiye saatine (UTC+3) çevirelim
                    date_str = ev.get("date")
                    match_saat = "Planlanıyor"
                    if date_str:
                        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                        dt_tr = dt + timedelta(hours=3)
                        match_saat = dt_tr.strftime("%H:%M")

                    status_type = ev.get("status", {}).get("type", {}).get("state")
                    
                    competitions = ev.get("competitions", [{}])[0]
                    competitors = competitions.get("competitors", [])
                    
                    home_team, away_team, home_score, away_score = "Ev Sahibi", "Deplasman", "0", "0"
                    for comp in competitors:
                        if comp.get("homeAway") == "home":
                            home_team = comp.get("team", {}).get("displayName", "Ev Sahibi")
                            home_score = comp.get("score", "0")
                        elif comp.get("homeAway") == "away":
                            away_team = comp.get("team", {}).get("displayName", "Deplasman")
                            away_score = comp.get("score", "0")

                    durum_metni = "Başlamadı"
                    if status_type == "in":
                        durum_metni = f"🔴 CANLI ({home_score} - {away_score})"
                    elif status_type == "post":
                        durum_metni = f"🏁 Bitti ({home_score} - {away_score})"
                    else:
                        durum_metni = "⏳ Başlayacak"

                    anomaliler.append({
                        "kaynak": "ESPN API",
                        "spor": sport_name,
                        "ev": home_team,
                        "dep": away_team,
                        "saat": match_saat,
                        "skor": durum_metni
                    })
        except Exception as e:
            print(f"ESPN {sport_name} Hatası: {e}")
        
        spor_sayilari[sport_name] = count

    return anomaliler, toplam_mac, spor_sayilari


async def run_scanner_loop(context):
    global IS_SCANNING

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        while IS_SCANNING:
            simdiki_zaman = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=3)

            espn_anom, toplam_mac, spor_sayilari = await tara_espn_multi_sport(client)

            if espn_anom:
                for item in espn_anom:
                    await send_telegram_alert(context, item)

            rapor_metni = (
                f"✅ **Günlük Program Taraması Tamamlandı!** ({simdiki_zaman.strftime('%H:%M')})\n\n"
                f"📊 **Branşlara Göre Maçlar:**\n"
                f"• {spor_sayilari.get('⚽ FUTBOL', 0)} Futbol\n"
                f"• {spor_sayilari.get('🎾 TENİS', 0)} Tenis\n"
                f"• {spor_sayilari.get('🏀 BASKETBOL', 0)} Basketbol\n"
                f"• {spor_sayilari.get('🏐 VOLEYBOL', 0)} Voleybol\n\n"
                f"📈 **Toplam Fikstür:** {toplam_mac} müsabaka\n"
                f"📋 **Listelenen Maç:** {len(espn_anom)} adet"
            )

            try:
                await context.bot.send_message(
                    chat_id=CHAT_ID,
                    text=rapor_metni,
                    parse_mode="Markdown"
                )
            except Exception:
                pass

            for _ in range(300):  # Fikstür taraması için döngüyü 5 dakikaya çıkardık
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

    print("🤖 Çoklu Spor Botu (Program Modu) Aktif ve Komut Bekliyor...")
    app.run_polling(drop_pending_updates=True)
