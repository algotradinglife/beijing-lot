# N7 pipeline: ticket valuation, funding, freeze, and settlement.
#
# The split follows the contract's chronology rule: valuation and funding see only
# pre-cutoff information; settlement is a separate consumer that never feeds back
# into a frozen plan.

# SP valuation transform. The contract fixes the rule: an SP above the threshold is
# replaced by the replacement value because that estimate is not credible at the
# top of the range; an SP exactly at the threshold is left alone. A missing SP for
# ANY leg makes the whole product unavailable rather than partially substituted,
# because a product with an imputed leg is not an estimate of the ticket.
parlay_transform_sp <- function(sp, threshold, replacement) {
  # .var.name makes each message name the parameter rather than "Element 1".
  # checkmate's lower = is inclusive, so the strict tests are explicit: a threshold
  # of exactly 1 would rewrite every priced SP, and a replacement of exactly 0
  # would zero the product.
  checkmate::assert_numeric(threshold, len = 1L, any.missing = FALSE, finite = TRUE,
                            .var.name = "sp_threshold")
  if (threshold <= 1) {
    stop("parlay_transform_sp: sp_threshold must be a finite value above 1; got ", threshold)
  }
  checkmate::assert_numeric(replacement, len = 1L, any.missing = FALSE, finite = TRUE,
                            .var.name = "sp_replacement")
  if (replacement <= 0) {
    stop("parlay_transform_sp: sp_replacement must be a positive finite value; got ",
         replacement)
  }
  # SP must be a real number vector. Coercing text here would only warn and hand
  # back NA, turning a malformed feed into 'no SP available'.
  checkmate::assert_numeric(sp, any.missing = TRUE, .var.name = "sp")
  values <- as.double(sp)
  # A missing, non-finite or degenerate SP for ANY leg makes the whole product
  # unavailable rather than partially substituted: a product with an imputed leg
  # is not an estimate of that ticket.
  if (anyNA(values) || any(!is.finite(values)) || any(values <= 1)) return(NA_real_)
  ifelse(values > threshold, replacement, values)
}

# parlay_value_tickets(tickets, ticket_legs, prematch_sp, cutoff, sp_threshold,
#                  sp_replacement, unit_cny, payout_factor)
#   -> valued tickets
#
# Values are in CNY per ticket, not ratios:
#   gross_est  = unit_cny * payout_factor * probability * prod(adjusted SP)
#   ev_net_est = gross_est - unit_cny
# The payout factor is applied exactly once, at ticket level.
#' Estimate ticket value using pre-cutoff single-match SP
#'
#' Operates on explicit inputs. Invalid contracts raise errors; no network,
#' package installation or database writes occur.
#' @param tickets Enumerated ticket tibble, or the enumeration result list where required by plan freezing.
#' @param ticket_legs Tibble keyed by ticket_id and fixture_id with the selected W/D/L outcome. Its complete fixture/outcome pairs must reproduce each canonical physical ticket_id.
#' @param prematch_sp Pre-cutoff SP tibble; an empty table is allowed and causes unavailable estimated EV.
#' @param cutoff Explicit cutoff object with cutoff_utc (UTC POSIXct) and character issue_id. Decision inputs must precede it.
#' @param sp_threshold Single-match SP threshold above which the replacement is used for estimation only.
#' @param sp_replacement Estimated SP to substitute for values above sp_threshold; actual settlement SP is unchanged.
#' @param unit_cny Positive numeric cost of one physical ticket, in CNY.
#' @param payout_factor Positive ticket-level payout factor, applied once.
#' @return A ticket tibble with estimated gross return and net EV in CNY; missing SP gives NA EV.
parlay_value_tickets <- function(tickets, ticket_legs, prematch_sp, cutoff, sp_threshold,
                             sp_replacement, unit_cny, payout_factor) {
  match_require_cutoff(cutoff)
  match_validate_table(tickets, "tickets", keys = "ticket_id")
  match_validate_table(ticket_legs, "ticket_legs", keys = c("ticket_id", "fixture_id"))
  match_validate_table(prematch_sp, "prematch_sp")
  # The same threshold/replacement pair parlay_transform_sp enforces. Validating it in
  # only one of the two would let a bad constant price tickets here while the
  # transform still refuses it.
  checkmate::assert_numeric(sp_threshold, len = 1L, any.missing = FALSE, finite = TRUE,
                            lower = 1, .var.name = "sp_threshold")
  if (sp_threshold <= 1) {
    stop("parlay_value_tickets: sp_threshold must be above 1; got ", sp_threshold)
  }
  checkmate::assert_numeric(sp_replacement, len = 1L, any.missing = FALSE, finite = TRUE,
                            lower = 0, .var.name = "sp_replacement")
  if (sp_replacement <= 0) {
    stop("parlay_value_tickets: sp_replacement must be positive; got ", sp_replacement)
  }
  checkmate::assert_numeric(unit_cny, len = 1L, any.missing = FALSE, finite = TRUE,
                            lower = 0, .var.name = "unit_cny")
  if (unit_cny <= 0) stop("parlay_value_tickets: unit_cny must be positive; got ", unit_cny)
  checkmate::assert_numeric(payout_factor, len = 1L, any.missing = FALSE, finite = TRUE,
                            lower = 0, upper = 1, .var.name = "payout_factor")
  if (payout_factor <= 0) {
    stop("parlay_value_tickets: payout_factor must lie in (0,1]; got ", payout_factor)
  }
  if (!setequal(tickets$ticket_id, ticket_legs$ticket_id)) {
    stop("parlay_value_tickets: ticket identifiers must match the ticket legs exactly")
  }
  if (!nrow(tickets)) {
    empty <- match_typed_empty("tickets")
    return(empty)
  }
  # SP must be pre-cutoff. A quote at or after the cutoff is not available to the
  # decision and must not price the ticket.
  usable_sp <- prematch_sp[prematch_sp$quote_at < cutoff$cutoff_utc, , drop = FALSE]

  out <- tickets
  # The plan width comes from the tickets themselves, so valuation works for any
  # n_legs the plan was built with instead of a fixed seven. ticket_legs is NOT a
  # group_legs table, so the width is read from its own leg counts; a plan that
  # mixed widths would already have been refused at enumeration.
  widths <- unique(as.integer(table(ticket_legs$ticket_id)))
  if (length(widths) != 1L || widths < 1L) {
    stop("parlay_value_tickets: every ticket must have the same positive leg count")
  }
  plan_legs <- widths
  # Resolve only referenced directions, once per call. Conflicts in unrelated
  # fixtures remain irrelevant; every historical instant for a used direction
  # retains the original contradiction check before its latest quote is chosen.
  directions <- dplyr::distinct(ticket_legs, fixture_id, outcome)
  direction_keys <- paste0(directions$fixture_id, "|", directions$outcome)
  quote_indices <- split(seq_len(nrow(usable_sp)),
    paste0(usable_sp$fixture_id, "|", usable_sp$outcome))
  direction_sp <- rep(NA_real_, nrow(directions))
  for (j in seq_len(nrow(directions))) {
    row <- usable_sp[quote_indices[[direction_keys[j]]], , drop = FALSE]
    if (nrow(row)) {
      by_instant <- split(row$sp_raw, as.numeric(row$quote_at))
      conflicting <- vapply(by_instant, function(v) length(unique(v)) > 1L, logical(1))
      if (any(conflicting)) {
        stop("parlay_value_tickets: conflicting SP quotes at one instant for fixture ",
             directions$fixture_id[j], " outcome ", directions$outcome[j])
      }
      row <- row[order(row$quote_at), , drop = FALSE]
      direction_sp[j] <- row$sp_raw[nrow(row)]
    }
  }
  # Outcome codes have fixed one-character W/D/L values, so the suffix makes
  # these direction keys injective even when a fixture identifier contains '|'.
  leg_indices <- split(seq_len(nrow(ticket_legs)), ticket_legs$ticket_id)
  for (i in seq_len(nrow(out))) {
    ticket_id <- out$ticket_id[i]
    legs <- ticket_legs[leg_indices[[ticket_id]], , drop = FALSE]
    if (nrow(legs) != plan_legs) {
      stop("parlay_value_tickets: ticket ", ticket_id, " has ", nrow(legs),
           " legs, expected ", plan_legs)
    }
    physical_id <- parlay_physical_ticket_key(
      legs$fixture_id, match(legs$outcome, match_outcomes()))
    if (!identical(ticket_id, physical_id)) {
      stop("parlay_value_tickets: ticket legs do not match the physical ticket identity")
    }
    sps <- direction_sp[match(paste0(legs$fixture_id, "|", legs$outcome),
                              direction_keys)]
    adjusted <- parlay_transform_sp(sps, sp_threshold, sp_replacement)
    if (anyNA(adjusted)) {
      out$sp_product_est[i] <- NA_real_
      out$ev_net_est[i] <- NA_real_
      next
    }
    product_sp <- prod(adjusted)
    out$sp_product_est[i] <- product_sp
    # Contract units: gross_est is the estimated CNY return of ONE unit, so the net
    # figure is gross_est minus that unit. Expressing EV as a ratio (gross/unit - 1)
    # would silently scale every number by unit_cny and break budget comparisons.
    gross_est <- unit_cny * payout_factor * out$probability[i] * product_sp
    out$ev_net_est[i] <- gross_est - unit_cny
  }
  match_validate_table(out, "tickets", keys = "ticket_id")
}

# --- group-level construction of the whole decision --------------------------

# One full issue decision: build groups, apply a structure, enumerate, value, then
# fund within the budget. Returns everything the freeze step needs.
#' Build candidate groups, structural supports and valued tickets
#'
#' Operates on explicit inputs. Invalid contracts raise errors; no network,
#' package installation or database writes occur.
#' @param fixtures Validated fixture tibble containing issue identity, kickoff time and handicap.
#' @param probabilities Tibble keyed by fixture_id and outcome, with nonnegative W/D/L probabilities summing to one per fixture.
#' @param prematch_sp Pre-cutoff SP tibble; an empty table is allowed and causes unavailable estimated EV.
#' @param cutoff Explicit cutoff object with cutoff_utc (UTC POSIXct) and character issue_id. Decision inputs must precede it.
#' @param match_status Required match-status observation ledger; a missing ledger errors and an empty one excludes every fixture.
#' @param patterns Named list of n_legs-long vectors of allowed outcome counts (1, 2 or 3).
#' @param construction Explicit group construction policy, including supplied groups when applicable.
#' @param max_candidates Positive integer limit on constructed fixture groups.
#' @param seed Explicit integer seed for deterministic construction.
#' @param constants Named business constants returned by parlay_settings(); values are passed explicitly, never learned here.
#' @return A list of group, structure, ticket and valuation tables without settlement information.
.BuildDecisionTables <- function(fixtures, probabilities, prematch_sp, cutoff,
                              match_status, patterns, construction, max_candidates,
                              seed, constants) {
  # constants$n_legs is read immediately below, and a NULL list would make it NULL
  # rather than fail. The other constants are read further down the same call.
  checkmate::assert_list(constants, names = "named", .var.name = "constants")
  required_constants <- c("n_legs", "unit_cny", "payout_factor", "sp_threshold")
  missing_constants <- setdiff(required_constants, names(constants))
  if (length(missing_constants)) {
    stop(".BuildDecisionTables: constants is missing ",
         paste(missing_constants, collapse = ", "))
  }
  # patterns is a list of integer vectors, each as long as the plan's n_legs. An
  # empty list would build no structures at all and silently produce an empty
  # decision; a pattern of the wrong width is a structural mismatch, not something
  # to pad or truncate.
  checkmate::assert_list(patterns, min.len = 1L, .var.name = "patterns")
  n_legs <- constants$n_legs
  checkmate::assert_count(n_legs, positive = TRUE, .var.name = "constants$n_legs")
  wrong_width <- vapply(patterns, function(p) length(p) != n_legs, logical(1))
  if (any(wrong_width)) {
    stop(".BuildDecisionTables: every pattern must have ", n_legs,
         " legs; pattern(s) ", paste(which(wrong_width), collapse = ", "),
         " disagree")
  }
  groups <- parlay_construct_groups(fixtures, probabilities, cutoff,
                                    n_legs, construction,
                                    max_candidates, seed, match_status)
  # Every pattern in the allocation is applied over the same groups, each under its
  # own candidate label. Applying only patterns[[1]] would silently ignore the rest
  # of a mixed allocation, and sharing one label would collide distinct structures.
  structures <- lapply(seq_along(patterns), function(index) {
    label <- paste0("p", paste(patterns[[index]], collapse = ""))
    parlay_apply_structure(groups$group_legs, probabilities, cutoff,
                       patterns[[index]], candidate_label = label)
  })
  supports <- dplyr::bind_rows(lapply(structures, function(s) s$supports))
  support_summary <- dplyr::bind_rows(lapply(structures, function(s) s$support_summary))
  exhausted <- unlist(lapply(structures, function(s) s$exhausted))
  structure <- list(supports = supports, support_summary = support_summary,
                    exhausted = exhausted, per_pattern = structures)
  tickets <- parlay_enumerate_tickets(groups$group_legs, probabilities, cutoff, supports,
                                       n_legs = constants$n_legs)
  valued <- parlay_value_tickets(tickets$tickets, tickets$ticket_legs, prematch_sp,
                             cutoff, constants$sp_threshold, constants$sp_replacement,
                             constants$unit_cny, constants$payout_factor)
  list(groups = groups, structure = structure, tickets = tickets, valued = valued)
}

# --- funding ----------------------------------------------------------------

