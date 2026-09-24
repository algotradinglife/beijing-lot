#' N7 管道的组构造、结构支撑与票枚举
#'
#' 三个可分离的步骤，各有自己的契约：
#'   n7_construct_candidates  选择**哪些比赛**组成一个 7 腿组
#'   n7_apply_structure       选择每条腿**保留几个选项**
#'   n7_enumerate_tickets     把受支撑的空间展开成物理票
#'
#' @details 保持三步分离很重要：'选哪些比赛'与'每场投多少'是两个不同的决策、
#'   对应不同的预算；契约要求结构是长度 7 的整数向量，而不是预算的代号。
#'   本模块只定义函数，导入时不触发任何 I/O。

#' W/D/L 三元组的归一化熵
#'
#' @param triple 数值向量，长度必须为 3。
#'   · 非数值        -> stop()（不得经 as.numeric 静默变成 NaN）
#'   · 长度 != 3     -> stop()
#'   · 含 NA / 非有限 -> stop()
#'   · 含负值        -> stop()
#'   · 总和 <= 0     -> stop()
#' @return 长度 1 的数值，取值 `[0, 1]`。
#' @details 1 表示三路均分，0 表示某个结果确定。这是契约指定的难度基线。
#'   大于 1 的输入（如 c(1,1,1)）会被按比例归一化。
n7_normalised_entropy <- function(triple) {
  # Catch non-numeric BEFORE as.numeric(): coercion would only warn and hand back
  # NaN, and a NaN entropy would silently rank a fixture as "hardest".
  if (!is.numeric(triple)) {
    stop("n7_normalised_entropy: triple must be numeric")
  }
  values <- as.numeric(triple)
  if (length(values) != 3L || anyNA(values) || any(!is.finite(values))) {
    stop("n7_normalised_entropy: need three finite values")
  }
  if (any(values < 0)) stop("n7_normalised_entropy: probabilities must be non-negative")
  total <- sum(values)
  if (total <= 0) stop("n7_normalised_entropy: probabilities must have positive mass")
  p <- values / total
  positive <- p > 0
  entropy <- -sum(p[positive] * log(p[positive]))
  entropy / log(3)
}

#' 概率的宽表视图：每场一行，列为 W/D/L
#'
#' @param probabilities tibble，probabilities 表（经 n7_validate_table 校验）。
#'   · 0 行 -> 返回带完整列集合的空表
#'   · 缺任一 W/D/L 列 -> stop()
#'   · 出现缺口（某场缺某结果）-> stop()
#'   · 任一行和不为 1 -> stop()
#' @return tibble：fixture_id, W, D, L, entropy。
n7_probability_wide <- function(probabilities) {
  n7_validate_table(probabilities, "probabilities")
  if (!nrow(probabilities)) {
    return(tibble::tibble(fixture_id = character(0), W = numeric(0),
                          D = numeric(0), L = numeric(0), entropy = numeric(0)))
  }
  wide <- tidyr::pivot_wider(probabilities, names_from = "outcome",
                             values_from = "probability")
  missing <- setdiff(n7_outcomes(), names(wide))
  if (length(missing)) stop("n7_probability_wide: missing outcomes ", paste(missing, collapse = ", "))
  wide <- wide[, c("fixture_id", n7_outcomes())]
  matrix_values <- as.matrix(wide[, n7_outcomes()])
  if (anyNA(matrix_values)) stop("n7_probability_wide: probabilities have gaps")
  n7_check_probability_sum(matrix_values)
  wide$entropy <- apply(matrix_values, 1, n7_normalised_entropy)
  wide
}

