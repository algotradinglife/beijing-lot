# Classification tests. `outcomes_of()` compares only the returned character
# vectors; `base_role` is asserted separately through attr() so a test of the
# classifier's values never accidentally depends on its metadata.
outcomes_of <- function(...) {
  result <- classify_outcomes(...)
  attributes(result) <- NULL
  result
}

test_that("signature exposes only win, draw and lose and matches by name", {
  expect_identical(names(formals(classify_outcomes)), c("win", "draw", "lose"))
  expected <- list(c("win", "lose"), c("win", "draw"))
  expect_identical(outcomes_of(lose = .33, win = .45, draw = .22), expected)
  expect_identical(outcomes_of(draw = .22, lose = .33, win = .45), expected)
})

test_that("result is an unnamed list of unnamed outcome-name vectors", {
  res <- classify_outcomes(.45, .22, .33)
  expect_type(res, "list")
  expect_null(names(res))
  for (v in res) {
    expect_type(v, "character")
    expect_null(names(v))
    expect_true(all(v %in% c("win", "draw", "lose")))
  }
})

test_that("documented examples return the specified outcome sets", {
  expect_identical(outcomes_of(.45, .22, .33),
                   list(c("win", "lose"), c("win", "draw")))
  expect_identical(outcomes_of(.40, .30, .30), list(c("win", "draw", "lose")))
  # .45 is not a single, and the weak third (.22) is above 0.20, so the double
  # guard adds the second protected pair.
  expect_identical(outcomes_of(.45, .33, .22),
                   list(c("win", "draw"), c("win", "lose")))
  expect_identical(outcomes_of(.50, .20, .30), list(c("win", "lose")))
  expect_identical(outcomes_of(.38, .31, .31), list(c("win", "draw", "lose")))
  # A single keeps its base Top1 and adds protected pairs that CONTAIN it.
  expect_identical(outcomes_of(.55, .23, .22),
                   list("win", c("win", "draw"), c("win", "lose")))
})

test_that("the attribute-free values stay exactly as before for non-single cases", {
  # base_role is metadata; the character vectors themselves are unchanged.
  expect_identical(outcomes_of(.45, .22, .33),
                   list(c("win", "lose"), c("win", "draw")))
  expect_identical(outcomes_of(.40, .30, .30), list(c("win", "draw", "lose")))
})

test_that("a single choice keeps the base Top1 plus strictly > 0.20 extras", {
  expect_identical(outcomes_of(.60, .20, .20), list("win"))
  # Each extra is a PAIR built on the base Top1, never a disjoint singleton.
  expect_identical(outcomes_of(.55, .23, .22),
                   list("win", c("win", "draw"), c("win", "lose")))
  expect_identical(outcomes_of(.60, .25, .15), list("win", c("win", "draw")))
  expect_identical(outcomes_of(.60, .15, .25), list("win", c("win", "lose")))
  # The extras follow the RANKED order, not argument order; every pair still
  # contains the base Top1 first.
  expect_identical(outcomes_of(.25, .60, .15),
                   list("draw", c("draw", "win")))
  expect_identical(outcomes_of(.25, .15, .60),
                   list("lose", c("lose", "win")))
  # A draw second never needs a lose complement, and vice versa.
  expect_identical(outcomes_of(.70, .22, .08), list("win", c("win", "draw")))
  # Both extras fire independently, so a single can yield three entries.
  expect_identical(outcomes_of(.55, .23, .22),
                   list("win", c("win", "draw"), c("win", "lose")))
  expect_identical(outcomes_of(.52, .25, .23),
                   list("win", c("win", "draw"), c("win", "lose")))
  # Every protected pair contains the base Top1.
  for (p in list(c(.55, .23, .22), c(.60, .25, .15), c(.60, .15, .25))) {
    res <- outcomes_of(p[1L], p[2L], p[3L])
    for (pair in res[-1L]) {
      expect_true(res[[1L]] %in% pair)
      expect_length(pair, 2L)
    }
  }
})

test_that("base_role labels the base category 1, 2 or 3", {
  expect_identical(attr(classify_outcomes(.55, .23, .22), "base_role"), 1L)
  expect_identical(attr(classify_outcomes(.60, .20, .20), "base_role"), 1L)
  expect_identical(attr(classify_outcomes(.50, .30, .20), "base_role"), 2L)
  expect_identical(attr(classify_outcomes(.45, .28, .27), "base_role"), 2L)
  expect_identical(attr(classify_outcomes(.40, .30, .30), "base_role"), 3L)
  expect_type(attr(classify_outcomes(.55, .23, .22), "base_role"), "integer")
  expect_length(attr(classify_outcomes(.55, .23, .22), "base_role"), 1L)
})

