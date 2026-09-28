# How's Life? data specificities

What you need to know to use the OECD's How's Life? well-being data correctly, found while building
`wise_mcp` against the OECD SDMX API (data downloaded September 2026) and the
[How's Life? 2024](https://www.oecd.org/en/publications/how-s-life-2024_90ba854a-en.html) report.

Each item below is something a person, or an AI assistant, would likely get wrong working from the
raw data alone. Most of the rules that fix them live in the report's text and tables, not in the
data or its metadata. That is the case for a shared, OECD-maintained layer such as an MCP server:
everyone who asks a question gets the same, correct assumptions applied.

Each item gives **what**, a real **example**, and **what `wise_mcp` does**.

## Averages and comparisons

### Not every country has data, so the OECD average covers fewer than 38

- **What:** the report's OECD average is a simple mean over the members that have data, and it says
  how many when it's fewer than all 38 ("OECD 33").
- **Example:** the latest life satisfaction values cover 34 members; household income in 2022, 33.
- **`wise_mcp`:** every average carries its country count and is labelled the same way
  (`OecdAverage.label`).

### Trend averages need the same countries in every year

- **What:** for trends, the report averages only countries with data in every year shown. Otherwise
  a country that starts reporting halfway through shifts the average and looks like a trend.
- **Example:** life satisfaction since 2010 can be assessed for 29 members; the other 9 lack a value
  around 2010 or after 2019.
- **`wise_mcp`:** the OECD change over time uses only members with both a baseline and an end value.

### The newest years have fewer countries, so trend lines stop early

- **What:** recent years are published for fewer countries, so a trend line that requires every
  country to have every year can collapse to almost nothing if it runs to the newest year.
- **Example:** in a life expectancy chart that includes Mexico (data to 2024), too few members have
  a 2024 value. Stopping at 2023 keeps 37 members in every year.
- **`wise_mcp`:** the OECD trend line stops at the last year that at least half the reporting
  members share, and the chart says where it stops ("37 members with data in every year to 2023").

### Each country's "latest" value is from a different year

- **What:** the latest available year varies by country, sometimes by several years.
- **Example:** a naive "top 3 countries for life satisfaction" gives Mexico (2021), Iceland (2018)
  and Colombia (2022): three different years compared as if they matched.
- **`wise_mcp`:** every value carries its year, and comparisons warn when years differ.

### Non-OECD countries sit in the same tables as members

- **What:** 9 of the 47 countries in the data aren't OECD members (Argentina, Brazil, Bulgaria,
  Croatia, Indonesia, Peru, Romania, South Africa, Thailand). The report leaves them out of its
  analysis.
- **Example:** Bulgaria, Croatia and Romania appear alongside members in a life satisfaction
  ranking.
- **`wise_mcp`:** analyses cover the 38 members only, for now.

### An "OECD" row appears in future well-being only

- **What:** future well-being includes a published `OECD` aggregate row; current well-being doesn't.
- **Example:** without filtering, "OECD" can show up as a country in a ranking.
- **`wise_mcp`:** it is never treated as a country.

### Today's data don't always match the figures the OECD published

- **What:** some OECD averages computed from today's database differ from the figures in How's
  Life? 2024. That isn't a bug by anyone. The likeliest explanation is that the OECD revised the
  database after the report came out in November 2024 (the report quotes income at 2021 PPPs, for
  example), but this couldn't be confirmed.
- **Example:**

  | Indicator | Published | From today's data | Difference |
  |---|---|---|---|
  | Life expectancy, 2022 | 80.7 | 80.55 | −0.2% |
  | Employment rate, 2023 | 78% | 78.4% | +0.5% |
  | Housing affordability, 2022 | 79% | 79.05% | +0.1% |
  | Long hours in paid work, 2022 | "1 in 14" (7.1%) | 7.3% | +2.2% |
  | Household income, 2022 | USD 35 200 | USD 42 126 | +20% |
  | Homicides, 2021 | 3.5 | 2.95 | −16% |
  | Overcrowding, 2022 | "almost 12%" | 11.1% | −7.5% |
  | Gender wage gap, 2022 | 11.6% | 10.9% | −6% |
  | Deaths of despair, 2021 | 23.6 | 22.3 | −6% |

  Using each country's latest year instead of the stated year doesn't close the gaps.
