"""Example: Scrape all municipalities for the 2026 municipal elections."""

import asyncio
from pathlib import Path

from nl_voting_data_scraper import StemwijzerScraper
from nl_voting_data_scraper.output import write_all


async def main():
    async with StemwijzerScraper("gr2026", rate_limit=2.0) as scraper:
        # Fetch index first to see how many municipalities
        index = await scraper.fetch_index()
        print(f"Found {len(index)} entries")

        # Scrape all
        results = await scraper.scrape()
        print(f"Scraped {len(results)} entries")

        # Write to output directory
        output_dir = Path("output") / "gr2026"
        paths = write_all(results, output_dir, write_combined=True)
        print(f"\nWritten to {output_dir}/")
        for name, path in paths.items():
            print(f"  {name}: {path}")


if __name__ == "__main__":
    asyncio.run(main())
