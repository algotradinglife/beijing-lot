# Build a priced epoch with enough fixtures for a multi-group slate.
candidate_fixture <- function(n_fixtures = 28L, seed = 42L) {
  issue <- make_example_issue('26097', match_kickoff_window('2026-09-22', n_fixtures),
                                 seed = seed)
  cutoff <- list(cutoff_utc = as.POSIXct('2026-09-22 12:00:00', tz = 'UTC'), issue_id = '26097')
  inputs <- read_match_inputs(example_match_source(issue), '26097')
  prepared <- prepare_engine(inputs, cutoff,
                             list(members = c('c01', 'c02', 'c03'), missing = 'error'),
                             list(companies = NULL, line = 'nearest_main', watermark = 'decimal'))
  projected <- estimate_engine(prepared, cutoff, -0.14, c(0.1, 16), 1e-10)
  list(fixtures = prepared$fixtures, probabilities = projected$probabilities,
       match_status = prepared$match_status, cutoff = cutoff)
}

testthat::test_that('the wide probability view validates and returns only W/D/L columns', {
  fx <- candidate_fixture(n_fixtures = 14L)
  wide <- parlay_probability_wide(fx$probabilities)
  testthat::expect_equal(nrow(wide), 14L)
  testthat::expect_identical(names(wide), c('fixture_id', 'W', 'D', 'L'))
  testthat::expect_false('entropy' %in% names(wide))
  testthat::expect_identical(wide$fixture_id, sort(fx$probabilities$fixture_id) |>
                               unique())
  testthat::expect_type(wide$fixture_id, 'character')
  testthat::expect_type(wide$W, 'double')
  testthat::expect_silent(match_check_probability_sum(as.matrix(wide[, c('W', 'D', 'L')])))

  empty <- parlay_probability_wide(match_typed_empty('probabilities'))
  testthat::expect_equal(nrow(empty), 0L)
  testthat::expect_identical(names(empty), c('fixture_id', 'W', 'D', 'L'))
  testthat::expect_type(empty$fixture_id, 'character')
  testthat::expect_type(empty$W, 'double')
})

testthat::test_that('the wide probability view refuses invalid sums and gaps', {
  fx <- candidate_fixture(n_fixtures = 4L)
  bad_sum <- fx$probabilities
  bad_sum$probability[bad_sum$fixture_id == bad_sum$fixture_id[1]] <-
    c(0.5, 0.2, 0.2)
  testthat::expect_error(parlay_probability_wide(bad_sum), 'sum')

  gap <- fx$probabilities[!(fx$probabilities$fixture_id == fx$probabilities$fixture_id[1] &
                              fx$probabilities$outcome == 'L'), , drop = FALSE]
  testthat::expect_error(parlay_probability_wide(gap))
})

testthat::test_that('fixture round-robin construction is deterministic and shaped', {
  fx <- candidate_fixture(n_fixtures = 28L)
  first <- parlay_construct_groups(fx$fixtures, fx$probabilities, fx$cutoff, 7L,
                                   'fixture_round_robin', 4L, seed = 1L, match_status = fx$match_status)
  second <- parlay_construct_groups(fx$fixtures, fx$probabilities, fx$cutoff, 7L,
                                    'fixture_round_robin', 4L, seed = 1L, match_status = fx$match_status)
  testthat::expect_identical(first$group_legs, second$group_legs)
  testthat::expect_equal(length(unique(first$group_legs$group_id)), 4L)
  testthat::expect_equal(nrow(first$group_legs), 28L)

  # Every group has exactly 7 distinct fixtures.
  counts <- table(first$group_legs$group_id)
  testthat::expect_true(all(counts == 7L))
  distinct <- tapply(first$group_legs$fixture_id, first$group_legs$group_id,
                     function(v) length(unique(v)))
  testthat::expect_true(all(distinct == 7L))
})

testthat::test_that('construction reports truncation instead of claiming full coverage', {
  fx <- candidate_fixture(n_fixtures = 28L)
  capped <- parlay_construct_groups(fx$fixtures, fx$probabilities, fx$cutoff, 7L,
                                    'fixture_round_robin', 2L, seed = 1L, match_status = fx$match_status)
  testthat::expect_equal(length(unique(capped$group_legs$group_id)), 2L)
  testthat::expect_true(capped$diagnostics$truncated)
  testthat::expect_gt(capped$diagnostics$dropped, 0L)
})

