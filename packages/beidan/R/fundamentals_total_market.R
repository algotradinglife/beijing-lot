# Poisson Over share of settled stake; quarter lines split into half stakes.
# lambda is goals/match, line is goals. Pure analytic projection, no history fit.
#' Compute the over share of settled Asian total stake
#'
#' Operates on explicit inputs. Invalid contracts raise errors; no network,
#' package installation or database writes occur.
#' @param lambda Positive numeric goal mean; home and away pair for score projection.
#' @param line Nonnegative Asian total line in quarter-goal increments.
#' @return A numeric over probability, accounting for pushes and quarter-line splits.
asian_total_probability <- function(lambda, line) {
  if(length(lambda)!=1L || length(line)!=1L || anyNA(c(lambda,line)) ||
     any(!is.finite(c(lambda,line))) || lambda<=0 || line<0 || line>30 || line*4!=round(line*4)) stop('Invalid total parameters')
  legs <- if(line*2==round(line*2)) line else c(floor(line*2)/2,ceiling(line*2)/2)
  over <- mean(stats::ppois(floor(legs),lambda,lower.tail=FALSE))
  under <- mean(stats::ppois(ceiling(legs)-1,lambda))
  over/(over+under)
}

# One latest quote/company; proportional inverse-decimal margin removal.
# Invert each Asian line separately, then equal-mean company lambda. No I/O.
#' Infer total goal means from company-specific over-under quotes
#'
#' Operates on explicit inputs. Invalid contracts raise errors; no network,
#' package installation or database writes occur.
#' @param quotes Data frame with company, line, over_hk and under_hk; one valid quote per company.
#' @param bounds Increasing pair of positive numeric limits for total-goal root finding.
#' @return A list with mean lambda_total and the per-company fitted table.
total_market_constraint <- function(quotes, bounds) {
  if(!is.data.frame(quotes) || !all(c('company','line','over_hk','under_hk') %in% names(quotes)) ||
     !nrow(quotes) || anyNA(quotes[c('company','line','over_hk','under_hk')]) ||
     anyDuplicated(quotes$company) || any(!is.finite(c(quotes$line,quotes$over_hk,quotes$under_hk))) ||
     any(quotes$over_hk<=0 | quotes$under_hk<=0) || length(bounds)!=2L || anyNA(bounds) ||
     any(!is.finite(bounds)) || bounds[1]<=0 || bounds[2]<=bounds[1]) stop('Invalid OU quote contract')
  quotes$over_target <- (1/(1+quotes$over_hk))/(1/(1+quotes$over_hk)+1/(1+quotes$under_hk))
  quotes$lambda_total <- vapply(seq_len(nrow(quotes)),function(i) {
    stats::uniroot(function(x)asian_total_probability(x,quotes$line[i])-quotes$over_target[i],
      interval=bounds,tol=1e-10,check.conv=TRUE)$root
  },numeric(1))
  list(lambda_total=mean(quotes$lambda_total),companies=quotes)
}

# Fix OU total mean; minimize ordinary W/D/L squared residual over home lambda.
# Overidentified grid need not match all prices: report residual. `rho` is the
# frozen Dixon-Coles dependence parameter; with it fixed this stays a
# one-dimensional search, which is what keeps the model identified.
#' Fit the home goal share with total goals and rho fixed
#'
#' Operates on explicit inputs. Invalid contracts raise errors; no network,
#' package installation or database writes occur.
#' @param total Positive fixed total goal mean.
#' @param ordinary_target Length-three positive ordinary W/D/L probability vector summing to one.
#' @param handicap Numeric home-goal handicap; applied to home minus away goals.
#' @param tail_tolerance Positive probability tolerance below one for truncating the score grid.
#' @param rho Explicit fixed Dixon-Coles low-score dependence parameter.
#' @return A list of grid and fields including the ordinary-market residual.
total_constrained_projection <- function(total, ordinary_target, handicap, tail_tolerance, rho) {
  if(length(total)!=1 || is.na(total) || !is.finite(total) || total<=.1 ||
     length(ordinary_target)!=3L || anyNA(ordinary_target) || any(!is.finite(ordinary_target)) ||
     any(ordinary_target<=0) || abs(sum(ordinary_target)-1)>1e-10) stop('Invalid total/ordinary target')
  objective <- function(home) {
    p <- market_score_projection(c(home,total-home),handicap,tail_tolerance,rho)
    sum((unlist(p$fields[c('ordinary_W','ordinary_D','ordinary_L')])-ordinary_target)^2)
  }
  fit <- stats::optimize(objective,c(.05,total-.05),tol=1e-10)
  p <- market_score_projection(c(fit$minimum,total-fit$minimum),handicap,tail_tolerance,rho)
  p$fields$market_residual <- max(abs(unlist(p$fields[c('ordinary_W','ordinary_D','ordinary_L')])-ordinary_target))
  p
}

# Extend sealed label-free market scenarios with OU and a fixed 10% home-share
# correction, holding OU total fixed. Match explicit cutoffs and source seals.