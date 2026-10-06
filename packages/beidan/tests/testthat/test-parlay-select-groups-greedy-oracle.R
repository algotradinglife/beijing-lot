test_that("both objectives choose the best feasible actual new purchase independently", {
  cutoff <- list(issue_id="26098",cutoff_utc=lubridate::ymd_hms("2026-09-26 12:00:00",tz="UTC"))
  matches <- tibble::tibble(fixture_id=c("A","B","C"),
    win=c(.55,.60,.52),draw=c(.23,.25,.28),lose=c(.22,.15,.20))
  probabilities <- tidyr::pivot_longer(matches,-fixture_id,names_to="label",values_to="probability") |>
    dplyr::mutate(outcome=c(win="W",draw="D",lose="L")[label])
  sp <- tibble::tibble(fixture_id=rep(c("A","B","C"),each=3),
    outcome=rep(c("W","D","L"),3),quote_at=cutoff$cutoff_utc-60,
    sp_raw=c(3,9,8,2.2,4,3,7,2.5,6),source_url="synthetic://independent-greedy-oracle")
  settings <- parlay_settings();settings$n_legs <- 2L
  pool <- parlay_construct_role_groups(rank_outcome_selections(
    prepare_outcome_selections(matches),cutoff),settings,c(1L,1L),
    max_candidates=NULL,prematch_sp=sp)
  # Enumerate each mask independently. Production space/funding/union helpers are not used.
  candidates <- list()
  candidate_fixtures <- list()
  all_legs <- list()
  for (id in pool$groups$group_id) {
    block <- pool$role_legs[pool$role_legs$group_id==id,]
    block <- dplyr::arrange(block,fixture_id)
    candidate_fixtures[[id]] <- block$fixture_id
    grid <- do.call(tidyr::expand_grid,stats::setNames(block$allowed_outcomes,block$fixture_id))
    keys <- character(nrow(grid));mass <- gross <- numeric(nrow(grid))
    for (j in seq_len(nrow(grid))) {
      outcomes <- as.character(grid[j,])
      keys[j] <- parlay_physical_ticket_key(names(grid),match(outcomes,c("W","D","L")))
      lookup <- paste(names(grid),outcomes)
      mass[j] <- prod(probabilities$probability[match(lookup,paste(probabilities$fixture_id,probabilities$outcome))])
      gross[j] <- 2*.65*prod(sp$sp_raw[match(lookup,paste(sp$fixture_id,sp$outcome))])
      all_legs[[keys[j]]] <- stats::setNames(outcomes,names(grid))
    }
    candidates[[id]] <- tibble::tibble(ticket_id=keys,probability=mass,
      ev=mass*gross-2) |>
      dplyr::arrange(dplyr::desc(probability),ticket_id)
  }
  states <- tidyr::expand_grid(A=c("W","D","L"),B=c("W","D","L"),C=c("W","D","L"))
  state_mass <- rep(1,nrow(states))
  for (fixture in names(states)) {
    row <- probabilities[probabilities$fixture_id==fixture,]
    state_mass <- state_mass*row$probability[match(states[[fixture]],row$outcome)]
  }
  for (objective in c("ev","coverage")) {
    for (budget in c(10,13)) {
      selected <- parlay_select_groups(pool,objective,budget_cny=budget,
        group_budget_cny=4,reuse_policy=list(max_reuse=2L),overlap_policy=list(max_overlap=1L))
      expect_gt(nrow(selected$selection),0L)
      remaining <- pool$groups$group_id
      bought <- character();admitted <- character();spent <- coverage <- 0
      while (length(remaining)) {
        scores <- stats::setNames(rep(-Inf,length(remaining)),remaining)
        probes <- list();coverages <- stats::setNames(rep(NA_real_,length(remaining)),remaining)
        for (id in remaining) {
          fixtures <- candidate_fixtures[[id]]
          reused <- table(c(unlist(candidate_fixtures[admitted],use.names=FALSE),fixtures))
          if (any(reused>2L)) next
          if (length(admitted) && any(vapply(admitted,function(prior)
            length(intersect(fixtures,candidate_fixtures[[prior]]))>1L,logical(1)))) next
          fresh <- candidates[[id]][!candidates[[id]]$ticket_id %in% bought,]
          units <- min(2L,floor((budget-spent)/2),nrow(fresh))
          if (units<1L) next
          fresh <- fresh[seq_len(units),]
          ev <- sum(fresh$ev)
          if (objective=="ev" && ev<=0) next
          hit_any <- rep(FALSE,nrow(states))
          for (ticket in c(bought,fresh$ticket_id)) {
            event <- all_legs[[ticket]]
            hit <- rep(TRUE,nrow(states))
            for (fixture in names(event)) hit <- hit & states[[fixture]]==event[[fixture]]
            hit_any <- hit_any | hit
          }
          coverages[id] <- sum(state_mass[hit_any])
          scores[id] <- if(objective=="ev") ev else coverages[id]-coverage
          probes[[id]] <- fresh
        }
        eligible <- names(scores)[is.finite(scores)]
        if (!length(eligible)) break
        best <- eligible[order(-scores[eligible],eligible,method="radix")][1L]
        step <- length(admitted)+1L
        expect_lte(step,nrow(selected$selection))
        if(step>nrow(selected$selection)) break
        expect_identical(selected$selection$group_id[step],best)
        actual <- selected$evaluation$purchases[selected$evaluation$purchases$group_id==best,]
        expect_identical(actual$ticket_id,probes[[best]]$ticket_id)
        expect_equal(selected$selection$new_ev_cny[step],sum(probes[[best]]$ev),tolerance=1e-12)
        expect_equal(selected$selection$marginal_coverage[step],unname(coverages[best])-coverage,
          tolerance=1e-12)
        bought <- c(bought,probes[[best]]$ticket_id)
        spent <- spent+2*nrow(probes[[best]])
        coverage <- unname(coverages[best])
        admitted <- c(admitted,best);remaining <- setdiff(remaining,best)
      }
      expect_identical(selected$selection$group_id,admitted)
      expect_equal(selected$summary$cost_cny,spent)
      expect_equal(selected$summary$coverage,coverage,tolerance=1e-12)
      expect_equal(selected$evaluation$summary$unspent_cny,budget-spent)
      expect_identical(anyDuplicated(bought),0L)
    }
  }
})
