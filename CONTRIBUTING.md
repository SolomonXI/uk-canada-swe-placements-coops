# Contributing

Thanks for helping improve the UK & Canada SWE placements/co-ops dataset.

## What belongs here

- UK software engineering industrial placements that are explicitly 12 months.
- Canadian software engineering / software developer co-op roles.
- Roles should be clearly relevant to SWE.

## Adding sources

Extend the scraper modules in `scrapers/`:

- `scrapers/uk_industrial_placements.py`
- `scrapers/canada_coops.py`

Prefer small, defensive parsers that tolerate changing HTML.
If a site uses a new layout, update the selectors in the scraper and leave a comment explaining why.

## Manual additions

If scraping is not feasible, you can add a normalized listing directly to `data/listings.json`.
Please ensure the object follows the existing schema and uses a stable `id`.

## Listing schema

Each listing should include:

- `id`
- `company`
- `role`
- `short_role`
- `type`
- `category`
- `ai_focus`
- `duration_months`
- `country`
- `city`
- `region`
- `locations`
- `application_url`
- `source`
- `posted_date`
- `last_seen_date`
- `open`
- `sponsorship`
- `notes`

## Contribution checklist

1. Fork or branch.
2. Edit the scraper or JSON data.
3. Run the scrapers locally.
4. Regenerate `README.md`.
5. Review the diff.
6. Open a pull request.

## Quality rules

- Only add software engineering roles.
- Only add UK industrial placements that are clearly 12-month placement-year roles.
- Only add Canadian co-op roles.
- Keep entries normalized and avoid duplicates.
