source(file.path('..','..','r','joint_rotation_settle_issue.R'))
source(file.path('..','..','r','joint_rotation_diagnostics.R'))
test_that('settlement preserves two copies, one factor, and typed zero-bet issues', {
 library(dplyr);library(tidyr)
 python<-Sys.getenv('RETICULATE_PYTHON');expect_true(file.exists(python));reticulate::use_python(python,required=TRUE)
 reticulate::import('sys',convert=FALSE)$path$insert(0L,normalizePath('../..'))
 e<-jsonlite::fromJSON(gzfile('../fixtures/n7_sleeve_numerical.json.gz'),simplifyVector=FALSE)$enumeration
 b<-list(issue=e$issue,fixtures=e$fixtures,sleeves=list(list(id=0L,fixture_indices=as.list(0:6))))
 audit<-bind_rows(e$fixtures) |> select(issue,slot,provider_id,handicap) |> mutate(actual_direction='W',spf_sp=2,status='COMPLETE')
 z<-tibble(issue=e$issue,policy=c('BASE','EXPAND','EXPAND_PROB','ROTATE','ROTATE_PROB'),ticket_id='0:1',sleeve_id=0L,ticket_col_idx=1L,copies=c(1L,2L,2L,0L,0L),base_copies=1L)
 a<-joint_rotation_settle_issue(z,b,audit,list(budget=1024,unit=2,payout_factor=.65),python)
 expect_equal(a$rows$gross,c(166.4,332.8,332.8,0,0),tolerance=1e-8)
 expect_equal(a$rows$stake,c(2,4,4,0,0));expect_equal(a$rows$hits,c(1,2,2,0,0))
 expect_equal(sum(a$bridge$net_change),0,tolerance=1e-8)
 empty<-joint_rotation_settle_issue(z[FALSE,],b,audit,list(budget=1024,unit=2,payout_factor=.65),python)
 expect_equal(empty$rows$gross,rep(0,5));expect_equal(empty$rows$stake,rep(0,5))
 audit$handicap[1]<-audit$handicap[1]+1
 expect_error(joint_rotation_settle_issue(z,b,audit,list(budget=1024,unit=2,payout_factor=.65),python))
})