testthat::test_that('explicit groups are validated for shape and pricing', {
  fx <- candidate_fixture(n_fixtures = 14L)
  ids <- fx$fixtures$fixture_id[1:7]
  explicit <- parlay_construct_groups(fx$fixtures, fx$probabilities, fx$cutoff, 7L,
                                      list(groups = list(ids)), 4L, seed = 1L,
                                      match_status = fx$match_status)
  testthat::expect_equal(length(unique(explicit$group_legs$group_id)), 1L)
  testthat::expect_equal(explicit$group_legs$fixture_id, ids)

  testthat::expect_error(
    parlay_construct_groups(fx$fixtures, fx$probabilities, fx$cutoff, 7L,
                            list(groups = list(ids[1:5])), 4L, seed = 1L,
                            match_status = fx$match_status),
    'has 5 legs, expected 7')
  testthat::expect_error(
    parlay_construct_groups(fx$fixtures, fx$probabilities, fx$cutoff, 7L,
                            list(groups = list(c(ids[1:6], 'not-a-fixture'))), 4L, seed = 1L,
                            match_status = fx$match_status),
    'references unpriced fixtures')
})

testthat::test_that('unknown construction modes are refused', {
  fx <- candidate_fixture(n_fixtures = 14L)
  testthat::expect_error(
    parlay_construct_groups(fx$fixtures, fx$probabilities, fx$cutoff, 7L,
                            'magic', 4L, seed = 1L, match_status = fx$match_status),
    "must be 'fixture_round_robin'")
})

testthat::test_that('the 3333222 pattern spans exactly 648 tickets per group', {
  fx <- candidate_fixture(n_fixtures = 28L)
  groups <- parlay_construct_groups(fx$fixtures, fx$probabilities, fx$cutoff, 7L,
                                    'fixture_round_robin', 4L, seed = 1L, match_status = fx$match_status)
  structure <- parlay_apply_structure(groups$group_legs, fx$probabilities, fx$cutoff,
                                  c(3L, 3L, 3L, 3L, 2L, 2L, 2L))
  testthat::expect_true(all(structure$support_summary$support_size == 648L))
  testthat::expect_true(all(structure$support_summary$structure_mass > 0))
  testthat::expect_true(all(structure$support_summary$structure_mass <= 1))
})

testthat::test_that('the documented pattern space sizes match the contract table', {
  # From the contract's "structure and budget must be separated" table.
  table_patterns <- list(
    c(3L, 3L, 3L, 3L, 2L, 2L, 2L), c(3L, 3L, 2L, 2L, 2L, 2L, 2L),
    c(3L, 2L, 2L, 2L, 2L, 2L, 2L), c(3L, 3L, 3L, 2L, 2L, 2L, 1L),
    c(3L, 3L, 2L, 2L, 2L, 2L, 1L), c(3L, 2L, 2L, 2L, 2L, 2L, 1L),
    c(2L, 2L, 2L, 2L, 2L, 2L, 1L), c(2L, 2L, 2L, 2L, 2L, 1L, 1L))
  expected <- c(648L, 288L, 192L, 216L, 144L, 96L, 64L, 32L)
  fx <- candidate_fixture(n_fixtures = 14L)
  groups <- parlay_construct_groups(fx$fixtures, fx$probabilities, fx$cutoff, 7L,
                                    'fixture_round_robin', 1L, seed = 1L, match_status = fx$match_status)
  for (i in seq_along(table_patterns)) {
    structure <- parlay_apply_structure(groups$group_legs, fx$probabilities, fx$cutoff,
                                    table_patterns[[i]])
    testthat::expect_equal(structure$support_summary$support_size[1], expected[i],
                           info = paste('pattern', paste(table_patterns[[i]], collapse = '')))
  }
})

testthat::test_that('structure patterns must be seven values drawn from 1, 2, 3', {
  fx <- candidate_fixture(n_fixtures = 14L)
  groups <- parlay_construct_groups(fx$fixtures, fx$probabilities, fx$cutoff, 7L,
                                    'fixture_round_robin', 1L, seed = 1L, match_status = fx$match_status)
  testthat::expect_error(
    parlay_apply_structure(groups$group_legs, fx$probabilities, fx$cutoff, c(3L, 3L, 3L)),
    'pattern must be 7 integers')
  testthat::expect_error(
    parlay_apply_structure(groups$group_legs, fx$probabilities, fx$cutoff,
                       c(4L, 3L, 3L, 3L, 2L, 2L, 2L)),
    'pattern must be 7 integers')
})

