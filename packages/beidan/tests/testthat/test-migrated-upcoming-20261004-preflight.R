cutoff <- list(issue_id="P",cutoff_utc=lubridate::ymd_hms("2026-09-25 00:00:00",tz="UTC"))
matches <- tibble::tibble(fixture_id=sprintf("P:%03d",1:14),win=.5,draw=.35,lose=.15)
sp <- tidyr::expand_grid(fixture_id=matches$fixture_id,outcome=c("W","D","L")) |>
 dplyr::mutate(quote_at=cutoff$cutoff_utc-3600,sp_raw=2,source_url="synthetic://prefix-sp")
settings <- beidan::parlay_settings(n_legs=7L,issue_budget_cny=512,unit_cny=2,payout_factor=.65,sp_threshold=.Machine$double.xmax)
pool <- beidan::parlay_construct_role_groups(beidan::rank_outcome_selections(
 beidan::prepare_outcome_selections(matches),cutoff,"coverage"),settings,rep(2L,7),
 max_candidates=2L,prematch_sp=sp)
selected <- beidan::parlay_select_groups(pool,objective="coverage",budget_cny=512,group_budget_cny=256)
labels <- tibble::tibble(issue_id="P",fixture_id=matches$fixture_id,outcome="W",settled_sp=2,
 label_available_at=cutoff$cutoff_utc+86400,status="settled",source_url="synthetic://prefix-labels")

test_that("whole 128-new-ticket groups freeze budget prefixes in purchase order", {
 frozen <- FreezeResearchBudgetPrefixes(selected,c(0,255,256,511,512),128L,2)
 expect_identical(frozen$prefixes$purchased_groups,c(0L,0L,1L,1L,2L))
 expect_identical(frozen$prefixes$purchased_tickets,c(0L,0L,128L,128L,256L))
 expect_equal(frozen$prefixes$stake_cny,c(0,0,256,256,512))
 expect_identical(frozen$prefixes$group_ids[[3]],selected$selection$group_id[1])
 expect_identical(frozen$prefixes$group_ids[[5]],selected$selection$group_id)
 expect_identical(frozen$prefixes$ticket_ids[[3]],
  selected$evaluation$purchases$ticket_id[selected$evaluation$purchases$group_id==selected$selection$group_id[1]])
 # The two seven-leg groups share five fixtures: their intersection has nine
 # distinct fixtures. Independent fixture outcomes, overlapping group events.
 expect_equal(frozen$prefixes$model_coverage[5],2*.85^7-.85^9,tolerance=1e-12)
 expect_equal(frozen$prefixes$model_coverage[3],.85^7,tolerance=1e-12)
 expect_error(FreezeResearchBudgetPrefixes(selected,513,128L,2),"exceeds")
 expect_error(FreezeResearchBudgetPrefixes(selected,c(256,256),128L,2),"unique|duplicated")
 expect_error(FreezeResearchBudgetPrefixes(selected,-1,128L,2))
 expect_error(FreezeResearchBudgetPrefixes(selected,256,127L,2),"quota")
 expect_error(FreezeResearchBudgetPrefixes(selected,256,128.5,2))
 changed <- selected;changed$selection$order <- rev(changed$selection$order)
 expect_error(FreezeResearchBudgetPrefixes(changed,256,128L,2),"binding")
 changed <- selected;changed$receipt$cutoff <- NULL
 expect_error(FreezeResearchBudgetPrefixes(changed,256,128L,2),"binding")
 empty <- FreezeResearchBudgetPrefixes(selected,numeric(),128L,2)
 expect_s3_class(empty$prefixes,"tbl_df")
 expect_identical(nrow(empty$prefixes),0L)
 expect_identical(names(empty$prefixes),names(frozen$prefixes))
 cash <- beidan::parlay_select_groups(pool,objective="coverage",budget_cny=0,group_budget_cny=256)
 cash_frozen <- FreezeResearchBudgetPrefixes(cash,0,128L,2)
 expect_identical(cash_frozen$prefixes$purchased_groups,0L)
 expect_identical(cash_frozen$prefixes$group_ids,list(character()))
})

test_that("prefix settlement uses fixed tickets and applies 0.65 once", {
 frozen <- FreezeResearchBudgetPrefixes(selected,c(0,256,512),128L,2)
 before <- rlang::hash(frozen)
 settled <- SettleResearchBudgetPrefixes(frozen,labels,cutoff$cutoff_utc+172800)
 expect_identical(settled$summary$won_groups,c(0L,1L,2L))
 expect_identical(settled$summary$won_tickets,c(0L,1L,2L))
 expect_equal(settled$summary$payout_cny,c(0,1,2)*2*.65*2^7)
 expect_equal(settled$summary$final_net_cny,c(0,-89.6,-179.2))
 expect_true(is.na(settled$summary$hit_rate[1]))
 expect_true(is.na(settled$summary$roi[1]))
 expect_equal(settled$summary$hit_rate[-1],c(1,1))
 pending <- SettleResearchBudgetPrefixes(frozen,labels,cutoff$cutoff_utc)
 expect_true(all(is.na(pending$summary$final_net_cny[-1])))
 expect_true(all(is.na(pending$summary$hit_rate[-1])))
 changed_labels <- labels;changed_labels$outcome <- "L"
 missed <- SettleResearchBudgetPrefixes(frozen,changed_labels,cutoff$cutoff_utc+172800)
 expect_identical(missed$summary$won_groups,c(0L,0L,0L))
 expect_identical(rlang::hash(frozen),before)
 altered <- frozen;altered$prefixes$group_ids[[2]] <- rev(frozen$prefixes$group_ids[[3]])
 expect_error(SettleResearchBudgetPrefixes(altered,labels,cutoff$cutoff_utc),"binding")
 altered <- frozen;altered$selected$evaluation$cutoff <- NULL
 expect_error(SettleResearchBudgetPrefixes(altered,labels,cutoff$cutoff_utc),"binding")
 expect_error(SettleResearchBudgetPrefixes(frozen,labels,
  lubridate::with_tz(cutoff$cutoff_utc,"Asia/Shanghai")),"UTC")
 empty <- FreezeResearchBudgetPrefixes(selected,numeric(),128L,2)
 empty_settled <- SettleResearchBudgetPrefixes(empty,labels,cutoff$cutoff_utc+172800)
 expect_identical(nrow(empty_settled$summary),0L)
 expect_identical(names(empty_settled$summary),names(settled$summary))
})