# Rank tickets inside the hard legal support space.
#
#   parlay_rank_tickets(tickets, candidate_tickets, cutoff, ranking)
#     -> candidate_id, ticket_id, rank, cumulative_mass  (+ probability, ev_net_est)
#
# The contract's first version ranks by descending probability ("probability_desc").
# The optional EV comparison exists for later use, but it requires a COMPLETE
# valuation: if any ticket in the space lacks an EV, EV ranking is refused rather
# than silently dropping those tickets or treating them as zero. Ranking on
# probability alone needs no SP at all, which is what keeps the decision available
# when only part of the slate is priced.
#' Rank tickets within each candidate
#'
#' Operates on explicit inputs. Invalid contracts raise errors; no network,
#' package installation or database writes occur.
#' @param tickets Enumerated ticket tibble, or the enumeration result list where required by plan freezing.
#' @param candidate_tickets Tibble of unique candidate_id/ticket_id associations; physical tickets may be shared.
#' @param cutoff Explicit cutoff object with cutoff_utc (UTC POSIXct) and character issue_id. Decision inputs must precede it.
#' @param ranking Ranking policy: probability_desc or ev_desc; EV ranking requires available values.
#' @return A ranked tibble with candidate-specific integer rank and unnormalised cumulative probability.
parlay_rank_tickets <- function(tickets, candidate_tickets, cutoff,
                            ranking = "probability_desc") {
  match_require_cutoff(cutoff)
  match_validate_table(tickets, "tickets", keys = "ticket_id")
  # Full schema validation, not just a column presence check. candidate_tickets
  # declares the composite key (candidate_id, ticket_id); a duplicated reference
  # would otherwise be ranked twice and then BOUGHT twice, charging the issue budget
  # for the same physical ticket. Enforcing the declared key here is what makes that
  # declaration load-bearing on the real purchase path.
  match_validate_table(candidate_tickets, "candidate_tickets")
  if (!ranking %in% c("probability_desc", "ev_desc")) {
    stop("parlay_rank_tickets: ranking must be 'probability_desc' or 'ev_desc', got ", ranking)
  }
  if (!nrow(candidate_tickets)) {
    return(tibble::tibble(
      candidate_id = character(0), ticket_id = character(0),
      group_id = character(0), probability = numeric(0), ev_net_est = numeric(0),
      rank = integer(0), cumulative_mass = numeric(0)))
  }
  merged <- merge(as.data.frame(candidate_tickets), as.data.frame(tickets),
                  by = "ticket_id", all.x = TRUE, sort = FALSE)
  if (anyNA(merged$probability)) {
    stop("parlay_rank_tickets: candidate_tickets references tickets outside the table")
  }
  if (identical(ranking, "ev_desc") && anyNA(merged$ev_net_est)) {
    # No silent fallback: an incomplete valuation cannot support an EV comparison.
    stop("parlay_rank_tickets: ev_desc requires a complete valuation; ",
         sum(is.na(merged$ev_net_est)), " of ", nrow(merged), " candidate tickets have no EV")
  }
  score <- if (identical(ranking, "ev_desc")) merged$ev_net_est else merged$probability
  # Descending score, ties broken by ticket_id so the order never depends on row order.
  ordering <- order(merged$candidate_id, -score, merged$ticket_id)
  merged <- merged[ordering, , drop = FALSE]
  merged$rank <- stats::ave(seq_len(nrow(merged)), merged$candidate_id, FUN = seq_along)
  merged$cumulative_mass <- stats::ave(merged$probability, merged$candidate_id,
                                       FUN = cumsum)
  merged$cumulative_mass[merged$rank == 1L] <- merged$probability[merged$rank == 1L]
  out <- tibble::as_tibble(merged[, c("candidate_id", "ticket_id", "group_id",
                                      "probability", "ev_net_est", "rank",
                                      "cumulative_mass")])
  out$rank <- as.integer(out$rank)
  out
}

# Fund the ranked list from a budget, honouring group admission.
#
# Two constraints act here and they are different:
#   * a per-GROUP ticket cap (the structure's share of the budget), and
#   * group admission (reuse and overlap caps across the issue).
# A ticket whose group cannot be admitted is not bought, and its budget share is
# not silently reassigned to another group.
#' 计算某个候选实际买中的票的派彩
#'
#' @param picked          tibble，该候选实际购买的票（含 ticket_id）。
#' @param ticket_strings  具名字符向量，ticket_id -> 实现结果串。
#' @param occupied       长度 1 的字符，本期的实现结果串（NA 表示尚未确定）。
#' @param legs           tibble，该候选所属组的腿（含 fixture_id）。
#' @param visible        tibble，可见的结算标签。
#' @param issue_id       长度 1 的非空字符串，期号（用于冲突错误信息）。
#' @param unit_cny       长度 1 的正数，单票成本。
#' @param payout_factor  长度 1 的数，派彩系数。
#' @return list(payout, sp_missing)：payout 为该候选全部中奖票的派彩合计；
#'   sp_missing 表示存在中奖票但 SP 尚不可用。
#' @details 一张票只有在**全部腿**都与实现结果一致时才派彩。必须检查每一张已购
#'   票，而不只是第一张：一个结构会买很多票，其中任何一张都可能是赢家。
#'
#' 中奖但 SP 尚不可用的票是 PENDING 而不是输：结算层同样拒绝结算它，诊断必须给出
#' 一致的结论。
#'
#' 两侧都以 W/D/L 字符串比较：数值编码串永不相等，会把一笔中奖购买报成未中。
parlay_payout_for_candidate <- function(picked, ticket_strings, occupied, legs, visible,
                                     issue_id, unit_cny, payout_factor) {
    # A ticket pays only if the realised result matches all of its legs. Every
    # purchased ticket must be checked, not just the first: a structure buys many
    # tickets and any one of them can be the winner.
    payout <- 0
    # A matching ticket whose SP is not yet available is PENDING, not a loss: the
    # settlement layer also refuses to settle it, so the diagnostic must agree.
    sp_missing <- FALSE
    if (!is.na(occupied) && nrow(picked)) {
      for (ticket_id in picked$ticket_id) {
        # Both sides are compared as W/D/L strings; a numeric code string would never
        # match and would report a winning purchase as a miss.
        if (!identical(ticket_strings[[ticket_id]], occupied)) next
        odds <- vapply(legs$fixture_id, function(fixture_id) {
          row <- visible[visible$fixture_id == fixture_id, , drop = FALSE]
          if (!nrow(row)) return(NA_real_)
          # Conflicting SP for one key is a data error here too: taking the last row
          # would make the payout depend on row order, exactly as in settlement.
          usable <- unique(row$settled_sp[!is.na(row$settled_sp)])
          if (length(usable) > 1L) {
            stop("parlay_diagnose_plan: conflicting settled SP for issue ", issue_id,
                 " fixture ", fixture_id)
          }
          if (!length(usable)) return(NA_real_)
          usable[1]
        }, numeric(1))
        # Only a usable odds can be valued. NA, zero, negative or non-finite odds all
        # mean the ticket is not yet valueable, so it stays PENDING rather than being
        # reported as a loss or producing a fabricated payout.
        if (anyNA(odds) || any(!is.finite(odds)) || any(odds <= 0)) {
          sp_missing <- TRUE
        } else {
          payout <- payout + unit_cny * payout_factor * prod(odds)
        }
      }
    }
  list(payout = payout, sp_missing = sp_missing)
}

#' 重建每个候选的合法结果组合
#'
#' @param candidates tibble，supports 表（含 candidate_id、fixture_id、outcome、allowed）。
#' @param group_legs tibble，group_legs 表（含 group_id、fixture_id、leg_order）。
#' @return 具名 list：名字为 candidate_id，值为该候选全部合法组合的字符串向量
#'   （每串 n_legs 位，按腿序拼接 W/D/L）。
#' @details 从候选**自己的支撑表**重建，而不是另算一套：诊断因此不可能与枚举实际
#'   产出的组合不一致。
#'
#' 枚举必须按**与实现串相同的腿序**：取首次出现的行序会让组合串依赖行序，于是
#' 成员判定与 support_mass 会在行被重排时改变。
#'
#' 重复的显式组会把同一场比赛列多次；按比赛折叠为一条腿，使组合串保持 n_legs 位，
#' 与枚举比较的实现串一致。
#'
#' 没有 allowed 结果的腿会产生空选项集，从而该候选一个组合都没有 —— 这是合法的
#' 结果（该结构已被完全排除），不是错误。
parlay_candidate_support_grid <- function(candidates, group_legs) {
  checkmate::assert_data_frame(candidates, .var.name = "candidates")
  checkmate::assert_data_frame(group_legs, .var.name = "group_legs")
  # The legal combinations of each candidate, rebuilt from its support table so the
  # diagnostic cannot disagree with what enumeration actually produced.
  candidate_support <- lapply(split(candidates, candidates$candidate_id), function(block) {
    # Enumerate the support in the SAME leg order the realised string uses. Taking
    # the first-seen row order would make the combination strings depend on row
    # order, so membership and support_mass could change when rows are shuffled.
    group_id <- sub("[|].*$", "", block$candidate_id[1])
    reference <- group_legs[group_legs$group_id == group_id, , drop = FALSE]
    reference <- reference[order(reference$leg_order), , drop = FALSE]
    reference <- reference[!duplicated(reference$fixture_id), , drop = FALSE]
    # A repeated explicit group lists a fixture more than once; collapse to one leg
    # per fixture so the combination strings stay n_legs long, matching the realised
    # string that enumeration compares against.
    fixture_ids <- reference$fixture_id[reference$fixture_id %in% block$fixture_id]
    fixture_ids <- unique(fixture_ids)
    options <- lapply(fixture_ids, function(f) {
      allowed <- block$outcome[block$fixture_id == f & block$allowed]
      match_outcomes()[match_outcomes() %in% allowed]
    })
    grid <- expand.grid(options, KEEP.OUT.ATTRS = FALSE, stringsAsFactors = FALSE)
    apply(grid, 1L, paste, collapse = "")
  })
  names(candidate_support) <- names(split(candidates, candidates$candidate_id))
  candidate_support
}

#' 解析在本诊断时点可见的权威结算标签
#'
#' @param settlements tibble，settlements 表。
#' @param issue_id    长度 1 的非空字符串，本决策的期号。
#' @param as_of       长度 1 的 UTC POSIXct，诊断时点。
#' @return tibble，仅含本期、在 as_of 前可用、且确实已结算的行。
#' @details 只允许读权威标签：**本期**、在 as_of 前**可用**、且真正**已结算**。
#'   别期的标签，或一条状态被取消却仍带 outcome 的行，会去结算一个与它无关的方案。
#'
#' 同一 (issue, fixture) 上标签互相冲突是数据错误 —— 与 parlay_settle_plan 一致。这项
#' 检查在**每一条可见行**上做，而不只是被买中的那张赢票触及的行，这样诊断的结论就
#' 不依赖于恰好买了哪张票，也不依赖行序。
#'
#' status 为 NA 的行**不是**已结算行：丢掉它会让诊断把该腿当成完整并把这票记成
#' 输。保留它，使该腿解析为 PENDING 与金额未知，与 parlay_settle_plan 保持一致。
parlay_visible_settlements <- function(settlements, issue_id, as_of) {
  checkmate::assert_data_frame(settlements, .var.name = "settlements")
  match_check_character_id(issue_id, "issue_id")
  checkmate::assert_posixct(as_of, len = 1L, any.missing = FALSE, .var.name = "as_of")
  # Only authoritative labels may be read: the right issue, available by as_of, and
  # actually settled. A foreign issue's label or a cancelled row that still carries an
  # outcome would otherwise settle a plan it has nothing to do with.
  visible <- settlements[!is.na(settlements$label_available_at) &
                           settlements$label_available_at <= as_of, , drop = FALSE]
  visible <- visible[visible$issue_id == issue_id, , drop = FALSE]
  # Conflicting labels for one (issue, fixture) are a data error, exactly as in
  # parlay_settle_plan. Checking this up front -- on every visible row, not only the rows
  # a purchased winner touches -- keeps the diagnostic's verdict independent of which
  # ticket happened to be bought and of row order.
  if (nrow(visible)) {
    by_key <- split(visible, paste(visible$issue_id, visible$fixture_id, sep = "\r"))
    for (block in by_key) {
      for (field in c("outcome", "status")) {
        if (!field %in% names(block)) next
        values <- unique(as.character(block[[field]]))
        if (length(values) > 1L && field == "outcome") {
          stop("parlay_diagnose_plan: conflicting settlement outcomes for issue ",
               block$issue_id[1], " fixture ", block$fixture_id[1])
        }
        if (length(values) > 1L && field == "status" &&
            any(values != "settled")) {
          stop("parlay_diagnose_plan: conflicting settlement status for issue ",
               block$issue_id[1], " fixture ", block$fixture_id[1])
        }
      }
      usable <- unique(block$settled_sp[!is.na(block$settled_sp)])
      if (length(usable) > 1L) {
        stop("parlay_diagnose_plan: conflicting settled SP for issue ",
             block$issue_id[1], " fixture ", block$fixture_id[1])
      }
    }
  }
  # A row whose status is MISSING is not a settled row: dropping it would let the
  # diagnostic treat the leg as complete and book the ticket as a loss. Keep it so the
  # leg resolves to PENDING with an unknown amount, matching parlay_settle_plan.
  if ("status" %in% names(visible)) {
    status_lower <- tolower(as.character(visible$status))
    visible <- visible[is.na(status_lower) | status_lower == "settled", , drop = FALSE]
  }
  visible
}

#' 逐候选执行准入与选票，生成购买台账
#'
#' @param allocations      list，每项含 candidate_id、group_id、budget_units。
#' @param ranked           tibble，ranked 表。
#' @param group_legs       tibble，group_legs 表。
#' @param admitted         list，此前已投的比赛集合（每项含 group_id 与 fixtures）。
#' @param selected_ticket_ids 字符向量，本 issue 已被选中的物理票。
#' @param budget_units_left 长度 1 的整数，本次调用剩余可用单位。
#' @param max_reuse,max_overlap 长度 1 的整数，组准入上限。
#' @param unit_cny         长度 1 的正数，单票成本。
#' @param issue_id,epoch_at 购买台账的期号与时点（可为 NULL）。
#' @return list：purchases(tibble)、funded_ids、selected_ticket_ids、
#'   budget_units_left、rejected、admitted。
#' @details 准入约束作用在**比赛集合**而不是结构上：同一批比赛上的两种结构在复用
#' 与重叠判定中仍然共用这批比赛。
#'
#' 一张在本 issue 任何位置已被选中的物理票永不再买 —— 无论它在更早的期次，还是
#' 就在本次调用的前面被选中。这正是阻止同一批比赛上的两种结构重复购买共享组合
#' 的机制。
#'
#' 注资严格限制在该候选自己的额度内：上限是声明的方案，剩余 issue 预算是最外层
#' 天花板。绝不借用其他候选的额度，否则会把混合配置抹平。
parlay_fund_admitted_groups <- function(allocations, ranked, group_legs, admitted,
                                    selected_ticket_ids, budget_units_left,
                                    max_reuse, max_overlap, unit_cny,
                                    issue_id = NULL, epoch_at = NULL) {
  n_groups <- length(allocations)
  # selected_ticket_ids and budget_units_left are INPUTS here: the caller has
  # already seeded them from the prior ledger and the affordable-unit count.
  purchases <- list()
  funded_ids <- character(0)
  rejected <- character(0)

  for (i in seq_len(n_groups)) {
    allocation <- allocations[[i]]
    group_id <- allocation$group_id
    candidate_id <- allocation$candidate_id
    legs <- group_legs[group_legs$group_id == group_id, , drop = FALSE]
    fixtures_of_group <- sort(unique(legs$fixture_id))
    # Admission is a constraint on FIXTURE SETS, not on structures: two patterns over
    # the same fixtures still share those fixtures for reuse/overlap purposes.
    verdict <- parlay_group_admission(
      prior_groups = lapply(admitted, function(x) x$fixtures),
      candidate = fixtures_of_group, max_reuse = max_reuse, max_overlap = max_overlap)
    if (!isTRUE(verdict$admitted)) {
      rejected <- c(rejected, candidate_id)
      next
    }
    # Tickets of this candidate only, already ranked; take the top of what is left.
    group_tickets <- ranked[ranked$candidate_id == candidate_id, , drop = FALSE]
    # A physical ticket selected anywhere on this issue is never bought again --
    # neither in an earlier epoch nor earlier in this very call, which is what stops
    # two structures over one fixture set from double-buying a shared combination.
    if (length(selected_ticket_ids)) {
      group_tickets <- group_tickets[!group_tickets$ticket_id %in% selected_ticket_ids, , drop = FALSE]
    }
    # Fund strictly inside this candidate's allowance: the cap is the declared plan
    # and the remaining issue budget is the outer ceiling. Never borrow from another
    # candidate's allowance, which would flatten a mixed allocation.
    allowance <- min(allocation$budget_units, budget_units_left)
    take <- min(nrow(group_tickets), allowance)
    if (take < 1L) next
    # Register the group as admitted only NOW, after it actually buys something.
    # Registering at the admission check let a group that bought NOTHING still
    # consume its fixture set for reuse/overlap: with max_reuse = 1, a zero-allowance
    # first group would block a later group that shares its fixtures -- even though
    # the first group never placed a ticket on them.
    existing <- which(vapply(admitted, function(x) identical(x$group_id, group_id), logical(1)))
    if (!length(existing)) {
      admitted[[length(admitted) + 1L]] <- list(group_id = group_id, fixtures = fixtures_of_group)
    } else if (!identical(sort(admitted[[existing[1L]]]$fixtures), fixtures_of_group)) {
      stop("parlay_fund_admitted_groups: one group identity names conflicting fixture sets")
    }

    chosen <- group_tickets[seq_len(take), , drop = FALSE]
    funded_ids <- c(funded_ids, chosen$ticket_id)
    selected_ticket_ids <- c(selected_ticket_ids, chosen$ticket_id)
    budget_units_left <- budget_units_left - take
    purchases[[length(purchases) + 1L]] <- tibble::tibble(
      issue_id = rep(if (is.null(issue_id)) NA_character_ else as.character(issue_id),
                     nrow(chosen)),
      ticket_id = chosen$ticket_id,
      epoch_at = rep(if (is.null(epoch_at)) as.POSIXct(NA, tz = "UTC") else epoch_at,
                     nrow(chosen)),
      group_id = chosen$group_id,
      candidate_id = chosen$candidate_id,
      stake_cny = rep(as.double(unit_cny), nrow(chosen)))
  }
  list(purchases = purchases, funded_ids = funded_ids,
       selected_ticket_ids = selected_ticket_ids,
       budget_units_left = budget_units_left, rejected = rejected, admitted = admitted)
}