testthat::test_that('roles are assigned 3->2->1 by the authoritative role scores', {
  fx <- candidate_fixture(n_fixtures = 14L)
  groups <- parlay_construct_groups(fx$fixtures, fx$probabilities, fx$cutoff, 7L,
                                    'fixture_round_robin', 1L, seed = 1L, match_status = fx$match_status)
  group_id <- groups$group_legs$group_id[1]
  legs <- groups$group_legs[groups$group_legs$group_id == group_id, , drop = FALSE]
  structure <- parlay_apply_structure(groups$group_legs, fx$probabilities, fx$cutoff,
                                  c(3L, 3L, 3L, 3L, 2L, 2L, 2L))
  candidate_id <- unique(structure$supports$candidate_id)[1]
  depth_by_fixture <- vapply(legs$fixture_id, function(f) {
    sum(structure$supports$allowed[structure$supports$candidate_id == candidate_id &
                                     structure$supports$fixture_id == f])
  }, numeric(1))
  # The pattern multiset must be handed out exactly: 3,3,3,3,2,2,2.
  testthat::expect_true(all(sort(depth_by_fixture, decreasing = TRUE) == c(3, 3, 3, 3, 2, 2, 2)))

  # Reproduce the contract explicitly from the role ranking: within this fixed group
  # each role takes the highest-ranked unassigned member, walking the ACTUAL pattern
  # 3,3,3,3,2,2,2 in descending order. Every leg of the group receives exactly one
  # role; the pattern multiset, not the unique role set {3,2,1}, defines the walk.
  scores <- beidan:::parlay_role_scores(fx$probabilities, fx$cutoff)
  assigned <- character(0)
  expected_fixture <- character(0)
  expected_role <- integer(0)
  for (role in sort(as.integer(c(3L, 3L, 3L, 3L, 2L, 2L, 2L)), decreasing = TRUE)) {
    ranked <- scores[scores$role == role & scores$fixture_id %in% legs$fixture_id, , drop = FALSE]
    ranked <- ranked[order(ranked$rank), , drop = FALSE]
    pick <- ranked$fixture_id[!ranked$fixture_id %in% assigned][1]
    assigned <- c(assigned, pick)
    expected_fixture <- c(expected_fixture, pick)
    expected_role <- c(expected_role, role)
  }
  testthat::expect_equal(unname(depth_by_fixture),
                         unname(expected_role[match(legs$fixture_id, expected_fixture)]))
})

testthat::test_that('a hard forbidden outcome is excluded and never topped up', {
  fx <- candidate_fixture(n_fixtures = 14L)
  groups <- parlay_construct_groups(fx$fixtures, fx$probabilities, fx$cutoff, 7L,
                                    'fixture_round_robin', 1L, seed = 1L, match_status = fx$match_status)
  group_id <- groups$group_legs$group_id[1]
  legs <- groups$group_legs[groups$group_legs$group_id == group_id, , drop = FALSE]
  wide_for_test <- parlay_probability_wide(fx$probabilities)
  leg_row <- wide_for_test[match(legs$fixture_id[1], wide_for_test$fixture_id), , drop = FALSE]
  best_outcome <- match_outcomes()[parlay_outcome_rank(as.numeric(leg_row[1, match_outcomes()]))[1]]
  banned <- tibble::tibble(fixture_id = legs$fixture_id[1], outcome = best_outcome)
  structure <- parlay_apply_structure(groups$group_legs, fx$probabilities, fx$cutoff,
                                  c(3L, 3L, 3L, 3L, 2L, 2L, 2L), banned)
  candidate_id <- unique(structure$supports$candidate_id)[1]
  banned_row <- structure$supports[structure$supports$candidate_id == candidate_id &
                                     structure$supports$fixture_id == banned$fixture_id &
                                     structure$supports$outcome == banned$outcome, , drop = FALSE]
  # The banned outcome is never admitted: either the row is absent, or it
  # is present and explicitly not allowed.
  testthat::expect_true(nrow(banned_row) == 0L || !isTRUE(banned_row$allowed[1]))
  # No substitute outcome replaced it.
  kept <- structure$supports[structure$supports$candidate_id == candidate_id &
                              structure$supports$fixture_id == banned$fixture_id &
                              structure$supports$allowed, , drop = FALSE]
  testthat::expect_false(banned$outcome %in% kept$outcome)
  # Support shrank by exactly one leg-outcome; no substitute was admitted.
  baseline <- parlay_apply_structure(groups$group_legs, fx$probabilities, fx$cutoff,
                                 c(3L, 3L, 3L, 3L, 2L, 2L, 2L))
  baseline_id <- unique(baseline$supports$candidate_id)[1]
  depth_before <- sum(baseline$supports$allowed[baseline$supports$fixture_id == banned$fixture_id &
                                                  baseline$supports$candidate_id == baseline_id])
  testthat::expect_equal(structure$support_summary$support_size[1], 648L %/% depth_before * (depth_before - 1L))
})

