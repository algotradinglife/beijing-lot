# Package tests for the role round-robin stage 1 (parlay_role_scores) and the shared
# internal helpers that stage exposes. Every helper is exercised through an exported
# or observable entry point; the root's independent numerical acceptance test lives
# separately in tests/testthat/test-role-strategy-independent.R and is not duplicated
# or edited here.

role_test_cutoff <- function(issue_id = "26098") {
  list(issue_id = issue_id,
       cutoff_utc = as.POSIXct("2026-09-26 11:52:04", tz = "UTC"))
}

role_test_probabilities <- function() {
  tibble::tibble(
    fixture_id = rep(paste0("26098:", 1:4), each = 3),
    outcome = rep(c("W", "D", "L"), 4),
    probability = c(0.50, 0.49, 0.01,
                    0.70, 0.28, 0.02,
                    0.85, 0.10, 0.05,
                    0.80, 0.15, 0.05))
}

test_that("parlay_role_scores returns the contracted role arithmetic and ranks", {
  probabilities <- role_test_probabilities()
  scores <- parlay_role_scores(probabilities, role_test_cutoff())
  expect_s3_class(scores, "tbl_df")
  expect_identical(nrow(scores), 12L)
  expect_identical(names(scores),
                   c("fixture_id", "role", "score", "rank",
                     "retained_probability", "allowed_outcomes"))
  # Role scores are p1, p1+p2 and p3; role 3's retained mass is the whole triple (1),
  # so score and retained_probability are deliberately different for role 3 only.
  role3 <- scores[scores$role == 3L, , drop = FALSE]
  expect_equal(role3$retained_probability, rep(1, nrow(role3)))
  expect_equal(role3$score, c(0.05, 0.05, 0.02, 0.01))
  # Role 3 is ranked by p3 descending, with a numeric tie on fixtures 3 and 4 broken
  # by fixture_id -- never by the W/D/L strings in allowed_outcomes.
  expect_identical(role3$rank, 1:4)
  expect_identical(role3$fixture_id, paste0("26098:", c(3, 4, 2, 1)))
  expect_identical(lengths(role3$allowed_outcomes), rep(3L, 4L))
  # Role 1 and 2 retain the masses their definitions state.
  role1 <- scores[scores$role == 1L, , drop = FALSE]
  expect_equal(role1$score, role1$retained_probability)
  expect_identical(lengths(role1$allowed_outcomes), rep(1L, 4L))
  role2 <- scores[scores$role == 2L, , drop = FALSE]
  expect_equal(role2$score, role2$retained_probability)
  expect_identical(lengths(role2$allowed_outcomes), rep(2L, 4L))
})

test_that("parlay_role_scores is order independent and binds its provenance", {
  probabilities <- role_test_probabilities()
  cutoff <- role_test_cutoff()
  scores <- parlay_role_scores(probabilities, cutoff)
  shuffled <- parlay_role_scores(probabilities[rev(seq_len(nrow(probabilities))), ],
                                 cutoff)
  expect_equal(dplyr::arrange(scores, role, fixture_id),
               dplyr::arrange(shuffled, role, fixture_id), ignore_attr = TRUE)
  expect_identical(attr(scores, "issue_id"), "26098")
  expect_identical(attr(scores, "cutoff"), cutoff)
  expect_identical(attr(scores, "probability_hash"), rlang::hash(probabilities))
  expect_true(is.character(attr(scores, "code_hash")))
  expect_true(nzchar(attr(scores, "code_hash")))
})

test_that("parlay_role_scores keeps a zero probability valid and the sum invariant", {
  probabilities <- tibble::tibble(
    fixture_id = rep("A", 3), outcome = c("W", "D", "L"),
    probability = c(0, 1, 0))
  scores <- parlay_role_scores(probabilities, role_test_cutoff())
  role3 <- scores[scores$role == 3L, , drop = FALSE]
  expect_equal(role3$score, 0)
  expect_equal(role3$retained_probability, 1)
  # The certain outcome (D) leads, and the two zero-probability outcomes follow in the
  # canonical W/D/L order, so the order is D, W, L -- not the input row order W, D, L.
  expect_identical(role3$allowed_outcomes[[1]], c("D", "W", "L"))
  # A role-3 leg always keeps the whole triple, whatever the probabilities are.
  expect_setequal(role3$allowed_outcomes[[1]], match_outcomes())
})

test_that("parlay_role_scores returns a typed empty table for an empty pool", {
  probabilities <- match_typed_empty("probabilities")
  scores <- parlay_role_scores(probabilities, role_test_cutoff())
  expect_identical(nrow(scores), 0L)
  expect_identical(names(scores),
                   c("fixture_id", "role", "score", "rank",
                     "retained_probability", "allowed_outcomes"))
  expect_type(scores$score, "double")
  expect_type(scores$allowed_outcomes, "list")
  expect_identical(attr(scores, "issue_id"), "26098")
})

test_that("parlay_role_scores failure paths are explicit", {
  cutoff <- role_test_cutoff()
  probabilities <- role_test_probabilities()
  # A malformed cutoff, probabilities that do not sum to one, negative values and a
  # foreign column set are all refused rather than silently repaired.
  expect_error(parlay_role_scores(probabilities, NULL), "cutoff")
  broken <- probabilities
  broken$probability[1] <- 0.9
  expect_error(parlay_role_scores(broken, cutoff))
  negative <- probabilities
  negative$probability[1] <- -0.5
  expect_error(parlay_role_scores(negative, cutoff))
  expect_error(parlay_role_scores(tibble::tibble(fixture_id = "A"), cutoff))
})

test_that("role group identity is the canonical sorted fixture set", {
  expect_identical(beidan:::.parlay_role_group_id(c("B", "A")),
                   parlay_group_identity(c("A", "B")))
  expect_error(beidan:::.parlay_role_group_id(character(0)))
})

test_that("the role code hash binds loaded code, not a file path", {
  hash <- beidan:::.parlay_role_code_hash()
  expect_true(is.character(hash))
  expect_true(nzchar(hash))
  # The binding is stable while the loaded namespace is unchanged, and it is NOT the
  # hash of an empty/short object.
  expect_identical(hash, beidan:::.parlay_role_code_hash())
  expect_gt(nchar(hash), 8L)
})