#' 校验票额上限的两种形式
#'
#' @param unit_cap  长度 1 的非负整数或 NULL，所有结构共用的票额上限。
#' @param unit_caps 具名数值向量或 NULL，按结构键索引的票额上限。
#' @return 不可见地返回 TRUE；不合法时抛错。
#' @details 抽取成独立函数，是因为 `.FundGroups()` 会在调用
#'   `parlay_resolve_allocations()` 之前提前返回。校验若只放在 resolver 内，空候选
#'   输入就会绕过全部检查并静默接受 NA/Inf/-1/1.5 这样的上限。
#'
#' `assert_count` 已拒绝 NA、负值与非整值；此处再补有限性与上界，避免
#' `as.integer()` 的溢出保护把越界值变成 NA。
parlay_check_unit_caps <- function(unit_cap, unit_caps) {
  if (!is.null(unit_cap)) {
    checkmate::assert_count(unit_cap, positive = FALSE, .var.name = "unit_cap")
  }
  if (!is.null(unit_caps)) {
    checkmate::assert_numeric(unit_caps, any.missing = FALSE, finite = TRUE,
                              lower = 0, .var.name = "unit_caps")
    if (any(unit_caps != trunc(unit_caps))) {
      stop(".FundGroups: unit_caps must be whole ticket counts")
    }
    if (any(unit_caps > .Machine$integer.max)) {
      stop(".FundGroups: unit_caps exceeds the integer range")
    }
  }
  invisible(TRUE)
}
#' 把 candidate 列表解析成逐候选的注资额度方案
#'
#' @param candidate_labels 字符向量，已定序的 candidate_id（形如 '<集合>|<结构键>'）。
#' @param pattern_keys     字符向量，已声明结构的键，顺序即声明顺序。
#' @param patterns         具名 list，名字为结构键，值为长度 n_legs 的整数向量。
#' @param unit_cap         长度 1 的整数或 NULL，所有结构共用的票额上限。
#' @param unit_caps        具名数值向量或 NULL，按结构键索引的票额上限。
#' @return list，每项含 candidate_id、group_id、pattern、cap_tickets。
#' @details candidate 与结构的配对**按它被构造时携带的 label**，绝不按它在 ranked
#'   表里的位置：用取模配对会把额度绑到恰好排在那里的结构上，从而把配置 B 的
#'   「3333222 拿 96」「2222221 拿 32」悄悄对调。
#'
#' unit_caps 按结构键索引而非按位置：两个恰好对齐的平行 list 一旦被改动就会静默
#' 错配，而错误的票额上限不会在输出里显形。缺名即报错，而不是退化成 NULL。
parlay_resolve_allocations <- function(candidate_labels, pattern_keys, patterns,
                                   unit_cap = NULL, unit_caps = NULL) {
  # Validate both cap forms BEFORE the loop, so an illegal cap fails even when the
  # candidate list is empty. Inside the loop an empty list would skip every check and
  # report success for NA/Inf/-1/1.5 -- a cap that is wrong but never exercised.
  # assert_count already rejects NA, negatives and non-whole values.
  parlay_check_unit_caps(unit_cap, unit_caps)
  n_groups <- length(candidate_labels)
  label_of <- function(candidate_id) sub("^.*[|]", "", candidate_id)
  allocations <- vector("list", n_groups)
  for (i in seq_len(n_groups)) {
    label <- label_of(candidate_labels[i])
    slot <- match(label, pattern_keys)
    if (is.na(slot)) {
      stop(".FundGroups: candidate ", candidate_labels[i],
           " does not match any declared pattern")
    }
    entry <- patterns[[slot]]
    # unit_cap (one value, or one per pattern key) is the allocation's own ticket
    # allowance for a group. Falling back to the structural space size would let a
    # group spend far beyond its share of the budget.
    #
    # unit_caps is indexed BY PATTERN NAME, not by position: two parallel lists that
    # merely happened to line up would mis-assign silently the moment either was
    # edited, and the wrong cap is not visible in the output. A missing name is an
    # error rather than a NULL that silently falls through to prod(entry).
    cap <- if (!is.null(unit_caps)) {
      key <- pattern_keys[[slot]]
      if (is.null(names(unit_caps)) || !key %in% names(unit_caps)) {
        stop(".FundGroups: no unit cap declared for pattern ", key,
             "; unit_caps must be named by pattern key (",
             paste(pattern_keys, collapse = ", "), ")")
      }
      as.integer(unit_caps[[key]])
    } else if (!is.null(unit_cap)) {
      as.integer(unit_cap)
    } else {
      prod(entry)
    }
    allocations[[i]] <- list(candidate_id = candidate_labels[i],
                             group_id = sub("[|].*$", "", candidate_labels[i]),
                             pattern = entry, cap_tickets = cap)
  }
  allocations
}

#' 把本次可用预算按优先级分配到各 candidate
#'
#' @param allocations  list，每项含 candidate_id 与 cap_tickets。
#' @param ranked       tibble，ranked 表（需 candidate_id 与 ticket_id）。
#' @param budget_cny   长度 1 的非负数值，本次分配声明的预算。
#' @param unit_cny     长度 1 的正数，单票成本。
#' @param prior_purchases tibble 或 NULL，本 issue 此前已购的票。
#' @param prior_fixture_sets list 或 NULL，此前已投的比赛集合。
#' @return list：allocations（补齐 capacity 与 budget_units）、prior_purchases、
#'   prior_msets、committed_ticket_ids、remaining、affordable、spent_before。
#' @details 这是**优先级填充**，不是按比例分摊：钱不够时排在前面的 candidate 先填满
#'   自己的上限，后面的拿剩下的。等比缩减会悄悄改变声明的方案 —— 两个上限 80 的
#'   candidate 拿着 160 元必须是 80/0，而不是 40/40。
#'
#' 预留时跟踪前面 candidate 已经占掉的票：只看历史期会把本次调用中已被前面
#' candidate 买走的组合也算进来，从而错误地扣掉后面 candidate 本可使用的额度。
parlay_allocate_budget_units <- function(allocations, ranked, budget_cny, unit_cny,
                                     prior_purchases = NULL, prior_fixture_sets = NULL) {
  n_groups <- length(allocations)
  prior_purchases <- prior_purchases %||% match_typed_empty("purchases")
  spent_before <- sum(prior_purchases$stake_cny)
  prior_msets <- prior_fixture_sets %||% list()
  committed_ticket_ids <- as.character(prior_purchases$ticket_id)
  remaining <- budget_cny - spent_before
  if (remaining < 0) remaining <- 0
  affordable <- floor(remaining / unit_cny)
  # Per-candidate allowance, filled IN ORDER to each candidate's cap. Two ceilings
  # bind together:
  #   * the declared cap, which encodes the allocation's spending plan, and
  #   * the candidate's own supported space, which cannot be exceeded however much
  #     budget is left.
  # This is a PRIORITY fill, not a proportional split: when money is short the
  # first-ordered candidate is filled to its cap and later ones receive what
  # remains. Scaling everyone down would silently change the requested allocation
  # (two candidates capped at 80 with CNY160 to spend must be 80/0, not 40/40).
  # Reserve for each candidate in priority order, tracking the tickets earlier
  # candidates already claimed. Counting each candidate's space in isolation against
  # only the PRIOR epochs would reserve units for combinations an earlier candidate in
  # this very call goes on to buy, stranding budget the later candidate could have
  # spent on an eligible ticket.
  left <- affordable
  reserved_tickets <- committed_ticket_ids
  for (i in seq_len(n_groups)) {
    own_tickets <- ranked$ticket_id[ranked$candidate_id == allocations[[i]]$candidate_id]
    available <- sum(!own_tickets %in% reserved_tickets)
    capacity <- min(as.integer(allocations[[i]]$cap_tickets), as.integer(available))
    if (capacity < 0L) capacity <- 0L
    allocations[[i]]$capacity <- capacity
    give <- min(capacity, left)
    allocations[[i]]$budget_units <- as.integer(give)
    left <- left - give
    # Only the tickets this candidate will actually take can block the next one.
    if (give > 0L) {
      claimable <- own_tickets[!own_tickets %in% reserved_tickets]
      reserved_tickets <- c(reserved_tickets, claimable[seq_len(min(give, length(claimable)))])
    }
  }
  list(allocations = allocations, prior_purchases = prior_purchases,
       prior_msets = prior_msets, committed_ticket_ids = committed_ticket_ids,
       remaining = remaining, affordable = affordable, spent_before = spent_before)
}

#' 选出本次注资参与的 candidate，并确定它们的优先顺序
#'
#' @param ranked_labels 字符向量，ranked 表里出现过的全部 candidate_id（去重）。
#' @param pattern_keys  字符向量，已声明结构的键（'p' + n_legs 位数字），顺序即声明顺序。
#' @param n_groups      长度 1 的正整数，本次分配声明的分组数。
#' @param group_order   字符向量或 NULL，调用方指定的注资优先级。
#' @return 字符向量：按最终注资顺序排列的 candidate_id。
#' @details 这一步把「投哪些结构」与「每个结构投多少」分开。三个决定：
#'   1. 可投宇宙始终是 ranked 表**实际产出**的 candidate，不因 group_order 收窄；
#'      调用方给的是优先级，不是替代清单。
#'   2. 声明的集合数按**不相交**方式分给各 structure：配置 B 是「8 组：4 组用
#'      3333222、4 组用 2222221」，把两个结构叠加到全部 8 个集合上会翻倍候选数
#'      并把每份票额减半，那不是声明的方案。集合数少于结构数时改为每个集合承载
#'      每个结构，以免后面的结构被完全饿死。
#'   3. group_order 命名的 candidate 必须进入候选清单（它可能落在不相交分配分给
#'      别的结构的那批集合上），随后按其请求顺序排到最前。
#'
#' 去重发生在 (集合, 结构) **配对**上而非集合上：只按集合去重会丢掉同一批比赛上
#' 另一个合法结构，留下一个可投却未投的票。
parlay_select_funding_candidates <- function(ranked_labels, pattern_keys, n_groups,
                                        group_order = NULL) {
  candidate_labels <- ranked_labels
  set_of <- function(candidate_id) sub("[|].*$", "", candidate_id)
  all_sets <- unique(set_of(candidate_labels))
  set_count <- min(length(all_sets), n_groups)
  # The rebuild chooses from EVERY ranked candidate, not from a pre-filtered subset:
  # narrowing the universe first would make a legitimately ranked structure
  # unreachable whenever it was not part of that subset.
  eligible_labels <- ranked_labels
  # Split the declared group count across the patterns as evenly as the declaration
  # allows: with 8 groups and 2 patterns that is 4 sets each, so no pattern can
  # appear on more sets than its own share. A plain modulo would keep cycling and
  # hand every remaining set to the first pattern.
  # Distribute the declared sets across the patterns DISJOINTLY where possible:
  # 8 groups over 2 patterns is 4 sets each, so config B stays 4 x 96 + 4 x 32 rather
  # than doubling every set. When there are fewer sets than patterns a disjoint split
  # would starve the later patterns entirely, so in that case each set carries each
  # pattern and no distinct structure is silently dropped.
  per_pattern <- rep(set_count %/% length(pattern_keys), length(pattern_keys))
  leftover <- set_count - sum(per_pattern)
  if (leftover > 0) per_pattern[seq_len(leftover)] <- per_pattern[seq_len(leftover)] + 1L
  chosen <- character(0)
  if (all(per_pattern > 0L)) {
    cursor <- 0L
    for (slot in seq_along(pattern_keys)) {
      for (take in seq_len(per_pattern[slot])) {
        cursor <- cursor + 1L
        wanted <- paste0(all_sets[cursor], "|", pattern_keys[slot])
        if (wanted %in% eligible_labels && !wanted %in% chosen) chosen <- c(chosen, wanted)
      }
    }
  } else {
    for (cursor in seq_len(set_count)) {
      for (slot in seq_along(pattern_keys)) {
        wanted <- paste0(all_sets[cursor], "|", pattern_keys[slot])
        if (wanted %in% eligible_labels && !wanted %in% chosen) chosen <- c(chosen, wanted)
      }
    }
  }
  # A caller-named priority must be part of the candidate list. The disjoint share
  # assigns each pattern to different sets, so a structure the caller explicitly
  # prioritised on a set that share gave to another pattern would otherwise be
  # missing -- and the priority would error as "not ranked" although it was ranked.
  if (!is.null(group_order)) {
    named <- as.character(group_order)
    for (label in named) {
      if (label %in% ranked_labels && !label %in% chosen) chosen <- c(chosen, label)
    }
  }
  # Deduplicate on the (set, pattern) PAIR. Deduplicating on the set alone would drop
  # a legitimately distinct second structure over the same fixtures -- exactly the
  # mixed allocation the declaration asks for when fixture sets are scarce -- leaving
  # an eligible, unpurchased ticket behind.
  chosen <- chosen[!duplicated(chosen)]
  candidate_labels <- chosen
  # Apply the caller's funding order to the FINAL candidate list. A full candidate id
  # names ONE structure; a bare fixture set names every structure over that set.
  # Matching only on the set would collapse two distinct structures over the same
  # fixtures into one priority and let the pattern order decide which is funded.
  if (!is.null(group_order)) {
    ordered <- as.character(group_order)
    priority <- vapply(candidate_labels, function(label) {
      hit <- match(label, ordered)
      if (!is.na(hit)) return(hit)
      match(sub("[|].*$", "", label), ordered)
    }, integer(1))
    # group_order names a PRIORITY, not a filter: every candidate the caller names
    # moves to the front in the requested order, and the rest follow in their existing
    # order. Requiring every candidate to be named would reject a caller who ranks one
    # structure ahead of the others; silently ignoring an unknown name would hide a
    # typo, so a name that matches nothing at all is still an error.
    # EVERY name the caller supplies must name something real. Tolerating an unknown
    # name just because another name happened to match would hide a typo and silently
    # fund the wrong structure.
    known <- unique(c(ranked_labels, sub("[|].*$", "", ranked_labels)))
    unknown <- setdiff(ordered, known)
    if (length(unknown)) {
      stop(".FundGroups: group_order names a group that was not ranked: ",
           paste(unknown, collapse = ", "))
    }
    if (all(is.na(priority))) {
      stop(".FundGroups: group_order names a group that was not ranked")
    }
    candidate_labels <- candidate_labels[order(is.na(priority), priority,
                                               seq_along(candidate_labels))]
  }
  candidate_labels
}

