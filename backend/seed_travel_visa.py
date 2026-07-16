#!/usr/bin/env python3
"""Seed Travel Visa data directly into MongoDB"""
import asyncio
import sys
import os
sys.path.insert(0, '/app/backend')

from motor.motor_asyncio import AsyncIOMotorClient

# Minimal seed data for testing
COUNTRY_DATA = [
    {"country_id": "US", "name": "United States", "region": "North America", "flag": "🇺🇸", "visa_complexity": "medium", "popular": True},
    {"country_id": "CA", "name": "Canada", "region": "North America", "flag": "🇨🇦", "visa_complexity": "medium", "popular": True},
    {"country_id": "GB", "name": "United Kingdom", "region": "Europe", "flag": "🇬🇧", "visa_complexity": "medium", "popular": True},
    {"country_id": "DE", "name": "Germany", "region": "Europe", "flag": "🇩🇪", "visa_complexity": "medium", "popular": True},
    {"country_id": "AU", "name": "Australia", "region": "Oceania", "flag": "🇦🇺", "visa_complexity": "medium", "popular": True},
]

CATEGORIES_DATA = [
    {"category_id": "visa-basics", "name": "Visa Basics", "group": "Foundation", "order": 1},
    {"category_id": "documentation", "name": "Required Documentation", "group": "Preparation", "order": 2},
    {"category_id": "interview-prep", "name": "Interview Preparation", "group": "Application", "order": 3},
]

LESSON_TEMPLATES = [
    {"lesson_id": "l1", "category_id": "visa-basics", "title": "Understanding Visa Types", "content": "Learn about different visa categories...", "xp": 50},
    {"lesson_id": "l2", "category_id": "documentation", "title": "Essential Documents Checklist", "content": "Prepare your document package...", "xp": 50},
    {"lesson_id": "l3", "category_id": "interview-prep", "title": "Common Interview Questions", "content": "Practice answering key questions...", "xp": 75},
]

QUIZ_TEMPLATES = [
    {"quiz_id": "q1", "category_id": "visa-basics", "title": "Visa Basics Quiz", "questions": [{"q": "What is a visa?", "options": ["Travel document", "Passport", "ID"], "answer": 0}], "xp": 25},
]

EMBASSY_DATA = [
    {"embassy_id": "us-london", "country_id": "US", "city": "London", "address": "24 Grosvenor Square", "phone": "+44-20-7499-9000"},
    {"embassy_id": "ca-paris", "country_id": "CA", "city": "Paris", "address": "35 Avenue Montaigne", "phone": "+33-1-44-43-29-00"},
]

async def seed_data():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://127.0.0.1:27017/"))
    db = client.realaicoach
    
    print("🧹 Clearing existing Travel Visa data...")
    await db.tv_countries.delete_many({})
    await db.tv_categories.delete_many({})
    await db.tv_embassies.delete_many({})
    await db.tv_lessons.delete_many({})
    await db.tv_quizzes.delete_many({})
    
    print(f"📦 Inserting {len(COUNTRY_DATA)} countries...")
    if COUNTRY_DATA:
        await db.tv_countries.insert_many(COUNTRY_DATA)
    
    print(f"📦 Inserting {len(CATEGORIES_DATA)} categories...")
    if CATEGORIES_DATA:
        await db.tv_categories.insert_many(CATEGORIES_DATA)
    
    print(f"📦 Inserting {len(EMBASSY_DATA)} embassies...")
    if EMBASSY_DATA:
        await db.tv_embassies.insert_many(EMBASSY_DATA)
    
    print(f"📦 Inserting {len(LESSON_TEMPLATES)} lessons...")
    if LESSON_TEMPLATES:
        await db.tv_lessons.insert_many(LESSON_TEMPLATES)
    
    print(f"📦 Inserting {len(QUIZ_TEMPLATES)} quizzes...")
    if QUIZ_TEMPLATES:
        await db.tv_quizzes.insert_many(QUIZ_TEMPLATES)
    
    # Get final counts
    counts = {
        "countries": await db.tv_countries.count_documents({}),
        "categories": await db.tv_categories.count_documents({}),
        "embassies": await db.tv_embassies.count_documents({}),
        "lessons": await db.tv_lessons.count_documents({}),
        "quizzes": await db.tv_quizzes.count_documents({}),
    }
    
    print("\n✅ Seed Complete!")
    for name, count in counts.items():
        print(f"  {name.capitalize()}: {count}")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(seed_data())