- **`wise_mcp`:** the first four are live tests (within 2.5%), which confirms the averaging method
  matches the report. The rest are not tested.

## What the numbers mean

### Whether higher is better isn't in the data

- **What:** the API gives no direction for any of the 103 measures. It has to be inferred from each
  definition, and some names point the wrong way.
- **Example:** "Corruption" is a perceptions index where 100 means very clean, so higher is better.
  "Housing affordability" is the share of income left after housing costs, so higher is better.
- **`wise_mcp`:** `measures.yaml` records the direction for every measure, with tests pinning the
  misleading ones.

### API labels hide what some measures are

- **What:** several labels describe the wrong thing.
- **Example:** "Top average household disposable income quintile" is the S80/S20 ratio (top 20%
  income divided by bottom 20%). "Top reading scores decile" is a top-to-bottom-10% ratio.
- **`wise_mcp`:** `measures.yaml` adds the report's own names and notes explaining the ratios.

### Gaps can be negative or go past parity

- **What:** for gaps, "lower is better" breaks down. The goal is no gap in either direction.
- **Example:** Luxembourg's gender wage gap was −8.7% in 2022 (women's median wage above men's). With
  "lower is better" it would rank best in the OECD. Mexico has 50.4% women in parliament, past
  parity. Romania and South Africa run soil nitrogen deficits, which harm soils as surpluses harm
  water.
- **`wise_mcp`:** these measures aim for a target (0, 50% or balance), and rankings use distance
  from it.

### "Lack of X" isn't 100 minus X

- **What:** paired measures look like complements but aren't. Some answers ("don't know", middle
  scores) count in neither.
- **Example:** "social support" plus "lack of social support" misses 100 by up to 11 points in about
  half of the rows. "Having a say" and "no say" in government miss by up to 39.
- **`wise_mcp`:** thresholds are never borrowed from the paired measure.

### One headline indicator isn't in the data at all

- **What:** the report's headline "gender gap in feeling safe" has to be computed from the data
  split by sex.
- **`wise_mcp`:** computed as men's share minus women's, in percentage points (our convention).

## Units and series

### A unit label is wrong

- **What:** greenhouse gas emissions per capita are labelled "kg CO₂e per person", but the values
  (2.6 to 28) are thousands of kg, i.e. tonnes. The report confirms "kilograms, thousands".
- **Example:** taking the label at face value makes the change threshold 1,000 times too big.
- **`wise_mcp`:** the threshold is stored in the data's real unit, and a `unit_label` in
  `measures.yaml` replaces the OECD's label, so every tool says "tonnes of CO₂-equivalent per
  person".

### One measure code can hold several series

- **What:** a code doesn't identify a single series. Carbon footprint comes in CO₂-equivalent
  (47 countries, to 2020) and CO₂ only (38 countries, to 2018). Breakdown rows (by sex, age or
  education) use separate `_SUB` units.
- **`wise_mcp`:** totals never use `_SUB` units; carbon footprint defaults to CO₂-equivalent.

### Some values are flagged as breaks or estimates

- **What:** observations carry a status. In current well-being: 1,749 series breaks, 7,904 "definition
  differs", 165 estimates, 107 provisional.
- **Example:** Canada's and Germany's life satisfaction series have breaks between 2010 and now, so
  part of their change may come from a change of method.
- **`wise_mcp`:** flagged values are listed in comparisons, and trends warn about breaks.

### Some indicators stopped years ago

- **Example:** job strain ends in 2015, labour market insecurity in 2016, access to green space in
  2018, depressive symptoms in 2019.
- **`wise_mcp`:** comparisons warn when a measure's newest data are 5+ years older than the rest.

### Some series start too late for a trend

- **Example:** France's S80/S20 income ratio is only in the database for 2020-2023, although the
  indicator goes back to 2004 for other countries. With no value around 2010 there is no baseline,
  so France's income-inequality trend can't be assessed.
- **`wise_mcp`:** trends mark such countries "insufficient data" and list them in the caveats.

### A country's score and its rank can disagree

