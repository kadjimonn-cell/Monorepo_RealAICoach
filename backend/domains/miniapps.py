"""Mini-Apps Domain — Digital bank, marketplace, lifestyle, lifegame, real estate, cars, dating, school, fitness."""
from fastapi import APIRouter


def register(api_router: APIRouter, app=None):
    from routes import global_miniapps
    from routes import marketplace
    from routes import digital_bank
    from routes import exchange_vc
    from routes import lifegame
    from routes import dating
    from routes import cars
    from routes import real_estate
    from routes import school
    from routes import fitness
    from routes.miniapps_bundle import router as miniapps_bundle_router
    from routes.core_platform import router as core_platform_router
    from routes.health_wellness_learning import router as health_wellness_learning_router
    from routes.lifestyle_services import router as lifestyle_services_router
    from routes.assistant_translate import router as assistant_translate_router
    from routes.bill_generator import router as bill_generator_router
    from routes.word_forge import router as word_forge_router
    from routes.watch_videos import router as watch_videos_router
    from routes.watch_audio_shared import router as watch_audio_shared_router
    from routes.audio_studio_v2 import router as audio_studio_v2_router
    from routes.podcasts_v2 import router as podcasts_v2_router
    from routes.sports_v2 import router as sports_v2_router
    from routes.watch_videos_retirement_governance import router as watch_videos_retirement_governance_router

    api_router.include_router(global_miniapps.router, tags=["Mini Apps"])
    api_router.include_router(marketplace.router, tags=["Marketplace"])
    api_router.include_router(digital_bank.router, tags=["Digital Bank"])
    api_router.include_router(exchange_vc.router, tags=["Exchange & VC"])
    api_router.include_router(core_platform_router, tags=["Core Platform"])
    api_router.include_router(health_wellness_learning_router, tags=["Health, Wellness & Learning"])
    api_router.include_router(lifestyle_services_router, tags=["Lifestyle Services"])
    api_router.include_router(miniapps_bundle_router, tags=["Mini Apps Bundle"])
    api_router.include_router(assistant_translate_router, tags=["Assistant & Translation"])
    api_router.include_router(bill_generator_router, tags=["Bill Generator"])
    api_router.include_router(word_forge_router, tags=["Lexicon Intelligence Hub"])
    api_router.include_router(watch_videos_router, tags=["Watch Videos"])
    api_router.include_router(watch_audio_shared_router, tags=["Watch Audio Hub"])
    api_router.include_router(audio_studio_v2_router, tags=["Audio Studio v2"])
    api_router.include_router(podcasts_v2_router, tags=["Podcasts v2"])
    api_router.include_router(sports_v2_router, tags=["Sports v2"])
    api_router.include_router(watch_videos_retirement_governance_router, tags=["Watch Videos Retirement Governance"])

    if app:
        app.include_router(lifegame.router, prefix="/api", tags=["LifeGame"])
        app.include_router(dating.router, prefix="/api", tags=["AI Found Love"])
        app.include_router(cars.router, prefix="/api", tags=["Smart Cars"])
        app.include_router(real_estate.router, prefix="/api", tags=["Real Estate"])
        app.include_router(school.router, prefix="/api", tags=["School Tutor"])
        app.include_router(fitness.router, prefix="/api", tags=["Fitness"])
        app.include_router(global_miniapps.router, prefix="/api", tags=["Global Mini Apps"])