testthat::test_that('near-tied probabilities keep the authoritative role outcome mask', {
  # Regression for #535: the fixed-group structure pass must consume the selected
  # role's authoritative allowed_outcomes rather than re-ranking with
  # parlay_outcome_rank(), which lacks the role scorer's nine-decimal tie handling.
  cutoff <- list(cutoff_utc = as.POSIXct('2026-09-22 12:00:00', tz = 'UTC'),
                 issue_id = '26097')
  probabilities <- tibble::tibble(
    fixture_id = rep('f1', 3L), outcome = c('W', 'D', 'L'),
    probability = c(0.4, 0.4000000001, 0.1999999999))
  legs <- tibble::tibble(group_id = 'f1', fixture_id = 'f1', leg_order = 1L)

  # Pin the disagreement that motivates the test: the authoritative role-1 mask is W
  # while the unrounded rank would keep D.
  authoritative <- parlay_role_scores(probabilities, cutoff)
  role1 <- authoritative[authoritative$role == 1L, , drop = FALSE]
  testthat::expect_identical(role1$allowed_outcomes[[1]], 'W')
  testthat::expect_identical(
    match_outcomes()[parlay_outcome_rank(c(0.4, 0.4000000001, 0.1999999999))[1]], 'D')

  structure <- parlay_apply_structure(legs, probabilities, cutoff, 1L)
  kept <- structure$supports$outcome[structure$supports$allowed]
  testthat::expect_identical(kept, 'W')

  # The retained mass is the authoritative kept mass, not the re-ranked substitute.
  testthat::expect_equal(structure$support_summary$support_size, 1L)
  testthat::expect_equal(structure$support_summary$support_mass, 0.4)
  testthat::expect_equal(structure$support_summary$structure_mass, 0.4)

  # Banning the non-kept D must NOT exhaust the leg: W is still retained.
  ban_d <- tibble::tibble(fixture_id = 'f1', outcome = 'D')
  ban_d_structure <- parlay_apply_structure(legs, probabilities, cutoff, 1L, ban_d)
  testthat::expect_identical(ban_d_structure$supports$outcome[ban_d_structure$supports$allowed], 'W')
  testthat::expect_equal(ban_d_structure$support_summary$support_size, 1L)
  testthat::expect_equal(ban_d_structure$support_summary$support_mass, 0.4)

  # Banning the authoritative kept W must exhaust the leg with no top-up to D.
  ban_w <- tibble::tibble(fixture_id = 'f1', outcome = 'W')
  ban_w_structure <- parlay_apply_structure(legs, probabilities, cutoff, 1L, ban_w)
  testthat::expect_equal(nrow(ban_w_structure$supports), 0L)
  testthat::expect_equal(nrow(ban_w_structure$support_summary), 0L)
  testthat::expect_identical(ban_w_structure$exhausted, 'f1|p1')

  # The mask is invariant to the caller's row order: the role scorer sorts internally.
  permuted <- probabilities[c(3L, 1L, 2L), , drop = FALSE]
  permuted_structure <- parlay_apply_structure(legs, permuted, cutoff, 1L)
  testthat::expect_identical(permuted_structure$supports$outcome[permuted_structure$supports$allowed], 'W')
  testthat::expect_equal(permuted_structure$support_summary$support_mass, 0.4)
})

testthat::test_that('support_mass is the raw mass before any renormalisation', {
  # The contract forbids renormalising probabilities after masking. For a full
  # 3/3/3/3/2/2/2 structure the raw mass must equal the product of kept masses.
  fx <- candidate_fixture(n_fixtures = 14L)
  groups <- parlay_construct_groups(fx$fixtures, fx$probabilities, fx$cutoff, 7L,
                                    'fixture_round_robin', 1L, seed = 1L, match_status = fx$match_status)
  group_id <- groups$group_legs$group_id[1]
  structure <- parlay_apply_structure(groups$group_legs, fx$probabilities, fx$cutoff,
                                  c(3L, 3L, 3L, 3L, 2L, 2L, 2L))
  candidate_id <- unique(structure$supports$candidate_id)[1]
  wide <- parlay_probability_wide(fx$probabilities)
  legs <- groups$group_legs[groups$group_legs$group_id == group_id, , drop = FALSE]
  legs <- legs[order(legs$leg_order), , drop = FALSE]
  expected_mass <- 1
  for (leg_index in seq_len(nrow(legs))) {
    fixture_id <- legs$fixture_id[leg_index]
    allowed <- structure$supports$outcome[structure$supports$candidate_id == candidate_id &
                                            structure$supports$fixture_id == fixture_id &
                                            structure$supports$allowed]
    row <- wide[wide$fixture_id == fixture_id, , drop = FALSE]
    expected_mass <- expected_mass * sum(as.numeric(row[1, allowed]))
  }
  testthat::expect_equal(structure$support_summary$structure_mass[1], expected_mass,
                         tolerance = 1e-10)
  testthat::expect_lt(expected_mass, 1)
})

