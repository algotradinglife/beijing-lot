#' Make an explicit three-fixture complete-space research decision
#' @param probabilities Optional complete normalized probabilities tibble.
#' @return Bound synthetic decision; exercised by oracle tests below.
#' @noRd
MarginResearchDecision <- function(probabilities = NULL) {
  q <- if(!is.null(probabilities)) probabilities else tibble::tibble(fixture_id=rep(c("A","B","C"),each=3),
    outcome=rep(c("W","D","L"),3),probability=c(.6,.25,.15,.5,.3,.2,.4,.35,.25))
  cutoff <- list(issue_id="009",cutoff_utc=lubridate::ymd_hms("2026-10-10 00:00:00",tz="UTC"))
  blocks <- list()
  for(g in c("g1","g2")) {
    fx <- if(g=="g1")c("A","B")else c("B","C")
    legs <- tibble::tibble(group_id=g,fixture_id=fx,leg_order=1:2)
    supports <- q |> dplyr::filter(fixture_id %in% fx) |>
      dplyr::transmute(candidate_id=paste0(g,"|2"),fixture_id,outcome,allowed=TRUE,
        preference=match(outcome,c("W","D","L")))
    space <- parlay_enumerate_tickets(legs,q,cutoff=cutoff,supports=supports,n_legs=2L)
    blocks[[g]] <- parlay_rank_tickets(space$tickets,space$candidate_tickets,
      cutoff=cutoff,ranking="probability_desc") |>
      dplyr::select(group_id,ticket_id,probability,rank)
  }
  d <- list(cutoff=cutoff,probabilities=q,candidates=dplyr::bind_rows(blocks),
    source_bindings=list(snapshot="synthetic-complete-space"))
  d$source_receipt <- list(cutoff=cutoff,probability_hash=rlang::hash(q),
    candidate_hash=rlang::hash(d$candidates),max_source_available_utc=cutoff$cutoff_utc-60,
    source_snapshots=list(snapshot=strrep("a",64)))
  d$input_hash <- rlang::hash(d)
  d
}

test_that("full-space purchases match independently integrated union probabilities", {
  d <- MarginResearchDecision()
  x <- SelectJointOutcomeTickets(d,2L,2L,2,27)
  expect_s3_class(x$purchases,"tbl_df")
  expect_equal(nrow(x$purchases),16L)
  expect_equal(x$receipt$worlds,27)
  states <- tidyr::expand_grid(A=1:3,B=1:3,C=1:3)
  pm <- d$probabilities$probability
  mass <- pm[states$A]*pm[3+states$B]*pm[6+states$C]
  for(policy in unique(x$purchases$policy)) {
    bought <- dplyr::filter(x$purchases,.data$policy==.env$policy)
    hit <- rep(FALSE,27)
    for(ticket in bought$ticket_id) {
      tokens <- strsplit(ticket,"|",fixed=TRUE)[[1]]
      a <- rep(TRUE,27)
      for(token in tokens) a <- a & states[[sub(":.*","",token)]]==as.integer(sub(".*:","",token))
      hit <- hit | a
    }
    trace <- dplyr::filter(x$trace,.data$policy==.env$policy)
    expect_equal(tail(trace$cumulative_coverage,1),sum(mass[hit]),tolerance=1e-12)
    expect_equal(tail(trace$cost_cny,1),8)
    expect_true(all(diff(trace$cumulative_coverage)>=-1e-12))
    expect_equal(trace$min_rank[1],if(policy=="FIXED")2L else 1L)
  }
  expect_identical(SelectJointOutcomeTickets(d,2L,2L,2,27),x)
  expect_error(SelectJointOutcomeTickets(d,2L,2L,2,26),"resource")
  expect_error(SelectJointOutcomeTickets(d,0L,2L,2,27))
  d$candidates$rank[1] <- 8L
  d$source_receipt$candidate_hash <- rlang::hash(d$candidates)
  d$input_hash <- rlang::hash(d[setdiff(names(d),"input_hash")])
  expect_error(SelectJointOutcomeTickets(d,2L,2L,2,27),"ranked space")
})