- **What:** the report's 0-1 scores rescale each indicator between the worst and best member. When
  most members are bunched at one end, a country can score near the top yet rank in the middle.
- **Example:** France's exposure to extreme temperatures scores 0.97 (almost the best) but ranks
  25th of 38, because most members are at or near 0% exposed. Homicides show the same pattern.
- **`wise_mcp`:** the profile chart shows both, bar length for the score and colour for the rank
  third, and its subtitle explains why they can disagree.

### Some values can't be compared across countries

- **Example:** intact forest landscapes are in absolute km², so large countries rank first.
- **`wise_mcp`:** such measures are listed but not ranked.

### "No base period" is written two ways

- **What:** current well-being uses `_Z`, future well-being leaves the field blank.
- **`wise_mcp`:** both are read as "no base period".

## The method lives outside the data

- **Change thresholds:** what counts as "improving" is set per indicator in the report's Tables 5 and
  6. Some are in other units ("20 minutes" for hours-per-day data). Some are "confidence intervals"
  with no number (PISA, corruption). Four sit only in merged table cells.
- **Headline indicators:** which 36 of the 103 measures are headlines, and their types, appear only
  in the report (Tables 3 and 4).
- **Time periods:** "around 2010" means the earliest year in 2010–15, "2019" the latest in 2016–19,
  "latest" means after 2019 (Box 2.1, Chapter 4).
- **Group gaps:** each group divided by the population average, within ±0.03 counting as no
  difference, is in the Chapter 3 figure notes.
- **Overall scores:** rescaling 0–1, then averaging within and across dimensions, is in a figure note
  in Chapter 4.

`wise_mcp` records all of this in `measures.yaml` and the analysis code, with the report section
cited next to each rule.

## Access

- **Rate limit:** about 60 requests per hour per IP, and reportedly some VPN traffic is blocked.
  `wise_mcp` downloads everything in 2 requests and works from a local copy.
- **Code lists are much bigger than the data:** 3,763 area codes, of which 47 have data here.
- **Four of the six How's Life? datasets repeat a fifth:** the by-age, by-sex, by-education and
  inequality datasets are exact subsets of "current well-being".
- **The report website blocks scripted downloads (HTTP 403),** so the method has to be read by hand.

## MCP notes: lessons from testing with Claude

What asking Claude real questions through the server showed about designing the tools, as opposed
to the data itself.

### Tools should match the questions people ask

- **What:** asked for "the trends in well-being in France", Claude made about 21 tool calls: a
  country profile, a `find_measures` lookup per indicator (the profile listed indicator names but not
  their codes), then `trend` ten times.
- **Idea:** a `country_trends(country, since)` tool that classes all 36 headline indicators for one
  country as improving, deteriorating or no clear change, in a single call. That is exactly what How's
  Life? 2024 Chapter 4 does for each country, so the tool follows the report's own way of looking
  at a country. "What are the trends in France?" then needs 1 call instead of about 20.
- **Status:** built. The profile table now also shows each indicator's code, and the server's
  instructions tell Claude to prefer `country_trends` for a country's overall picture.

## Choices `wise_mcp` makes where the OECD doesn't specify

- Strengths and weaknesses are the top and bottom thirds of members.
- The education gap compares the lowest (primary) and highest (tertiary) groups.
- The gender gap in feeling safe is men's share minus women's.
- A change of exactly the threshold counts as meaningful.
- "Since 2015" (or any year) uses the first year with data in the following five years.
- Only the 38 OECD members are analysed, for now.
- "Better Life 36" is the working name for the overall score: Better Life Index-style weights over
  the How's Life? headline indicators, kept as two scores like the report (current: 24 indicators;
  future: 12). The Better Life Index itself uses a different set of 24 indicators.
- Not built yet: the report's rule for whether a gap between groups is widening or narrowing
  (a change of at least 0.01 in the ratio).

## What would make the data easier to use correctly

Most of the rules above could travel with the data instead of living in report prose:

- whether higher is better, and the change threshold, for each measure (e.g. as SDMX annotations)
- which measures are headlines, and their type
- OECD averages published with the number of countries behind them
- corrected unit labels, and labels that name ratios as ratios
