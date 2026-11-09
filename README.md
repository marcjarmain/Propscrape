# PropScrape

A small desktop command-line collector for Property24 for-sale search cards. It saves a structured JSON file for an LLM and a CSV for Excel. Search results are asking prices, not sale prices or valuations. The default is the Southern Suburbs regional search, which includes many suburbs. Other regions can be searched by supplying their Property24 search URL.

Property24's [terms](https://www.property24.com/terms-and-conditions) restrict automated copying. Obtain permission where needed. The collector checks robots.txt, identifies itself, slows requests, and stops on blocks; it does not bypass challenges. A desktop connection does not guarantee access. Do not upload listing data to a public repository. This repository itself is public.

## Windows setup

1. Install Python 3 from python.org, selecting **Add Python to PATH**. Download or clone this repository to your PC and open a terminal in its folder.
2. Edit `subject.json` in Notepad. Save another subject file when comparing a different property.
3. Run `py propscrape.py`.
4. Open `output/comparison.json` in an LLM, or `output/listings.csv` in Excel. Ask it to compare the subject with listings of similar type, size and location and explain missing data.

For a different regional search, copy its full URL from your browser and run:

```
py propscrape.py --url "https://www.property24.com/for-sale/alias/southern-suburbs/25/western-cape/9" --subject subject.json --output output
```

Use `python3` instead of `py` on macOS/Linux. `--max-pages 10` limits pages; `--delay 2` controls seconds between requests. Runs overwrite output files, so use a different `--output` folder for each region or date. This first version searches one regional URL per run; it does not combine regions automatically.

The JSON contains the subject, all extracted listings, source URLs, collection time and coverage/stop reason. Duplicates within a run are removed by listing ID. `Unclassified` suburbs remain in the results. Region labels are a starting list, not a complete authoritative geography. If a page has no recognisable cards, access is blocked, or a page limit is reached, the run stops and marks coverage incomplete. Search-card size is kept as `advertised_size_m2`, not assumed to be erf or floor area; specific erf and floor fields remain blank until confirmed. Room counts can be blank when not labelled in the page. Check output against the website. It has not been tested against a live Property24 page in the development environment.
