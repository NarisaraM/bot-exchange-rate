# BOT exchange rate logger

`bot_exchange_rate.py` fetches the Bank of Thailand daily foreign-exchange rates
and appends them to a tab-separated text file, one row per currency per day.

Data comes from the JSON endpoint that
<https://www.bot.or.th/th/statistics/exchange-rate.html> itself calls, so there
is no HTML scraping and no browser required. Standard library only — no
`pip install` needed.

## Usage

```bash
python bot_exchange_rate.py                 # USD row (includes weighted average)
python bot_exchange_rate.py USD EUR JPY     # specific currencies
python bot_exchange_rate.py --all           # every currency BOT publishes
python bot_exchange_rate.py --file rates.txt USD
```

Re-running for a day already recorded does nothing (rows are de-duplicated on
`date + currency`). BOT publishes once per business day, so schedule this daily
(e.g. Windows Task Scheduler) to build a history.

## Output columns (`thb_exchange_rate.txt`)

| column | meaning |
| --- | --- |
| `date` | rate date, ISO `YYYY-MM-DD` (BOT's publication day, not today) |
| `currency` | ISO currency code |
| `buying_sight` | average buying rate, sight bill |
| `buying_transfer` | average buying rate, transfer |
| `selling` | average selling rate |
| `weighted_avg_interbank` | weighted-average interbank USD/THB rate; filled on the `USD` row only, `-` elsewhere |
| `fetched_at_utc` | when the script pulled the data |

Rates are the commercial-bank average for Bangkok. A `-` in a rate field is
BOT's own "not quoted" marker, passed through unchanged.