testthat::test_that('enumeration expands the support product and keeps raw probabilities', {
  fx <- candidate_fixture(n_fixtures = 28L)
  groups <- parlay_construct_groups(fx$fixtures, fx$probabilities, fx$cutoff, 7L,
                                    'fixture_round_robin', 4L, seed = 1L, match_status = fx$match_status)
  structure <- parlay_apply_structure(groups$group_legs, fx$probabilities, fx$cutoff,
                                  c(3L, 3L, 3L, 3L, 2L, 2L, 2L))
  tickets <- parlay_enumerate_tickets(groups$group_legs, fx$probabilities, fx$cutoff,
                                  structure$supports)
  testthat::expect_equal(nrow(tickets$tickets), 4L * 648L)
  testthat::expect_equal(nrow(tickets$candidate_tickets), 4L * 648L)

  legs_per_ticket <- table(tickets$ticket_legs$ticket_id)
  testthat::expect_true(all(legs_per_ticket == 7L))
  testthat::expect_true(all(tickets$tickets$probability > 0))
  testthat::expect_true(all(tickets$tickets$probability <= 1))

  # The stored probability is the product of the leg probabilities.
  first_id <- tickets$tickets$ticket_id[1]
  legs <- tickets$ticket_legs[tickets$ticket_legs$ticket_id == first_id, , drop = FALSE]
  wide <- parlay_probability_wide(fx$probabilities)
  manual <- 1
  for (i in seq_len(nrow(legs))) {
    row <- wide[wide$fixture_id == legs$fixture_id[i], , drop = FALSE]
    manual <- manual * as.numeric(row[1, legs$outcome[i]])
  }
  stored <- tickets$tickets$probability[tickets$tickets$ticket_id == first_id]
  testthat::expect_equal(stored, manual, tolerance = 1e-12)
})

testthat::test_that('a ticket supported by two structures keeps one physical identity', {
  # The contract: the same physical ticket referenced by two candidates must share
  # one ticket_id, so it cannot be bought twice.
  fx <- candidate_fixture(n_fixtures = 14L)
  ids <- fx$fixtures$fixture_id[1:7]
  groups <- parlay_construct_groups(fx$fixtures, fx$probabilities, fx$cutoff, 7L,
                                    list(groups = list(ids, ids)), 4L, seed = 1L,
                                      match_status = fx$match_status)
  structure <- parlay_apply_structure(groups$group_legs, fx$probabilities, fx$cutoff,
                                  c(3L, 3L, 3L, 3L, 2L, 2L, 2L))
  tickets <- parlay_enumerate_tickets(groups$group_legs, fx$probabilities, fx$cutoff,
                                  structure$supports)
  # The same fixture set IS the same group: group_id is the sorted fixture set, so
  # requesting it twice must not create two groups or buy the space twice.
  testthat::expect_equal(length(unique(groups$group_legs$group_id)), 1L)
  testthat::expect_equal(nrow(tickets$tickets), 648L)
  testthat::expect_equal(nrow(tickets$candidate_tickets), 648L)
  testthat::expect_equal(length(unique(tickets$tickets$ticket_id)), 648L)
})

testthat::test_that('two structures over one fixture set share ticket identities', {
  # The contract's deliberate case: candidate_id separates structures over the
  # SAME seven fixtures, and a physical ticket common to both keeps one ticket_id.
  fx <- candidate_fixture(n_fixtures = 14L)
  ids <- fx$fixtures$fixture_id[1:7]
  groups <- parlay_construct_groups(fx$fixtures, fx$probabilities, fx$cutoff, 7L,
                                    list(groups = list(ids)), 4L, seed = 1L,
                                      match_status = fx$match_status)
  group_id <- unique(groups$group_legs$group_id)
  # Two structural variants over the same group, expressed as two candidate ids.
  wide_supports <- parlay_apply_structure(groups$group_legs, fx$probabilities, fx$cutoff,
                                      c(3L, 3L, 3L, 3L, 2L, 2L, 2L))$supports
  narrow_supports <- parlay_apply_structure(groups$group_legs, fx$probabilities, fx$cutoff,
                                        c(2L, 2L, 2L, 2L, 2L, 2L, 2L))$supports
  narrow_supports$candidate_id <- paste0(group_id, '#b')
  combined <- dplyr::bind_rows(wide_supports, narrow_supports)
  groups_b <- groups
  groups_b$group_legs <- dplyr::bind_rows(
    groups$group_legs,
    dplyr::mutate(groups$group_legs, group_id = paste0(group_id, '#b')))
  tickets <- parlay_enumerate_tickets(groups_b$group_legs, fx$probabilities, fx$cutoff, combined)
  # A uniform 2-per-leg structure spans 2^7 = 128 tickets, all of which are also
  # in the wide 3333222 space, so the physical ticket count stays 648 while the
  # candidate references total 648 + 128.
  testthat::expect_equal(nrow(tickets$tickets), 648L)
  testthat::expect_equal(nrow(tickets$candidate_tickets), 648L + 128L)
  testthat::expect_equal(sum(tickets$candidate_tickets$candidate_id == paste0(group_id, '#b')), 128L)
  # Every narrow ticket is a physical ticket that already existed.
  narrow_ids <- tickets$candidate_tickets$ticket_id[
    tickets$candidate_tickets$candidate_id == paste0(group_id, '#b')]
  testthat::expect_true(all(narrow_ids %in% tickets$tickets$ticket_id))
})