#' 一个组的稳定标识：其排序后的比赛集合
#'
#' @param fixture_ids 字符向量。允许重复（重复会被去重）。
#'   · 零长度   -> stop()
#'   · 非字符   -> stop()
#'   · 含 NA    -> stop()（NA 会变成字符串 "NA"，与真实名为 "NA" 的比赛无法区分）
#'   · 含空串   -> stop()
#' @return 长度 1 的字符，为排序去重后以 "+" 连接的集合。
#' @details 同一组七场比赛上的两种结构共享同一个 group_id，这正是让一张物理票
#'   可以被多个 candidate 引用而不被重复购买的依据。
n7_group_identity <- function(fixture_ids) {
  if (!length(fixture_ids)) stop("n7_group_identity: fixture_ids must not be empty")
  if (!is.character(fixture_ids)) {
    stop("n7_group_identity: fixture_ids must be character")
  }
  # An NA fixture id would stringify to "NA" and become indistinguishable from a
  # real fixture literally named "NA", corrupting the group identity.
  if (anyNA(fixture_ids)) stop("n7_group_identity: fixture_ids must not be NA")
  if (any(!nzchar(fixture_ids))) {
    stop("n7_group_identity: fixture_ids must not be empty strings")
  }
  paste(sort(unique(fixture_ids)), collapse = "+")
}

