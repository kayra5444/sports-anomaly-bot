import asyncio
from datetime import datetime
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
        "▶ `/tara` - 3 kaynaklı canlı anomali taramasını başlatır\n"
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
        "🚀 **3 Kaynaklı Hızlı Anomali Taraması Başlatıldı!**\n"
        "Flashscore, BeSoccer ve Sofascore taranıyor..."
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


# 1. Sofascore API Taraması
async def tara_sofascore_api(client, simdiki_zaman):
    anomaliler, toplam = [], 0
    url = "https://api.sofascore.com/api/v1/sport/football/events/live"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.sofascore.com/"
    }

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
        print(f"Sofascore Hatası: {e}")

    return anomaliler, toplam


# 2. Flashscore Mobil HTTP Taraması
async def tara_flashscore_http(client, simdiki_zaman):
    anomaliler, toplam = [], 0
    url = "https://m.flashscore.com.tr/"
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
    }

    try:
        res = await client.get(url, headers=headers)
        if res.status_code == 200:
            # Ham içerikten maç verilerini tespit etme
            matches = re.findall(r'([A-Za-z0-9\s]+)\s*(\d{1,2}:\d{2})\s*([0-9]+)-([0-9]+)\s*([A-Za-z0-9\s]+)', res.text)
            toplam = len(matches)
            for m in matches:
                ev, saat_str, home_score, away_score, dep = m
                saat_match = re.search(r"(\d{2}):(\d{2})", saat_str)
                if saat_match:
                    h, m_m = int(saat_match.group(1)), int(saat_match.group(2))
                    if h > simdiki_zaman.hour or (h == simdiki_zaman.hour and m_m > simdiki_zaman.minute):
                        anomaliler.append({
                            "kaynak": "Flashscore",
                            "spor": "⚽ FUTBOL",
                            "ev": ev.strip(),
                            "dep": dep.strip(),
                            "saat": f"{h:02d}:{m_m:02d}",
                            "skor": f"{home_score} - {away_score}"
                        })
    except Exception as e:
        print(f"Flashscore Hatası: {e}")

    return anomaliler, toplam


# 3. BeSoccer Mobil HTTP Taraması
async def tara_besoccer_http(client, simdiki_zaman, bugun):
    anomaliler, toplam = [], 0
    url = f"https://www.besoccer.com/livescore/{bugun}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    }

    try:
        res = await client.get(url, headers=headers)
        if res.status_code == 200:
            # HTML kartlarını regex ile say
            matches = re.findall(r'class="[^\"]*match-link[^\"]*"', res.text)
            toplam = len(matches)
    except Exception as e:
        print(f"BeSoccer Hatası: {e}")

    return anomaliler, toplam


async def run_scanner_loop(context):
    global IS_SCANNING

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        while IS_SCANNING:
            simdiki_zaman = datetime.now()
            bugun = simdiki_zaman.strftime("%Y-%m-%d")

            # 3 Kaynağı Paralel Olarak Çek
            flash_task = tara_flashscore_http(client, simdiki_zaman)
            be_task = tara_besoccer_http(client, simdiki_zaman, bugun)
            sofa_task = tara_sofascore_api(client, simdiki_zaman)

            (flash_anom, flash_cnt), (be_anom, be_cnt), (sofa_anom, sofa_cnt) = await asyncio.gather(
                flash_task, be_task, sofa_task
            )

            tum_anomaliler = flash_anom + be_anom + sofa_anom
            toplam_mac = flash_cnt + be_cnt + sofa_cnt

            if tum_anomaliler:
                for item in tum_anomaliler:
                    await send_telegram_alert(context, item)

            rapor_metni = (
                f"✅ **Tarama Döngüsü Tamamlandı!** ({simdiki_zaman.strftime('%H:%M')})\n\n"
                f"📊 **Taranan Maç Sayıları:**\n"
                f"• 🟡 **Flashscore:** {flash_cnt} maç\n"
                f"• 🟢 **BeSoccer:** {be_cnt} maç\n"
                f"• 🔵 **Sofascore API:** {sofa_cnt} maç\n\n"
                f"📈 **Toplam Taranan:** {toplam_mac} maç\n"
                f"🚨 **Yakalanan Anomali:** {len(tum_anomaliler)} adet"
            )

            try:
                await context.bot.send_message(
                    chat_id=CHAT_ID,
                    text=rapor_metni,
                    parse_mode="Markdown"
                )
            except Exception:
                pass

            # 60 saniye sonra tekrar tara
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

    print("🤖 Bot Aktif (3 Kaynaklı Hızlı Mod) ve Komut Bekliyor...")
    app.run_polling()
