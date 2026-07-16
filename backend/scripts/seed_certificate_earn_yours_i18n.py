#!/usr/bin/env python3
"""Seed certificateVerify.earnYours.* keys into all 23 locale files (idempotent)."""
import re
from pathlib import Path

LOCALES_DIR = Path("/app/frontend/src/i18n/locales")

T = {
    "en": ["START YOUR JOURNEY", "Earn yours", "This credential was earned through RealAICoach's AI-powered courses. Start learning today and earn your own verifiable certificate.", "Start Learning Free", "Explore RealAICoach"],
    "fr": ["COMMENCEZ VOTRE PARCOURS", "Obtenez le vôtre", "Cette certification a été obtenue grâce aux cours propulsés par l'IA de RealAICoach. Commencez à apprendre dès aujourd'hui et obtenez votre propre certificat vérifiable.", "Commencer à apprendre gratuitement", "Découvrir RealAICoach"],
    "es": ["COMIENZA TU CAMINO", "Obtén el tuyo", "Esta credencial se obtuvo a través de los cursos impulsados por IA de RealAICoach. Empieza a aprender hoy y obtén tu propio certificado verificable.", "Empieza a aprender gratis", "Explorar RealAICoach"],
    "de": ["STARTE DEINE REISE", "Hol dir deins", "Dieses Zertifikat wurde über die KI-gestützten Kurse von RealAICoach erworben. Beginne noch heute zu lernen und erhalte dein eigenes verifizierbares Zertifikat.", "Kostenlos lernen starten", "RealAICoach entdecken"],
    "pt": ["COMECE SUA JORNADA", "Conquiste o seu", "Esta credencial foi conquistada por meio dos cursos com IA da RealAICoach. Comece a aprender hoje e conquiste seu próprio certificado verificável.", "Comece a aprender grátis", "Explorar a RealAICoach"],
    "it": ["INIZIA IL TUO PERCORSO", "Ottieni il tuo", "Questa credenziale è stata ottenuta tramite i corsi basati sull'IA di RealAICoach. Inizia a imparare oggi e ottieni il tuo certificato verificabile.", "Inizia a imparare gratis", "Scopri RealAICoach"],
    "nl": ["BEGIN JOUW REIS", "Verdien de jouwe", "Deze credential is behaald via de AI-gestuurde cursussen van RealAICoach. Begin vandaag met leren en verdien je eigen verifieerbare certificaat.", "Gratis beginnen met leren", "Ontdek RealAICoach"],
    "sv": ["BÖRJA DIN RESA", "Skaffa ditt eget", "Denna merit har erhållits genom RealAICoachs AI-drivna kurser. Börja lära dig idag och få ditt eget verifierbara certifikat.", "Börja lära dig gratis", "Utforska RealAICoach"],
    "pl": ["ROZPOCZNIJ SWOJĄ PODRÓŻ", "Zdobądź swój", "Ten certyfikat zdobyto dzięki kursom RealAICoach opartym na AI. Zacznij naukę już dziś i zdobądź własny weryfikowalny certyfikat.", "Zacznij naukę za darmo", "Poznaj RealAICoach"],
    "ro": ["ÎNCEPE-ȚI CĂLĂTORIA", "Obține-l pe al tău", "Această acreditare a fost obținută prin cursurile RealAICoach bazate pe IA. Începe să înveți astăzi și obține propriul certificat verificabil.", "Începe să înveți gratuit", "Explorează RealAICoach"],
    "ru": ["НАЧНИТЕ СВОЙ ПУТЬ", "Получите свой", "Этот сертификат получен благодаря курсам RealAICoach на основе ИИ. Начните учиться сегодня и получите собственный проверяемый сертификат.", "Начать учиться бесплатно", "Узнать о RealAICoach"],
    "uk": ["ПОЧНІТЬ СВІЙ ШЛЯХ", "Отримайте свій", "Цей сертифікат здобуто завдяки курсам RealAICoach на основі ШІ. Почніть навчання сьогодні та отримайте власний перевірюваний сертифікат.", "Почати навчання безкоштовно", "Дізнатися про RealAICoach"],
    "tr": ["YOLCULUĞUNA BAŞLA", "Seninkini kazan", "Bu sertifika, RealAICoach'un yapay zekâ destekli kurslarıyla kazanıldı. Bugün öğrenmeye başla ve kendi doğrulanabilir sertifikanı kazan.", "Ücretsiz öğrenmeye başla", "RealAICoach'u keşfet"],
    "ja": ["旅を始めよう", "あなたも取得しよう", "この資格はRealAICoachのAI搭載コースで取得されました。今日から学習を始めて、あなた自身の検証可能な証明書を取得しましょう。", "無料で学習を始める", "RealAICoachを見る"],
    "zh": ["开启你的旅程", "获取你的证书", "此证书通过 RealAICoach 的 AI 课程获得。立即开始学习，获得属于你的可验证证书。", "免费开始学习", "了解 RealAICoach"],
    "ko": ["여정을 시작하세요", "나만의 인증서 받기", "이 자격 증명은 RealAICoach의 AI 기반 강좌를 통해 취득되었습니다. 오늘 학습을 시작하고 검증 가능한 나만의 인증서를 받아보세요.", "무료로 학습 시작", "RealAICoach 둘러보기"],
    "ar": ["ابدأ رحلتك", "احصل على شهادتك", "تم الحصول على هذه الشهادة من خلال دورات RealAICoach المدعومة بالذكاء الاصطناعي. ابدأ التعلم اليوم واحصل على شهادتك القابلة للتحقق.", "ابدأ التعلم مجانًا", "استكشف RealAICoach"],
    "hi": ["अपनी यात्रा शुरू करें", "अपना प्रमाणपत्र पाएं", "यह क्रेडेंशियल RealAICoach के AI-संचालित कोर्स के माध्यम से अर्जित किया गया। आज ही सीखना शुरू करें और अपना सत्यापन योग्य प्रमाणपत्र पाएं।", "मुफ़्त में सीखना शुरू करें", "RealAICoach देखें"],
    "th": ["เริ่มต้นเส้นทางของคุณ", "รับใบรับรองของคุณ", "ใบรับรองนี้ได้รับผ่านคอร์ส AI ของ RealAICoach เริ่มเรียนวันนี้และรับใบรับรองที่ตรวจสอบได้ของคุณเอง", "เริ่มเรียนฟรี", "สำรวจ RealAICoach"],
    "vi": ["BẮT ĐẦU HÀNH TRÌNH CỦA BẠN", "Nhận chứng chỉ của bạn", "Chứng chỉ này được cấp thông qua các khóa học AI của RealAICoach. Bắt đầu học ngay hôm nay và nhận chứng chỉ có thể xác minh của riêng bạn.", "Bắt đầu học miễn phí", "Khám phá RealAICoach"],
    "id": ["MULAI PERJALANANMU", "Raih milikmu", "Kredensial ini diperoleh melalui kursus bertenaga AI dari RealAICoach. Mulai belajar hari ini dan raih sertifikat terverifikasi milikmu sendiri.", "Mulai belajar gratis", "Jelajahi RealAICoach"],
    "ms": ["MULAKAN PERJALANAN ANDA", "Dapatkan milik anda", "Kelayakan ini diperoleh melalui kursus berkuasa AI RealAICoach. Mula belajar hari ini dan dapatkan sijil boleh disahkan anda sendiri.", "Mula belajar secara percuma", "Terokai RealAICoach"],
    "sw": ["ANZA SAFARI YAKO", "Pata chako", "Cheti hiki kilipatikana kupitia kozi za RealAICoach zinazoendeshwa na AI. Anza kujifunza leo na upate cheti chako kinachoweza kuthibitishwa.", "Anza kujifunza bila malipo", "Chunguza RealAICoach"],
}

KEYS = ["overline", "title", "copy", "primaryCta", "secondaryCta"]


def esc(v: str) -> str:
    return v.replace("\\", "\\\\").replace('"', '\\"')


def main() -> None:
    for lang, values in T.items():
        path = LOCALES_DIR / f"{lang}.ts"
        src = path.read_text(encoding="utf-8")
        if "certificateVerify.earnYours.overline" in src:
            print(f"{lang}: already seeded, skipping")
            continue
        anchor = re.search(r'^(\s*)"certificateVerify\.errors\.', src, flags=re.M)
        if not anchor:
            anchor = re.search(r'^(\s*)"certificateVerify\.hero\.', src, flags=re.M)
        assert anchor, f"{lang}: no certificateVerify anchor found"
        indent = anchor.group(1)
        block = "".join(
            f'{indent}"certificateVerify.earnYours.{k}": "{esc(v)}",\n' for k, v in zip(KEYS, values)
        )
        src = src[: anchor.start()] + block + src[anchor.start():]
        path.write_text(src, encoding="utf-8")
        print(f"{lang}: seeded 5 keys")


if __name__ == "__main__":
    main()
