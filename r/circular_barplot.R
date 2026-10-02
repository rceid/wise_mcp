# Circular barplot with groups: life satisfaction across OECD members, by region.
#
# After the R Graph Gallery's "circular barplot with groups"
# (https://r-graph-gallery.com/297-circular-barplot-with-groups.html), drawn from
# wise_mcp's export of the How's Life? database (r/data/life_satisfaction.csv).
#
#   Rscript r/circular_barplot.R
#
# Writes r/output/life_satisfaction_circular.png and a dark-theme twin.

library(dplyr)
library(readr)
library(ggplot2)

source(file.path(dirname(sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE))), "regions.R"))

# ---- Data ------------------------------------------------------------------

satisfaction <- read_csv(here("data", "life_satisfaction.csv"), show_col_types = FALSE) |>
  inner_join(regions, by = "iso3")

stopifnot(nrow(satisfaction) == 34) # every member with data (one not shown) has a region

# The OECD average as How's Life? computes it: a simple mean over members with data
oecd_average <- mean(satisfaction$value)

# ---- Layout: bars in groups, with empty bars as gaps between groups --------

empty_bar <- 2

layout <- satisfaction |>
  arrange(region, desc(value)) |>
  group_by(region) |>
  group_modify(~ bind_rows(.x, tibble(value = rep(NA_real_, empty_bar)))) |>
  ungroup() |>
  mutate(id = row_number())

n_bars <- nrow(layout)

# Label angle: perpendicular to the circle, flipped on the left half to stay readable
labels <- layout |>
  filter(!is.na(value)) |>
  mutate(
    angle = 90 - 360 * (id - 0.5) / n_bars,
    hjust = ifelse(angle < -90, 1, 0),
    angle = ifelse(angle < -90, angle + 180, angle),
    text = sprintf("%s  %.1f", country, value)
  )

# One arc under each group
groups <- layout |>
  filter(!is.na(value)) |>
  group_by(region) |>
  summarise(start = min(id) - 0.4, end = max(id) + 0.4, .groups = "drop")

circular_barplot <- function(p, titles = TRUE) {
  ggplot(layout, aes(x = id, y = value)) +
    geom_col(aes(fill = region), width = 0.82, na.rm = TRUE) +
    # OECD average: a dashed ring across every bar
    geom_hline(yintercept = oecd_average, colour = p$ink, linewidth = 0.35, linetype = "22") +
    geom_text(
      data = labels, aes(x = id, y = value + 0.35, label = text, angle = angle, hjust = hjust),
      colour = p$ink2, size = 2.55, family = font, inherit.aes = FALSE
    ) +
    # an arc under each group, in its colour
    geom_segment(
      data = groups, aes(x = start, xend = end, y = -0.6, yend = -0.6, colour = region),
      linewidth = 0.9, inherit.aes = FALSE, show.legend = FALSE
    ) +
    scale_fill_manual(values = p$fill, name = NULL) +
    scale_colour_manual(values = p$fill) +
    scale_y_continuous(limits = c(-8.5, 13)) +
    coord_polar(start = 0) +
    labs(
      title = "Life satisfaction across the OECD",
      subtitle = sprintf(
        "Each member's latest year, 0–10 scale. Dashed ring: OECD average (%.2f, %d members).",
        oecd_average, nrow(satisfaction)
      ),
      caption = paste(
        "Source: OECD How's Life? well-being database; methods of How's Life? 2024.",
        "Members without data are not shown.",
        sep = "\n"
      )
    ) +
    theme_void(base_family = font) +
    theme(
      plot.background = element_rect(fill = p$bg, colour = NA),
      plot.title = element_text(colour = p$ink, size = 17, face = "bold", hjust = 0.5,
                                margin = margin(t = 14, b = 4)),
      plot.subtitle = element_text(colour = p$ink2, size = 9.5, hjust = 0.5),
      plot.caption = element_text(colour = p$ink3, size = 7.5, hjust = 0.5,
                                  margin = margin(b = 12), lineheight = 1.2),
      plot.margin = margin(4, 4, 4, 4),
      # the region key sits in the hole in the middle
      legend.position = "inside",
      legend.position.inside = c(0.5, 0.487),
      legend.text = element_text(colour = p$ink2, size = 8.5),
      legend.key.size = unit(10, "pt"),
      legend.key.spacing.y = unit(3, "pt"),
      legend.background = element_blank()
    ) +
    # the website card shows the chart on its own, with the title beside it
    if (!titles) labs(title = NULL, subtitle = NULL, caption = NULL)
}

# ---- Render ----------------------------------------------------------------

dir.create(here("output"), showWarnings = FALSE)
for (theme in names(palettes)) {
  suffix <- if (theme == "light") "" else "_dark"
  path <- here("output", paste0("life_satisfaction_circular", suffix, ".png"))
  ggsave(path, circular_barplot(palettes[[theme]]),
         width = 7, height = 7.4, dpi = 220, device = "png", type = "cairo")
  card <- here("output", paste0("life_satisfaction_circular_card", suffix, ".png"))
  ggsave(card, circular_barplot(palettes[[theme]], titles = FALSE),
         width = 6.4, height = 6.4, dpi = 220, device = "png", type = "cairo")
  message("wrote ", path, " and ", card)
}
