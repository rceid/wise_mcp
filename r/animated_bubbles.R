# Animated bubble chart: household income vs life expectancy across OECD members, 2004-2023.
#
# After the R Graph Gallery's gganimate Gapminder chart
# (https://r-graph-gallery.com/271-ggplot2-animated-gif-chart-with-gganimate.html), drawn from
# wise_mcp's export of the How's Life? database (r/data/income_life_expectancy.csv).
#
#   Rscript r/animated_bubbles.R
#
# gganimate needs transformr, which pulls in the whole spatial stack (sf, GDAL, PROJ), so this
# does what gganimate does under the hood instead: tweenr interpolates every country between
# years, ggplot draws one PNG per frame, and the gifski command-line tool
# (brew install gifski) joins them into r/output/income_life_expectancy.gif and a dark twin.

source(file.path(dirname(sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE))), "regions.R"))

suppressPackageStartupMessages({
  library(dplyr)
  library(readr)
  library(ggplot2)
  library(tweenr)
})

panel <- read_csv(here("data", "income_life_expectancy.csv"), show_col_types = FALSE) |>
  inner_join(regions, by = "iso3") |>
  mutate(log_income = log10(income))

first_year <- min(panel$year)
last_year <- max(panel$year)
frames_per_year <- 10 # at 20 fps: half a second per year
end_pause <- 40 # frames held on the last year (2 seconds)

# ---- Interpolation ----------------------------------------------------------
# tweenr::tween_elements moves each country (id) through its own years (time) at a steady
# pace, so the dots glide through the years without stopping at each one; a country missing a year simply glides between the years it has. Income is tweened on
# the log scale it's drawn on.

tweened <- panel |>
  transmute(year, iso3, country, region, log_income, life_expectancy, ease = "linear") |>
  tween_elements("year", "iso3", "ease",
                 nframes = (last_year - first_year) * frames_per_year + 1) |>
  as_tibble() |>
  rename(iso3 = .group, frame = .frame) |>
  mutate(region = factor(region, levels = levels(regions$region)))

n_frames <- max(tweened$frame)

# A few countries worth following: the richest, the poorest, the longest-lived,
# the fastest riser, and the largest economy
labelled <- c("USA", "MEX", "JPN", "LUX", "KOR")

x_breaks <- c(10000, 20000, 30000, 50000, 70000)

# ---- One frame ------------------------------------------------------------------

frame_plot <- function(f, p) {
  points <- filter(tweened, frame == f)
  year <- first_year + floor(f / frames_per_year)

  ggplot(points, aes(x = 10^log_income, y = life_expectancy, colour = region)) +
    # the year, large and faint behind the points
    annotate("text", x = 23000, y = 77.6, label = year,
             colour = p$grid, alpha = 0.55, size = 34, family = font, fontface = "bold") +
    geom_point(size = 3.6, alpha = 0.88) +
    geom_text(
      data = filter(points, iso3 %in% labelled) |> mutate(dy = if_else(iso3 == "KOR", -0.55, 0.45)),
      aes(y = life_expectancy + dy, label = country),
      size = 3.1, family = font, show.legend = FALSE
    ) +
    scale_x_log10(
      limits = c(15000, 72000), breaks = x_breaks,
      labels = scales::label_dollar(scale = 1e-3, suffix = "k", accuracy = 1)
    ) +
    scale_y_continuous(limits = c(68, 86), breaks = seq(68, 84, 4)) +
    scale_colour_manual(values = p$fill, name = NULL, drop = FALSE) +
    labs(
      title = "Richer and longer-lived, until COVID",
      subtitle = "Household disposable income per person (USD, PPP, log scale) and life expectancy at birth",
      x = NULL, y = "Life expectancy (years)",
      caption = paste(
        "Source: OECD How's Life? well-being database. Income in current dollars, not adjusted",
        "for inflation. Members without both series are not shown."
      )
    ) +
    theme_minimal(base_family = font, base_size = 11) +
    theme(
      plot.background = element_rect(fill = p$bg, colour = NA),
      panel.grid.major = element_line(colour = p$grid, linewidth = 0.3),
      panel.grid.minor = element_blank(),
      axis.text = element_text(colour = p$ink3),
      axis.title.y = element_text(colour = p$ink3, size = 9.5, margin = margin(r = 8)),
      plot.title = element_text(colour = p$ink, size = 16, face = "bold"),
      plot.subtitle = element_text(colour = p$ink2, size = 9.5, margin = margin(b = 10)),
      plot.caption = element_text(colour = p$ink3, size = 7.5, hjust = 0),
      plot.title.position = "plot",
      plot.caption.position = "plot",
      legend.position = "top",
      legend.justification = "left",
      legend.text = element_text(colour = p$ink2, size = 8.5),
      legend.key.spacing.x = unit(6, "pt"),
      legend.margin = margin(0, 0, 0, -6),
      plot.margin = margin(16, 20, 12, 16)
    ) +
    guides(colour = guide_legend(nrow = 2, override.aes = list(size = 3, alpha = 1)))
}

# ---- Render ---------------------------------------------------------------------

dir.create(here("output"), showWarnings = FALSE)
for (theme in names(palettes)) {
  suffix <- if (theme == "light") "" else "_dark"
  frames <- file.path(tempdir(), paste0("frames", suffix))
  unlink(frames, recursive = TRUE)
  dir.create(frames)

  sequence <- c(seq_len(n_frames), rep(n_frames, end_pause))
  for (i in seq_along(sequence)) {
    ggsave(file.path(frames, sprintf("frame%04d.png", i)), frame_plot(sequence[i], palettes[[theme]]),
           width = 1000 / 140, height = 700 / 140, dpi = 140, device = "png", type = "cairo")
  }

  gif <- here("output", paste0("income_life_expectancy", suffix, ".gif"))
  pngs <- sort(list.files(frames, pattern = "\\.png$", full.names = TRUE))
  status <- system2("gifski", c("--fps", "20", "--quality", "85", "--width", "1000",
                                "-o", shQuote(gif), shQuote(pngs)))
  stopifnot(status == 0)
  message("wrote ", gif, " (", length(pngs), " frames)")

  # the last frame as a still, for places a GIF can't go
  file.copy(pngs[length(pngs)], here("output", paste0("income_life_expectancy_still", suffix, ".png")),
            overwrite = TRUE)
}
