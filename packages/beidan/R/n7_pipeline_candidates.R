#' N7 管道的组构造、结构支撑与票枚举
#'
#' 三个可分离的步骤，各有自己的契约：
#'   parlay_construct_groups  选择**哪些比赛**组成一个 n_legs 腿组
#'   parlay_apply_structure       选择每条腿**保留几个选项**
#'   parlay_enumerate_tickets     把受支撑的空间展开成物理票
#'
#' @details 保持三步分离很重要：'选哪些比赛'与'每场投多少'是两个不同的决策、
#'   对应不同的预算；契约要求结构是长度 n_legs 的整数向量，而不是预算的代号。
#'   本模块只定义函数，导入时不触发任何 I/O。

#' 概率的宽表视图：每场一行，列为 W/D/L
#'
#' @param probabilities tibble，probabilities 表（经 match_validate_table 校验）。
#'   · 0 行 -> 返回带完整列集合的空表
#'   · 缺任一 W/D/L 列 -> stop()
#'   · 出现缺口（某场缺某结果）-> stop()
#'   · 任一行和不为 1 -> stop()
#' @return tibble：fixture_id, W, D, L。仅做概率合同校验与宽表转换，不派生任何指标列。
#' @details 本函数不隐式计算熵或其它难度指标。调用方需要熵时必须显式自行计算，
#'   共享整理函数不得暗中替算法做决定。
parlay_probability_wide <- function(probabilities) {
  match_validate_table(probabilities, "probabilities")
  if (!nrow(probabilities)) {
    return(tibble::tibble(fixture_id = character(0), W = numeric(0),
                          D = numeric(0), L = numeric(0)))
  }
  wide <- tidyr::pivot_wider(probabilities, names_from = "outcome",
                             values_from = "probability")
  missing <- setdiff(match_outcomes(), names(wide))
  if (length(missing)) stop("parlay_probability_wide: missing outcomes ", paste(missing, collapse = ", "))
  wide <- wide[, c("fixture_id", match_outcomes())]
  matrix_values <- as.matrix(wide[, match_outcomes()])
  if (anyNA(matrix_values)) stop("parlay_probability_wide: probabilities have gaps")
  match_check_probability_sum(matrix_values)
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
#' @details 同一组 n_legs 场比赛上的两种结构共享同一个 group_id，这正是让一张物理票
#'   可以被多个 candidate 引用而不被重复购买的依据。
parlay_group_identity <- function(fixture_ids) {
  if (!length(fixture_ids)) stop("parlay_group_identity: fixture_ids must not be empty")
  if (!is.character(fixture_ids)) {
    stop("parlay_group_identity: fixture_ids must be character")
  }
  # An NA fixture id would stringify to "NA" and become indistinguishable from a
  # real fixture literally named "NA", corrupting the group identity.
  if (anyNA(fixture_ids)) stop("parlay_group_identity: fixture_ids must not be NA")
  if (any(!nzchar(fixture_ids))) {
    stop("parlay_group_identity: fixture_ids must not be empty strings")
  }
  paste(sort(unique(fixture_ids)), collapse = "+")
}

#' 读出 group_legs 实际的场数（方案级结构宽度）
#'
#' @param group_legs tibble，group_legs 表（组 -> 比赛 -> 腿序），可为空表。
#' @return 长度 1 的 integer：每组实际的不同比赛数；空表返回 0L。
#' @details 一个方案只有一个场数，因此同一 group_legs 里每个组的腿数必须相同；
#'   这里既读出宽度，也顺带拒绝混用场数的表。它取代了此前写死的 n7_legs() 常量，
#'   使结构层与结算层可以对 6/7/8 场工作而不引入任何臆测上限。
parlay_structure_legs <- function(group_legs) {
  match_validate_table(group_legs, "group_legs")
  if (!nrow(group_legs)) return(0L)
  per_group <- vapply(split(group_legs$fixture_id, group_legs$group_id),
                      function(ids) length(unique(ids)), integer(1))
  if (length(unique(per_group)) != 1L) {
    stop("parlay_structure_legs: groups have mixed leg counts (",
         paste(sort(unique(per_group)), collapse = ", "),
         "); one plan must use a single n_legs")
  }
  for (group in unique(group_legs$group_id)) {
    block <- group_legs[group_legs$group_id == group, , drop = FALSE]
    block <- unique(block[, c("fixture_id", "leg_order"), drop = FALSE])
    if (anyDuplicated(block$fixture_id) ||
        !identical(sort(block$leg_order), seq_len(nrow(block)))) {
      stop("parlay_structure_legs: leg_order must be exactly 1:n_legs within each group")
    }
  }
  return(as.integer(per_group[[1L]]))
}

#' 构造候选组
#'
#' @param fixtures      tibble，fixtures 表，强制 (issue_id, fixture_id) 唯一键。
#'   · 含非 cutoff 期号的比赛 -> stop()
#'   · 开赛 <= cutoff 的比赛   -> stop()（已开赛的不可购买）
#'   · 开赛落在 D+1 决策窗口之外的比赛 -> stop()
#' @param probabilities tibble，probabilities 表；每场必须 W/D/L 齐全且行和为 1。
#' @param cutoff        temporal_learning 对象。
#' @param match_status tibble，比赛状态台账（语义见 match_select_status）。
#'   **必填且无默认值**：附加在末尾以保持既有位置调用的可读性，但缺失即 stop()，
#'   因为"没有台账"与"台账为空"是两件事，前者是输入契约错误。
#' @param n_legs        长度 1 的正整数（方案级场数）。
#' @param construction  显式的 fixture-id 组 list，或 "fixture_round_robin"。
#' @param max_candidates 长度 1 的正整数。
#' @param seed          整数标量；保留为确定性种子参数，当前构造不消耗随机数。
#' @return list(groups, group_legs, diagnostics); diagnostics$status_exclusions
#'   records each fixture excluded by its visible match status.，均为 tibble。
#' @details 不执行完整的 n_legs-of-N 枚举：那是组合爆炸，且契约禁止声称全局最优。
#'   决策绑定到**一期**：拿别的期号的比赛对着本 cutoff 定价，会让回放买到
#'   不属于它自己赛程的比赛。
#'
#'   比赛可见性由唯一的共享选择器 match_select_status() 决定，且使用完全相同的
#'   cutoff：本函数不自己实现一套状态判定，因此从 fixtures 直接构造候选与经由
#'   prepare_match_inputs 构造得到同一批比赛。台账的关系键已经由输入边界
#'   （read_match_inputs 或 prepare_match_inputs）对着完整帧校验过，因此这里直接把同一份
#'   fixtures 交给选择器，不再另做关系检查。
parlay_construct_groups <- function(fixtures, probabilities, cutoff, n_legs,
                                    construction, max_candidates, seed = 1L,
                                    match_status) {
  match_require_cutoff(cutoff)
  # Select FIRST, then validate the survivors: a fixture that is not visible as
  # scheduled at this cutoff must never reach the group builder.
  status_selection <- match_select_status(fixtures, match_status, cutoff)
  fixtures <- status_selection$fixtures
  match_validate_table(fixtures, "fixtures", keys = c("issue_id", "fixture_id"))
  # The decision is bound to ONE issue. Pricing another issue's fixtures against this
  # cutoff would let a replay purchase matches outside its own slate.
  if ("issue_id" %in% names(fixtures)) {
    stray <- setdiff(unique(as.character(fixtures$issue_id)), as.character(cutoff$issue_id))
    if (length(stray)) {
      stop("parlay_construct_groups: fixtures belong to issue(s) ",
           paste(stray, collapse = ", "), ", not ", cutoff$issue_id)
    }
  }
  # The allocation path must be as bound to the cutoff as projection is: a fixture
  # that had already kicked off cannot be purchased, and a fixture outside the D+1
  # rolling decision window is not part of this decision either.
  if ("kickoff_at" %in% names(fixtures)) {
    cutoff_bound <- match_cutoff_utc(cutoff)
    if (any(fixtures$kickoff_at <= cutoff_bound)) {
      stop("parlay_construct_groups: fixtures already kicked off at the cutoff ",
           "are not eligible")
    }
    # Keep subsecond boundaries identical to input preparation.
    window <- match_decision_window(cutoff_bound)
    window_start <- window$start_utc
    window_end <- window$end_utc
    outside <- fixtures$kickoff_at < window_start | fixtures$kickoff_at >= window_end
    if (any(outside)) {
      stop("parlay_construct_groups: fixture(s) outside the decision window ",
           window$start_utc, " to ", window$end_utc, " are not eligible")
    }
  }
  checkmate::assert_count(n_legs, positive = TRUE, .var.name = "n_legs")
  if (length(max_candidates) != 1L || max_candidates < 1L) {
    stop("parlay_construct_groups: max_candidates must be positive")
  }
  wide <- parlay_probability_wide(probabilities)
  usable <- intersect(fixtures$fixture_id, wide$fixture_id)
  diagnostics <- list(n_fixtures = nrow(fixtures), n_priced = length(usable),
                      truncated = FALSE, dropped = 0L,
                      status_exclusions = status_selection$exclusions)

  if (!length(usable)) {
    return(list(groups = match_typed_empty("group_legs"),
                group_legs = match_typed_empty("group_legs"),
                diagnostics = diagnostics))
  }

  # Explicit groups: caller names them; we validate shape and pricing.
  if (is.list(construction) && !is.null(construction$groups)) {
    requested <- construction$groups
    rows <- list()
    for (g in seq_along(requested)) {
      members <- as.character(requested[[g]])
      if (length(members) != n_legs) {
        stop("parlay_construct_groups: group ", g, " has ", length(members),
             " legs, expected ", n_legs)
      }
      absent <- setdiff(members, usable)
      if (length(absent)) {
        stop("parlay_construct_groups: group ", g, " references unpriced fixtures ",
             paste(absent, collapse = ", "))
      }
      group_id <- parlay_group_identity(members)
      for (order_index in seq_along(members)) {
        rows[[length(rows) + 1L]] <- tibble::tibble(
          group_id = group_id, fixture_id = members[order_index],
          leg_order = as.integer(order_index))
      }
    }
    legs <- if (length(rows)) match_validate_table(dplyr::bind_rows(rows), "group_legs") else match_typed_empty("group_legs")
    return(list(groups = legs, group_legs = legs, diagnostics = diagnostics))
  }

  if (!identical(construction, "fixture_round_robin")) {
    stop("parlay_construct_groups: construction must be 'fixture_round_robin' or a list with $groups")
  }

  # Deterministic round-robin construction: order fixtures by fixture_id (ascending)
  # and deal them round-robin into groups. This is a fixture-selection baseline for
  # the legacy group builder, NOT a difficulty-balancing rule: it makes no claim
  # about which group is easier, and it does not consult any probability-derived
  # difficulty metric. Role-based construction is a separate API.
  ordered <- wide[match(usable, wide$fixture_id), , drop = FALSE]
  ordered <- ordered[order(ordered$fixture_id), , drop = FALSE]
  n_groups_avail <- floor(nrow(ordered) / n_legs)
  n_groups <- min(n_groups_avail, max_candidates)
  if (n_groups < n_groups_avail) diagnostics$truncated <- TRUE
  diagnostics$dropped <- nrow(ordered) - n_groups * n_legs
  if (n_groups < 1L) {
    return(list(groups = match_typed_empty("group_legs"),
                group_legs = match_typed_empty("group_legs"),
                diagnostics = diagnostics))
  }

  rows <- list()
  used <- character(0)
  # Deal round-robin rather than in contiguous blocks, so consecutive fixture ids are
  # spread across groups. Only the first n_groups * n_legs fixtures are dealt; the
  # remainder are dropped and already counted in diagnostics$dropped.
  dealt <- split(ordered$fixture_id[seq_len(n_groups * n_legs)],
                 rep(seq_len(n_groups), length.out = n_groups * n_legs))
  for (g in seq_len(n_groups)) {
    members <- dealt[[g]]
    used <- c(used, members)
    group_id <- parlay_group_identity(members)
    for (order_index in seq_along(members)) {
      rows[[length(rows) + 1L]] <- tibble::tibble(
        group_id = group_id, fixture_id = members[order_index],
        leg_order = as.integer(order_index))
    }
  }
  diagnostics$n_groups <- n_groups
  legs <- match_validate_table(dplyr::bind_rows(rows), "group_legs")
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
#' @return 数值向量，取值 1/2/3，对应 match_outcomes() 的顺序。
parlay_outcome_codes <- function(outcomes) {
  if (!is.character(outcomes)) stop("parlay_outcome_codes: outcomes must be character")
  if (!length(outcomes)) stop("parlay_outcome_codes: outcomes must not be empty")
  if (anyNA(outcomes)) stop("parlay_outcome_codes: outcomes must not be NA")
  codes <- match(outcomes, match_outcomes())
  if (anyNA(codes)) stop("parlay_outcome_codes: outcomes must be W, D or L")
  as.numeric(codes)
}

#' 一场比赛内赛果的确定性排序
#'
#' @param triple 数值向量，长度必须为 3，非负且有限。
#'   · 非数值 / 长度 != 3 / 含 NA / 非有限 -> stop()
#'   · 含负值                               -> stop()
#' @return 长度 3 的整数向量，为按概率降序、并列时按固定 W/D/L 顺序的排列索引。
#' @details 没有这个确定性排序，支撑集会依赖于列顺序而不是模型本身。
parlay_outcome_rank <- function(triple) {
  if (!is.numeric(triple)) stop("parlay_outcome_rank: triple must be numeric")
  values <- as.numeric(triple)
  if (length(values) != 3L || anyNA(values) || any(!is.finite(values))) {
    stop("parlay_outcome_rank: need three finite values")
  }
  if (any(values < 0)) stop("parlay_outcome_rank: probabilities must be non-negative")
  names(values) <- match_outcomes()
  order(-values, match(names(values), match_outcomes()))
}

#' 对每个组施加结构，得到受支撑的候选
#'
#' @param group_legs    tibble，group_legs 表（组 -> 比赛 -> 腿序）。
#' @param probabilities tibble，probabilities 表。
#' @param cutoff        temporal_learning 对象。
#' @param pattern       长度 n_legs 的整数向量，元素取 1/2/3，表示"该条腿保留几个选项"。
#'   · 长度与组场数不一致 / 取值超出 1..3 -> stop()
#' @param pattern       长度 n_legs 的整数向量，元素取 1/2/3，表示"该条腿保留几个选项"。
#'   · 长度与组场数不一致 / 取值超出 1..3 -> stop()
#' @param forbidden     硬掩码。与结构掩码取交集，且绝不用其它结果补足：被硬禁掉
#'                      一个选项的腿就是支撑更少，不得被顶替。
#' @param candidate_label 区分叠加在**同一**比赛集合上的多种结构。
#' @return list(candidates, supports, support_summary)，均为 tibble。
#' @details pattern 不是预算代号：同样的总支撑量可以由不同分布产生，而那是不同的注。
#'   group_id 是排序后的比赛集合因而被共享；candidate_id 必须按结构唯一，使两种
#'   结构能被独立排名与注资。否则同一组上的结构 A 与 B 会在 candidate_id 上撞车，
#'   它们的支撑集会被合并。
#'
#'   每条腿的角色由权威的 parlay_role_scores() 决定：在每个固定组内，按排序后的
#'   pattern 角色 3→2→1 依次处理，每一步在该角色榜上选取分数最高、且尚未被本组
#'   占用的成员（分数并列按 fixture_id 升序）。被选中的角色即该腿最终保持的角色。
#'   本函数不复制任何评分逻辑，也不按熵重排角色。
parlay_apply_structure <- function(group_legs, probabilities, cutoff, pattern,
                               forbidden = NULL,
                               candidate_label = NULL) {
  match_require_cutoff(cutoff)
  match_validate_table(group_legs, "group_legs")
  if (!nrow(group_legs)) {
    checkmate::assert_integerish(pattern, lower = 1, upper = 3, min.len = 1,
                                any.missing = FALSE, .var.name = "pattern")
    return(list(candidates = match_typed_empty("supports"),
                supports = match_typed_empty("supports"),
                support_summary = tibble::tibble(
                  candidate_id = character(0), support_size = integer(0),
                  support_mass = numeric(0), structure_mass = numeric(0))))
  }
  # The structure's width is the plan's n_legs, read from the legs it is applied
  # over. A plan never mixes widths, so a pattern whose length disagrees with the
  # group's legs is a structural mismatch, not something to pad or truncate.
  n_legs <- parlay_structure_legs(group_legs)
  if (length(pattern) != n_legs || any(!pattern %in% c(1L, 2L, 3L))) {
    stop("parlay_apply_structure: pattern must be ", n_legs,
         " integers drawn from 1, 2, 3")
  }
  wide <- parlay_probability_wide(probabilities)
  # The authoritative role ranking. Scoring lives in parlay_role_scores() only; this
  # structure pass consumes its rank column instead of re-deriving p1 / p1+p2 / p3.
  role_scores <- parlay_role_scores(probabilities, cutoff)
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
    # Every group in one plan carries the SAME width, which is the width of this
    # structure's pattern. A group whose leg count differs is a mixed-width plan
    # and is refused here rather than being padded or truncated.
    if (nrow(legs) != n_legs) {
      stop("parlay_apply_structure: group ", group_id, " has ", nrow(legs),
           " legs, expected ", n_legs)
    }
    if (!all(legs$fixture_id %in% wide$fixture_id)) {
      stop("parlay_apply_structure: group ", group_id, " has unpriced fixtures")
    }
    rows <- wide[match(legs$fixture_id, wide$fixture_id), , drop = FALSE]

    # Assign roles inside this FIXED group: process the sorted pattern roles from 3
    # down to 2 down to 1, each time picking the highest-ranked still-unassigned
    # member in that role's ranking. Ties inside one role are already broken by
    # fixture_id in parlay_role_scores(). The chosen role is the leg's FINAL role and
    # its authoritative outcome mask is recorded per leg; neither is re-derived later.
    # The kept outcomes come from the SAME authoritative role row that assigned the
    # leg, captured at assignment time. Re-deriving them here with
    # parlay_outcome_rank() would drop the role scorer's nine-decimal tie handling and
    # let a near-tie keep a different outcome than the role definition (AGENTS.md:48,
    # one authoritative implementation per contract).
    allowed_by_leg <- vector("list", n_legs)
    assigned <- logical(n_legs)
    for (role in sort(as.integer(pattern), decreasing = TRUE)) {
      ranked <- role_scores[role_scores$role == role, , drop = FALSE]
      ranked <- ranked[order(ranked$rank), , drop = FALSE]
      # Keep only members of THIS group that are still unassigned, in role-rank order.
      order_in_group <- match(ranked$fixture_id, legs$fixture_id)
      keep <- !is.na(order_in_group) & !assigned[order_in_group]
      ranked_members <- order_in_group[keep]
      # Every member is priced for every role, so a pick is always available while a
      # leg is unassigned; a missing pick would mean the role table is incomplete.
      if (!length(ranked_members)) {
        stop("parlay_apply_structure: no unassigned member for role ", role,
             " in group ", group_id)
      }
      pick <- ranked_members[[1L]]
      allowed_by_leg[[pick]] <- ranked$allowed_outcomes[[which(keep)[[1L]]]]
      assigned[pick] <- TRUE
    }

    # Support size is the PRODUCT of per-leg depths; structure_mass is the
    # product of the kept probabilities. Both must multiply across legs, not
    # sum: a ticket is a conjunction of n_legs legs.
    support_size <- 1
    structure_mass <- 1
    for (leg_index in seq_len(n_legs)) {
      triple <- as.numeric(rows[leg_index, match_outcomes()])
      names(triple) <- match_outcomes()
      # Consume the selected role's authoritative outcome mask directly. The role
      # scorer already fixed which outcomes this leg keeps, near ties included; no
      # second ranking pass runs here and the mask is never topped up.
      leg_allowed <- match_outcomes() %in% allowed_by_leg[[leg_index]]
      if (!is.null(forbidden) && nrow(forbidden)) {
        banned_here <- forbidden$outcome[forbidden$fixture_id == legs$fixture_id[leg_index]]
        leg_allowed <- leg_allowed & !(match_outcomes() %in% banned_here)
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
      for (outcome in match_outcomes()) {
        supports[[length(supports) + 1L]] <- tibble::tibble(
          candidate_id = candidate_id, fixture_id = legs$fixture_id[leg_index],
          outcome = outcome, allowed = leg_allowed[match(outcome, match_outcomes())],
          preference = 1L)
      }
    }
    # An exhausted group contributes no support rows and no summary.
    if (zero_support) {
      exhausted <- c(exhausted, candidate_id)
      next
    }
    if (!is.finite(support_size) || support_size > .Machine$integer.max) {
      stop("parlay_apply_structure: support size exceeds the representable integer range")
    }
    summaries[[length(summaries) + 1L]] <- tibble::tibble(
      candidate_id = candidate_id, support_size = as.integer(support_size),
      support_mass = structure_mass, structure_mass = structure_mass)
  }

  # An all-exhausted run has no support rows at all; build the typed-empty table
  # rather than validating a zero-column frame.
  support_table <- if (length(supports)) {
    match_validate_table(dplyr::bind_rows(supports), "supports")
  } else {
    match_typed_empty("supports")
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

# parlay_enumerate_tickets(group_legs, probabilities, cutoff, supports, n_legs)
#   -> list(tickets, ticket_legs, candidate_tickets)
#
# Expansion over the allowed support only, so the space is the product of the
# per-leg depths. At the maximum per-leg depth of 3 this is 3^n_legs: 729 for six
# legs, 2187 for seven and 6561 for eight. Those counts are small enough to
# allocate, so no arbitrary cap is imposed; the guard below refuses only the one
# case that is a real numeric limit rather than a speculative policy -- a product
# that no longer fits in an R integer (or a non-finite double), which is where the
# expansion would silently overflow and produce a wrong ticket count.
#
# Ticket identity is the physical ticket: the fixture/outcome pairs. Two candidates
# that support the same ticket share one ticket_id and appear twice in
# candidate_tickets; that is what stops the same physical ticket being bought twice
# under two structures.
#' 把受支撑的空间展开为物理票
#'
#' @param group_legs    tibble，group_legs 表（组 -> 比赛 -> 腿序）。
#' @param probabilities tibble，probabilities 表。
#' @param cutoff        temporal_learning 对象。
#' @param supports      tibble，supports 表（每个 candidate 每场的允许结果）。
#' @param n_legs        长度 1 的正整数（>= 1），默认取 group_legs 的实际场数。
#'   · 与 group_legs 的场数不一致 -> stop()（一个方案禁止混合场数）
#' @return 物理票的展开结果（每个 candidate 的票集合）。
#' @details 票是**物理**实体：同一组 n_legs 场比赛上的不同结构共享 ticket_id，
#'   因此同一张票不会因为出现在两个 candidate 里而被买两次。
parlay_enumerate_tickets <- function(group_legs, probabilities, cutoff, supports,
                                     n_legs = parlay_structure_legs(group_legs)) {
  match_require_cutoff(cutoff)
  match_validate_table(group_legs, "group_legs")
  match_validate_table(supports, "supports")
  # One plan, one width. The declared n_legs must equal the width of the legs it
  # expands, so a caller cannot enumerate a 7-leg group while claiming 6.
  if (nrow(group_legs) || !missing(n_legs)) {
    if (length(n_legs) != 1L || !is.numeric(n_legs) || is.na(n_legs) || n_legs < 1 ||
        n_legs != trunc(n_legs)) {
      stop("parlay_enumerate_tickets: n_legs must be one whole number of at least 1")
    }
    n_legs <- as.integer(n_legs)
    if (nrow(group_legs) && n_legs != parlay_structure_legs(group_legs)) {
      stop("parlay_enumerate_tickets: n_legs ", n_legs,
           " does not match the group width ", parlay_structure_legs(group_legs))
    }
  }
  if (!nrow(group_legs)) {
    return(list(tickets = match_typed_empty("tickets"),
                ticket_legs = match_typed_empty("ticket_legs"),
                candidate_tickets = tibble::tibble(candidate_id = character(0),
                                                   ticket_id = character(0))))
  }
  wide <- parlay_probability_wide(probabilities)
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
      stop("parlay_enumerate_tickets: candidate ", candidate_id, " has no support")
    }
    options_per_leg <- list()
    for (leg_index in seq_len(nrow(legs))) {
      fixture_id <- legs$fixture_id[leg_index]
      allowed <- group_supports$outcome[group_supports$fixture_id == fixture_id &
                                          group_supports$allowed]
      if (!length(allowed)) {
        stop("parlay_enumerate_tickets: candidate ", candidate_id,
             " has an empty leg at ", fixture_id)
      }
      # Hold the declared outcome order so enumeration is deterministic.
      options_per_leg[[leg_index]] <- match_outcomes()[match_outcomes() %in% allowed]
    }
    supported_size <- prod(lengths(options_per_leg))
    if (!is.finite(supported_size) || supported_size > .Machine$integer.max) {
      stop("parlay_enumerate_tickets: supported ticket count exceeds the representable integer count")
    }
    grid <- expand.grid(options_per_leg, KEEP.OUT.ATTRS = FALSE, stringsAsFactors = FALSE)
    for (combo_index in seq_len(nrow(grid))) {
      combo <- as.character(unlist(grid[combo_index, ]))
      combo_codes <- parlay_outcome_codes(combo)
      ticket_key <- parlay_physical_ticket_key(legs$fixture_id, combo_codes)
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
      match_validate_table(dplyr::bind_rows(ticket_rows), "tickets", keys = "ticket_id")
    } else {
      match_typed_empty("tickets")
    },
    ticket_legs = if (length(leg_rows)) {
      match_validate_table(dplyr::bind_rows(leg_rows), "ticket_legs")
    } else {
      match_typed_empty("ticket_legs")
    },
    candidate_tickets = if (length(link_rows)) {
      dplyr::bind_rows(link_rows)
    } else {
      tibble::tibble(candidate_id = character(0), ticket_id = character(0))
    })
}
