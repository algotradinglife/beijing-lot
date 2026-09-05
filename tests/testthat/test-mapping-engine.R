library(testthat)
library(tidyverse)

project_root <- normalizePath(testthat::test_path("..", ".."))
source(file.path(project_root, "r", "mapping_engine.R"))

fixture_500 <- function() {
  paste0(
    "<select id='expect_select'><option value='120711' selected>120711</option></select>",
    "<table>",
    "<tr class='vs_lines' value=\"{index:'1',leagueName:'英超',homeTeam:'主队',guestTeam:'客队',",
    "endTime:'2012-07-30 20:45',scheduleDate:'2012-07-30',rangqiuNum:'-1'}\" fid='123'><td>x</td></tr>",
    "<tr class='vs_lines' value=\"{index:'2',leagueName:'英超',homeTeam:'取消主队',guestTeam:'取消客队',",
    "endTime:'2012-07-30 20:45',scheduleDate:'2012-07-30',rangqiuNum:'0'}\" fid='-1'><td>x</td></tr>",
    "</table>"
  )
}

fixture_nowscore <- function() {
  paste0(
    "<input id='issueNum' value='120711'><script>",
    "M[1][0] = 719003; M[1][3] = new Date(2012,6,30,12,00,00); ",
    "M[1][16] = 90; M[1][17] = \"主队\"; M[1][20] = \"客队\"; ",
    "M[2][0] = -1; M[2][3] = new Date(2012,6,30,13,00,00); ",
    "M[2][16] = 91; M[2][17] = \"推迟主队\"; M[2][20] = \"推迟客队\";",
    "</script>"
  )
}

test_that("parse_500 keeps valid rows and extracts handicap", {
  out <- parse_500(fixture_500(), "120711")
  expect_s3_class(out, "tbl_df")
  expect_equal(nrow(out), 1)
  expect_equal(out$issue, "120711")
  expect_equal(out$slot, 1)
  expect_equal(out$fid_500, 123L)
  expect_equal(out$handicap_500, -1)
  expect_equal(out$home_500, "主队")
  expect_s3_class(out$schedule_date_500, "Date")
})
test_that("parse_nowscore separates valid provider from void slot", {
  out <- parse_nowscore(fixture_nowscore(), "120711")
  expect_s3_class(out$candidates, "tbl_df")
  expect_equal(out$candidates$slot, 90)
  expect_equal(out$candidates$provider_id, "719003")
  expect_equal(out$void_slots, 91)
  expect_equal(out$team_pairs$home_ns, c("主队", "推迟主队"))
})

test_that("status normalization has stable semantic classes", {
  raw <- c("完场", "取消", "推迟", "中断", "上", "下", "中场", "截止", "20:45")
  expect_equal(
    normalize_status(raw),
    c("finished", "cancelled", "postponed", "suspended", "first_half",
      "second_half", "halftime", "closed", "not_started")
  )
})

test_that("parse_nowscore_status extracts slot, status and cutoff", {
  html <- paste0(
    '<tr id="row_90" matchid="90">',
    '<td title="截止时间：2012-07-30 20:45"><font color=red>完场</font></td>',
    '</tr>'
  )
  out <- parse_nowscore_status(html, "120711")
  expect_equal(out$slot, 90)
  expect_equal(out$status_raw, "完场")
  expect_s3_class(out$cutoff_ns_html, "POSIXct")
})

test_that("resolve_alignment returns same-slot mapping for exact teams", {
  p500 <- tibble(
    issue = "120711", slot = c(1L, 2L), fid_500 = c(1L, 2L),
    home_500 = c("甲", "丙"), away_500 = c("乙", "丁")
  )
  ns <- tibble(
    issue = "120711", slot = c(1L, 2L),
    home_ns = c("甲", "丙"), away_ns = c("乙", "丁"),
    deadline_ns = as.POSIXct(c("2012-07-30", "2012-07-30"), tz = "Asia/Shanghai")
  )
  mapping <- resolve_alignment(p500, ns, "120711")
  expect_equal(unname(mapping), c(1L, 2L))
  expect_equal(names(mapping), c("1", "2"))
})