#' 构造候选组
#'
#' @param fixtures      tibble，fixtures 表，强制 (issue_id, fixture_id) 唯一键。
#'   · 含非 cutoff 期号的比赛 -> stop()
#'   · 开赛 <= cutoff 的比赛   -> stop()（已开赛的不可购买）
#'   · 开赛落在 D+1 决策窗口之外的比赛 -> stop()
#' @param probabilities tibble，probabilities 表；每场必须 W/D/L 齐全且行和为 1。
#' @param cutoff        temporal_learning 对象。
#' @param n_legs        长度 1 的正整数（本管道固定为 7）。
#' @param construction  显式的 fixture-id 组 list，或 "entropy_balanced"。
#' @param max_candidates 长度 1 的正整数。
#' @param seed          整数标量，控制 entropy_balanced 的确定性抽样。
#' @return list(groups, group_legs, diagnostics)，均为 tibble。
#' @details 不执行完整的 7-of-N 枚举：那是组合爆炸，且契约禁止声称全局最优。
#'   决策绑定到**一期**：拿别的期号的比赛对着本 cutoff 定价，会让回放买到
#'   不属于它自己赛程的比赛。
n7_construct_candidates <- function(fixtures, probabilities, cutoff, n_legs,
                                    construction, max_candidates, seed = 1L) {
  n7_require_cutoff(cutoff)
  n7_validate_table(fixtures, "fixtures", keys = c("issue_id", "fixture_id"))
  # The decision is bound to ONE issue. Pricing another issue's fixtures against this
  # cutoff would let a replay purchase matches outside its own slate.
  if ("issue_id" %in% names(fixtures)) {
    stray <- setdiff(unique(as.character(fixtures$issue_id)), as.character(cutoff$issue_id))
    if (length(stray)) {
      stop("n7_construct_candidates: fixtures belong to issue(s) ",
           paste(stray, collapse = ", "), ", not ", cutoff$issue_id)
    }
  }
  # The allocation path must be as bound to the cutoff as projection is: a fixture
  # that had already kicked off cannot be purchased, and a fixture outside the D+1
  # natural-day decision window is not part of this decision either.
  if ("kickoff_at" %in% names(fixtures)) {
    cutoff_bound <- n7_cutoff_utc(cutoff)
    if (any(fixtures$kickoff_at <= cutoff_bound)) {
      stop("n7_construct_candidates: fixtures already kicked off at the cutoff ",
           "are not eligible")
    }
    # n7_decision_window takes the ISO-8601 UTC string form of the epoch.
    window <- n7_decision_window(n7_utc_iso(as.numeric(cutoff_bound),
                                            "n7_construct_candidates: cutoff"))
    window_start <- n7_parse_utc(window$start_utc, "window start")
    window_end <- n7_parse_utc(window$end_utc, "window end")
    outside <- fixtures$kickoff_at < window_start | fixtures$kickoff_at >= window_end
    if (any(outside)) {
      stop("n7_construct_candidates: fixture(s) outside the decision window ",
           window$start_utc, " to ", window$end_utc, " are not eligible")
    }
  }
  if (length(n_legs) != 1L || n_legs < 1L) stop("n7_construct_candidates: n_legs must be positive")
  if (length(max_candidates) != 1L || max_candidates < 1L) {
    stop("n7_construct_candidates: max_candidates must be positive")
  }
  wide <- n7_probability_wide(probabilities)
  usable <- intersect(fixtures$fixture_id, wide$fixture_id)
  diagnostics <- list(n_fixtures = nrow(fixtures), n_priced = length(usable),
                      truncated = FALSE, dropped = 0L)

  if (!length(usable)) {
    return(list(groups = n7_typed_empty("group_legs"),
                group_legs = n7_typed_empty("group_legs"),
                diagnostics = diagnostics))
  }

  # Explicit groups: caller names them; we validate shape and pricing.
  if (is.list(construction) && !is.null(construction$groups)) {
    requested <- construction$groups
    rows <- list()
    for (g in seq_along(requested)) {
      members <- as.character(requested[[g]])
      if (length(members) != n_legs) {
        stop("n7_construct_candidates: group ", g, " has ", length(members),
             " legs, expected ", n_legs)
      }
      absent <- setdiff(members, usable)
      if (length(absent)) {
        stop("n7_construct_candidates: group ", g, " references unpriced fixtures ",
             paste(absent, collapse = ", "))
      }
      group_id <- n7_group_identity(members)
      for (order_index in seq_along(members)) {
        rows[[length(rows) + 1L]] <- tibble::tibble(
          group_id = group_id, fixture_id = members[order_index],
          leg_order = as.integer(order_index))
      }
    }
    legs <- if (length(rows)) n7_validate_table(dplyr::bind_rows(rows), "group_legs") else n7_typed_empty("group_legs")
    return(list(groups = legs, group_legs = legs, diagnostics = diagnostics))
  }

  if (!identical(construction, "entropy_balanced")) {
    stop("n7_construct_candidates: construction must be 'entropy_balanced' or a list with $groups")
  }

  # Deterministic difficulty-balanced construction: order fixtures by entropy
  # (descending, ties by fixture_id so the result is reproducible), then deal them
  # into groups round-robin so every group gets a similar difficulty mix.
  ordered <- wide[match(usable, wide$fixture_id), , drop = FALSE]
  ordered <- ordered[order(-ordered$entropy, ordered$fixture_id), , drop = FALSE]
  n_groups_avail <- floor(nrow(ordered) / n_legs)
  n_groups <- min(n_groups_avail, max_candidates)
  if (n_groups < n_groups_avail) diagnostics$truncated <- TRUE
  diagnostics$dropped <- nrow(ordered) - n_groups * n_legs
  if (n_groups < 1L) {
    return(list(groups = n7_typed_empty("group_legs"),
                group_legs = n7_typed_empty("group_legs"),
                diagnostics = diagnostics))
  }

  rows <- list()
  used <- character(0)
  # Deal round-robin rather than in contiguous blocks. Taking blocks would put the
  # seven hardest fixtures in one group and the seven easiest in another, which is
  # not "entropy balanced" and would concentrate risk instead of spreading it.
  # Only the first n_groups * n_legs fixtures are dealt; the remainder are dropped
  # and already counted in diagnostics$dropped.
  dealt <- split(ordered$fixture_id[seq_len(n_groups * n_legs)],
                 rep(seq_len(n_groups), length.out = n_groups * n_legs))
  for (g in seq_len(n_groups)) {
    members <- dealt[[g]]
    used <- c(used, members)
    group_id <- n7_group_identity(members)
    for (order_index in seq_along(members)) {
      rows[[length(rows) + 1L]] <- tibble::tibble(
        group_id = group_id, fixture_id = members[order_index],
        leg_order = as.integer(order_index))
    }
  }
  diagnostics$n_groups <- n_groups
  legs <- n7_validate_table(dplyr::bind_rows(rows), "group_legs")
  list(groups = legs, group_legs = legs, diagnostics = diagnostics)
}

