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


API_SPORTS_KEY = "21db1cc08f22993c3817d143a2b20c73"
API_SPORTS_KEY = "21db1cc08f22993c3817d143a2b20c73"

API:
    anomaliler = []
    spor_sayilari = {}

    headers = {"x-apisports-key": API_SPORTS_KEY}
    bugun = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    endpoints = {
        "⚽ FUTBOL": {
            "url": "https://v3.football.api-sports.io/fixtures",
            "params": {"date": bugun, "timezone": "Europe/Istanbul"}
        },
        "🏀 BASKETBOL": {
            "url": "https://v1.basketball.api-sports.io/games",
            "params": {"date": bugun, "timezone": "Europe/Istanbul"}
        },
        "🏐 VOLEYBOL": {
            "url": "https://v1.volleyball.api-sports.io/games",
            "params": {"date": bugun, "timezone": "Europe/Istanbul"}
        }
    }

    toplam_mac = 0

    for spor_name, endpoint in endpoints.items():
        count = 0

        try:
            res = await client.get(
                endpoint["url"],
                headers=headers,
                params=endpoint["params"]
            )

            if res.status_code != 200:
                print(f"{spor_name} HTTP hatası: {res.status_code} - {res.text[:300]}")
                spor_sayilari[spor_name] = 0
                continue

            data = res.json()

            if data.get("errors"):
                print(f"{spor_name} API hatası: {data['errors']}")
                spor_sayilari[spor_name] = 0
                continue

            maclar = data.get("response", [])
            count = len(maclar)
            toplam_mac += count

            for mac in maclar:
                if spor_name == "⚽ FUTBOL":
                    fixture = mac.get("fixture", {})
                    teams = mac.get("teams", {})
                    goals = mac.get("goals", {})
                    status = fixture.get("status", {})

                    ev = teams.get("home", {}).get("name", "Ev Sahibi")
                    dep = teams.get("away", {}).get("name", "Deplasman")
                    ev_skor = goals.get("home")
                    dep_skor = goals.get("away")
                    durum = status.get("short", "")
                    tarih = fixture.get("date", "")

                else:
                    game = mac.get("game", {})
                    teams = mac.get("teams", {})
                    scores = mac.get("scores", {})
                    status_data = game.get("status", {})

                    ev_data = teams.get("home", {})
                    dep_data = teams.get("away", {})

                    ev = ev_data.get("name", "Ev Sahibi")
                    dep = dep_data.get("name", "Deplasman")

                    ev_score_data = scores.get("home", {})
                    dep_score_data = scores.get("away", {})

                    ev_skor = ev_score_data.get("total") if isinstance(ev_score_data, dict) else ev_score_data
                    dep_skor = dep_score_data.get("total") if isinstance(dep_score_data, dict) else dep_score_data

                    durum = status_data.get("short", "")
                    tarih = game.get("date", "")

                match_saat = "Bilinmiyor"

                if tarih:
                    try:
                        dt = datetime.fromisoformat(tarih.replace("Z", "+00:00"))
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        match_saat = dt.astimezone().strftime("%H:%M")
                    except (ValueError, TypeError):
                        pass

                canli_durumlar = {
                    "1H", "2H", "HT", "ET", "BT", "P", "LIVE",
                    "Q1", "Q2", "Q3", "Q4", "OT",
                    "IN1", "IN2", "IN3", "IN4", "IN5",
                    "IN6", "IN7", "IN8", "IN9",
                    "P1", "P2", "P3", "PT"
                }

                biten_durumlar = {"FT", "AET", "PEN", "AOT", "AP"}

                skor = (
                    f"{ev_skor if ev_skor is not None else 0} - "
                    f"{dep_skor if dep_skor is not None else 0}"
                )

                if durum in canli_durumlar:
                    durum_metni = f"🔴 CANLI ({skor})"
                elif durum in biten_durumlar:
                    durum_metni = f"🏁 Bitti ({skor})"
                elif durum == "NS":
                    durum_metni = "⏳ Başlayacak"
                else:
                    durum_metni = f"📌 {durum or 'Durum bilinmiyor'} ({skor})"

                anomaliler.append({
                    "kaynak": "API-Sports",
                    "spor": spor_name,
                    "ev": ev,
                    "dep": dep,
                    "saat": match_saat,
                    "skor": durum_metni
                })

            print(f"{spor_name}: {count} maç bulundu.")

        except Exception as e:
            print(f"{spor_name} bağlantı hatası: {e}")

        spor_sayilari[spor_name] = count

    spor_sayilari["🎾 TENİS"] = 0

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
