# Circular barplot with groups: trust in national government across OECD members, by region.
#
# After the R Graph Gallery's "circular barplot with groups"
# (https://r-graph-gallery.com/297-circular-barplot-with-groups.html), drawn from
# wise_mcp's export of the How's Life? database (r/data/trust_government.csv).
#
#   Rscript r/circular_barplot.R
#
# Writes, each with a dark-theme twin (*_dark):
#   output/trust_government_circular.png       the chart
#   output/trust_government_circular.html      interactive version (ggiraph): hover a bar
#   output/trust_government_circular_card.html the website card: interactive, 16:10, no country
#                                              labels, a region legend beside the circle

suppressPackageStartupMessages({
  library(dplyr)
  library(readr)
  library(ggplot2)
  library(ggiraph)
})

source(file.path(dirname(sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE))), "regions.R"))

# ---- Data ------------------------------------------------------------------

trust <- read_csv(here("data", "trust_government.csv"), show_col_types = FALSE) |>
  inner_join(regions, by = "iso3")

stopifnot(nrow(trust) == 37) # every member shown has a region

# The OECD average as How's Life? reports it: a simple mean over every member with data
average <- read_csv(here("data", "oecd_averages.csv"), show_col_types = FALSE) |>
  filter(measure == "trust_government")
period <- "2023–25" # the latest pooled survey period, the same for every member

# ---- Layout: bars in groups, with empty bars as gaps between groups --------

empty_bar <- 2

layout <- trust |>
  arrange(region, desc(value)) |>
  group_by(region) |>
  group_modify(~ bind_rows(.x, tibble(value = rep(NA_real_, empty_bar)))) |>
  ungroup() |>
  mutate(
    id = row_number(),
    tooltip = sprintf("<b>%s</b><br>%.0f%% trust their government<br>%s", country, value, region)
  )

n_bars <- nrow(layout)

# Label angle: perpendicular to the circle, flipped on the left half to stay readable
labels <- layout |>
  filter(!is.na(value)) |>
  mutate(
    angle = 90 - 360 * (id - 0.5) / n_bars,
    hjust = ifelse(angle < -90, 1, 0),
    angle = ifelse(angle < -90, angle + 180, angle),
    text = country
  )

# One arc under each group
groups <- layout |>
  filter(!is.na(value)) |>
  group_by(region) |>
  summarise(start = min(id) - 0.4, end = max(id) + 0.4, .groups = "drop") |>
  mutate(tooltip = as.character(region))

