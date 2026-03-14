"""Example: Scrape national (Tweede Kamer) election data."""

import asyncio
import json

from nl_voting_data_scraper import StemwijzerScraper


async def main():
    async with StemwijzerScraper("tk2025") as scraper:
        results = await scraper.scrape()

        for data in results:
            print(f"Election: {data.votematch.name}")
            print(f"Context: {data.votematch.context}")
            print(f"Parties: {len(data.parties)}")
            print(f"Statements: {len(data.statements)}")

            # Save to file
            filename = f"{data.votematch.context}.json"
            with open(filename, "w") as f:
                json.dump(data.model_dump(by_alias=True), f, ensure_ascii=False, indent=2)
            print(f"Saved to {filename}")


if __name__ == "__main__":
    asyncio.run(main())