test_that("the strict 0.50 boundary decides single versus double", {
  expect_identical(attr(classify_outcomes(.50, .30, .20), "base_role"), 2L)
  expect_identical(outcomes_of(.50, .30, .20), list(c("win", "draw")))
  # Just above 0.50 is a single; one ULP below is not.
  expect_identical(attr(classify_outcomes(.50 + 1e-12, .30, .20 - 1e-12), "base_role"), 1L)
  expect_identical(attr(classify_outcomes(.50 - 1e-12, .30, .20 + 1e-12), "base_role"), 2L)
})

test_that("the strict 0.20 boundary decides extras and the double guard", {
  # Exactly 0.20 adds nothing in either branch.
  expect_identical(outcomes_of(.60, .20, .20), list("win"))
  expect_identical(outcomes_of(.50, .30, .20), list(c("win", "draw")))
  expect_identical(attr(classify_outcomes(.50, .30, .20), "base_role"), 2L)
  # Just above 0.20 adds the extra / opens the guarded double.
  expect_identical(outcomes_of(.60, .20 + 1e-12, .20 - 1e-12),
                   list("win", c("win", "draw")))
  expect_identical(outcomes_of(.50, .30 - 1e-12, .20 + 1e-12),
                   list(c("win", "draw"), c("win", "lose")))
})

test_that("the double branch guards the weak third outcome with > 0.20", {
  # Without the guard the pair is the top two only.
  expect_identical(outcomes_of(.50, .30, .20), list(c("win", "draw")))
  # .45/.28/.27 is a double whose third (.27) exceeds 0.20, so the guard adds
  # the Top1+Top3 pair alongside the basic Top1+Top2 pair.
  expect_identical(outcomes_of(.45, .28, .27),
                   list(c("win", "draw"), c("win", "lose")))
  # With the guard the third outcome is added as a second direction.
  expect_identical(outcomes_of(.50, .28, .22),
                   list(c("win", "draw"), c("win", "lose")))
  # The added outcome may be the draw: no draw-complement admission applies.
  expect_identical(outcomes_of(.50, .22, .28),
                   list(c("win", "lose"), c("win", "draw")))
  expect_identical(outcomes_of(.50, .30 - 1e-12, .20 + 1e-12),
                   list(c("win", "draw"), c("win", "lose")))
})

test_that("the triple branch keeps exactly one canonical full-coverage choice", {
  expect_identical(outcomes_of(.40, .30, .30), list(c("win", "draw", "lose")))
  expect_length(classify_outcomes(.34, .33, .33), 1L)
  expect_identical(attr(classify_outcomes(.34, .33, .33), "base_role"), 3L)
  # The 0.10 boundary keeps the documented 1e-15 floating tolerance.
  expect_identical(attr(classify_outcomes(.40, .30, .30), "base_role"), 3L)
  expect_identical(attr(classify_outcomes(.40000000000001, .30, .29999999999999), "base_role"), 2L)
})

test_that("permuting which label carries which probability permutes the labels", {
  # win/draw/lose are fixed identities, not a sorted vector: moving a value to
  # another label moves that label in the result. The classifier is therefore
  # equivariant under relabeling, and base_role is invariant because it depends
  # only on the value ordering.
  names3 <- c("win", "draw", "lose")
  scenarios <- list(
    list(p = c(.55, .23, .22), role = 1L),
    list(p = c(.60, .20, .20), role = 1L),
    list(p = c(.50, .30, .20), role = 2L),
    list(p = c(.45, .28, .27), role = 2L),
    list(p = c(.40, .30, .30), role = 3L)
  )
  perms <- list(c(1L, 2L, 3L), c(1L, 3L, 2L), c(2L, 1L, 3L),
                c(2L, 3L, 1L), c(3L, 1L, 2L), c(3L, 2L, 1L))
  for (scenario in scenarios) {
    p <- scenario$p
    reference <- classify_outcomes(p[1L], p[2L], p[3L])
    expect_identical(attr(reference, "base_role"), scenario$role)
    tripled <- identical(attr(reference, "base_role"), 3L)
    for (perm in perms) {
      # perm maps original label i to new label perm[i]; label names3[i] keeps
      # its probability but answers to names3[perm[i]] afterwards.
      moved <- numeric(3)
      for (i in 1:3) moved[perm[i]] <- p[i]
      shifted <- outcomes_of(moved[1L], moved[2L], moved[3L])
      # A triple always returns the canonical full set, which is label-invariant;
      # otherwise the result relabels with the probabilities.
      expected <- if (tripled) {
        list(c("win", "draw", "lose"))
      } else {
        relabeled <- lapply(reference, function(v) names3[perm][match(v, names3)])
        names(relabeled) <- NULL
        relabeled
      }
      expect_identical(shifted, expected)
      expect_identical(attr(classify_outcomes(moved[1L], moved[2L], moved[3L]),
                            "base_role"), scenario$role)
    }
  }
})

