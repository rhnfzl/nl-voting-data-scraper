"""Example: Scrape a single municipality."""

import asyncio

from nl_voting_data_scraper import StemwijzerScraper


async def main():
    async with StemwijzerScraper("gr2026") as scraper:
        # Scrape Groningen
        data = await scraper.scrape_one("GM0014")
        print(f"Municipality: {data.votematch.name}")
        print(f"Parties: {len(data.parties)}")
        print(f"Statements: {len(data.statements)}")
        print(f"Shootout statements: {len(data.shootoutStatements)}")

        # Print first party and first statement
        party = data.parties[0]
        print(f"\nFirst party: {party.name}")
        print(f"  Positions: {len(party.statements)}")

        stmt = data.statements[0]
        print(f"\nFirst statement: {stmt.title}")
        print(f"  Theme: {stmt.theme}")


if __name__ == "__main__":
    asyncio.run(main())
