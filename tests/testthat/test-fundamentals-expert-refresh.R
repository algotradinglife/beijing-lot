source('../../r/fundamentals_expert_refresh.R')
testthat::test_that('refresh labels preserve identities and reject conflicting records', {
  rows <- tibble::tibble(issue='001',slot=1:4,native_match_id=c('01','02','03','04'),
    status=c('','推迟','', ''),score=c('3-0','1-0','待定','2:2'),source_sha256='hash')
  query <- function(db,issue,play) list(settlement=dplyr::bind_rows(rows,rows),findings=tibble::tibble(),receipt=list())
  x <- query_expert_refresh_labels('unused','001',query)$labels
  testthat::expect_equal(nrow(x),4L)
  testthat::expect_equal(x$provider_id[1],'01')
  testthat::expect_equal(x$actual_home,c(3L,1L,NA_integer_,2L))
  testthat::expect_equal(x$label_status,c('COMPLETED','NON_COMPLETED_STATUS','NO_COMPLETED_SCORE','COMPLETED'))
  testthat::expect_error(query_expert_refresh_labels('x',c('001','001'),query),'unique')
  rows$slot[2] <- 1L
  testthat::expect_error(query_expert_refresh_labels('x','001',query),'Conflicting')
  rows <- rows[0,]
  testthat::expect_equal(nrow(query_expert_refresh_labels('x','001',query)$labels),0L)
})