test_that("ties order win, then draw, then lose and are stable across calls", {
  # .40 - .30 is 0.10, so this is a triple and base_role 3 dominates tie order.
  expect_identical(outcomes_of(.30, .30, .40), list(c("win", "draw", "lose")))
  expect_identical(attr(classify_outcomes(.30, .30, .40), "base_role"), 3L)
  # A three-way tie is a triple, so base_role 3 dominates the tie order.
  expect_identical(outcomes_of(1 / 3, 1 / 3, 1 / 3), list(c("win", "draw", "lose")))
  expect_identical(attr(classify_outcomes(1 / 3, 1 / 3, 1 / 3), "base_role"), 3L)
  # A two-way tie at the top still ranks win before draw before lose. Here the
  # base Top1 is 0.50, which is NOT a single, so this is an ordinary double
  # whose third outcome (draw, 0.25) is above the 0.20 guard.
  expect_identical(outcomes_of(.25, .25, .50),
                   list(c("lose", "win"), c("lose", "draw")))
  expect_identical(attr(classify_outcomes(.25, .25, .50), "base_role"), 2L)
  # Repeated calls are identical: no hidden state, no reordering.
  first <- classify_outcomes(.55, .23, .22)
  second <- classify_outcomes(.55, .23, .22)
  expect_identical(first, second)
  expect_identical(attributes(first), attributes(second))
})

test_that("the values are deduplicated and never repeat an outcome", {
  cases <- list(c(.55, .23, .22), c(.60, .20, .20), c(.50, .30, .20),
                c(.45, .28, .27), c(.40, .30, .30), c(.50, .25, .25))
  for (p in cases) {
    res <- classify_outcomes(p[1L], p[2L], p[3L])
    for (choice in res) {
      expect_identical(anyDuplicated(choice), 0L)
    }
    keys <- vapply(res, paste, character(1), collapse = "|")
    expect_identical(anyDuplicated(keys), 0L)
  }
})

test_that("documented empty-input semantics are errors, never empty results", {
  expect_error(classify_outcomes(numeric(0), .5, .5), "length 1")
  expect_error(classify_outcomes(.5, numeric(0), .5), "length 1")
  expect_error(classify_outcomes(.5, .5, numeric(0)), "length 1")
  expect_error(classify_outcomes(NULL, .5, .5), "number")
  expect_error(classify_outcomes(.5, NULL, .5), "number")
  expect_error(classify_outcomes(.5, .5, NULL), "number")
})

test_that("triple takes priority even when draw is the lowest-ranked name", {
  expect_identical(outcomes_of(.38, .28, .34), list(c("win", "draw", "lose")))
  expect_identical(outcomes_of(1 / 3, 1 / 3, 1 / 3), list(c("win", "draw", "lose")))
})

test_that("tied top probabilities keep the fixed win, draw, lose tie order", {
  # .45/.10/.45: win and lose tie at the top and are ranked win then lose by
  # the fixed tie order, so the base Top1 is win (0.45) and this is a double.
  # The third outcome is draw at 0.10, below the 0.20 guard, so only one pair.
  expect_identical(outcomes_of(.45, .10, .45), list(c("win", "lose")))
  expect_identical(attr(classify_outcomes(.45, .10, .45), "base_role"), 2L)
  # draw and lose tie at the top; the third outcome is win at 0.10.
  expect_identical(outcomes_of(.10, .45, .45), list(c("draw", "lose")))
})