#' Allocate the remaining issue budget to ranked candidates
#'
#' Operates on explicit inputs. Invalid contracts raise errors; no network,
#' package installation or database writes occur.
#' @param group_legs Tibble keyed by group_id and fixture_id, with n_legs ordered legs per group.
#' @param ranked Ranked tibble with candidate-specific authoritative rank and cumulative mass.
#' @param patterns Named list of n_legs-long vectors of allowed outcome counts (1, 2 or 3).
#' @param budget_cny Nonnegative available budget in CNY, bounded by the explicit issue budget.
#' @param constants Named business constants returned by parlay_settings(); values are passed explicitly, never learned here.
#' @param max_reuse Positive integer limit on fixture reuse across distinct purchased groups.
#' @param max_overlap Integer upper limit on shared fixtures between distinct purchased groups.
#' @param group_order Character candidate priority order, or NULL to use the declared order.
#' @param unit_cap One nonnegative integer ticket cap shared by structures, or NULL.
#' @param prior_purchases Tibble of prior physical purchases; duplicates must not be bought again.
#' @param issue_id Nonempty character issue identifier, preserving leading zeros.
#' @param epoch_at UTC POSIXct decision instant, or NULL when no purchase is made.
#' @param unit_caps Named nonnegative integer caps keyed by structure, or NULL.
#' @param prior_fixture_sets Named list of fixture identifiers in groups bought earlier in this issue.
#' @return A list of purchases, funded tickets, admitted fixture sets and budget diagnostics. Empty inputs retain the prior ledger.
.FundGroups <- function(group_legs, ranked, patterns, budget_cny, constants,
                           max_reuse, max_overlap, group_order = NULL, unit_cap = NULL,
                           prior_purchases = NULL, issue_id = NULL, epoch_at = NULL,
                           unit_caps = NULL, prior_fixture_sets = NULL) {
  # constants supplies the issue ceiling consulted immediately below, so a NULL or
  # partial list would silently disable that ceiling rather than fail.
  checkmate::assert_list(constants, names = "named", .var.name = "constants")
  required_constants <- c("issue_budget_cny", "unit_cny", "payout_factor")
  missing_constants <- setdiff(required_constants, names(constants))
  if (length(missing_constants)) {
    stop(".FundGroups: constants is missing ",
         paste(missing_constants, collapse = ", "))
  }
  checkmate::assert_numeric(budget_cny, len = 1L, any.missing = FALSE, finite = TRUE,
                            .var.name = "budget_cny")
  if (budget_cny < 0) {
    stop(".FundGroups: budget_cny must be non-negative; got ", budget_cny)
  }
  # max_reuse and max_overlap are the group-admission caps. An NA cap would make
  # every admission comparison NA and silently admit nothing (or everything),
  # so both must be present whole numbers.
  # assert_count rejects NA, negatives and non-whole values by default
  # (na.ok defaults to FALSE), so no extra argument is needed here.
  checkmate::assert_count(max_reuse, .var.name = "max_reuse")
  checkmate::assert_count(max_overlap, .var.name = "max_overlap")
  # patterns 必须具名，且名字就是结构键。名字是从 pattern 内容派生的，因此必须与
  # 内容一致：一个叫 p3333222 但内容为 2222221 的条目会让 unit_caps 张冠李戴。
  #
  # 这段校验必须在下面的空宇宙提前返回**之前**：参数是否合法与本次调用恰好没有
  # 候选无关，放在返回之后会让空输入静默接受畸形 patterns。
  checkmate::assert_list(patterns, min.len = 1L, names = "unique",
                         .var.name = "patterns")
  if (is.null(names(patterns)) || any(!nzchar(names(patterns)))) {
    stop(".FundGroups: patterns must be a named list; names are the structure keys")
  }
  derived_keys <- vapply(patterns, function(p) paste0("p", paste(p, collapse = "")),
                         character(1))
  if (!identical(unname(names(patterns)), unname(derived_keys))) {
    mismatched <- names(patterns)[names(patterns) != derived_keys]
    stop(".FundGroups: pattern name(s) ",
         paste(mismatched, collapse = ", "),
         " do not match their contents")
  }
  # 上限本身必须先合法，再谈它挂在哪个 pattern 名下。这一步放在所有提前返回之前：
  # 空候选不该让 NA/Inf/-1/1.5 这样的上限静默通过。
  parlay_check_unit_caps(unit_cap, unit_caps)
  # unit_caps 必须按 pattern 名索引。两个恰好对齐的平行 list 一旦被改动就会静默
  # 错配，而错误的票额上限不会在输出里显形，所以这里要求名字完整。
  if (!is.null(unit_caps)) {
    checkmate::assert_numeric(unit_caps, names = "unique", .var.name = "unit_caps")
    if (is.null(names(unit_caps))) {
      stop(".FundGroups: unit_caps must be named by pattern key (",
           paste(derived_keys, collapse = ", "), ")")
    }
    missing_caps <- setdiff(derived_keys, names(unit_caps))
    if (length(missing_caps)) {
      stop(".FundGroups: no unit cap declared for pattern ",
           paste(missing_caps, collapse = ", "),
           "; unit_caps must be named by pattern key")
    }
  }
  # Validate the ranked input BEFORE any early return. Its declared composite key is
  # what stops the same physical ticket from being bought twice; checking it only on
  # the purchase path would let a duplicated reference through the empty-candidate
  # return and, more importantly, would leave the declaration unenforced wherever a
  # caller reaches this function directly.
  match_validate_table(ranked, "ranked", keys = c("candidate_id", "ticket_id"))
  # The ISSUE budget is an absolute ceiling on everything bought on one issue. A
  # config may declare a smaller demo limit, but never a larger one: an allocation
  # alone must not be able to spend past CNY1,024.
  budget_cny <- min(budget_cny, constants$issue_budget_cny)
  # Ledger state is computed BEFORE any early return, so the empty-candidate exits
  # report the same history the non-empty path would. An empty candidate list means
  # "nothing bought THIS call", not "this issue has no history": zeroing spent_before
  # or dropping fixture_sets would tell the next epoch the issue was untouched and
  # invite rebuying tickets that were already paid for.
  prior_purchases <- prior_purchases %||% match_typed_empty("purchases")
  prior_msets <- prior_fixture_sets %||% list()
  spent_before <- sum(prior_purchases$stake_cny)
  remaining <- budget_cny - spent_before
  if (remaining < 0) remaining <- 0
  affordable <- floor(remaining / constants$unit_cny)
  empty_exit <- function() {
    fixture_sets <- prior_msets
    list(purchases = match_typed_empty("purchases"),
         funded = match_typed_empty("ranked"),
         fixture_sets = fixture_sets,
         diagnostics = list(n_groups = 0L,
                            admitted_groups = names(prior_msets),
                            admitted_candidates = character(0),
                            rejected_groups = character(0),
                            affordable_units = as.integer(affordable),
                            unspent_units = as.integer(affordable),
                            spent_before_cny = spent_before,
                            remaining_cny = remaining))
  }
  # Allocation runs over CANDIDATES: one structure over one fixture set is one
  # investable unit. group_id alone cannot identify it, because several structures
  # may share a fixture set.
  # The investable universe is ALWAYS what the ranked table actually produced. It must
  # not be narrowed to group_order: the caller names a priority, not a replacement, and
  # using the requested labels as the universe would make the rebuild below unable to
  # recognise any candidate the caller did not happen to name first.
  ranked_labels <- unique(as.character(ranked$candidate_id))
  candidate_labels <- ranked_labels
  # Honour a caller-supplied funding order BEFORE any allowance is computed. Ordering
  # afterwards would leave the rounding leftovers attached to the original first
  # group_order is applied AFTER the candidate list is rebuilt below. Sorting or
  # validating here would be discarded by that rebuild, and would reject a label the
  # rebuild is about to create.
  n_groups <- length(candidate_labels)
  if (!n_groups) {
    # funded is returned in the RANKED shape by every other branch, so the empty
    # branch must use it too. Returning the tickets schema here changed the column
    # set between branches (no candidate_id/rank/cumulative_mass) and made every
    # downstream reader warn about a missing candidate_id column.
    return(empty_exit())
  }
  # Each candidate is matched to a pattern by the LABEL it was built with, never by
  # its position in the ranked table. Iterating with a modulo would pair a cap with
  # whichever pattern happened to sort there, silently swapping config B's "96 for
  # 3333222" and "32 for 2222221".
  label_of <- function(candidate_id) sub("^.*[|]", "", candidate_id)
  pattern_keys <- derived_keys
  # n_groups is the number of FIXTURE SETS the allocation invests in. A mixed
  # allocation alternates its patterns across those sets rather than applying every
  # pattern to every set: config B is "8 groups: 4 at 3333222 and 4 at 2222221", so
  # taking both structures on all 8 sets would double the candidate count and halve
  # each cap, which is not the declared plan.
  candidate_labels <- parlay_select_funding_candidates(ranked_labels, pattern_keys,
                                                 n_groups, group_order)
  n_groups <- length(candidate_labels)
  if (!n_groups) {
    return(empty_exit())
  }
  allocations <- parlay_resolve_allocations(candidate_labels, pattern_keys, patterns,
                                           unit_cap, unit_caps)
  budget_plan <- parlay_allocate_budget_units(allocations, ranked, budget_cny,
                                              constants$unit_cny,
                                              prior_purchases, prior_fixture_sets)
  allocations <- budget_plan$allocations
  prior_purchases <- budget_plan$prior_purchases
  prior_msets <- budget_plan$prior_msets
  committed_ticket_ids <- budget_plan$committed_ticket_ids
  remaining <- budget_plan$remaining
  affordable <- budget_plan$affordable
  spent_before <- budget_plan$spent_before
  # Every fixture set already invested in on this issue, from prior epochs and from
  # this call. Admission compares against the union, not just the current call.
  admitted <- list()
  if (length(prior_msets)) {
    for (k in seq_along(prior_msets)) {
      admitted[[length(admitted) + 1L]] <- list(group_id = names(prior_msets)[k],
                                                fixtures = prior_msets[[k]])
    }
  }
  # Seed the funding loop: physical tickets already bought on this issue, and the
  # units still affordable. Both are issue-level facts carried forward from the
  # budget plan, not per-candidate allowances.
  selected_ticket_ids <- as.character(prior_purchases$ticket_id)
  budget_units_left <- affordable
  funding <- parlay_fund_admitted_groups(allocations, ranked, group_legs, admitted,
                                       selected_ticket_ids, budget_units_left,
                                       max_reuse, max_overlap, constants$unit_cny,
                                       issue_id, epoch_at)
  purchases <- funding$purchases
  funded_ids <- funding$funded_ids
  selected_ticket_ids <- funding$selected_ticket_ids
  budget_units_left <- funding$budget_units_left
  rejected <- funding$rejected
  admitted <- funding$admitted
  # Cap and structure can both leave budget unspent; report it rather than silently
  # shifting the shortfall onto a later candidate.
  unspent <- budget_units_left
  # Funded is returned in the ranked shape so callers keep candidate identity, and
  # one row per PURCHASE: a ticket shared by two structures must not appear twice.
  # One row per BOUGHT ticket, taken from the purchase ledger and tied to the
  # CANDIDATE that bought it. A ticket id is shared by every structure over the same
  # fixture set, so a bare id lookup would report candidates that bought nothing.
  bought <- if (length(purchases)) dplyr::bind_rows(purchases) else match_typed_empty("purchases")
  funded <- if (nrow(bought)) {
    pick <- match(paste(bought$ticket_id, bought$candidate_id),
                  paste(ranked$ticket_id, ranked$candidate_id))
    if (anyNA(pick)) {
      stop(".FundGroups: a purchase has no matching ranked candidate")
    }
    ranked[pick, , drop = FALSE]
  } else {
    ranked[0, , drop = FALSE]
  }
  purchase_table <- bought
  # Admission inputs are returned alongside the ledger so the next epoch can seed
  # reuse/overlap from every group already invested in on this issue.
  fixture_sets <- lapply(admitted, function(x) x$fixtures)
  names(fixture_sets) <- vapply(admitted, function(x) x$group_id, character(1))
  list(purchases = purchase_table, funded = funded, fixture_sets = fixture_sets,
       diagnostics = list(n_groups = n_groups,
                          admitted_groups = vapply(admitted, function(x) x$group_id, character(1)),
                          admitted_candidates = setdiff(candidate_labels, rejected),
                          rejected_groups = rejected,
                          affordable_units = affordable,
                          unspent_units = unspent,
                          spent_before_cny = spent_before,
                          remaining_cny = remaining))
}

