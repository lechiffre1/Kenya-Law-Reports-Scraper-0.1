# Kenya-Law-Reports-Scraper-0.1
# Kenya Law Reports Scraper

A robust and efficient scraper for extracting judgments from Kenya Law Reports (new.kenyalaw.org/judgements). This tool is designed to reliably scrape all 275,979+ judgments from the website while respecting server limitations.

## Features

- **Optimized for Kenya Law Reports**: Specifically designed for the structure of new.kenyalaw.org/judgements
- **Organized Storage**: Judgments are categorized by court hierarchy
- **Robust Error Handling**: Comprehensive logging and error recovery
- **Rate Limiting**: Respects the server by using delays between requests
- **Resumable**: Can resume from where it left off if interrupted
- **Parallel Processing**: Configurable multi-threading for faster scraping
- **Progress Tracking**: Detailed statistics and progress monitoring

## Requirements

- Python 3.6+
- Required Python packages:
  - requests
  - beautifulsoup4
  - tqdm

## Directory Structure

```
KLR/
├── supreme_court/           # Supreme Court judgments
├── court_of_appeal/         # Court of Appeal judgments
├── high_court/              # High Court judgments
├── employment_and_labour_court/
├── environment_and_land_court/
├── magistrates_courts/
├── specialized_tribunals/
├── other_courts/            # Judgments from other courts or unidentified courts
├── logs/                    # Log files
├── metadata.csv             # CSV file with metadata for all judgments
├── progress.json            # Progress tracking for resuming
├── errors.log               # Detailed error log
└── summary.json             # Summary of scraping results
```

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/kenya-law-reports-scraper.git
   cd kenya-law-reports-scraper
   ```

2. Install required packages:
   ```
   pip install requests beautifulsoup4 tqdm
   ```

3. Make the scripts executable:
   ```
   chmod +x klr-scraper-optimized.py run-scraper.sh
   ```

## Usage

### Basic Usage

Run the scraper with default settings:

```bash
./run-scraper.sh
```

This will start scraping judgments from page 1 and store them in the `KLR` directory. It will automatically resume from where it left off if interrupted.

### Advanced Usage

The scraper supports several command-line arguments:

```bash
./klr-scraper-optimized.py --output KLR --max-pages 100 --start-page 10
```

Options:
- `--output DIR`: Specify the output directory (default: KLR)
- `--no-resume`: Do not resume from the last position, start fresh
- `--max-pages N`: Limit scraping to N pages
- `--start-page N`: Start scraping from page N

When using the shell script:

```bash
./run-scraper.sh --max-pages 100 --start-page 10 --no-loop
```

Additional shell script options:
- `--no-loop`: Run the scraper only once instead of continuously

## Monitoring Progress

- Check the `KLR/logs/` directory for detailed logs
- View `KLR/metadata.csv` for a complete list of scraped judgments
- Check `KLR/progress.json` for current progress
- View `KLR/errors.log` for any errors encountered
- Check `KLR/summary.json` for overall statistics

## Handling Large-Scale Scraping

The Kenya Law Reports website contains over 275,000 judgments, which is a significant amount of data. Here are some tips for handling this scale:

1. **Run in smaller batches**: Use the `--max-pages` option to limit each run to a manageable number of pages.
2. **Use a server or VPS**: For continuous scraping, it's better to use a dedicated machine rather than your personal computer.
3. **Monitor disk space**: The complete dataset may require significant storage space.
4. **Be patient**: Scraping all judgments may take several days or even weeks, depending on your connection speed and rate limiting.

## Ethical Considerations

This scraper is designed to respect the server's resources:

- It uses random delays between requests
- It limits parallel processing to avoid overwhelming the server
- It handles rate limiting gracefully

As noted, Kenya Law Reports content is in the public domain under a Creative Commons license. However, please consider the following:

1. Review the website's terms of service before scraping
2. Use the data only for legitimate purposes
3. If you plan to distribute the scraped content, provide proper attribution

## Troubleshooting

- **The scraper stops unexpectedly**: Check the error logs. It might be due to network issues or changes in the website structure.
- **Rate limiting**: If you see rate limiting errors, increase the delay parameters in the script.
- **Missing content**: Some judgments might not have content or might have a different structure. The scraper logs these as "no_content" in the summary.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
