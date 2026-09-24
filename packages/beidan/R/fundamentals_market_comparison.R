# Fixed inverse-price sensitivity, not a learned league-strength conversion.
# All lambdas are goals/match. alpha is in [0,1], cap in [0,1). Pure, no I/O.
#' Apply a bounded fixed change to goal means
#'
#' Operates on explicit inputs. Invalid contracts raise errors; no network,
#' package installation or database writes occur.
#' @param market Length-two positive numeric market goal means.
#' @param home_away Length-two positive numeric alternative goal means.
#' @param alpha Numeric mixing fraction in `[0, 1]`.
#' @param cap Numeric maximum relative change in `[0, 1)`.
#' @return A length-two positive numeric vector of goal means.
bounded_market_lambdas <- function(market, home_away, alpha, cap) {
  for (v in list(market,home_away)) if (!is.numeric(v) || length(v)!=2L ||
      anyNA(v) || any(!is.finite(v)) || any(v<=0)) stop('Positive paired lambdas required')
  if (length(alpha)!=1L || length(cap)!=1L || anyNA(c(alpha,cap)) ||
      any(!is.finite(c(alpha,cap))) || alpha<0 || alpha>1 || cap<0 || cap>=1) stop('Invalid correction policy')
  market+pmax(-cap*market,pmin(cap*market,alpha*(home_away-market)))
}

# Poisson grid projections used by the existing shape evaluator/coverage rules.
# No outcome inputs. Tail probability is bounded by the supplied tolerance.
#
# `rho` is the Dixon-Coles low-score dependence parameter and is REQUIRED: an
# independent-Poisson grid (rho = 0) understates the draw against a de-vigged
# 1X2 target, so leaving this implicit would let the compressed caliber survive
# by default. Callers that genuinely want independence must pass 0 explicitly.
#' Project Dixon-Coles scores to ordinary and handicap outcomes
#'
#' Operates on explicit inputs. Invalid contracts raise errors; no network,
#' package installation or database writes occur.
#' @param lambda Positive numeric goal mean; home and away pair for score projection.
#' @param handicap Numeric home-goal handicap; applied to home minus away goals.
#' @param tail_tolerance Positive probability tolerance below one for truncating the score grid.
#' @param rho Explicit fixed Dixon-Coles low-score dependence parameter.
#' @return A list containing the score grid and probability/mean diagnostics.
market_score_projection <- function(lambda, handicap, tail_tolerance, rho) {
  g <- dixon_coles_score_grid(lambda[1],lambda[2],handicap,tail_tolerance,rho)$grid
  g$net <- g$home_goals-g$away_goals
  g$outcome <- g$handicap_outcome
  total <- g$home_goals+g$away_goals
  p <- list(lambda_home=lambda[1],lambda_away=lambda[2],
    low_score_dependence_rho=rho,
    finite_mean_total=sum(total*g$probability),finite_mean_net=sum(g$net*g$probability),
    boundary_mass=sum(g$probability[g$home_goals==max(g$home_goals) | g$away_goals==max(g$away_goals)]))
  for(d in c('W','D','L')) p[[d]] <- sum(g$probability[g$outcome==d])
  p$ordinary_W <- sum(g$probability[g$net>0]);p$ordinary_D <- sum(g$probability[g$net==0]);p$ordinary_L <- sum(g$probability[g$net<0])
  for(k in 2:4) {
    p[[paste0('home_ge',k)]] <- sum(g$probability[g$net>=k])
    p[[paste0('away_ge',k)]] <- sum(g$probability[g$net<= -k])
  }
  for(k in 5:6) p[[paste0('total_ge',k)]] <- sum(g$probability[total>=k])
  list(grid=g,fields=p)
}