# Freeze: bind the plan to its inputs so a later settlement cannot rewrite it.
# The plan is a plain list of immutable tables plus the identity of what produced
# it. Nothing here reads settlement.
#' Freeze an explicit ticket proposal without writing to storage
#'
#' Operates on explicit inputs. Invalid contracts raise errors; no network,
#' package installation or database writes occur.
#' @param issue_id Nonempty character issue identifier, preserving leading zeros.
#' @param epoch_utc One UTC POSIXct decision instant.
#' @param group_legs Tibble keyed by group_id and fixture_id, with n_legs ordered legs per group.
#' @param structure Structural support result containing candidates and their legal outcome masks.
#' @param tickets Enumerated ticket tibble, or the enumeration result list where required by plan freezing.
#' @param valued Ticket tibble with probability and estimated value fields.
#' @param funded Funded candidate ticket table produced by allocation.
#' @param purchases Purchase ledger tibble with issue_id, ticket_id and stake_cny.
#' @param constants Named business constants returned by parlay_settings(); values are passed explicitly, never learned here.
#' @param policies Explicit named policy settings; no historical tuning is performed by this function.
#' @return A frozen plan list with receipt and immutable input identities.
.FreezeParlayPlan <- function(issue_id, epoch_utc, group_legs, structure, tickets,
                           valued, funded, purchases, constants, policies) {
  match_check_character_id(issue_id, "issue_id")
  # The epoch is the freeze's chronology anchor: a character or non-UTC instant
  # would pass through unread and make the frozen artifact wrongly replayable.
  checkmate::assert_posixct(epoch_utc, len = 1L, any.missing = FALSE,
                            .var.name = "epoch_utc")
  checkmate::assert_list(constants, names = "named", .var.name = "constants")
  # Freeze the plan width alongside unit_cny/payout_factor. Settlement reads these
  # values back from the plan, so a later session update can never re-price or
  # re-shape an already frozen plan.
  #
  # An EMPTY plan (no fixtures survived selection) has no group legs to read a width
  # from. That is not a width of zero: it is the declared plan width with nothing
  # built, so the frozen width uses the declared n_legs and a following
  # settle/diagnose call returns typed-empty instead of erroring on 0 == 7.
  n_legs <- parlay_structure_legs(group_legs)
  frozen_constants <- constants
  if (n_legs == 0L) n_legs <- as.integer(constants$n_legs)
  frozen_constants$n_legs <- n_legs
  checkmate::assert_true(as.integer(constants$n_legs) == n_legs,
                         .var.name = "constants$n_legs must match the plan width")
  list(
    issue_id = issue_id,
    epoch_utc = epoch_utc,
    constants = frozen_constants,
    policies = policies,
    group_legs = group_legs,
    supports = structure$supports,
    tickets = tickets$tickets,
    ticket_legs = tickets$ticket_legs,
    valued = valued,
    funded = funded,
    purchases = purchases)
}

# --- settlement (post-freeze only) ------------------------------------------

# parlay_settle_plan(plan, settlements, as_of)
#   -> list(ticket_returns, group_returns, issue_returns)
#
# Chronology: this is the only function that reads outcomes, and it reads a FROZEN
# plan. A ticket is:
#   * WON    - every leg matched, payout = unit * payout_factor * prod(settled SP)
#   * LOST   - at least one leg is known and differs, payout 0
#   * PENDING- some leg has no settled label yet as of as_of
# Pending is never counted as lost: an unsettled leg is unknown, not a miss.
# Cancelled or otherwise abnormal results are not forced into W/D/L; they are
# reported as their own status and left for the authoritative settlement logic.
#' Settle a frozen plan at an explicit observation time
#'
#' Operates on explicit inputs. Invalid contracts raise errors; no network,
#' package installation or database writes occur.
#' @param plan Frozen plan returned by parlay_build_plan(); it carries the frozen
#'   n_legs, unit_cny and payout_factor, so settlement cannot be re-priced or
#'   re-shaped by a later session change.
#' @param settlements Validated settlement tibble with actual SP and label_available_at; only labels visible at as_of are consumed.
#'   Explicit status all_options_one requires outcome ALL and SP=1, and is a
#'   neutral parlay leg, not a prediction hit. Single-leg and all-neutral tickets
#'   remain SPECIAL; refunds are not inferred.
#' @param as_of UTC POSIXct instant limiting visible settlement labels.
#' @return A list of ticket, group and issue return tibbles; unresolved outcomes remain pending.
parlay_settle_plan <- function(plan, settlements, as_of) {
  match_validate_table(settlements, "settlements")
  if (!inherits(as_of, "POSIXct") || !identical(attr(as_of, "tzone"), "UTC")) {
    stop("parlay_settle_plan: as_of must be a UTC POSIXct instant")
  }
  # The frozen constants are the authority. Passing unit/payout in again would let a
  # caller re-price a plan that was already frozen with different values.
  if (!is.list(plan) || is.null(plan$constants)) {
    stop("parlay_settle_plan: plan must be a frozen plan with a constants block")
  }
  unit_cny <- plan$constants$unit_cny
  payout_factor <- plan$constants$payout_factor
  plan_n_legs <- plan$constants$n_legs
  if (length(unit_cny) != 1L || !is.finite(unit_cny) || unit_cny <= 0) {
    stop("parlay_settle_plan: plan unit_cny must be positive")
  }
  if (length(payout_factor) != 1L || !is.finite(payout_factor) ||
      payout_factor <= 0 || payout_factor > 1) {
    stop("parlay_settle_plan: plan payout_factor must lie in (0,1]")
  }
  if (length(plan_n_legs) != 1L || !is.finite(plan_n_legs) || plan_n_legs < 1) {
    stop("parlay_settle_plan: plan n_legs must be a positive whole number")
  }
  funded <- plan$funded
  ticket_legs <- plan$ticket_legs

  # Only labels that were actually available by as_of may be used. A label with a
  # later availability time is future information relative to this settlement.
  visible <- settlements[!is.na(settlements$label_available_at) &
                           settlements$label_available_at <= as_of, , drop = FALSE]

  empty_ticket <- tibble::tibble(
    ticket_id = character(0), group_id = character(0), status = character(0),
    stake_cny = numeric(0), payout_cny = numeric(0), net_cny = numeric(0))
  empty_group <- tibble::tibble(
    group_id = character(0), stake_cny = numeric(0), payout_cny = numeric(0),
    net_cny = numeric(0), n_won = integer(0), n_lost = integer(0),
    n_pending = integer(0), n_special = integer(0))
  empty_issue <- tibble::tibble(
    issue_id = character(0), stake_cny = numeric(0), settled_stake_cny = numeric(0),
    pending_stake_cny = numeric(0), special_stake_cny = numeric(0),
    payout_cny = numeric(0), net_cny = numeric(0), roi = numeric(0))
  if (!nrow(funded)) {
    return(list(ticket_returns = empty_ticket, group_returns = empty_group,
                issue_returns = empty_issue))
  }

  rows <- list()
  for (i in seq_len(nrow(funded))) {
    ticket_id <- funded$ticket_id[i]
    legs <- ticket_legs[ticket_legs$ticket_id == ticket_id, , drop = FALSE]
    # A ticket whose leg count disagrees with the frozen plan width is a corrupted
    # plan, not a settlement question: paying it would settle a ticket the plan
    # never froze.
    if (nrow(legs) != as.integer(plan_n_legs)) {
      stop("parlay_settle_plan: ticket ", ticket_id, " has ", nrow(legs),
           " legs but the frozen plan declares ", as.integer(plan_n_legs))
    }
    # Every leg is examined. Stopping at the first unavailable label would leave a
    # ticket PENDING even when a later leg is already a known miss, which wrongly
    # keeps its stake out of the settled denominator.
    leg_status <- rep("WON", nrow(legs))
    leg_sp <- rep(NA_real_, nrow(legs))
    neutral_leg <- rep(FALSE, nrow(legs))
    for (leg_index in seq_len(nrow(legs))) {
      fixture_id <- legs$fixture_id[leg_index]
      expected <- legs$outcome[leg_index]
      # Settlements are keyed by (issue_id, fixture_id). Matching on fixture_id
      # alone would let another issue's result settle this plan.
      row <- visible[visible$issue_id == plan$issue_id &
                       visible$fixture_id == fixture_id, , drop = FALSE]
      if (!nrow(row)) {
        leg_status[leg_index] <- "PENDING"
        next
      }
      # Conflicting labels or odds for one key are a data error, not a row-order
      # choice: picking a row silently would make the payout depend on row order.
      if (nrow(row) > 1L && length(unique(row$outcome)) > 1L) {
        stop("parlay_settle_plan: conflicting settlement outcomes for issue ",
             plan$issue_id, " fixture ", fixture_id)
      }
      if (nrow(row) > 1L) {
        usable <- unique(row$settled_sp[!is.na(row$settled_sp)])
        if (length(usable) > 1L) {
          stop("parlay_settle_plan: conflicting settled SP for issue ", plan$issue_id,
               " fixture ", fixture_id)
        }
      }
      observed <- row$outcome[1]
      # The status column is authoritative: a row that is not 'settled' carries no
      # ordinary W/D/L settlement even if it still holds an outcome and odds.
      # Conflicting statuses for one key are a data error, never a row-order choice.
      statuses <- unique(tolower(as.character(row$status)))
      if (length(statuses) > 1L) {
        stop("parlay_settle_plan: conflicting settlement status for issue ", plan$issue_id,
             " fixture ", fixture_id)
      }
      settlement_status <- tolower(as.character(row$status[1]))
      if (is.na(settlement_status)) {
        # A missing authoritative status cannot authorise an ordinary settlement:
        # treating it as "settled" would pay a win on a label whose validity was
        # never asserted. Leave the leg pending so the amount is not invented.
        leg_status[leg_index] <- "PENDING"
        next
      }
      if (settlement_status == "all_options_one") {
        if (!identical(observed, "ALL") || anyNA(row$settled_sp) ||
            any(row$settled_sp != 1)) {
          stop("parlay_settle_plan: all_options_one requires ALL and SP=1")
        }
        # Explicit source publication for every option: neutral parlay leg,
        # not a prediction hit. Single-ticket refunds remain special handling.
        if (plan_n_legs == 1L) {
          leg_status[leg_index] <- "SPECIAL"
        } else {
          leg_sp[leg_index] <- 1
          neutral_leg[leg_index] <- TRUE
        }
        next
      }
      if (settlement_status != "settled") {
        leg_status[leg_index] <- "SPECIAL"
        next
      }
      if (!identical(observed, expected)) {
        # An abnormal/cancelled label is not a plain miss; flag it distinctly.
        leg_status[leg_index] <- if (observed %in% match_outcomes()) "LOST" else "SPECIAL"
        next
      }
      # Prefer any USABLE odds among the rows for this key. Taking row 1 would make
      # the outcome depend on whether the NA duplicate happened to sort first: an
      # NA-first pair would be PENDING while valid-first would pay.
      usable_sp <- unique(row$settled_sp[!is.na(row$settled_sp)])
      sp <- if (length(usable_sp)) usable_sp[1] else NA_real_
      if (is.na(sp) || !is.finite(sp) || sp <= 0) {
        # A win with no usable settled odds cannot be paid; leave it pending so the
        # amount is not silently invented.
        leg_status[leg_index] <- "PENDING"
        next
      }
      leg_sp[leg_index] <- sp
    }
    # A known miss determines the ticket even if another leg is still unknown, but a
    # SPECIAL (cancelled/void) leg outranks it: the ticket cannot be settled normally,
    # so booking it as LOST would push its stake into the settled denominator and
    # distort ROI.
    status <- if (all(neutral_leg) || any(leg_status == "SPECIAL")) "SPECIAL" else
      if (any(leg_status == "LOST")) "LOST" else
        if (any(leg_status == "PENDING")) "PENDING" else "WON"
    stake <- unit_cny
    # Only an ordinary, fully determined win pays. A special result is reported for
    # authoritative handling and is never counted as a settled loss.
    payout <- if (identical(status, "WON")) unit_cny * payout_factor * prod(leg_sp) else 0
    net <- if (status %in% c("PENDING", "SPECIAL")) NA_real_ else payout - stake
    rows[[length(rows) + 1L]] <- tibble::tibble(
      ticket_id = ticket_id, group_id = funded$group_id[i], status = status,
      stake_cny = stake, payout_cny = payout, net_cny = net)
  }
  ticket_returns <- dplyr::bind_rows(rows)

  group_returns <- ticket_returns |>
    dplyr::group_by(.data$group_id) |>
    dplyr::summarise(stake_cny = sum(.data$stake_cny),
                     payout_cny = sum(.data$payout_cny),
                     net_cny = sum(.data$net_cny, na.rm = TRUE),
                     n_won = sum(status == "WON"),
                     n_lost = sum(status == "LOST"),
                     n_pending = sum(status == "PENDING"),
                     n_special = sum(status == "SPECIAL"), .groups = "drop")

  # Three buckets, not two. A special result has no ordinary W/D/L settlement, so
  # its stake is neither a settled loss nor a pending bet; folding it into
  # settled_stake would book a cancellation as a realised loss.
  pending_stake <- sum(ticket_returns$stake_cny[ticket_returns$status == "PENDING"])
  special_stake <- sum(ticket_returns$stake_cny[ticket_returns$status == "SPECIAL"])
  settled_stake <- sum(ticket_returns$stake_cny[
    !ticket_returns$status %in% c("PENDING", "SPECIAL")])
  payout_total <- sum(ticket_returns$payout_cny)
  net_total <- payout_total - settled_stake
  issue_returns <- tibble::tibble(
    issue_id = plan$issue_id,
    stake_cny = sum(ticket_returns$stake_cny),
    settled_stake_cny = settled_stake,
    pending_stake_cny = pending_stake,
    special_stake_cny = special_stake,
    payout_cny = payout_total,
    net_cny = net_total,
    # ROI denominator is the SETTLED stake only: including pending stake would
    # understate the return on money whose outcome is genuinely unknown, and
    # including a special stake would book an unresolved result as a loss.
    roi = if (settled_stake > 0) net_total / settled_stake else NA_real_)
  list(ticket_returns = ticket_returns, group_returns = group_returns,
       issue_returns = issue_returns)
}

# --- explicit Block 8 strategy configuration ---------------------------------

