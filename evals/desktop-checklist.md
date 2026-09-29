# Desktop checklist

The eval questions, asked in Claude Desktop with wise_mcp connected. `results.md` checks the
numbers; this list checks what Claude does with them. Tick a question when the answer has every
item listed.

Every answer:

- [ ] gives the year of each figure
- [ ] says "OECD N" when fewer than 38 members have data
- [ ] ends with the source line
- [ ] uses "improving" / "deteriorating" only past the How's Life? threshold

| # | Question | A good answer also… |
|---|---|---|
| 1 | What was the OECD average life expectancy at birth in 2022? | about 80.6 years, members only |
| 2 | What was the OECD average employment rate in 2023? | about 78% |
| 3 | How much income did OECD households have left after housing costs in 2022? | about 79%, "OECD 36" |
| 4 | What share of employees worked very long hours in 2022, OECD-wide? | about 7%, "OECD 36" |
| 5 | Which three OECD countries have the highest life satisfaction? | Mexico, Iceland, Colombia, each with its (different) year |
| 6 | Which countries have the lowest homicide rates? | Ireland, Japan, Italy: lowest is best |
| 7 | Which country has the smallest gender wage gap? | ranks by distance from 0; notes Luxembourg's negative gap |
| 8 | Has life satisfaction in France improved since 2010? | "no clear change" (+0.05 is under the 0.2 threshold) |
| 9 | Has trust in national government in France changed since 2010? | deteriorating; 2010 stands for 2008–10 and 2025 for 2023–25 |
| 10 | Has trust in others fallen in France since 2013? | deteriorating, with the series breaks as a caveat |
| 11 | How big is the gender gap in feeling safe at night in France? | about 11 points, men minus women |
| 12 | What share of people in France lack social support? | 12.2% from its own measure, not 100 minus social support |
| 13 | How much greenhouse gas does France emit per person? | 5.65 tonnes (not kg) |
| 14 | What was France's carbon footprint per person in 2018? | 9.86 t CO2-equivalent; mentions the CO2-only series |
| 15 | What does measure 1_2 show for France? | the S80/S20 ratio, 4.56 |
| 16 | What is the OECD average trust in others? | 5.68, "OECD 30", years 2018–2025 |
| 17 | Where does France rank on renewable energy supply? | 29th of 38 members |
| 18 | What share of employees in France face job strain? | 25.8% in 2015, flagged as old |
| 19 | Where does France rank on overall well-being? | 17th of 38 on Better Life 36; explains the score |
| 20 | How many of the headline indicators have recent data? | 24 current-well-being headlines after 2019 |

Charts (Desktop only):

- [ ] "Chart trust in government in France and Germany" opens the interactive panel
- [ ] switching tabs, then asking a follow-up, gets an answer about the new chart
- [ ] "Show a map of homicide rates" draws the tile map, blue for low rates
- [ ] a chart no template covers (e.g. "a histogram of life satisfaction across OECD
      countries") uses `custom_chart`, and Claude says it's a custom view