circular_barplot <- function(p, card = FALSE) {
  chart <- ggplot(layout, aes(x = id, y = value)) +
    geom_col_interactive(
      aes(fill = region, tooltip = tooltip, data_id = iso3),
      width = 0.82, na.rm = TRUE
    ) +
    # OECD average: a dashed ring across every bar
    geom_hline(yintercept = average$value, colour = p$ink, linewidth = 0.35, linetype = "22") +
    # an arc under each group, in its colour
    geom_segment_interactive(
      data = groups,
      aes(x = start, xend = end, y = -6, yend = -6, colour = region, tooltip = tooltip, data_id = region),
      linewidth = 0.9, inherit.aes = FALSE, show.legend = FALSE
    ) +
    scale_fill_manual(values = p$fill) +
    scale_colour_manual(values = p$fill) +
    labs(
      title = "Trust in national government across the OECD",
      subtitle = sprintf(
        "Share of people aged 15+, %s. Dashed ring: OECD average (%.0f%%, %d members).",
        period, average$value, average$countries
      ),
      caption = paste(
        "Source: OECD How's Life? well-being database; methods of How's Life? 2024.",
        "Not every member is shown.",
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
      legend.position = "none"
    )

  if (!card) {
    return(chart +
      geom_text(
        data = labels, aes(x = id, y = value + 3.5, label = text, angle = angle, hjust = hjust),
        colour = p$ink2, size = 2.55, family = font, inherit.aes = FALSE
      ) +
      scale_y_continuous(limits = c(-55, 130)) +
      coord_polar(start = 0))
  }

  # The website card: no country labels (the tooltip names each bar), so the circle can fill
  # the frame, and a region legend in the space beside it
  chart +
    scale_y_continuous(limits = c(-38, 84)) +
    coord_radial(start = 0, expand = FALSE) +
    labs(
      subtitle = sprintf(
        "Share of people aged 15+, %s. Dashed ring: OECD average (%.0f%%).",
        period, average$value
      ),
      caption = NULL, fill = NULL
    ) +
    theme(
      plot.title = element_text(colour = p$ink, size = 20, face = "bold", hjust = 0.5,
                                margin = margin(t = 10, b = 4)),
      # the circle fills only the middle 80% of its panel: negative margins let the panel run
      # under the subtitle and off the bottom edge, so the circle fills the frame's height
      plot.subtitle = element_text(colour = p$ink2, size = 12.5, hjust = 0.5, margin = margin(b = -30)),
      plot.title.position = "plot",
      plot.margin = margin(2, 10, -50, 10),
      legend.position = "right",
      legend.text = element_text(colour = p$ink2, size = 12.5),
      legend.key.size = unit(14, "pt"),
      legend.key.spacing.y = unit(5, "pt")
    )
}

# The interactive version uses a system font (Helvetica on Macs; Windows substitutes Arial)
# instead of ggiraph's default bundle of Liberation fonts, which adds 8 MB to the page
web_fonts <- gdtools::font_set(sans = "Helvetica")
web_fonts$dependencies <- list() # don't attach Liberation fonts for the unused families

# Hover styling for the interactive version, in the chart's own palette
interactive <- function(p, card = FALSE) {
  font <<- "Helvetica"
  on.exit(font <<- "Helvetica Neue")
  girafe(
    ggobj = circular_barplot(p, card),
    width_svg = if (card) 8 else 7, height_svg = if (card) 5 else 7.4,
    font_set = web_fonts, bg = p$bg,
    options = list(
      opts_hover(css = sprintf("stroke:%s;stroke-width:1.5px;", p$ink)),
      opts_hover_inv(css = "opacity:0.35;"),
      opts_tooltip(
        css = sprintf(paste(
          "background:%s;color:%s;border:1px solid %s;border-radius:4px;padding:6px 9px;",
          "font-family:Helvetica,Arial,sans-serif;font-size:12px;line-height:1.45;"
        ), p$bg, p$ink, p$grid),
        opacity = 1, use_fill = FALSE
      ),
      opts_selection(type = "none"),
      opts_toolbar(saveaspng = FALSE, hidden = c("selection", "zoom", "misc")),
      opts_sizing(rescale = TRUE, width = 1)
    )
  )
}

# ---- Render ----------------------------------------------------------------

dir.create(here("output"), showWarnings = FALSE)
for (theme in names(palettes)) {
  suffix <- if (theme == "light") "" else "_dark"
  p <- palettes[[theme]]
  out <- function(kind) here("output", paste0("trust_government_circular", kind, suffix))

  ggsave(paste0(out(""), ".png"), circular_barplot(p),
         width = 7, height = 7.4, dpi = 220, device = "png", type = "cairo")
  for (card in c(FALSE, TRUE)) {
    file <- out(if (card) "_card" else "")
    widget <- interactive(p, card)
    widget$sizingPolicy$padding <- 0 # fill the page (or the website's frame) edge to edge
    widget$sizingPolicy$browser$fill <- TRUE
    htmlwidgets::saveWidget(widget, paste0(file, ".html"),
                            selfcontained = TRUE, background = p$bg,
                            title = "Trust in national government across the OECD")
    unlink(paste0(file, "_files"), recursive = TRUE) # saveWidget's leftover libraries
  }
  message("wrote ", basename(out("")), " (.png, .html, _card.html)")
}