testthat::test_that('a group whose only leg loses all support is refused', {
  fx <- candidate_fixture(n_fixtures = 14L)
  ids <- fx$fixtures$fixture_id[1:7]
  groups <- parlay_construct_groups(fx$fixtures, fx$probabilities, fx$cutoff, 7L,
                                    list(groups = list(ids)), 4L, seed = 1L,
                                      match_status = fx$match_status)
  supports <- parlay_apply_structure(groups$group_legs, fx$probabilities, fx$cutoff,
                                 c(1L, 1L, 1L, 1L, 1L, 1L, 1L))$supports
  # Ban every outcome at one leg.
  leg_fixture <- ids[1]
  supports$allowed[supports$fixture_id == leg_fixture] <- FALSE
  testthat::expect_error(
    parlay_enumerate_tickets(groups$group_legs, fx$probabilities, fx$cutoff, supports),
    'empty leg')
})

testthat::test_that('empty groups yield typed empty enumeration output', {
  cutoff <- list(cutoff_utc = as.POSIXct('2026-09-22 12:00:00', tz = 'UTC'), issue_id = '26097')
  empty_groups <- match_typed_empty('group_legs')
  empty_supports <- match_typed_empty('supports')
  tickets <- parlay_enumerate_tickets(empty_groups, match_typed_empty('probabilities'), cutoff,
                                  empty_supports)
  testthat::expect_equal(nrow(tickets$tickets), 0L)
  testthat::expect_equal(nrow(tickets$ticket_legs), 0L)
  testthat::expect_silent(match_validate_table(tickets$tickets, 'tickets'))
  testthat::expect_silent(match_validate_table(tickets$ticket_legs, 'ticket_legs'))

  structure <- parlay_apply_structure(empty_groups, match_typed_empty('probabilities'), cutoff,
                                  c(3L, 3L, 3L, 3L, 2L, 2L, 2L))
  testthat::expect_equal(nrow(structure$candidates), 0L)
  testthat::expect_silent(match_validate_table(structure$supports, 'supports'))

  constructed <- parlay_construct_groups(match_typed_empty('fixtures'),
                                         match_typed_empty('probabilities'), cutoff, 7L,
                                         'fixture_round_robin', 4L, seed = 1L,
                                         match_status = match_typed_empty('match_status'))
  testthat::expect_equal(nrow(constructed$group_legs), 0L)
  testthat::expect_silent(match_validate_table(constructed$group_legs, 'group_legs'))
})

testthat::test_that('the group identity depends on the fixture set, not its order', {
  testthat::expect_identical(parlay_group_identity(c('b', 'a', 'c')),
                             parlay_group_identity(c('c', 'b', 'a')))
  testthat::expect_error(parlay_group_identity(character(0)), 'must not be empty')
})

# --- 逐函数边界测试（candidates）--------------------------------------------
# review 在此文件累计指出 13 处问题，因此边界必须钉死。

testthat::test_that('parlay_probability_wide 产出每场一行且仅含 W/D/L 列', {
  probabilities <- tibble::tibble(
    fixture_id = rep(c('f1','f2'), each = 3L),
    outcome = rep(match_outcomes(), 2L),
    probability = c(0.5, 0.3, 0.2, 1/3, 1/3, 1/3))
  wide <- parlay_probability_wide(probabilities)
  testthat::expect_equal(nrow(wide), 2L)
  testthat::expect_identical(names(wide), c('fixture_id', match_outcomes()))
  testthat::expect_equal(wide$W[wide$fixture_id == 'f1'], 0.5)
})

testthat::test_that('parlay_probability_wide 在空表上返回带完整列的空表', {
  wide <- parlay_probability_wide(match_typed_empty('probabilities'))
  testthat::expect_equal(nrow(wide), 0L)
  testthat::expect_identical(names(wide), c('fixture_id', match_outcomes()))
  testthat::expect_type(wide$fixture_id, 'character')
  testthat::expect_type(wide$W, 'double')
})

testthat::test_that('parlay_probability_wide 拒绝缺结果、有缺口与行和不为 1', {
  # 某场缺一个结果。
  missing_outcome <- tibble::tibble(
    fixture_id = c('f1','f1','f2','f2','f2'),
    outcome = c('W','D', match_outcomes()),
    probability = c(0.5, 0.5, 1/3, 1/3, 1/3))
  # 缺列报 'missing outcomes'，某行缺值报 'have gaps'；两者都是合法拒绝。
  testthat::expect_error(parlay_probability_wide(missing_outcome),
                         'missing outcomes|have gaps')
  # 行和不为 1。
  bad_sum <- tibble::tibble(
    fixture_id = rep('f1', 3L), outcome = match_outcomes(),
    probability = c(0.5, 0.4, 0.4))
  testthat::expect_error(parlay_probability_wide(bad_sum), 'must sum to 1')
})

