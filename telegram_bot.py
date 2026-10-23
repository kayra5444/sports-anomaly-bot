import asyncio
from datetime import datetime
import json
import os
import random
import re
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram.request import HTTPXRequest
from playwright.async_api import async_playwright

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
        "🚀 **3 Kaynaklı Canlı Anomali Taraması Başlatıldı!**\n"
        "Sofascore Mobil Stealth Modunda taranıyor..."
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


async def run_scanner_loop(context):
    global IS_SCANNING

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context_browser = await browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
            viewport={"width": 390, "height": 844},
            is_mobile=True,
            has_touch=True
        )
        page = await context_browser.new_page()

        while IS_SCANNING:
            simdiki_zaman = datetime.now()
            bugun = simdiki_zaman.strftime("%Y-%m-%d")

            anomaliler = []

            # 1. Flashscore Tarama
            flash_anom, flash_cnt = await tara_flashscore(page, simdiki_zaman)
            anomaliler.extend(flash_anom)
            await asyncio.sleep(1.5)

            # 2. BeSoccer Tarama
            be_anom, be_cnt = await tara_besoccer(page, simdiki_zaman, bugun)
            anomaliler.extend(be_anom)
            await asyncio.sleep(1.5)

            # 3. Sofascore Mobil Tarama
            sofa_anom, sofa_cnt = await tara_sofascore_mobile(page, simdiki_zaman, bugun)
            anomaliler.extend(sofa_anom)

            toplam_mac = flash_cnt + be_cnt + sofa_cnt

            if anomaliler:
                for item in anomaliler:
                    await send_telegram_alert(context, item)

            rapor_metni = (
                f"✅ **Tarama Döngüsü Tamamlandı!** ({simdiki_zaman.strftime('%H:%M')})\n\n"
                f"📊 **Taranan Maç Sayıları:**\n"
                f"• 🟡 **Flashscore:** {flash_cnt} maç\n"
                f"• 🟢 **BeSoccer:** {be_cnt} maç\n"
                f"• 🔵 **Sofascore (Mobil):** {sofa_cnt} maç\n\n"
                f"📈 **Toplam Taranan:** {toplam_mac} maç\n"
                f"🚨 **Yakalanan Anomali:** {len(anomaliler)} adet"
            )

            try:
                await context.bot.send_message(
                    chat_id=CHAT_ID,
                    text=rapor_metni,
                    parse_mode="Markdown"
                )
            except Exception:
                pass

            for _ in range(120):
                if not IS_SCANNING:
                    break
                await asyncio.sleep(1)

        await browser.close()


async def tara_flashscore(page, simdiki_zaman):
    anomaliler, toplam = [], 0
    try:
        await page.goto("https://www.flashscore.com.tr/", timeout=30000)
        await asyncio.sleep(2)

        for _ in range(3):
            await page.evaluate("window.scrollBy(0, 1500)")
            await asyncio.sleep(0.4)

        matches = await page.query_selector_all(".event__match")
        toplam = len(matches)

        for m in matches:
            home_score_el = await m.query_selector(".event__score--home")
            away_score_el = await m.query_selector(".event__score--away")
            time_el = await m.query_selector(".event__time")

            if home_score_el and away_score_el and time_el:
                home_score = (await home_score_el.inner_text()).strip()
                away_score = (await away_score_el.inner_text()).strip()
                time_txt = (await time_el.inner_text()).strip()

                if home_score.isdigit() and away_score.isdigit():
                    saat_match = re.search(r"(\d{2}):(\d{2})", time_txt)
                    if saat_match:
                        h, m_m = int(saat_match.group(1)), int(saat_match.group(2))
                        if h > simdiki_zaman.hour or (h == simdiki_zaman.hour and m_m > simdiki_zaman.minute):
                            home_team_el = await m.query_selector(".event__participant--home")
                            away_team_el = await m.query_selector(".event__participant--away")
                            ev = (await home_team_el.inner_text()).strip() if home_team_el else "Ev Sahibi"
                            dep = (await away_team_el.inner_text()).strip() if away_team_el else "Deplasman"

                            anomaliler.append({
                                "kaynak": "Flashscore",
                                "spor": "⚽ FUTBOL",
                                "ev": ev,
                                "dep": dep,
                                "saat": f"{h:02d}:{m_m:02d}",
                                "skor": f"{home_score} - {away_score}"
                            })
    except Exception:
        pass
    return anomaliler, toplam


async def tara_besoccer(page, simdiki_zaman, bugun):
    anomaliler, toplam = [], 0
    try:
        await page.goto(f"https://www.besoccer.com/livescore/{bugun}", timeout=30000)
        await asyncio.sleep(2)

        try:
            btn = await page.query_selector("#didomi-notice-agree-button, .cc-btn")
            if btn:
                await btn.click()
                await asyncio.sleep(0.5)
        except Exception:
            pass

        for _ in range(3):
            await page.evaluate("window.scrollBy(0, 1500)")
            await asyncio.sleep(0.4)

        matches = await page.query_selector_all(
            "a.match-link, div.match-block, div.match-card, tr.match, div[data-match-id]"
        )
        toplam = len(matches)
    except Exception:
        pass
    return anomaliler, toplam


async def tara_sofascore_mobile(page, simdiki_zaman, bugun):
    anomaliler, toplam = [], 0
    try:
        # Sofascore Mobil Web Görünümü
        await page.goto(f"https://m.sofascore.com/tr/futbol/{bugun}", timeout=35000)
        await asyncio.sleep(3)

        for _ in range(4):
            await page.evaluate("window.scrollBy(0, 1000)")
            await asyncio.sleep(0.5)

        # Mobil kart seçicileri
        matches = await page.query_selector_all("a[href*='/match/'], div[data-testid='event_cell'], div[class*='EventCell']")
        toplam = len(matches)

    except Exception:
        toplam = 0

    return anomaliler, toplam


if __name__ == "__main__":
    request = HTTPXRequest(connect_timeout=60.0, read_timeout=60.0)
    app = ApplicationBuilder().token(BOT_TOKEN).request(request).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("tara", tara_command))
    app.add_handler(CommandHandler("dur", dur_command))
    app.add_handler(CommandHandler("durum", durum_command))

    print("🤖 Telegram Botu Aktif (Mobil Stealth Modlu) ve Komut Bekliyor...")
    app.run_polling()