test_that("all six named argument permutations map to the same outcomes", {
  expected <- list(c("win", "lose"), c("win", "draw"))
  args <- list(win = .45, draw = .22, lose = .33)
  perms <- list(c("win", "draw", "lose"), c("win", "lose", "draw"),
                c("draw", "win", "lose"), c("draw", "lose", "win"),
                c("lose", "win", "draw"), c("lose", "draw", "win"))
  for (p in perms) {
    # Compare the outcome vectors, not the base_role attribute they also carry.
    call <- do.call(classify_outcomes, args[p])
    attributes(call) <- NULL
    expect_identical(call, expected)
    expect_identical(do.call(classify_outcomes, args[p]), classify_outcomes(.45, .22, .33))
  }
})

test_that("a single-choice base entry is the protected Top1, never a free singleton", {
  # A single-choice fixture DOES emit its base Top1 as the first entry: that
  # entry is the protected base, and every other entry is a pair containing it.
  # It is never a standalone alternative conjured next to disjoint extras.
  expect_identical(outcomes_of(1, 0, 0), list("win"))
  expect_identical(attr(classify_outcomes(1, 0, 0), "base_role"), 1L)
  for (p in list(c(1, 0, 0), c(0, 1, 0), c(0, 0, 1))) {
    res <- classify_outcomes(p[1L], p[2L], p[3L])
    expect_identical(length(res), 1L)
    expect_identical(res[[1L]], c("win", "draw", "lose")[which(p > 0)])
  }
  # Non-single cases never return a bare singleton.
  for (p in list(c(.5, .5, 0), c(.5, 0, .5), c(0, .5, .5), c(.45, .28, .27))) {
    expect_gte(min(lengths(outcomes_of(p[1L], p[2L], p[3L]))), 2L)
  }
})

test_that("the triple threshold uses a floating 1e-15 boundary tolerance", {
  expect_identical(outcomes_of(.40, .30, .30), list(c("win", "draw", "lose")))
  expect_identical(outcomes_of(.4, .3, .3), list(c("win", "draw", "lose")))
  # Just past the 0.10 range this is a double whose third (.30) clears 0.20.
  expect_identical(outcomes_of(0.40000000000001, 0.3, 0.29999999999999),
                   list(c("win", "draw"), c("win", "lose")))
})

test_that("the draw expansion uses a strict > 0.20 comparison", {
  expect_identical(outcomes_of(.50, .20, .30), list(c("win", "lose")))
  expect_identical(outcomes_of(.45, .1999999999, .3500000001),
                   list(c("win", "lose")))
  expect_identical(outcomes_of(.45, .2000000001, .3499999999),
                   list(c("win", "lose"), c("win", "draw")))
  # .25 is above 0.20, so the double guard adds the second pair.
  expect_identical(outcomes_of(.40, .35, .25),
                   list(c("win", "draw"), c("win", "lose")))
})

test_that("the sum must be within 1e-9 of one without normalization", {
  expect_identical(outcomes_of(.5, .2, .3 + 5e-10), list(c("win", "lose")))
  expect_error(classify_outcomes(.4, .3, .2))
  expect_error(classify_outcomes(.5, .2, .3 + 1e-8))
  expect_error(classify_outcomes(1, 1, 1))
  expect_error(classify_outcomes(0, 0, 0))
})

test_that("invalid types, shapes and non-finite values fail", {
  expect_error(classify_outcomes(c(.6, .25, .15), .1, .1))
  expect_error(classify_outcomes(".5", .3, .2))
  expect_error(classify_outcomes(TRUE, .1, .1))
  expect_error(classify_outcomes(numeric(0), .5, .5))
  expect_error(classify_outcomes(NULL, .5, .5))
  expect_error(classify_outcomes(list(.5), .3, .2))
  expect_error(classify_outcomes(NA_real_, .5, .5))
  expect_error(classify_outcomes(NaN, .5, .5))
  expect_error(classify_outcomes(Inf, 0, 0))
  expect_error(classify_outcomes(-Inf, 1, 1))
  expect_error(classify_outcomes(-.1, .5, .6))
  expect_error(classify_outcomes(1.1, -.1, 0))
})

test_that("the obsolete single-vector API errors", {
  expect_error(classify_outcomes(c(.6, .25, .15)))
  expect_error(classify_outcomes(probabilities = c(.6, .25, .15)))
})