# The Block 8 public path takes ONE strategy configuration carrying every explicit
# policy the five stages consume. There is no purchased group count: how many
# groups are funded is an OUTPUT of the allocation, derived from the budget and the
# reuse/overlap constraints. The obsolete fixed n_groups/equal-split path was
# removed rather than kept behind a compatibility switch, so a caller cannot
# silently fall back to a fixed group count.
#' Construct a Block 8 budget-derived strategy configuration
#'
#' Operates on explicit inputs. Invalid contracts raise errors; no network,
#' package installation or database writes occur.
#' @param settings Named business settings snapshot with the complete key set:
#'   n_legs, issue_budget_cny, unit_cny, payout_factor, sp_threshold,
#'   sp_replacement. parlay_settings() supplies the session snapshot by default.
#' @param name Length-1 nonempty character configuration name, carried into the
#'   frozen plan's policies for audit.
#' @param patterns Named list of `n_legs`-long integer vectors (each value 1, 2 or
#'   3): the legal mask per structure. Names are the structure keys.
#' @param construction_policy Explicit list with `max_candidates` and `seed`. When
#'   supplied it is the sole source of the search bound and deterministic seed.
#' @param objective Either "probability" (expected NUMBER of winning tickets,
#'   the sum of marginal masses -- not a union) or "ev" (marginal net EV per
#'   ticket, requiring a complete valid pre-cutoff SP valuation).
#' @param min_support_mass Single number in `0..1`: minimum total legal support
#'   mass a candidate must carry to be admitted. 0 is the uncalibrated default.
#' @param max_reuse Positive whole number of distinct funded groups a fixture may
#'   appear in, INCLUDING prior purchased groups.
#' @param max_overlap Whole number in 0..n_legs: how many fixtures a new group may
#'   share with a prior/selected group.
#' @param spend_limit_cny Optional single nonnegative CNY ceiling for this
#'   decision. NULL (default) means no additional cap; the issue budget remains the
#'   absolute ceiling.
#' @return A complete strategy configuration list for [parlay_build_plan()]. It
#'   carries its own settings snapshot plus patterns, construction_policy,
#'   objective, admission and optional spend-limit fields.
#' @details This constructor makes NO optimality claim and declares no purchased
#'   group count. Under a "probability" objective the returned plan optimises the
#'   expected COUNT of winning tickets, which is not a union probability and not a
#'   financial-return claim.
#' @export
parlay_strategy_config <- function(settings = parlay_settings(), name = "block8",
                                   patterns = NULL,
                                   construction_policy = list(max_candidates = 32L, seed = 1L),
                                   objective = "probability", min_support_mass = 0,
                                   max_reuse = 1L, max_overlap = NULL,
                                   spend_limit_cny = NULL) {
  parlay_validate_settings(settings)
  if (is.null(patterns)) patterns <- list(all = rep(3L, settings$n_legs))
  if (is.null(max_overlap)) max_overlap <- settings$n_legs - 1L
  config <- list(name = name, settings = settings, patterns = patterns,
                 construction_policy = construction_policy, objective = objective,
                 min_support_mass = min_support_mass, max_reuse = max_reuse,
                 max_overlap = max_overlap, spend_limit_cny = spend_limit_cny)
  parlay_validate_strategy_config(config)
  config
}

# Validate one Block 8 strategy configuration. An UNKNOWN field is refused rather
# than ignored: a misspelled bound would otherwise leave the real policy at its
# default and change what the plan buys. There is no n_groups field: funded group
# count is an output, so a configuration that declares one is a contract error.
#' Validate a complete Block 8 strategy configuration
#' @param strategy_config Named list from [parlay_strategy_config()].
#' @return The input invisibly; invalid or unknown fields raise errors even for
#'   empty decisions.
#' @noRd
parlay_validate_strategy_config <- function(strategy_config) {
  checkmate::assert_list(strategy_config, names = "unique",
                         .var.name = "strategy_config")
  allowed <- c("name", "label", "settings", "patterns", "construction_policy",
               "objective", "min_support_mass", "max_reuse", "max_overlap",
               "spend_limit_cny")
  unknown <- setdiff(names(strategy_config), allowed)
  if (length(unknown)) {
    stop("parlay_validate_strategy_config: unknown field(s) ",
         paste(unknown, collapse = ", "), "; allowed fields are ",
         paste(allowed, collapse = ", "))
  }
  required <- c("settings", "patterns", "construction_policy", "objective",
                "min_support_mass", "max_reuse", "max_overlap", "name")
  missing <- setdiff(required, names(strategy_config))
  if (length(missing)) {
    stop("parlay_validate_strategy_config: strategy_config is missing ",
         paste(missing, collapse = ", "))
  }
  parlay_validate_settings(strategy_config$settings)
  checkmate::assert_list(strategy_config$patterns, min.len = 1L, names = "unique",
                         .var.name = "strategy_config$patterns")
  n_legs <- as.integer(strategy_config$settings$n_legs)
  wrong_width <- vapply(strategy_config$patterns,
                        function(p) length(p) != n_legs, logical(1))
  if (any(wrong_width)) {
    stop("parlay_validate_strategy_config: every pattern must have ", n_legs,
         " legs; pattern(s) ", paste(which(wrong_width), collapse = ", "),
         " disagree")
  }
  policy <- strategy_config$construction_policy
  checkmate::assert_list(policy, names = "unique",
                         .var.name = "strategy_config$construction_policy")
  unknown_policy <- setdiff(names(policy), c("max_candidates", "seed"))
  if (length(unknown_policy)) {
    stop("parlay_validate_strategy_config: unknown construction_policy field(s) ",
         paste(unknown_policy, collapse = ", "))
  }
  missing_policy <- setdiff(c("max_candidates", "seed"), names(policy))
  if (length(missing_policy)) {
    stop("parlay_validate_strategy_config: construction_policy is missing ",
         paste(missing_policy, collapse = ", "))
  }
  checkmate::assert_count(policy$max_candidates, positive = TRUE,
                          .var.name = "strategy_config$construction_policy$max_candidates")
  checkmate::assert_count(policy$seed,
                          .var.name = "strategy_config$construction_policy$seed")
  checkmate::assert_string(strategy_config$objective, min.chars = 1L)
  if (!strategy_config$objective %in% c("probability", "ev")) {
    stop("parlay_validate_strategy_config: objective must be 'probability' or ",
         "'ev', got ", strategy_config$objective)
  }
  checkmate::assert_numeric(strategy_config$min_support_mass, len = 1L,
                            any.missing = FALSE, finite = TRUE, lower = 0, upper = 1,
                            .var.name = "strategy_config$min_support_mass")
  checkmate::assert_count(strategy_config$max_reuse, positive = TRUE,
                          .var.name = "strategy_config$max_reuse")
  checkmate::assert_count(strategy_config$max_overlap,
                          .var.name = "strategy_config$max_overlap")
  if (strategy_config$max_overlap > n_legs) {
    stop("parlay_validate_strategy_config: max_overlap must not exceed n_legs ",
         n_legs)
  }
  if (!is.null(strategy_config$spend_limit_cny)) {
    checkmate::assert_numeric(strategy_config$spend_limit_cny, len = 1L,
                              any.missing = FALSE, finite = TRUE, lower = 0,
                              .var.name = "strategy_config$spend_limit_cny")
  }
  if (!is.null(strategy_config$name)) {
    checkmate::assert_string(strategy_config$name, min.chars = 1L,
                             .var.name = "strategy_config$name")
  }
  invisible(strategy_config)
}

# Prior history: either the object returned by a previous parlay_build_plan()/call,
# a list(purchases=, fixture_sets=), or NULL. The two parts are validated together
# because dropping the fixture sets is what silently re-opens already-bought groups.
#' Validate paired cumulative purchases and group identities
#' @param prior_purchases NULL or list(purchases, fixture_sets). Purchases are a typed tibble with CNY stakes; sets are named character vectors.
#' @return Validated list of purchases and fixture sets. Detached, duplicate, nonpositive or unmatched records raise errors.
parlay_validate_prior_state <- function(prior_purchases) {
  if (is.null(prior_purchases)) {
    return(list(purchases = NULL, fixture_sets = NULL))
  }
  # A bare purchase tibble is REFUSED, not silently accepted. Purchases without their
  # fixture sets would let a later decision re-open a group it already deepened, so
  # the two halves must travel together. Callers pass the `history` object returned by
  # an earlier parlay_build_plan(), which is exactly list(purchases=, fixture_sets=).
  if (is.data.frame(prior_purchases)) {
    stop("parlay_validate_prior_state: prior_purchases must carry purchases AND ",
         "fixture_sets together; pass the `history` object from an earlier ",
         "parlay_build_plan() call instead of a bare purchases tibble")
  }
  if (!is.list(prior_purchases)) {
    stop("parlay_validate_prior_state: prior_purchases must be NULL or ",
         "list(purchases=, fixture_sets=)")
  }
  purchases <- prior_purchases$purchases
  fixture_sets <- prior_purchases$fixture_sets
  if (is.null(purchases)) {
    stop("parlay_validate_prior_state: prior history is missing purchases")
  }
  match_validate_table(purchases, "purchases")
  # fixture_sets is REQUIRED: the contract is that purchases and their fixture sets
  # are never detached. A caller with no prior groups states an empty list.
  if (is.null(fixture_sets)) {
    stop("parlay_validate_prior_state: prior history is missing fixture_sets; ",
         "the purchases and their fixture sets must travel together")
  }
  if (!is.list(fixture_sets)) {
    stop("parlay_validate_prior_state: prior history fixture_sets must be a list")
  }
  checkmate::assert_character(purchases$group_id, any.missing = FALSE, min.chars = 1,
                              .var.name = "prior purchases group_id")
  checkmate::assert_character(purchases$ticket_id, any.missing = FALSE, min.chars = 1,
                              .var.name = "prior purchases ticket_id")
  if (anyDuplicated(paste(purchases$issue_id, purchases$ticket_id))) {
    stop("parlay_validate_prior_state: duplicate prior physical purchase")
  }
  if (any(!is.finite(purchases$stake_cny)) || any(purchases$stake_cny <= 0)) {
    stop("parlay_validate_prior_state: prior stakes must be positive and finite")
  }
  if (length(fixture_sets) && (is.null(names(fixture_sets)) ||
      anyNA(names(fixture_sets)) || any(!nzchar(names(fixture_sets))) ||
      anyDuplicated(names(fixture_sets)))) {
    stop("parlay_validate_prior_state: fixture_sets must have unique nonempty group names")
  }
  if (!setequal(names(fixture_sets), unique(purchases$group_id))) {
    stop("parlay_validate_prior_state: fixture_sets must match exactly the purchased groups")
  }
  for (ids in fixture_sets) {
    checkmate::assert_character(ids, min.len = 1L, any.missing = FALSE,
                                min.chars = 1L, unique = TRUE,
                                .var.name = "prior fixture identifiers")
  }
  return(list(purchases = purchases, fixture_sets = fixture_sets))
}

# Bind a projection object to the context its engine needs. Every public entrypoint
# that consumes a projection goes through this one check, so "the projection's
# cutoff is the decision instant" is enforced in exactly one place.
#' Validate the decision context on a probability projection
#' @param projected List containing cutoff, fixtures, probabilities, prematch_sp and match_status.
#' @return Invisibly a list containing the validated cutoff; errors on missing or mismatched issue identity.
parlay_projection_context <- function(projected) {
  if (is.list(projected) && (!is.null(projected$probability_base) ||
      !is.null(projected$probability_base_receipt))) .ValidateProbabilityBaseProjection(projected)
  if (!is.list(projected)) {
    stop("parlay_projection_context: projected must be a projection object")
  }
  for (field in c("cutoff", "fixtures", "probabilities", "prematch_sp", "match_status")) {
    if (is.null(projected[[field]])) {
      stop("parlay_projection_context: projected is missing ", field)
    }
  }
  match_require_cutoff(projected$cutoff)
  checkmate::assert_data_frame(projected$fixtures, .var.name = "projected$fixtures")
  checkmate::assert_character(projected$match_status$status, min.len = 0L,
                              .var.name = "projected$match_status")
  # The projection's cutoff is bound to the fixture slate it carries. A hand-assembled
  # projection whose cutoff names another issue would otherwise price and buy one
  # issue's fixtures under a different decision identity.
  if ("issue_id" %in% names(projected$fixtures)) {
    stray <- setdiff(unique(as.character(projected$fixtures$issue_id)),
                     as.character(projected$cutoff$issue_id))
    if (length(stray)) {
      stop("parlay_projection_context: projected fixtures belong to issue ",
           paste(stray, collapse = ", "), " but the cutoff is bound to '",
           projected$cutoff$issue_id, "'")
    }
  }
  invisible(list(cutoff = projected$cutoff))
}

#' Build one issue's parlay plan from a bound projection
#'
#' Runs the four authoritative Block 8 decision stages over one bound projection:
#' budget state, candidate generation, coverage frontier and constrained portfolio
#' allocation. Operates on explicit inputs. Invalid contracts raise errors; no
#' network, package installation or database writes occur.
#' @param projected Projection returned by estimate_match_probabilities(). It binds
#'   the decision cutoff, the selected fixtures, the status ledger and the pre-match
#'   SP, so the plan cannot be built against a different instant than the one the
#'   probabilities were projected for.
#' @param strategy_config One explicit Block 8 strategy configuration, normally from
#'   [parlay_strategy_config()]. It carries the full settings snapshot plus patterns,
#'   a construction policy (max_candidates, seed), objective, min_support_mass,
#'   max_reuse/max_overlap and an optional spend_limit_cny. There is no purchased
#'   group count: how many groups are funded is derived by the allocation.
#' @param prior_purchases Previous history for the SAME issue: the `history` object
#'   returned by an earlier call, or list(purchases=, fixture_sets=). NULL means this
#'   is the issue's first decision.
#' @return A list with config, cutoff, constants, built, probabilities, ranked,
#'   funded, plan, history and the extra stage evidence `summary`, `search`,
#'   `frontier`, `selection`, `budget_state` and `search_diagnostics`. `history` is what the next call must receive.
#'   `plan`, `funded` and `history` keep the shapes immutable save, settlement and
#'   diagnosis consume; `funded` carries the derived `n_groups` in its diagnostics.
#' @details The funded group count is an OUTPUT of the budget and constraints, not
#'   an input. Group admission (reuse/overlap) counts DISTINCT funded groups, and
#'   one structure per selected group is enforced. This is a greedy approximation:
#'   no global-optimality claim is made, and the probability objective is the
#'   expected COUNT of winning tickets (sum of marginals), never a union.
parlay_build_plan <- function(projected, strategy_config, prior_purchases = NULL) {
  parlay_validate_strategy_config(strategy_config)
  prior <- parlay_validate_prior_state(prior_purchases)
  context <- parlay_projection_context(projected)
  .ValidatePriorBinding(prior, context$cutoff, strategy_config)
  cutoff <- context$cutoff
  settings <- strategy_config$settings
  patterns <- strategy_config$patterns
  policy <- strategy_config$construction_policy

  # --- stage 1: budget state (prior ledger in, affordable units out) ---------
  budget_state <- parlay_budget_state(settings, prior_purchases, cutoff,
                                      spend_limit_cny = strategy_config$spend_limit_cny)

  # --- stage 2: bounded candidate search over the eligible slate ------------
  search <- parlay_generate_candidates(projected, settings, policy)
  # `group_legs` is the shared group universe the later stages consume. The
  # frontier is never built from a fixture set that stage 2 did not admit.
  group_legs <- search$group_legs
  # `n_legs` comes from the artifact itself (0 for a typed-empty universe), so an
  # empty decision does not invent a width.
  n_legs <- parlay_structure_legs(group_legs)
  if (!nrow(group_legs)) n_legs <- as.integer(settings$n_legs)

  # --- stage 3: coverage frontier over the legal support space ---------------
  frontier_policy <- list(min_support_mass = strategy_config$min_support_mass,
                          max_depth = budget_state$affordable_units,
                          ranking = if (strategy_config$objective == "ev") "ev_desc" else "probability_desc")
  frontier_result <- parlay_coverage_frontier(projected, group_legs, patterns,
                                              settings, frontier_policy)

  # --- stage 4: constrained greedy portfolio allocation ---------------------
  allocation <- parlay_allocate_portfolio(
    frontier_result, group_legs, budget_state, prior_purchases, cutoff,
    list(max_reuse = strategy_config$max_reuse,
         max_overlap = strategy_config$max_overlap),
    strategy_config$objective)

  # --- stage 5: human-readable summary --------------------------------------
  funded_tickets <- dplyr::semi_join(frontier_result$ranked,
    allocation$purchases, by = c("candidate_id", "ticket_id"))

  # --- freeze the decision ---------------------------------------------------
  built <- list(groups = list(group_legs = group_legs,
                              diagnostics = search$diagnostics),
                structure = list(supports = frontier_result$supports),
                tickets = list(tickets = frontier_result$tickets,
                               ticket_legs = frontier_result$ticket_legs,
                               candidate_tickets = frontier_result$candidate_tickets),
                valued = frontier_result$tickets)
  plan <- .FreezeParlayPlan(cutoff$issue_id, cutoff$cutoff_utc, group_legs,
                            built$structure, built$tickets, built$valued,
                            funded_tickets, allocation$purchases, settings,
                            list(allocation = strategy_config$name,
                                 objective = strategy_config$objective,
                                 max_reuse = strategy_config$max_reuse,
                                 max_overlap = strategy_config$max_overlap,
                                 model_config = projected$model_config,
                                 market_policy = projected$market_policy))
  # `funded` is the ranked-shaped selection table plus the allocation ledger, so
  # the save/settle/diagnose consumers keep reading the same shapes they did on
  # the frozen path: `funded$purchases` and `funded$fixture_sets` are the ledger,
  # and `funded$funded` is the ranked-derived selection.
  funded <- list(purchases = allocation$purchases,
                 funded = funded_tickets,
                 fixture_sets = allocation$history$fixture_sets,
                 diagnostics = allocation$diagnostics,
                 trace = allocation$trace,
                 selected = allocation$selected,
                 history = allocation$history)
  history <- allocation$history
  result <- list(config = strategy_config, cutoff = cutoff, constants = settings,
       built = built, probabilities = projected$probabilities,
       ranked = frontier_result$ranked, funded = funded, plan = plan,
       history = history, search = search,
       budget_state = budget_state, search_diagnostics = search$diagnostics,
       frontier = frontier_result, selection = allocation)
  result$summary <- parlay_plan_summary(result)
  result
}