# W/D/L -> 1/2/3, the code the shared ticket-identity helper expects. The
# mapping lives in one place so identity can never drift from the outcome order.
#' 把赛果标签映射为数值编码
#'
#' @param outcomes 字符向量。
#'   · 非字符   -> stop()
#'   · 零长度   -> stop()
#'   · 含 NA    -> stop()
#'   · 出现 W/D/L 之外的取值 -> stop()
#' @return 数值向量，取值 1/2/3，对应 n7_outcomes() 的顺序。
n7_outcome_codes <- function(outcomes) {
  if (!is.character(outcomes)) stop("n7_outcome_codes: outcomes must be character")
  if (!length(outcomes)) stop("n7_outcome_codes: outcomes must not be empty")
  if (anyNA(outcomes)) stop("n7_outcome_codes: outcomes must not be NA")
  codes <- match(outcomes, n7_outcomes())
  if (anyNA(codes)) stop("n7_outcome_codes: outcomes must be W, D or L")
  as.numeric(codes)
}

#' 一场比赛内赛果的确定性排序
#'
#' @param triple 数值向量，长度必须为 3，非负且有限。
#'   · 非数值 / 长度 != 3 / 含 NA / 非有限 -> stop()
#'   · 含负值                               -> stop()
#' @return 长度 3 的整数向量，为按概率降序、并列时按固定 W/D/L 顺序的排列索引。
#' @details 没有这个确定性排序，支撑集会依赖于列顺序而不是模型本身。
n7_outcome_rank <- function(triple) {
  if (!is.numeric(triple)) stop("n7_outcome_rank: triple must be numeric")
  values <- as.numeric(triple)
  if (length(values) != 3L || anyNA(values) || any(!is.finite(values))) {
    stop("n7_outcome_rank: need three finite values")
  }
  if (any(values < 0)) stop("n7_outcome_rank: probabilities must be non-negative")
  names(values) <- n7_outcomes()
  order(-values, match(names(values), n7_outcomes()))
}