testthat::test_that('parlay_group_identity 规范化排序与去重', {
  testthat::expect_identical(parlay_group_identity(c('a','b')), 'a+b')
  # 乱序输入必须产出同一标识，否则同一组会被当成两组。
  testthat::expect_identical(parlay_group_identity(c('b','a')), 'a+b')
  testthat::expect_identical(parlay_group_identity(c('b','a','b')), 'a+b')
  testthat::expect_identical(parlay_group_identity('a'), 'a')
})

testthat::test_that('parlay_group_identity 拒绝空、非字符、NA 与空串', {
  testthat::expect_error(parlay_group_identity(character(0)), 'must not be empty')
  testthat::expect_error(parlay_group_identity(1:3), 'must be character')
  # 回归：NA 会变成字符串 'NA'，与真实名为 NA 的比赛无法区分。
  testthat::expect_error(parlay_group_identity(NA_character_), 'must not be NA')
  testthat::expect_error(parlay_group_identity(c('a', NA)), 'must not be NA')
  testthat::expect_error(parlay_group_identity(''), 'empty strings')
})

testthat::test_that('parlay_outcome_codes 把 W/D/L 映射为 1/2/3', {
  testthat::expect_identical(parlay_outcome_codes(c('W','D','L')), c(1, 2, 3))
  testthat::expect_identical(parlay_outcome_codes('W'), 1)
  testthat::expect_identical(parlay_outcome_codes('L'), 3)
  testthat::expect_type(parlay_outcome_codes('W'), 'double')
})

testthat::test_that('parlay_outcome_codes 拒绝非字符、空、NA 与非 W/D/L', {
  testthat::expect_error(parlay_outcome_codes(1), 'must be character')
  testthat::expect_error(parlay_outcome_codes(character(0)), 'must not be empty')
  testthat::expect_error(parlay_outcome_codes(NA_character_), 'must not be NA')
  testthat::expect_error(parlay_outcome_codes(c('W', NA)), 'must not be NA')
  testthat::expect_error(parlay_outcome_codes('X'), 'must be W, D or L')
  testthat::expect_error(parlay_outcome_codes('w'), 'must be W, D or L')
})

testthat::test_that('parlay_outcome_rank 按概率降序、并列按 W/D/L 顺序', {
  testthat::expect_identical(parlay_outcome_rank(c(0.5, 0.3, 0.2)), c(1L, 2L, 3L))
  testthat::expect_identical(parlay_outcome_rank(c(0.2, 0.3, 0.5)), c(3L, 2L, 1L))
  # 完全并列时必须退化为固定顺序，否则排名依赖于列顺序。
  testthat::expect_identical(parlay_outcome_rank(c(1/3, 1/3, 1/3)), c(1L, 2L, 3L))
  testthat::expect_identical(parlay_outcome_rank(c(0.5, 0.5, 0)), c(1L, 2L, 3L))
})

testthat::test_that('parlay_outcome_rank 拒绝非数值、NA 与负值', {
  testthat::expect_error(parlay_outcome_rank(c('a','b','c')), 'must be numeric')
  testthat::expect_error(parlay_outcome_rank(c(NA, 0.5, 0.5)), 'three finite values')
  testthat::expect_error(parlay_outcome_rank(c(0.5, 0.5)), 'three finite values')
  testthat::expect_error(parlay_outcome_rank(c(0.5, 0.5, Inf)), 'three finite values')
  testthat::expect_error(parlay_outcome_rank(c(-1, 1, 1)), 'must be non-negative')
})

testthat::test_that('parlay_construct_groups 校验 cutoff 与 n_legs/max_candidates', {
  cutoff <- list(cutoff_utc = as.POSIXct('2026-09-22 12:00:00', tz = 'UTC'), issue_id = '26097')
  fixtures <- match_typed_empty('fixtures')
  probabilities <- match_typed_empty('probabilities')
  ledger <- match_typed_empty('match_status')
  testthat::expect_error(
    parlay_construct_groups(fixtures, probabilities, NULL, 7L, list(), 4L, match_status = ledger),
    'explicit cutoff is required')
  testthat::expect_error(
    parlay_construct_groups(fixtures, probabilities, cutoff, 0L, list(), 4L, match_status = ledger),
    'n_legs')
  testthat::expect_error(
    parlay_construct_groups(fixtures, probabilities, cutoff, 7L, list(), 0L, match_status = ledger),
    'max_candidates must be positive')
})

testthat::test_that('parlay_construct_groups 强制要求 match_status 台账', {
  # 缺失台账是输入契约错误：没有台账与台账为空是两件事，前者绝不能静默通过。
  # match_status 是无默认值的形参，因此漏传在 R 的参数匹配阶段就失败。
  fx <- candidate_fixture(n_fixtures = 14L)
  testthat::expect_error(
    parlay_construct_groups(fx$fixtures, fx$probabilities, fx$cutoff, 7L,
                            'fixture_round_robin', 4L, seed = 1L),
    'match_status')
  empty <- parlay_construct_groups(fx$fixtures, fx$probabilities, fx$cutoff, 7L,
                                   'fixture_round_robin', 4L, seed = 1L,
                                   match_status = match_typed_empty('match_status'))
  testthat::expect_equal(nrow(empty$group_legs), 0L)
})

