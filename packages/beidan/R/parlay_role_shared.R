# Role round-robin baseline (#533): shared internal utilities.
#
# Both role stages need the same three things: a conservative, transitive hash of
# the R implementation that produced a receipt, the canonical identity of a role
# group, and the typed-empty shapes the contract fixes. They live here so the two
# exported entry points cannot drift apart.

#' Hash the loaded role implementation that produced an artifact
#'
#' Conservative transitive binding of the CODE, not of a file path. The binding is
#' built from the LOADED `beidan` namespace, which is what actually executes:
#' the formals and deparse'd body of every role function plus the transitive
#' closure of namespace functions they call, and the explicit versions of the
#' dependency packages the role stages consume. File bytes are never read, so the
#' hash does not depend on the working directory, on `source()` provenance, or on
#' whether only this feature's own files happen to be readable.
#'
#' @return A single non-empty character hash. When the namespace cannot be
#'   inspected at all the literal `"unavailable"` is returned rather than a
#'   guess: an honest label is preferable to a hash of nothing.
#' @details No hidden state is serialized. The function walks the namespace
#'   environment each call, so its value follows the loaded code and never a
#'   cached snapshot.
#' @noRd
.parlay_role_code_hash <- function() {
  ns <- tryCatch(asNamespace("beidan"), error = function(e) NULL)
  if (is.null(ns)) return("unavailable")
  # Roots of the transitive closure: the role entry points plus the shared
  # internals they rely on. `getNamespaceExports` is deliberately not used, so a
  # private helper cannot be silently omitted from the receipt.
  roots <- c("parlay_role_scores", "parlay_construct_role_groups",
             "parlay_evaluate_portfolio", ".parlay_role_code_hash",
             ".parlay_role_triple_key", ".parlay_role_definition",
             ".parlay_role_score")
  parts <- c("beidan-schema:2")
  # Explicit dependency versions: a binding that named no versions would stay
  # identical across a dependency upgrade that changed the arithmetic.
  dep_versions <- vapply(
    c("R", "tibble", "dplyr", "tidyr", "rlang", "checkmate", "lubridate"),
    function(pkg) {
      version <- if (pkg == "R") as.character(getRversion()) else tryCatch(as.character(utils::packageVersion(pkg)),
                          error = function(e) "absent")
      paste0(pkg, "==", version)
    }, character(1))
  parts <- c(parts, dep_versions)
  seen <- new.env(parent = emptyenv())
  visit <- function(name) {
    if (!nzchar(name) || exists(name, envir = seen, inherits = FALSE)) return(invisible(NULL))
    assign(name, TRUE, envir = seen)
    fn <- tryCatch(get(name, envir = ns, inherits = FALSE), error = function(e) NULL)
    if (!is.function(fn)) {
      parts <<- c(parts, paste0(name, "=", paste(utils::capture.output(utils::str(fn)),
                                                 collapse = " ")))
      return(invisible(NULL))
    }
    formals_text <- paste(utils::capture.output(base::args(fn)), collapse = " ")
    body_text <- paste(deparse(body(fn)), collapse = " ")
    parts <<- c(parts, paste0(name, "::formals=", formals_text),
                paste0(name, "::body=", body_text))
    # Transitive closure: every symbol the body names that also lives in the
    # namespace, so an imported time helper is bound as well.
    symbols <- all.names(body(fn), functions = TRUE, unique = TRUE)
    for (symbol in symbols) {
      if (exists(symbol, envir = ns, inherits = FALSE)) visit(symbol)
    }
    invisible(NULL)
  }
  for (name in roots) visit(name)
  hash <- rlang::hash(parts)
  if (is.null(hash) || !nzchar(hash)) "unavailable" else hash
}

#' Canonical identity of a role group
#'
#' Internal. The identity is the sorted fixture set, exactly as
#' [parlay_group_identity()] defines it for every other parlay group, so a role
#' group and a structure group over the same fixtures share one identity.
#' @param fixture_ids Character vector of the group's fixtures.
#' @return A single character group id.
#' @noRd
.parlay_role_group_id <- function(fixture_ids) {
  parlay_group_identity(as.character(fixture_ids))
}