#' 对每个组施加结构，得到受支撑的候选
#'
#' @param group_legs    tibble，group_legs 表（组 -> 比赛 -> 腿序）。
#' @param probabilities tibble，probabilities 表。
#' @param cutoff        temporal_learning 对象。
#' @param pattern       长度 7 的整数向量，元素取 1/2/3，表示"该条腿保留几个选项"。
#'   · 非长度 7 / 取值超出 1..3 -> stop()
#' @param assignment    "entropy_desc"（默认，越不确定的腿给越多选项）
#'                      或 "by_leg_order"（按 leg_order 位置施加 pattern）。
#' @param forbidden     硬掩码。与结构掩码取交集，且绝不用其它结果补足：被硬禁掉
#'                      一个选项的腿就是支撑更少，不得被顶替。
#' @param candidate_label 区分叠加在**同一**比赛集合上的多种结构。
#' @return list(candidates, supports, support_summary)，均为 tibble。
#' @details pattern 不是预算代号：同样的总支撑量可以由不同分布产生，而那是不同的注。
#'   group_id 是排序后的比赛集合因而被共享；candidate_id 必须按结构唯一，使两种
#'   结构能被独立排名与注资。否则同一组上的结构 A 与 B 会在 candidate_id 上撞车，
#'   它们的支撑集会被合并。
n7_apply_structure <- function(group_legs, probabilities, cutoff, pattern,
                               assignment = "entropy_desc", forbidden = NULL,
                               candidate_label = NULL) {
  n7_require_cutoff(cutoff)
  n7_validate_table(group_legs, "group_legs")
  if (!nrow(group_legs)) {
    return(list(candidates = n7_typed_empty("supports"),
                supports = n7_typed_empty("supports"),
                support_summary = tibble::tibble(
                  candidate_id = character(0), support_size = integer(0),
                  support_mass = numeric(0), structure_mass = numeric(0))))
  }
  if (length(pattern) != n7_legs() || any(!pattern %in% c(1L, 2L, 3L))) {
    stop("n7_apply_structure: pattern must be ", n7_legs(), " integers drawn from 1, 2, 3")
  }
  if (!assignment %in% c("entropy_desc", "by_leg_order")) {
    stop("n7_apply_structure: assignment must be 'entropy_desc' or 'by_leg_order'")
  }
  wide <- n7_probability_wide(probabilities)
  group_ids <- unique(group_legs$group_id)
  supports <- list()
  summaries <- list()
  exhausted <- character(0)

  # The default label is derived from the PATTERN, not left as the bare group id.
  # Two different structures over one fixture set are different candidates, so
  # defaulting to group_id alone would silently collide them when a caller omits the
  # optional label -- the contracted call must be safe without the extra argument.
  # The label carries the SAME "p" prefix funding matches on, so the default
  # apply -> enumerate -> rank -> fund sequence composes without an extra argument.
  effective_label <- candidate_label %||% paste0("p", paste(pattern, collapse = ""))
  make_candidate_id <- function(group_id) paste0(group_id, "|", effective_label)

  for (group_id in group_ids) {
    zero_support <- FALSE
    candidate_id <- make_candidate_id(group_id)
    legs <- group_legs[group_legs$group_id == group_id, , drop = FALSE]
    legs <- legs[order(legs$leg_order), , drop = FALSE]
    # A group_id is the sorted fixture set, so the same group can legitimately
    # appear more than once when two structures are requested over it. Collapse
    # those rows to one leg per fixture instead of treating them as extra legs.
    legs <- legs[!duplicated(legs$fixture_id), , drop = FALSE]
    if (nrow(legs) != n7_legs()) {
      stop("n7_apply_structure: group ", group_id, " has ", nrow(legs), " legs, expected ", n7_legs())
    }
    if (!all(legs$fixture_id %in% wide$fixture_id)) {
      stop("n7_apply_structure: group ", group_id, " has unpriced fixtures")
    }
    rows <- wide[match(legs$fixture_id, wide$fixture_id), , drop = FALSE]

    # Determine depth per leg.
    if (identical(assignment, "entropy_desc")) {
      # Most uncertain legs get the largest depths. Ties break by leg_order so the
      # result is stable.
      rank_order <- order(-rows$entropy, legs$leg_order)
      depths <- integer(n7_legs())
      sorted_pattern <- sort(pattern, decreasing = TRUE)
      depths[rank_order] <- sorted_pattern
    } else {
      depths <- as.integer(pattern)
    }

    # Support size is the PRODUCT of per-leg depths; structure_mass is the
    # product of the kept probabilities. Both must multiply across legs, not
    # sum: a ticket is a conjunction of seven legs.
    support_size <- 1L
    structure_mass <- 1
    for (leg_index in seq_len(n7_legs())) {
      triple <- as.numeric(rows[leg_index, n7_outcomes()])
      names(triple) <- n7_outcomes()
      rank_order <- n7_outcome_rank(triple)
      keep <- n7_outcomes()[rank_order][seq_len(depths[leg_index])]
      leg_allowed <- n7_outcomes() %in% keep
      if (!is.null(forbidden) && nrow(forbidden)) {
        banned_here <- forbidden$outcome[forbidden$fixture_id == legs$fixture_id[leg_index]]
        leg_allowed <- leg_allowed & !(n7_outcomes() %in% banned_here)
      }
      # Depth counts only outcomes that survive the hard mask, so a banned leg
      # simply has fewer supported outcomes rather than a substitute.
      depth_here <- sum(leg_allowed)
      if (depth_here < 1L) {
        # A hard mask can legitimately forbid every outcome of a leg. That is a
        # zero-support business case (the group is uninvestable), not a programming
        # error, so it yields empty output plus a reason instead of aborting.
        # Support is never topped up with a substitute outcome, and rows already
        # emitted for EARLIER legs are withdrawn with it: leaving them behind would
        # hand enumeration a candidate with a missing leg.
        for (other in legs$fixture_id) {
          drop <- vapply(supports, function(s) {
            identical(s$candidate_id, candidate_id) && identical(s$fixture_id, other)
          }, logical(1))
          if (any(drop)) supports <- supports[!drop]
        }
        support_size <- 0L
        structure_mass <- 0
        zero_support <- TRUE
        break
      }
      support_size <- support_size * depth_here
      structure_mass <- structure_mass * sum(triple[leg_allowed])
      for (outcome in n7_outcomes()) {
        supports[[length(supports) + 1L]] <- tibble::tibble(
          candidate_id = candidate_id, fixture_id = legs$fixture_id[leg_index],
          outcome = outcome, allowed = leg_allowed[match(outcome, n7_outcomes())],
          preference = 1L)
      }
    }
    # An exhausted group contributes no support rows and no summary.
    if (zero_support) {
      exhausted <- c(exhausted, candidate_id)
      next
    }
    summaries[[length(summaries) + 1L]] <- tibble::tibble(
      candidate_id = candidate_id, support_size = as.integer(support_size),
      support_mass = structure_mass, structure_mass = structure_mass)
  }

  # An all-exhausted run has no support rows at all; build the typed-empty table
  # rather than validating a zero-column frame.
  support_table <- if (length(supports)) {
    n7_validate_table(dplyr::bind_rows(supports), "supports")
  } else {
    n7_typed_empty("supports")
  }
  summary_table <- if (length(summaries)) {
    dplyr::bind_rows(summaries)
  } else {
    tibble::tibble(candidate_id = character(0), support_size = integer(0),
                   support_mass = numeric(0), structure_mass = numeric(0))
  }
  list(candidates = support_table, supports = support_table,
       support_summary = summary_table, exhausted = exhausted)
}

