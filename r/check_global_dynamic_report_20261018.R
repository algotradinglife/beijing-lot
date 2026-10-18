# Rscript r/check_global_dynamic_report_20261018.R ROOT
# Executed HTML regression: every command/evidence row must remain literal and aligned.
args<-commandArgs(TRUE);stopifnot(length(args)==1L)
root<-normalizePath(args[1],mustWork=TRUE);setwd(root)
suppressPackageStartupMessages(library(tidyverse));library(testthat)
a<-jsonlite::fromJSON('results/global-dynamic-walkforward-20261018/acceptance.json')
doc<-xml2::read_html('quarto/global_dynamic_walkforward_20261018.html')
tables<-rvest::html_table(doc,trim=FALSE);matches<-list()
for(t in tables)if(all(c('check','command','exit_status','evidence')%in%names(t)))matches[[length(matches)+1L]]<-as_tibble(t)
test_that('rendered acceptance keeps every literal command paired with its evidence',{
 expect_length(matches,1L)
 shown<-matches[[1]];expected<-as_tibble(a$checks)
 expect_equal(nrow(shown),nrow(expected))
 expect_identical(shown$check,expected$check)
 expect_equal(shown$exit_status,expected$exit_status)
 for(i in seq_len(nrow(expected))) {
  expect_identical(shown$command[i],expected$command[i])
  expect_identical(shown$evidence[i],expected$evidence[i])
 }
 code<-xml2::xml_find_all(doc,'.//table//td/code')
 expect_length(code,nrow(expected))
 expect_true(any(grepl('$R_LIBS_USER',xml2::xml_text(code),fixed=TRUE)))
 expect_true(any(grepl('$PWD',xml2::xml_text(code),fixed=TRUE)))
})