# Bind the running ledger to THIS decision. A prior history that belongs to another
# issue, that was bought at or after the current decision instant, or that was built
# under a different leg width cannot be carried forward: each of those would let a
# decision reuse money or groups it never had. The ledger records its own issue and
# purchase instant, so the check is done against evidence rather than a caller claim.
#' Bind prior purchase history to the next decision
#' @param prior Validated purchases/fixture_sets list.
#' @param cutoff Explicit issue_id and UTC cutoff_utc decision context.
#' @param config Strategy containing the explicit plan-level settings snapshot.
#' @return TRUE invisibly; future/missing purchase times, another issue or differing leg counts error.
.ValidatePriorBinding <- function(prior, cutoff, config) {
  purchases <- prior$purchases
  if (is.null(purchases) || !nrow(purchases)) {
    return(invisible(TRUE))
  }
  issues <- unique(as.character(purchases$issue_id))
  if (length(issues) != 1L || !identical(issues, as.character(cutoff$issue_id))) {
    stop("parlay_build_plan: prior purchases belong to issue ",
         paste(issues, collapse = ", "), " but this decision is for '",
         cutoff$issue_id, "'")
  }
  if ("epoch_at" %in% names(purchases)) {
    times <- purchases$epoch_at
    if (anyNA(times) || any(!is.finite(as.numeric(times)))) {
      stop("parlay_build_plan: prior purchase instants must be finite and nonmissing")
    }
    if (length(times) && any(times >= cutoff$cutoff_utc)) {
      stop("parlay_build_plan: prior purchases must have been made strictly before ",
           "the current decision instant")
    }
  }
  widths <- vapply(prior$fixture_sets %||% list(),
                   function(set) length(as.character(set)), integer(1))
  if (length(widths) && any(widths != config$settings$n_legs)) {
    stop("parlay_build_plan: prior fixture sets mix leg widths (",
         paste(sort(unique(widths)), collapse = ", "), "); this plan uses ",
         config$settings$n_legs)
  }
  invisible(TRUE)
}
# --- multi-issue replay and depth diagnostics -------------------------------

# .DiagnoseParlayPlan(candidates, probabilities, group_legs, ranked, purchased,
#                   ticket_legs, candidate_tickets, settlements, as_of, unit_cny, payout_factor, issue_id)
#   -> candidate_id, group_id, k, support_mass, selected_mass, true_rank, hit,
#      stake_cny, gross_cny, net_cny, status
#
# Two different notions of rank are reported side by side and must never be
# conflated:
#   * the ranking WITHIN the structural support, which is what the decision saw, and
#   * the rank in the FULL space (true_rank), which is only knowable after the fact.
# The full-space rank is diagnostic; it must never be used to make the decision.
#
# It consumes the pipeline's own tables rather than a bespoke structure, so the
# diagnostic cannot drift from what was actually bought. This is the AUTHORITATIVE
# engine; parlay_diagnose_plan() is the thin public facade that pulls those tables
# out of a build result and reads unit_cny/payout_factor from its FROZEN constants
# rather than from a detached argument.
#' Diagnose explicit candidate support and purchased tickets
#' @param candidates Candidate support tibble.
#' @param probabilities Match outcome probability tibble.
#' @param group_legs Group-to-fixture ordering tibble.
#' @param ranked Candidate-specific ranking tibble.
#' @param purchased Physical purchase tibble with CNY stakes.
#' @param ticket_legs Ticket-to-fixture-outcome tibble.
#' @param candidate_tickets Unique candidate/ticket associations.
#' @param settlements Actual outcomes, settled SP and label availability tibble.
#' @param as_of UTC POSIXct settlement observation instant.
#' @param unit_cny Frozen positive CNY cost per ticket.
#' @param payout_factor Frozen ticket-level payout multiplier.
#' @param issue_id Single character issue identifier.
#' @return Candidate diagnostic tibble; unavailable outcomes remain pending, empty input is typed.
.DiagnoseParlayPlan <- function(candidates, probabilities, group_legs, ranked, purchased,
                              ticket_legs, candidate_tickets, settlements, as_of,
                              unit_cny, payout_factor, issue_id) {
  match_validate_table(settlements, "settlements")
  match_validate_table(group_legs, "group_legs")
  if (!inherits(as_of, "POSIXct") || !identical(attr(as_of, "tzone"), "UTC")) {
    stop("parlay_diagnose_plan: as_of must be a UTC POSIXct instant")
  }
  if (length(unit_cny) != 1L || !is.finite(unit_cny) || unit_cny <= 0) {
    stop("parlay_diagnose_plan: unit_cny must be positive")
  }
  empty <- tibble::tibble(
    candidate_id = character(0), group_id = character(0), k = integer(0),
    support_mass = numeric(0), selected_mass = numeric(0), support_rank = integer(0),
    true_rank = integer(0),
    hit = logical(0), stake_cny = numeric(0), gross_cny = numeric(0),
    net_cny = numeric(0), status = character(0))
  if (!nrow(candidates)) return(empty)

  visible <- parlay_visible_settlements(settlements, issue_id, as_of)
  wide <- parlay_probability_wide(probabilities)
  candidate_support <- parlay_candidate_support_grid(candidates, group_legs)
  # The realised string of each ticket, in its group's leg order.
  ticket_strings <- parlay_ticket_strings(ticket_legs, group_legs)
  rows <- list()
  # One row per CANDIDATE. The supports table holds one row per outcome, so iterate
  # the distinct candidate ids rather than every support row.
  candidate_ids <- unique(candidates$candidate_id)
  for (i in seq_along(candidate_ids)) {
    candidate_id <- candidate_ids[i]
    group_id <- sub("[|].*$", "", candidate_id)
    legs <- group_legs[group_legs$group_id == group_id, , drop = FALSE]
    legs <- legs[order(legs$leg_order), , drop = FALSE]
    legs <- legs[!duplicated(legs$fixture_id), , drop = FALSE]

    # Realised outcome per fixture, where it was available by as_of.
    realised <- character(0)
    pending <- FALSE
    for (fixture_id in legs$fixture_id) {
      row <- visible[visible$fixture_id == fixture_id, , drop = FALSE]
      if (!nrow(row)) { pending <- TRUE; next }
      # A row whose status is missing or not "settled" is not an authoritative
      # result. Treating it as available would let the diagnostic declare the ticket
      # complete and book a loss (or a win) the settlement path would never pay.
      status_ok <- if ("status" %in% names(row)) {
        !is.na(row$status) & tolower(as.character(row$status)) == "settled"
      } else {
        rep(TRUE, nrow(row))
      }
      row <- row[status_ok, , drop = FALSE]
      if (!nrow(row)) { pending <- TRUE; next }
      realised[fixture_id] <- row$outcome[order(row$label_available_at)][nrow(row)]
    }
    complete <- !pending && length(realised) == nrow(legs)
    # The realised string in the candidate's own leg order.
    occupied <- if (complete) paste(realised[legs$fixture_id], collapse = "") else NA_character_

    # The candidate's FULL legal space, ranked by raw probability.
    if (nrow(legs) * log(3) > log(.Machine$integer.max)) {
      stop("parlay_diagnose_plan: full outcome space exceeds the representable integer range")
    }
    support <- match_outcomes()
    full_combos <- expand.grid(rep(list(support), nrow(legs)), KEEP.OUT.ATTRS = FALSE,
                               stringsAsFactors = FALSE)
    combo_strings <- apply(full_combos, 1L, paste, collapse = "")
    combo_prob <- apply(full_combos, 1L, function(combo) {
      product <- 1
      for (j in seq_along(combo)) {
        cell <- wide[wide$fixture_id == legs$fixture_id[j], , drop = FALSE]
        product <- product * as.numeric(cell[1, combo[j]])
      }
      product
    })
    # The candidate's own hard support: only combinations inside it were ever
    # investable, so a realised result outside it is MASK_EXCLUDED rather than a
    # plain miss.
    support_rows <- candidate_support[[candidate_id]]
    in_support <- if (complete) occupied %in% support_rows else NA
    # Two ranks are reported side by side and must never be conflated:
    #   support_rank - the position WITHIN the structure's legal support, which is
    #                  the only ordering the decision could have known, and
    #   true_rank    - the position in the candidate's FULL combination space, which
    #                  is diagnostic and knowable only after the fact.
    # Ranking the realised result in the full space and calling it the support rank
    # would report e.g. 1,111 for a result that was 96th of 96 within its support.
    # Rank by sorting the PAIRS together. Sorting the strings separately from the
    # probabilities would pair a probability with the wrong combination and produce a
    # rank that is simply wrong -- bounded, plausible, and incorrect.
    # Ties break by TICKET ID, exactly as parlay_rank_tickets orders a candidate's
    # tickets. Breaking ties by outcome string instead would make a rank-1 purchase
    # report a different rank whenever probabilities are uniform.
    # parlay_ticket_strings returns ONE string per ticket; indexing it with positions
    # from the leg table (n_legs rows per ticket) would read the wrong elements.
    # Build the (candidate, combination) -> ticket map from the ticket table itself,
    # once, so every combination resolves to its own ticket id.
    # Map each combination string to the ticket that encodes it, WITHIN this
    # candidate. parlay_ticket_strings returns a vector NAMED by ticket id, so the names
    # carry the alignment; indexing it positionally against the n_legs-row-per-ticket
    # leg table reads the wrong elements.
    # SUPPORT rank is the position a BUYER could have seen, so it must follow the
    # SAME ranking the purchase used -- ranked$rank is authoritative (it honours the
    # requested "probability_desc" or "ev_desc"). Reconstructing probability order
    # here would disagree with an EV-ranked purchase.
    # SUPPORT rank is the position a BUYER could have seen, so it must follow the SAME
    # ranking the purchase used -- ranked$rank is authoritative (it honours the
    # requested "probability_desc" or "ev_desc"). Reconstructing probability order here
    # would disagree with an EV-ranked purchase.
    # Build a (rank, string) table and order it, so the string and its rank can never
    # drift apart. A named lookup risks positional mismatch; sorting the pairs does not.
    # The population must be the candidate's WHOLE ticket space, not the subset the
    # caller happened to pass in "ranked" (often just the purchased row). Ranking
    # against that subset would leave the realised result unmatched and the rank NA.
    own_ids <- unique(candidate_tickets$ticket_id[
      candidate_tickets$candidate_id == candidate_id])
    # Use the AUTHORITATIVE rank column, not probability. ranked$rank already honours
    # the requested policy ("probability_desc" or "ev_desc"); re-deriving the order
    # from probability here made the diagnostic disagree with an EV-ranked purchase,
    # reporting the winner's support_rank as if the buy had been probability-ranked.
    # Fall back to probability only when the rank column is absent, and to a stable
    # ticket_id order when neither is comparable.
    # Match on the COMPOSITE key, never ticket_id alone. ranked is keyed by
    # (candidate_id, ticket_id) and one physical ticket is legitimately shared by
    # several structures over the same fixture set. Matching a bare ticket_id let a
    # shared ticket pick up whichever candidate's row came first, so a structure's
    # support_rank depended on row order -- and could report another structure's rank.
    own_key <- paste(candidate_id, own_ids, sep = "\r")
    ranked_key <- paste(as.character(ranked$candidate_id),
                        as.character(ranked$ticket_id), sep = "\r")
    own_pos <- match(own_key, ranked_key)
    own_scores <- if ("rank" %in% names(ranked)) {
      as.numeric(ranked$rank[own_pos])
    } else {
      as.numeric(ranked$probability[own_pos])
    }
    own_ranked <- data.frame(ticket_id = own_ids, score = own_scores,
                             stringsAsFactors = FALSE)
    string_lookup <- parlay_ticket_strings(ticket_legs, group_legs)
    pair_strings <- unname(string_lookup[as.character(own_ranked$ticket_id)])
    keep <- !is.na(pair_strings)
    pair_table <- data.frame(score = own_ranked$score[keep],
                             ticket_id = own_ranked$ticket_id[keep],
                             string = pair_strings[keep],
                             stringsAsFactors = FALSE)
    # rank is 1 = best, so ascending; probability is larger = better, so descending.
    # Ties break on ticket id in both cases, matching parlay_rank_tickets.
    use_rank <- "rank" %in% names(ranked)
    pair_table <- if (use_rank) {
      pair_table[order(pair_table$score, pair_table$ticket_id), , drop = FALSE]
    } else {
      pair_table[order(-pair_table$score, pair_table$ticket_id), , drop = FALSE]
    }
    ordered_strings <- pair_table$string
    support_rank <- if (complete && isTRUE(in_support)) {
      position <- match(occupied, ordered_strings)
      if (use_rank) as.integer(pair_table$score[position]) else position
    } else {
      NA_integer_
    }
    # FULL-SPACE rank is a property of the combination space ALONE: it must not
    # consult the mask or the ticket table, or the same realised result would rank
    # differently depending on which structure happened to be built. Ties break on
    # the outcome string, independent of what was enumerated.
    true_rank <- if (complete && isTRUE(in_support)) {
      match(occupied, combo_strings[order(-combo_prob, combo_strings)])
    } else {
      NA_integer_
    }
    # status describes the REALISED RESULT relative to this candidate's support:
    #   PENDING       - not every leg has a label available yet
    #   MASK_EXCLUDED - the result happened, but the hard mask had excluded it
    #   IN_SUPPORT    - the result was inside the legal space the structure kept

    # What the decision actually bought from this candidate. Purchases are keyed on
    # the fixture set, so the candidate link is resolved through candidate_tickets.
    # Attribute purchases by the candidate that MADE them. Support membership alone
    # would credit a shared ticket to every structure over the fixture set, so two
    # candidates would each claim the same stake and payout.
    picked <- if ("candidate_id" %in% names(purchased)) {
      purchased[purchased$candidate_id == candidate_id, , drop = FALSE]
    } else {
      mine <- candidate_tickets$ticket_id[candidate_tickets$candidate_id == candidate_id]
      purchased[purchased$ticket_id %in% mine, , drop = FALSE]
    }
    ordered <- ranked[ranked$candidate_id == candidate_id, , drop = FALSE]
    payout_result <- parlay_payout_for_candidate(picked, ticket_strings, occupied, legs,
                                             visible, issue_id, unit_cny, payout_factor)
    payout <- payout_result$payout
    sp_missing <- payout_result$sp_missing
    # A matching ticket with unavailable SP cannot be valued yet, so the diagnostic
    # stays PENDING exactly as parlay_settle_plan does -- it is not a loss.
    status <- if (!complete || isTRUE(sp_missing)) "PENDING" else
      if (!isTRUE(in_support)) "MASK_EXCLUDED" else "IN_SUPPORT"
    # Support mass is the summed probability of the candidate's own legal space,
    # which is what the structure kept -- not a renormalised quantity.
    support_idx <- combo_strings %in% support_rows
    rows[[length(rows) + 1L]] <- tibble::tibble(
      candidate_id = candidate_id, group_id = group_id,
      # k is the DEPTH ACTUALLY PURCHASED, which is the coverage being diagnosed;
      # the candidate's full supported space is reported separately as support_size.
      k = as.integer(nrow(picked)),
      support_mass = sum(combo_prob[support_idx]),
      selected_mass = if (nrow(picked)) sum(ordered$probability[ordered$ticket_id %in% picked$ticket_id]) else 0,
      support_rank = support_rank,
      true_rank = true_rank,
      # hit is the narrow claim: a ticket this candidate BOUGHT actually won.
      hit = payout > 0,
      stake_cny = nrow(picked) * unit_cny,
      gross_cny = payout,
      net_cny = if (identical(status, "PENDING")) NA_real_ else
        payout - nrow(picked) * unit_cny,
      status = status)
  }
  dplyr::bind_rows(rows)
}