# n7_enumerate_tickets(group_legs, probabilities, cutoff, supports, n_legs)
#   -> list(tickets, ticket_legs, candidate_tickets)
#
# Expansion over the allowed support only, so the space is the product of the
# per-leg depths, at most 3^7 = 2187. Ticket identity is the physical ticket:
# the fixture/outcome pairs. Two candidates that support the same ticket share one
# ticket_id and appear twice in candidate_tickets; that is what stops the same
# physical ticket being bought twice under two structures.
#' 把受支撑的空间展开为物理票
#'
#' @param group_legs    tibble，group_legs 表（组 -> 比赛 -> 腿序）。
#' @param probabilities tibble，probabilities 表。
#' @param cutoff        temporal_learning 对象。
#' @param supports      tibble，supports 表（每个 candidate 每场的允许结果）。
#' @param n_legs        长度 1 的正整数，默认 n7_legs()。
#' @return 物理票的展开结果（每个 candidate 的票集合）。
#' @details 票是**物理**实体：同一组七场比赛上的不同结构共享 ticket_id，
#'   因此同一张票不会因为出现在两个 candidate 里而被买两次。
n7_enumerate_tickets <- function(group_legs, probabilities, cutoff, supports, n_legs = n7_legs()) {
  n7_require_cutoff(cutoff)
  n7_validate_table(group_legs, "group_legs")
  n7_validate_table(supports, "supports")
  if (length(n_legs) != 1L || n_legs != n7_legs()) {
    stop("n7_enumerate_tickets: this pipeline fixes n_legs at ", n7_legs())
  }
  if (!nrow(group_legs)) {
    return(list(tickets = n7_typed_empty("tickets"),
                ticket_legs = n7_typed_empty("ticket_legs"),
                candidate_tickets = tibble::tibble(candidate_id = character(0),
                                                   ticket_id = character(0))))
  }
  wide <- n7_probability_wide(probabilities)
  ticket_rows <- list()
  leg_rows <- list()
  link_rows <- list()
  seen <- new.env(parent = emptyenv())

  # Iterate CANDIDATES, not groups. Several structures may share one fixture set, so
  # one group_id can carry several candidate_ids and each must expand separately.
  for (candidate_id in unique(supports$candidate_id)) {
    group_id <- sub("[|].*$", "", candidate_id)
    legs <- group_legs[group_legs$group_id == group_id, , drop = FALSE]
    legs <- legs[order(legs$leg_order), , drop = FALSE]
    legs <- legs[!duplicated(legs$fixture_id), , drop = FALSE]
    group_supports <- supports[supports$candidate_id == candidate_id, , drop = FALSE]
    if (!nrow(group_supports)) {
      stop("n7_enumerate_tickets: candidate ", candidate_id, " has no support")
    }
    options_per_leg <- list()
    for (leg_index in seq_len(nrow(legs))) {
      fixture_id <- legs$fixture_id[leg_index]
      allowed <- group_supports$outcome[group_supports$fixture_id == fixture_id &
                                          group_supports$allowed]
      if (!length(allowed)) {
        stop("n7_enumerate_tickets: candidate ", candidate_id,
             " has an empty leg at ", fixture_id)
      }
      # Hold the declared outcome order so enumeration is deterministic.
      options_per_leg[[leg_index]] <- n7_outcomes()[n7_outcomes() %in% allowed]
    }
    grid <- expand.grid(options_per_leg, KEEP.OUT.ATTRS = FALSE, stringsAsFactors = FALSE)
    for (combo_index in seq_len(nrow(grid))) {
      combo <- as.character(unlist(grid[combo_index, ]))
      combo_codes <- n7_outcome_codes(combo)
      ticket_key <- n7_physical_ticket_key(legs$fixture_id, combo_codes)
      ticket_id <- ticket_key
      if (!exists(ticket_id, envir = seen, inherits = FALSE)) {
        assign(ticket_id, TRUE, envir = seen)
        # Raw probability: the product of the leg probabilities, declaring the
        # independence approximation rather than hiding it.
        probability <- 1
        for (leg_index in seq_len(nrow(legs))) {
          outcome <- combo[leg_index]
          row <- wide[wide$fixture_id == legs$fixture_id[leg_index], , drop = FALSE]
          probability <- probability * as.numeric(row[1, outcome])
        }
        # group_id stays the fixture set so ticket identity is one row per physical
        # ticket; candidate_tickets records which structures support it.
        ticket_rows[[length(ticket_rows) + 1L]] <- tibble::tibble(
          ticket_id = ticket_id, group_id = group_id, probability = probability,
          sp_product_est = NA_real_, ev_net_est = NA_real_)
        for (leg_index in seq_len(nrow(legs))) {
          leg_rows[[length(leg_rows) + 1L]] <- tibble::tibble(
            ticket_id = ticket_id, fixture_id = legs$fixture_id[leg_index],
            outcome = combo[leg_index])
        }
      }
      link_rows[[length(link_rows) + 1L]] <- tibble::tibble(
        candidate_id = candidate_id, ticket_id = ticket_id)
    }
  }
  # An all-exhausted structure leaves every list empty; bind_rows on an empty list has
  # no columns at all, so fall back to the typed-empty tables rather than failing
  # validation. Zero tickets is a legitimate outcome, not an error.
  list(
    tickets = if (length(ticket_rows)) {
      n7_validate_table(dplyr::bind_rows(ticket_rows), "tickets", keys = "ticket_id")
    } else {
      n7_typed_empty("tickets")
    },
    ticket_legs = if (length(leg_rows)) {
      n7_validate_table(dplyr::bind_rows(leg_rows), "ticket_legs")
    } else {
      n7_typed_empty("ticket_legs")
    },
    candidate_tickets = if (length(link_rows)) {
      dplyr::bind_rows(link_rows)
    } else {
      tibble::tibble(candidate_id = character(0), ticket_id = character(0))
    })
}
