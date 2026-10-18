test_that('category maxima equal explicit first mapping, with deterministic ties', {
  cutoff <- list(issue_id='26104',cutoff_utc=as.POSIXct('2026-10-14',tz='UTC'))
  margins <- tidyr::expand_grid(fixture_id=paste0('26104:',1:7),margin=c(-1,0,1,2)) |>
    dplyr::mutate(handicap=-1,probability=rep(c(.15,.25,.35,.25),7))
  legs <- tibble::tibble(group_slot=1L,fixture_id=paste0('26104:',1:7))
  decision <- list(cutoff=cutoff,margins=margins,legs=legs)
  decision$receipt <- list(cutoff=cutoff,input_hash=rlang::hash(list(margins=margins,legs=legs)),
    source_hashes=list(raw=paste(rep('a',64),collapse='')),
    max_source_available_utc=cutoff$cutoff_utc-1)
  actual <- RankFirstMarginTickets(decision,4)
  bins <- tidyr::expand_grid(!!!setNames(rep(list(1:4),7),legs$fixture_id))
  score <- rep(0,nrow(bins));tokens <- vector('list',7)
  for (j in 1:7) {
    m <- margins[margins$fixture_id==legs$fixture_id[j],]
    k <- bins[[j]]
    score <- score+log(m$probability[k])
    tokens[[j]] <- paste0(legs$fixture_id[j],':',ifelse(m$margin[k]-1>0,1,ifelse(m$margin[k]-1==0,2,3)))
  }
  explicit <- tibble::tibble(ticket_id=do.call(paste,c(tokens,sep='|')),log_scenario_score=score) |>
    dplyr::arrange(dplyr::desc(log_scenario_score),ticket_id) |>
    dplyr::distinct(ticket_id,.keep_all=TRUE)
  expect_equal(nrow(actual$tickets),2187)
  expect_equal(actual$tickets$ticket_id,explicit$ticket_id)
  expect_equal(actual$tickets$log_scenario_score,explicit$log_scenario_score,tolerance=1e-14)
  expect_equal(sum(actual$tickets$retained_ticket_mass),1,tolerance=1e-12)
  shallow <- RankFirstMarginTickets(decision,1)
  expect_equal(nrow(shallow$tickets),1)
  expect_true(all(shallow$retained$outcome=='D'))
  expect_equal(shallow$tickets$scenario_score,.35^7)
  expect_false(shallow$receipt$normalized)
  expect_equal(RankFirstMarginTickets(decision,Inf)$tickets,actual$tickets)
  for(depth in list(0,-1,NA_real_,1.5)) expect_error(RankFirstMarginTickets(decision,depth),'depth')
  broken <- decision;broken$cutoff$cutoff_utc <- cutoff$cutoff_utc+1
  expect_error(RankFirstMarginTickets(broken,4),'receipt')
  broken <- decision;broken$margins$probability[1] <- .9
  expect_error(RankFirstMarginTickets(broken,4),'receipt')
  broken <- decision;broken$receipt$max_source_available_utc <- cutoff$cutoff_utc
  expect_error(RankFirstMarginTickets(broken,4),'receipt')
  broken <- decision;broken$legs <- broken$legs[-1,]
  broken$receipt$input_hash <- rlang::hash(list(margins=broken$margins,legs=broken$legs))
  expect_error(RankFirstMarginTickets(broken,4),'contract|seven-leg')
})