testthat::test_that('parlay_construct_groups 拒绝其它期号的比赛', {
  # 回归：拿别的期号的比赛对着本 cutoff 定价，会让回放买到不属于其赛程的比赛。
  cutoff <- list(cutoff_utc = as.POSIXct('2026-09-22 12:00:00', tz = 'UTC'), issue_id = '26097')
  stray <- tibble::tibble(
    issue_id = '26098', fixture_id = 'f1', slot = 1L, provider_id = 'p',
    kickoff_at = as.POSIXct('2026-09-23 02:00:00', tz = 'UTC'), handicap = 0L,
    sale_state = 'open', source_url = 'synthetic://x')
  stray_ledger <- tibble::tibble(
    issue_id = '26098', fixture_id = 'f1', status = 'scheduled',
    status_at = as.POSIXct('2026-09-22 08:00:00', tz = 'UTC'),
    available_at = as.POSIXct('2026-09-22 08:00:00', tz = 'UTC'),
    source_url = 'synthetic://x')
  testthat::expect_error(
    parlay_construct_groups(stray, match_typed_empty('probabilities'), cutoff, 7L, list(), 4L,
                            match_status = stray_ledger),
    'fixtures belong to issue')
})

testthat::test_that('parlay_construct_groups 拒绝已开赛与窗口外的比赛', {
  cutoff <- list(cutoff_utc = as.POSIXct('2026-09-22 12:00:00', tz = 'UTC'), issue_id = '26097')
  already <- tibble::tibble(
    issue_id = '26097', fixture_id = 'f1', slot = 1L, provider_id = 'p',
    kickoff_at = as.POSIXct('2026-09-22 10:00:00', tz = 'UTC'), handicap = 0L,
    sale_state = 'open', source_url = 'synthetic://x')
  bound_ledger <- tibble::tibble(
    issue_id = '26097', fixture_id = 'f1', status = 'scheduled',
    status_at = as.POSIXct('2026-09-22 08:00:00', tz = 'UTC'),
    available_at = as.POSIXct('2026-09-22 08:00:00', tz = 'UTC'),
    source_url = 'synthetic://x')
  testthat::expect_error(
    parlay_construct_groups(already, match_typed_empty('probabilities'), cutoff, 7L, list(), 4L,
                            match_status = bound_ledger),
    'already kicked off')
  # 决策窗口是 D+1：2026-09-22 16:00Z .. 2026-09-23 16:00Z。
  outside <- already
  outside$kickoff_at <- as.POSIXct('2026-09-25 02:00:00', tz = 'UTC')
  testthat::expect_error(
    parlay_construct_groups(outside, match_typed_empty('probabilities'), cutoff, 7L, list(), 4L,
                            match_status = bound_ledger),
    'outside the decision window')
})

testthat::test_that('parlay_enumerate_tickets 校验 cutoff', {
  empty <- match_typed_empty('group_legs')
  testthat::expect_error(
    parlay_enumerate_tickets(empty, match_typed_empty('probabilities'), NULL,
                         match_typed_empty('supports'), 7L),
    'explicit cutoff is required')
})

testthat::test_that('group construction preserves fractional cutoff window boundaries', {
  fx <- candidate_fixture(n_fixtures = 7L)
  fx$cutoff$cutoff_utc <- fx$cutoff$cutoff_utc + lubridate::dseconds(0.5)
  start <- fx$cutoff$cutoff_utc + lubridate::dhours(4)
  end <- fx$cutoff$cutoff_utc + lubridate::dhours(28)
  fx$fixtures$kickoff_at[] <- start
  fx$fixtures$kickoff_at[7] <- end - lubridate::dseconds(0.25)
  testthat::expect_no_error(parlay_construct_groups(fx$fixtures, fx$probabilities,
    fx$cutoff, 7L, 'fixture_round_robin', 1L, seed = 1L,
    match_status = fx$match_status))
  fx$fixtures$kickoff_at[1] <- start - lubridate::dseconds(0.25)
  testthat::expect_error(parlay_construct_groups(fx$fixtures, fx$probabilities,
    fx$cutoff, 7L, 'fixture_round_robin', 1L, seed = 1L,
    match_status = fx$match_status), 'outside the decision window')
  fx$fixtures$kickoff_at[1] <- start
  fx$fixtures$kickoff_at[7] <- end
  testthat::expect_error(parlay_construct_groups(fx$fixtures, fx$probabilities,
    fx$cutoff, 7L, 'fixture_round_robin', 1L, seed = 1L,
    match_status = fx$match_status), 'outside the decision window')
})
