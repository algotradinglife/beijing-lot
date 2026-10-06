test_that("indexed validation preserves group spaces and checks every distinct direction", {
  fixture <- readRDS(test_path("fixtures", "ranked-validation-parity.rds"))
  args <- fixture$validation_args
  expect_true(do.call(beidan:::.parlay_ranked_validate_legs, args))
  expect_identical(do.call(beidan:::.parlay_ranked_group_space, fixture$space_args),
                   fixture$space_expected)
  late <- which(args$legs$group_id == tail(unique(args$legs$group_id), 1L) &
                  args$legs$base_role == 3L)[1L]
  # An altered later copy must not be hidden by the earlier valid direction.
  bad <- args
  bad$legs$allowed_outcomes[[late]][1L] <- "X"
  expect_error(do.call(beidan:::.parlay_ranked_validate_legs, bad), "allowed mask")
  bad <- args
  bad$legs$retained_probability[late] <- .9
  expect_error(do.call(beidan:::.parlay_ranked_validate_legs, bad), "retained_probability")
  bad <- args
  bad$legs$selection_id[late] <- 99999L
  expect_error(do.call(beidan:::.parlay_ranked_validate_legs, bad), "unique ranked selection")
  bad <- args
  bad$portfolio$group_patterns <- dplyr::bind_rows(bad$portfolio$group_patterns,
                                                 bad$portfolio$group_patterns[1L, ])
  expect_error(do.call(beidan:::.parlay_ranked_validate_legs, bad), "exactly one row")
  bad <- args
  bad$portfolio$group_patterns$group_id[1L] <- NA_character_
  expect_error(do.call(beidan:::.parlay_ranked_validate_legs, bad), "missing group keys")
})

test_that("indexed owned ticket events retain exact unions and missing-ticket errors", {
  probabilities <- tibble::tibble(fixture_id = rep(c("a", "b", "c"), each = 3L),
    outcome = rep(c("W", "D", "L"), 3L),
    probability = c(.5, .3, .2, .4, .4, .2, .6, .2, .2))
  legs <- tibble::tibble(ticket_id = c("A", "A", "B", "B", "C", "unused"),
    fixture_id = c("a", "b", "b", "c", "a", "irrelevant"),
    outcome = c("W", "D", "D", "L", "W", "L"))
  union <- beidan:::.parlay_ranked_union_coverage
  # A is contained in C; B overlaps C only through independent outcomes.
  expect_equal(union(c("A", "B", "C", "A"), legs, probabilities), .54,
               tolerance = 1e-14)
  expect_identical(union(c("A", "B", "C"), legs, probabilities),
                   union(c("A", "B", "C"), legs[rev(seq_len(nrow(legs))), ], probabilities))
  expect_identical(union(character(), legs[0, ], probabilities), 0)
  expect_error(union("missing", legs, probabilities), "has no legs")
  bad <- legs
  bad$ticket_id[6L] <- NA_character_
  expect_error(union("A", bad, probabilities), "missing ticket identities")
  bad <- legs
  bad$outcome[1L] <- "X"
  expect_error(union("A", bad, probabilities), "outcome")
})

test_that("duplicate ticket fixture sets preserve exact connected components", {
  events <- list(c(A="W",B="D"),c(B="L",C="W"),c(D="W"))
  expected <- list(A=c("A","B","C"),D="D",E="E")
  expect_identical(beidan:::.parlay_ranked_components(events,c("A","B","C","D","E")),expected)
  expect_identical(beidan:::.parlay_ranked_components(rep(events,128),c("A","B","C","D","E")),expected)
  expect_identical(beidan:::.parlay_ranked_components(list(),character()),stats::setNames(list(),character()))
})

test_that("shared-first ordering preserves a cyclic three-group union against independent arithmetic", {
  sets <- list(A=paste0("F",1:7),B=paste0("F",c(1,2,8:12)),C=paste0("F",c(3,8,13:17)))
  legs <- tibble::tibble(ticket_id=rep(names(sets),each=7L),fixture_id=unlist(sets,use.names=FALSE),outcome="W")
  p <- tibble::tibble(fixture_id=rep(paste0("F",1:17),each=3L),outcome=rep(c("W","D","L"),17L),probability=rep(c(.4,.3,.3),17L))
  expected <- 3*.4^7-.4^12-2*.4^13+.4^17
  expect_equal(beidan:::.parlay_ranked_union_coverage(names(sets),legs,p),expected,tolerance=1e-14)
  expect_equal(beidan:::.parlay_ranked_union_coverage(rev(names(sets)),legs[nrow(legs):1,],p[nrow(p):1,]),expected,tolerance=1e-14)
})