test_that("shared calibration excludes target and future rows and predicts reproducibly", {
  root <- Sys.getenv("BEIDAN_REPO_ROOT",unset=normalizePath("../../../..",mustWork=FALSE))
  python <- Sys.getenv("BEIDAN_TEST_PYTHON",unset=file.path(root,".venv/bin/python"))
  d <- MarginResearchDecision(); n <- 210L; k <- seq_len(n)
  history <- tibble::tibble(fixture_id=paste0("H",k),issue_code="008",issue_year=2026L,
    label_available_ts="2026-10-01T00:00:00Z",data_available_ts="2026-09-30T00:00:00Z",
    actual_outcome=c("W","W","W","D","D","L","L")[(k-1L)%%7L+1L],
    W=.45,D=.25,L=.3,entropy=1.2+(k%%11)/20,local_mass=.4+(k%%13)/30)
  policy <- list(prior_issues="008",features=c("entropy","local_mass"),minimum_ess=100,
    minimum_class_count=15L,epsilon=1e-8)
  fit <- FitMarginShapeCalibration(history,d$cutoff,policy,list(snapshot=strrep("b",64)),root,python)
  features <- tibble::tibble(fixture_id="T",W=.45,D=.25,L=.3,entropy=1.4,local_mass=.6)
  decision <- list(cutoff=d$cutoff,features=features,receipt=list(cutoff=d$cutoff,
    feature_hash=rlang::hash(features),max_source_available_utc=d$cutoff$cutoff_utc-60))
  p <- PredictMarginShapeCalibration(fit,decision)
  expect_s3_class(p,"tbl_df");expect_equal(sum(p$probability),1)
  expect_true(all(p$probability>0));expect_equal(nrow(fit$admitted),210L)
  expect_equal(nrow(fit$ledger),210L)
  expect_equal(fit$receipt$target_issue,"009")
  expect_identical(PredictMarginShapeCalibration(fit,decision),p)
  path <- tempfile(fileext=".rds");saveRDS(fit,path)
  restored <- readRDS(path)
  expect_identical(restored,fit)
  expect_identical(PredictMarginShapeCalibration(restored,decision),p)
  independent <- FitMarginShapeCalibration(history,d$cutoff,policy,list(snapshot=strrep("b",64)),root,python)
  expect_identical(independent,fit)
  extra <- history[1:2,];extra$fixture_id <- c("TARGET","FUTURE")
  extra$issue_code <- c("009","010")
  extra$label_available_ts <- c("2026-10-01T00:00:00Z","2026-10-11T00:00:00Z")
  h <- dplyr::bind_rows(history,extra)
  changed <- FitMarginShapeCalibration(h,d$cutoff,policy,list(snapshot=strrep("b",64)),root,python)
  expect_equal(changed$coefficients,fit$coefficients)
  expect_equal(PredictMarginShapeCalibration(changed,decision),p)
  extra$actual_outcome <- "D"
  extra$label_available_ts <- "2026-10-01T00:00:00Z"
  extra$W <- NA_real_
  h <- dplyr::bind_rows(history,extra)
  mutated <- FitMarginShapeCalibration(h,d$cutoff,policy,list(snapshot=strrep("b",64)),root,python)
  expect_equal(PredictMarginShapeCalibration(mutated,decision),p)
  q <- tibble::tibble(fixture_id=rep(c("A","B","C"),each=3),
    outcome=rep(p$outcome,3),probability=rep(p$probability,3))
  q2 <- PredictMarginShapeCalibration(mutated,decision)
  q2 <- tibble::tibble(fixture_id=rep(c("A","B","C"),each=3),
    outcome=rep(q2$outcome,3),probability=rep(q2$probability,3))
  expect_identical(SelectJointOutcomeTickets(MarginResearchDecision(q),2L,2L,2,27),
    SelectJointOutcomeTickets(MarginResearchDecision(q2),2L,2L,2,27))
  global <- policy;global$features <- character()
  gf <- FitMarginShapeCalibration(history,d$cutoff,global,list(snapshot=strrep("b",64)),root,python)
  gp <- PredictMarginShapeCalibration(gf,decision)
  expect_equal(gp$probability,c(3/7,2/7,2/7),tolerance=1e-7)
  expect_error(FitMarginShapeCalibration(history[1:5,],d$cutoff,policy,
    list(snapshot=strrep("b",64)),root,python),"sample|below|insufficient")
  broken <- history;broken$W[1]<-NA_real_
  expect_error(FitMarginShapeCalibration(broken,d$cutoff,policy,list(snapshot=strrep("b",64)),root,python),"history")
  broken <- history;broken$W[1]<-.9
  expect_error(FitMarginShapeCalibration(broken,d$cutoff,policy,list(snapshot=strrep("b",64)),root,python),"probabilities")
  broken <- decision;broken$cutoff$cutoff_utc <- broken$cutoff$cutoff_utc+1
  expect_error(PredictMarginShapeCalibration(fit,broken),"binding")
  broken <- decision;broken$features$W <- .4
  expect_error(PredictMarginShapeCalibration(fit,broken),"receipt")
  broken <- decision;broken$receipt$max_source_available_utc <- d$cutoff$cutoff_utc
  expect_error(PredictMarginShapeCalibration(fit,broken),"receipt")
  broken <- fit;broken$coefficients[[1]][1]<-0
  expect_error(PredictMarginShapeCalibration(broken,decision),"binding")
  broken <- policy;broken$features <- "unknown"
  expect_error(FitMarginShapeCalibration(history,d$cutoff,broken,list(snapshot=strrep("b",64)),root,python),"features")
  broken <- policy;broken$prior_issues <- c("008","010")
  expect_error(FitMarginShapeCalibration(history,d$cutoff,broken,list(snapshot=strrep("b",64)),root,python),"prior issue")
  broken <- history;broken$actual_outcome <- "W"
  expect_error(FitMarginShapeCalibration(broken,d$cutoff,policy,list(snapshot=strrep("b",64)),root,python),"class support")
  broken <- history;broken$entropy <- 1
  expect_error(FitMarginShapeCalibration(broken,d$cutoff,policy,list(snapshot=strrep("b",64)),root,python),"singular")
})