#' Diagnose realised support depth and ticket returns for a built plan
#'
#' Operates on explicit inputs. Invalid contracts raise errors; no network,
#' package installation or database writes occur.
#' @param result Build result returned by parlay_build_plan(). It already carries
#'   the bound cutoff and the tables the diagnostic consumes, so nothing is
#'   reassembled by the caller.
#' @param settlements Validated settlement tibble with actual SP and label_available_at; only labels visible at as_of are consumed.
#'   Explicit status all_options_one requires outcome ALL and SP=1, and is a
#'   neutral parlay leg, not a prediction hit. Single-leg and all-neutral tickets
#'   remain SPECIAL; refunds are not inferred.
#' @param as_of UTC POSIXct instant limiting visible settlement labels.
#' @return A tibble with one row per candidate, exactly as the private depth engine
#'   produces. `unit_cny` and `payout_factor` come from the result's FROZEN constants,
#'   never from a detached argument or a later session change.
parlay_diagnose_plan <- function(result, settlements, as_of) {
  if (!is.list(result) || is.null(result$built) || is.null(result$ranked) ||
      is.null(result$funded) || is.null(result$cutoff)) {
    stop("parlay_diagnose_plan: result must be a build result from parlay_build_plan()")
  }
  constants <- result$constants
  if (is.null(constants)) {
    stop("parlay_diagnose_plan: result must carry its frozen constants block")
  }
  .DiagnoseParlayPlan(
    result$built$structure$supports, result$probabilities,
    result$built$groups$group_legs, result$ranked,
    result$funded$purchases, result$built$tickets$ticket_legs,
    result$built$tickets$candidate_tickets, settlements, as_of,
    constants$unit_cny, constants$payout_factor, result$cutoff$issue_id)
}

# parlay_ticket_strings(ticket_legs, group_legs) -> named character vector
#
# The outcome string of every ticket, in its group's leg order, so a realised result
# can be compared to a specific ticket without relying on row order.
parlay_ticket_strings <- function(ticket_legs, group_legs) {
  # Subsetting a non-data.frame with $ silently yields NULL, which would make this
  # return a zero-length result rather than report a bad call.
  checkmate::assert_data_frame(ticket_legs, .var.name = "ticket_legs")
  checkmate::assert_data_frame(group_legs, .var.name = "group_legs")
  # A ticket's legs are stored in enumeration order; a realised result must be
  # compared in a defined order, so reorder each ticket by its group's leg_order.
  reference <- group_legs[!duplicated(group_legs$group_id), , drop = FALSE]
  legs_per_ticket <- split(ticket_legs, ticket_legs$ticket_id)
  out <- vapply(names(legs_per_ticket), function(ticket_id) {
    block <- legs_per_ticket[[ticket_id]]
    candidates <- unique(group_legs$group_id[group_legs$fixture_id %in% block$fixture_id])
    # A repeated explicit group lists a fixture more than once, so compare UNIQUE
    # fixture sets on both sides. Comparing the raw lists (14 entries vs 7) would
    # never match, silently skipping the ordering and making the verdict depend on
    # ticket-leg row order.
    owner <- candidates[vapply(candidates, function(g) {
      identical(unique(sort(group_legs$fixture_id[group_legs$group_id == g])),
                unique(sort(block$fixture_id)))
    }, logical(1))]
    if (length(owner)) {
      # Collapse the reference to ONE leg per fixture first. A repeated explicit
      # group lists a fixture more than once, so an uncollapsed reference would take
      # the block to repeated legs and produce an over-long string that can
      # never equal an n_legs-character realised result.
      order_ref <- group_legs[group_legs$group_id == owner[1], , drop = FALSE]
      order_ref <- order_ref[order(order_ref$leg_order), , drop = FALSE]
      order_ref <- order_ref[!duplicated(order_ref$fixture_id), , drop = FALSE]
      keep <- match(order_ref$fixture_id, block$fixture_id)
      if (anyNA(keep)) stop("parlay_ticket_strings: fixture ordering contains unmatched identifiers")
      block <- block[keep, , drop = FALSE]
    }
    # The realised string is compared with a W/D/L string, so codes must be rendered
    # as outcomes rather than as their numeric encoding.
    paste(block$outcome, collapse = "")
  }, character(1))
  out
}

# .ReplayIssue(projected_decisions, strategy_config, settlements, as_of)
#   -> list(plans, purchases, settled, depth, metrics)
#
# Calls the SAME production decision function once per bound projection, in cutoff
# order, passing the cumulative purchase ledger forward so reuse and overlap caps
# are enforced across the whole sequence rather than per decision. Settlement
# happens only at the end: no decision in this loop can see an outcome.
#
# It is ONE issue by construction: every projection must carry the same issue_id.
# A caller that genuinely needs several issues calls this function once per issue
# and combines the ledgers itself, rather than hiding parallelism behind an
# argument that changes the function's meaning.
#
# This is the AUTHORITATIVE engine; parlay_replay_issue() is the thin public facade
# that validates the sequence and then delegates here.
#' Replay one issue through the authoritative public plan builder
#' @param projected_decisions List of projections with their own bound cutoff.
#' @param strategy_config Complete explicit strategy snapshot.
#' @param settlements Outcome/SP/availability tibble, consumed only after planning.
#' @param as_of UTC POSIXct settlement observation time.
#' @return Plans, cumulative purchases, returns, depth and metrics; no external side effects.
.ReplayIssue <- function(projected_decisions, strategy_config, settlements, as_of) {
  order_index <- order(vapply(projected_decisions,
                              function(p) as.numeric(p$cutoff$cutoff_utc), numeric(1)))
  plans <- list()
  purchases <- list()
  results <- list()
  # The running issue-level purchase ledger. Each decision receives everything
  # bought before it, so reuse and overlap caps hold across decisions and no
  # physical ticket is bought twice. Freezing the ledger BEFORE settlement is what
  # keeps this causal: the loop below finishes before any label is read.
  ledger <- match_typed_empty("purchases")
  ledger_sets <- list()
  for (step in order_index) {
    projected <- projected_decisions[[step]]
    result <- parlay_build_plan(projected, strategy_config,
                                prior_purchases = list(purchases = ledger,
                                                       fixture_sets = ledger_sets))
    plans[[length(plans) + 1L]] <- result$plan
    results[[length(results) + 1L]] <- result
    bought <- result$funded$purchases
    if (nrow(bought)) {
      ledger <- dplyr::bind_rows(ledger, bought)
      ledger_sets <- result$funded$fixture_sets
      purchases[[length(purchases) + 1L]] <- bought
    }
  }
  all_purchases <- if (length(purchases)) dplyr::bind_rows(purchases) else match_typed_empty("purchases")
  # Two decisions of the SAME issue must never collide on a physical ticket. One
  # replay covers one issue, so the ticket id alone is the collision key.
  if (nrow(all_purchases) && anyDuplicated(all_purchases$ticket_id)) {
    stop("parlay_replay_issue: a physical ticket was bought more than once on one issue")
  }
  # Settlement reads the frozen constants from each plan, so a later session
  # change cannot re-price a plan that was already frozen.
  settled <- lapply(plans, function(p) parlay_settle_plan(p, settlements, as_of))
  # Depth diagnostics run only AFTER every decision is frozen: they are the one
  # place a realised result is allowed to meet the decision that was made.
  depth <- dplyr::bind_rows(lapply(results, function(result) {
    parlay_diagnose_plan(result, settlements, as_of)
  }))
  ticket_returns <- if (length(settled)) {
    dplyr::bind_rows(lapply(settled, function(x) x$ticket_returns))
  } else {
    tibble::tibble(ticket_id = character(0), group_id = character(0),
                   status = character(0), stake_cny = numeric(0),
                   payout_cny = numeric(0), net_cny = numeric(0))
  }
  stake <- sum(ticket_returns$stake_cny)
  # Special results stay in their own bucket, mirroring parlay_settle_plan.
  settled_stake <- sum(ticket_returns$stake_cny[
    !ticket_returns$status %in% c("PENDING", "SPECIAL")])
  pending_stake <- sum(ticket_returns$stake_cny[ticket_returns$status == "PENDING"])
  special_stake <- sum(ticket_returns$stake_cny[ticket_returns$status == "SPECIAL"])
  payout <- sum(ticket_returns$payout_cny)
  metrics <- list(
    n_epochs = length(plans),
    n_tickets = nrow(all_purchases),
    total_stake_cny = stake,
    settled_stake_cny = settled_stake,
    pending_stake_cny = pending_stake,
    special_stake_cny = special_stake,
    payout_cny = payout,
    net_cny = payout - settled_stake,
    roi = if (settled_stake > 0) (payout - settled_stake) / settled_stake else NA_real_)
  # The three stake buckets PARTITION total stake, so subtracting them yields zero.
  # Cash is what the replay's ISSUE left unspent: one replay is one issue, entitled
  # to its own ISSUE budget. An issue that spent nothing leaves its whole allowance
  # as cash. The allowance is the ISSUE budget (CNY1,024), not the strategy config's
  # own demo limit -- a config that spends less than the issue budget simply leaves
  # the rest unspent.
  allowance <- strategy_config$settings$issue_budget_cny
  metrics$cash_cny <- max(0, allowance - stake)
  metrics$gross_cny <- payout
  list(plans = plans, purchases = all_purchases, settled = ticket_returns,
       depth = depth, metrics = metrics)
}

#' Replay one issue's decisions in time order using the accumulated purchase ledger
#'
#' Operates on explicit inputs. Invalid contracts raise errors; no network,
#' package installation or database writes occur.
#' @param projected_decisions List of projection objects from
#'   estimate_match_probabilities(), each already bound to its own decision cutoff.
#'   Every element must belong to the SAME issue: this function replays one issue,
#'   and a mixed-issue sequence is refused rather than silently split.
#' @param strategy_config One explicit strategy configuration applied to every
#'   decision in the sequence.
#' @param settlements Validated settlement tibble with actual SP and label_available_at; only labels visible at as_of are consumed.
#'   Explicit status all_options_one requires outcome ALL and SP=1, and is a
#'   neutral parlay leg, not a prediction hit. Single-leg and all-neutral tickets
#'   remain SPECIAL; refunds are not inferred.
#' @param as_of UTC POSIXct instant limiting visible settlement labels.
#' @return A list of plans, purchases, settlement, depth and aggregate metrics for
#'   the replayed issue.
parlay_replay_issue <- function(projected_decisions, strategy_config, settlements, as_of) {
  if (!is.list(projected_decisions) || !length(projected_decisions)) {
    stop("parlay_replay_issue: projected_decisions must be a non-empty list of projections")
  }
  parlay_validate_strategy_config(strategy_config)
  cutoff_of <- function(p) {
    parlay_projection_context(p)
    p$cutoff
  }
  cutoffs <- lapply(projected_decisions, cutoff_of)
  issues <- unique(vapply(cutoffs, function(c) as.character(c$issue_id), character(1)))
  if (length(issues) != 1L) {
    stop("parlay_replay_issue: one replay covers one issue; got ",
         length(issues), " (", paste(issues, collapse = ", "),
         "). Replay each issue separately and combine the ledgers explicitly.")
  }
  .ReplayIssue(projected_decisions, strategy_config, settlements, as_of)
}
