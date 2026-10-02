# Regions used to group and colour OECD members in the R charts, with their colours.
# Sourced by circular_barplot.R and animated_bubbles.R.

regions <- dplyr::tribble(
  ~region,                     ~iso3,
  "Nordic",                    c("DNK", "FIN", "ISL", "NOR", "SWE"),
  "Western Europe",            c("AUT", "BEL", "CHE", "DEU", "FRA", "GBR", "IRL", "LUX", "NLD"),
  "Central & Eastern Europe",  c("CZE", "EST", "HUN", "LTU", "LVA", "POL", "SVK", "SVN"),
  "Southern Europe",           c("ESP", "GRC", "ITA", "PRT", "TUR"),
  "Americas",                  c("CAN", "CHL", "COL", "CRI", "MEX", "USA"),
  "Asia-Pacific",              c("AUS", "JPN", "KOR", "NZL")
) |>
  tidyr::unnest(iso3) |>
  dplyr::mutate(region = factor(region, levels = unique(region)))

# Categorical palette in region order, validated for colour-blind separation on each surface
palettes <- list(
  light = list(
    bg = "#f7f1e9", ink = "#2a2622", ink2 = "#4a453f", ink3 = "#7d766d", grid = "#d9d2c6",
    fill = c("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300")
  ),
  dark = list(
    bg = "#18130e", ink = "#ede7df", ink2 = "#c9c3bc", ink3 = "#98918b", grid = "#3d3732",
    fill = c("#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300")
  )
)

font <- "Helvetica Neue"

# The folder this script lives in, so it runs from any working directory
here <- function(...) {
  args <- commandArgs(trailingOnly = FALSE)
  script <- sub("^--file=", "", args[grep("^--file=", args)])
  base <- if (length(script)) dirname(normalizePath(script)) else "r"
  file.path(base, ...)
}
