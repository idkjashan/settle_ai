"""
scripts/seed_demo_settlement.py
Unified demo settlement seeder for Auto-Settle AI.
Invokes app.infrastructure.db.seed.clear_and_seed_database() to populate all 4 video test scenarios.
"""
import asyncio
from app.infrastructure.db.seed import clear_and_seed_database

if __name__ == "__main__":
    result = asyncio.run(clear_and_seed_database(clear_existing=True))
    print("✅ Demo seeding completed successfully:")
    for claim in result["demo_claims"]:
        print(f"  • [{claim['stage']}] {claim['vehicle']}: {claim['url']}")
