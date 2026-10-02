# Interactive Gapminder-style chart: household income vs life expectancy, 2004-2023.
#
# The plotly twin of animated_bubbles.R: play the years, drag the slider, hover any country.
# Source and units: OECD How's Life? well-being database; household disposable income per
# person in current US dollars at PPP (log scale), life expectancy at birth in years.
#
#   Rscript r/interactive_bubbles.R
#
# Writes output/income_life_expectancy.html and a dark-theme twin (needs pandoc to inline
# plotly.js into one file: brew install pandoc).

source(file.path(dirname(sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE))), "regions.R"))

suppressPackageStartupMessages({
  library(dplyr)
  library(readr)
  library(plotly)
})

panel <- read_csv(here("data", "income_life_expectancy.csv"), show_col_types = FALSE) |>
  inner_join(regions, by = "iso3") |>
  arrange(year, region, iso3)

# A few countries worth following, labelled as they move
labelled <- c("USA", "MEX", "JPN", "LUX", "KOR")

x_ticks <- c(20000, 30000, 50000, 70000)

bubbles <- function(p) {
  axis <- function(title) {
    list(title = list(text = title, font = list(size = 12, color = p$ink3)),
         gridcolor = p$grid, zeroline = FALSE, linecolor = p$grid,
         tickfont = list(color = p$ink3, size = 11), fixedrange = TRUE)
  }

  plot_ly(panel, x = ~income, y = ~life_expectancy, frame = ~year, ids = ~iso3) |>
    add_markers(
      color = ~region, colors = setNames(p$fill, levels(regions$region)),
      text = ~country,
      marker = list(size = 12, opacity = 0.88, line = list(width = 1, color = p$bg)),
      hovertemplate = paste(
        "<b>%{text}</b><br>Income $%{x:,.0f}<br>Life expectancy %{y:.1f} years",
        "<extra>%{fullData.name}</extra>"
      )
    ) |>
    add_text(
      data = filter(panel, iso3 %in% labelled),
      text = ~country, textposition = "top center", showlegend = FALSE, hoverinfo = "skip",
      textfont = list(size = 11, color = p$ink2)
    ) |>
    layout(
      title = list(
        text = "<b>Richer and longer-lived, until COVID</b>",
        x = 0.02, xanchor = "left", y = 0.97, yref = "container", yanchor = "top",
        font = list(size = 18, color = p$ink)
      ),
      xaxis = c(axis("Household income per person"),
                list(type = "log", range = log10(c(15000, 72000)),
                     tickvals = x_ticks, ticktext = paste0("$", x_ticks / 1000, "k"))),
      yaxis = c(axis("Life expectancy (years)"), list(range = c(68, 86.5))),
      paper_bgcolor = p$bg, plot_bgcolor = p$bg,
      font = list(family = paste0(font, ", Arial, sans-serif"), color = p$ink2),
      # inside the plot, bottom right: rich but short-lived, a corner no country reaches
      legend = list(x = 0.99, xanchor = "right", y = 0.02, yanchor = "bottom",
                    bgcolor = p$bg, bordercolor = p$grid, borderwidth = 1,
                    font = list(size = 11, color = p$ink2), itemclick = "toggleothers"),
      hoverlabel = list(bgcolor = p$bg, bordercolor = p$grid,
                        font = list(color = p$ink, size = 12)),
      margin = list(t = 60, r = 20, b = 40, l = 60)
    ) |>
    animation_opts(frame = 600, transition = 600, easing = "linear", redraw = FALSE) |>
    animation_slider(
      currentvalue = list(prefix = "", font = list(size = 16, color = p$ink)),
      font = list(color = p$ink3), bordercolor = p$grid, tickcolor = p$grid,
      activebgcolor = p$fill[1], bgcolor = p$grid, pad = list(t = 50)
    ) |>
    animation_button(
      x = 0, xanchor = "left", y = -0.18, yanchor = "top",
      font = list(color = p$ink), bgcolor = p$bg, bordercolor = p$grid
    ) |>
    config(displayModeBar = FALSE, responsive = TRUE)
}

dir.create(here("output"), showWarnings = FALSE)
for (theme in names(palettes)) {
  suffix <- if (theme == "light") "" else "_dark"
  path <- here("output", paste0("income_life_expectancy", suffix, ".html"))
  # plotly's "basic" build has everything a scatter needs, at about a quarter of the size
  widget <- partial_bundle(bubbles(palettes[[theme]]), type = "basic", local = TRUE)
  widget$sizingPolicy$padding <- 0
  widget$sizingPolicy$browser$fill <- TRUE
  htmlwidgets::saveWidget(widget, path, selfcontained = TRUE, background = palettes[[theme]]$bg,
                          title = "Household income and life expectancy, 2004-2023")
  unlink(sub("\\.html$", "_files", path), recursive = TRUE) # saveWidget's leftover libraries
  message("wrote ", basename(path))
}