#' Typed-empty planning results for the role stages
#'
#' Internal. Empty results keep their full column set and types so "no rows" and
#' "wrong shape" stay distinguishable, and so an empty role plan can be consumed
#' by the same code as a populated one.
#' @param what One of "scores", "legs", "groups", "trace", "shortages",
#'   "budget_state".
#' @return The typed-empty tibble for that shape.
#' @noRd
.parlay_role_typed_empty <- function(what) {
  switch(what,
    scores = tibble::tibble(
      fixture_id = character(0), role = integer(0), score = numeric(0),
      rank = integer(0), retained_probability = numeric(0),
      allowed_outcomes = list()),
    legs = tibble::tibble(
      group_slot = integer(0), group_id = character(0), fixture_id = character(0),
      role = integer(0), round = integer(0), allowed_outcomes = list(),
      retained_probability = numeric(0)),
    groups = tibble::tibble(
      group_slot = integer(0), group_id = character(0), complete = logical(0)),
    trace = tibble::tibble(
      round = integer(0), turn = integer(0), group_slot = integer(0),
      role = integer(0), fixture_id = character(0), action = character(0),
      reason = character(0)),
    shortages = tibble::tibble(
      group_slot = integer(0), group_id = character(0), round = integer(0),
      turn = integer(0), role = integer(0), reason = character(0)),
    selection = tibble::tibble(
      group_slot = integer(0), group_id = character(0), rank = integer(0),
      package_units = integer(0), package_cost_cny = numeric(0),
      package_score = numeric(0), selected = logical(0), reason = character(0)),
    stop(".parlay_role_typed_empty: unknown shape ", what))
}

#' Typed-empty evaluation tables for the role portfolio stage
#'
#' Internal. `parlay_evaluate_portfolio()` must return ONE shape whether it found
#' work or not: `improve = TRUE` and `improve = FALSE` share it exactly, and only
#' the `changes` table differs (typed-empty when improvement is disabled).
#' @param what One of "metrics", "group_summary", "tickets", "changes".
#' @return The typed-empty tibble for that shape.
#' @noRd
.parlay_role_eval_empty <- function(what) {
  switch(what,
    metrics = tibble::tibble(
      stage = character(0), objective = character(0), purchased_tickets = integer(0),
      cost_cny = numeric(0), expected_winning_tickets = numeric(0),
      ev_net_cny = numeric(0), ev_available = logical(0), unspent_cny = numeric(0),
      complete_groups = integer(0), planned_groups = integer(0)),
    group_summary = tibble::tibble(
      group_slot = integer(0), group_id = character(0), complete = logical(0),
      tickets = integer(0), cost_cny = numeric(0),
      expected_winning_tickets = numeric(0), ev_net_cny = numeric(0),
      ev_available = logical(0), unspent_cny = numeric(0),
      role1_fixture = character(0), role2_fixture = character(0),
      role3_fixture = character(0)),
    tickets = tibble::tibble(
      group_slot = integer(0), group_id = character(0), ticket_id = character(0),
      rank = integer(0), probability = numeric(0), cost_cny = numeric(0),
      sp_product_est = numeric(0), ev_net_est = numeric(0),
      ev_available = logical(0), legal = logical(0), objective_value = numeric(0)),
    changes = tibble::tibble(
      pass = integer(0), move = character(0), group_slot_a = integer(0),
      group_slot_b = integer(0), fixture_a = character(0), fixture_b = character(0),
      round_a = integer(0), round_b = integer(0), old_fixture = character(0), new_fixture = character(0),
      role = integer(0), objective_before = numeric(0), objective_after = numeric(0),
      delta = numeric(0), accepted = logical(0)),
    stop(".parlay_role_eval_empty: unknown shape ", what))
}
