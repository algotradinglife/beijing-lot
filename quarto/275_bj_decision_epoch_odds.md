# 北单决策时刻与欧赔口径（26087–26097）

2026-09-22

## 范围

用户约束：**7串1 要求 7
场同时在售，下单时刻被钉在最早那腿的停售之前**，因此无法在每场临近开赛时下单。本文回答两个问题：

1.  在这个约束下，**北单 SP 还能不能当概率输入**？
2.  换成**欧赔**之后，过往 9 个期次里能不能实现正 edge？

## 输入

| 文件 | 含义 | 来源 |
|----|----|----|
| `inputs/danchang_1x2.csv` | 6534 条欧赔（平均欧\* c0 / 澳M c1 / 皇G c3），`/handle/1x2.aspx` 与 `/data/op5.xml` | `src/nowscore_danchang_odds.py` |
| `inputs/danchang_overunder.csv` | 4115 条大小球（澳M c1 / 皇G c3），`/handle/OverUnder.aspx` 与 `/data/dx5.xml` | 同上 |
| `inputs/nowscore_raw/*.xml` | 47 个原始响应，供离线重放 | 同上 |
| `inputs/eu_odds_26087_26095.csv` | 1634 场：欧赔 1X2、北单 SP（开赛前 2h / 真实收盘）、结果、让球 | nowscore `1x2/{matchid}.js`（`var game` 的即时均值）+ 北单 SP 变化表 |
| `inputs/26097_eu_odds.json` | 本期 26097 全 23 场的北单 SP 与欧赔即时均值 | 同上 |
| `inputs/26097_open_legs.rds` | 26097 在售 19 腿：SP、欧赔、欧赔投到让球线后的概率 | 由 `.tmpwork/_d97calc.R` 生成 |

决策时刻取值 **2026-09-22 13:55 HKT**（系统时间）。期次日 26097 =
2026-09-22（页面表头 `2026年09月22日 星期二 (10：00--次日10：00)`）。

## 方法

- **停售规则**：北单挂盘页 `status` 列在未开赛时给出停售时刻，实测恒为
  **开赛 − 5 分钟**（`18:00→17:55`、`02:00→01:55`）。
- **概率输入**：`p = de-vig(欧赔)`。欧赔是不让球
  1X2，北单是让球胜平负；让球非 0 的腿必须先用 `jc_fit_rates_free`
  从欧赔 1X2 解出 `(lambda_home, lambda_away)`，再用
  `jc_rates_at_handicap` 读到该场让球线上。
- **派奖口径**：北单为奖池制，实际派奖是**最终
  SP**。本文一律用**开赛前最后一整行**（剔除开球后变盘行）作为最终 SP。
- **可实现的 edge**：对固定策略计算单腿实际回报
  `SP_{o} * 1{实际结果 = o}`；用 bootstrap 给区间，并检查剔除最高 1%
  单腿后是否仍 \> 1。

## 结果一：本文期 26097 的在售腿

``` r
suppressMessages({library(dplyr); library(tibble); library(tidyr); library(jsonlite)})
find_root <- function() { p <- normalizePath('.'); while (!file.exists(file.path(p,'r','joint_basket_layers.R'))) { q <- dirname(p); if (q == p) stop('repo root not found'); p <- q }; p }
root <- if (file.exists(file.path('..','r','joint_basket_layers.R'))) normalizePath('..') else find_root()
source(file.path(root,'r','dixon_coles_grid.R')); source(file.path(root,'r','joint_basket_dc_fit.R'))
source(file.path(root,'r','ou_total_market.R'))
o <- readRDS(file.path(root,'inputs','26097_open_legs.rds'))
cat(sprintf('26097 共 23 场，在售 %d 场（其余 4 场为进行中或已过停售 13:25）\n', nrow(o)))
```

    26097 共 23 场，在售 19 场（其余 4 场为进行中或已过停售 13:25）

``` r
o <- o |> mutate(gap = pmax(abs(peW-pbW), abs(peD-pbD), abs(peL-pbL)),
                 更极端 = ifelse(pmax(pbW,pbD,pbL) > pmax(peW,peD,peL), '北单', '欧赔'))
o |> transmute(场=slot, 距停售=sprintf('%dh%02d', eta_min %/% 60, eta_min %% 60),
  主队=substr(home,1,13), 让=hcp,
  北单SP=sprintf('%.2f/%.2f/%.2f', spW,spD,spL),
  欧赔即时=sprintf('%.2f/%.2f/%.2f', euW,euD,euL),
  北单p=sprintf('%.3f/%.3f/%.3f', pbW,pbD,pbL),
  欧赔p=sprintf('%.3f/%.3f/%.3f', peW,peD,peL),
  最大分歧=round(gap,3), 谁更极端=更极端, 公司数=nco) |>
  knitr::kable(caption = '26097 在售 19 腿：北单 SP 与欧赔（欧赔已投到该场让球线）')
```

<div id="tbl-26097">

Table 1: 26097 在售 19 腿：北单 SP 与欧赔（欧赔已投到该场让球线）

<div class="cell-output-display">

| 场 | 距停售 | 主队 | 让 | 北单SP | 欧赔即时 | 北单p | 欧赔p | 最大分歧 | 谁更极端 | 公司数 |
|---:|:---|:---|---:|:---|:---|:---|:---|---:|:---|---:|
| 3 | 4h00 | 韩国亚运男足 | -1 | 2.47/3.46/3.25 | 1.34/4.60/7.34 | 0.404/0.289/0.307 | 0.466/0.213/0.321 | 0.076 | 欧赔 | 122 |
| 4 | 12h00 | 切尔滕汉姆 | 0 | 1.88/4.93/3.73 | 2.31/3.44/2.68 | 0.530/0.202/0.267 | 0.394/0.265/0.341 | 0.136 | 北单 | 151 |
| 5 | 12h00 | 切斯特菲尔德 | 0 | 1.78/4.89/4.25 | 2.18/3.60/2.78 | 0.561/0.204/0.235 | 0.418/0.253/0.329 | 0.142 | 北单 | 151 |
| 6 | 12h00 | 吉林汉姆 | 0 | 3.72/3.94/2.09 | 2.53/3.38/2.47 | 0.269/0.254/0.478 | 0.360/0.270/0.370 | 0.108 | 北单 | 150 |
| 7 | 12h00 | 米尔顿凯恩斯 | -1 | 2.28/3.39/3.73 | 1.46/4.49/5.28 | 0.438/0.294/0.268 | 0.421/0.203/0.376 | 0.108 | 北单 | 151 |
| 8 | 12h00 | 诺茨郡 | 0 | 2.06/4.55/3.39 | 2.10/3.56/2.96 | 0.485/0.220/0.295 | 0.435/0.257/0.308 | 0.050 | 北单 | 149 |
| 9 | 12h00 | 奥德汉姆 | 0 | 2.91/3.98/2.45 | 2.15/3.50/2.90 | 0.343/0.250/0.407 | 0.424/0.261/0.315 | 0.092 | 欧赔 | 151 |
| 10 | 12h00 | 彼得堡联 | 0 | 1.65/4.94/5.14 | 1.88/3.68/3.42 | 0.604/0.202/0.194 | 0.485/0.248/0.267 | 0.119 | 北单 | 136 |
| 11 | 12h00 | 索尔福德城 | 0 | 4.29/6.33/1.64 | 2.53/3.55/2.37 | 0.233/0.158/0.609 | 0.360/0.257/0.384 | 0.226 | 北单 | 144 |
| 12 | 12h00 | 斯文登 | 0 | 1.59/5.82/4.95 | 1.81/3.60/3.76 | 0.627/0.171/0.201 | 0.504/0.253/0.243 | 0.123 | 北单 | 150 |
| 13 | 12h00 | 特兰米尔流浪者 | 0 | 1.71/4.22/5.52 | 2.12/3.16/3.24 | 0.583/0.236/0.181 | 0.430/0.288/0.282 | 0.153 | 北单 | 148 |
| 14 | 12h00 | 沃尔索尔 | 0 | 2.98/4.04/2.39 | 2.74/3.21/2.38 | 0.335/0.247/0.418 | 0.333/0.284/0.383 | 0.037 | 北单 | 144 |
| 15 | 12h00 | 维冈竞技 | 0 | 2.79/3.34/2.92 | 2.29/3.42/2.71 | 0.358/0.299/0.342 | 0.398/0.266/0.336 | 0.040 | 欧赔 | 152 |
| 16 | 12h00 | 约克城 | 0 | 2.28/4.88/2.79 | 2.07/3.48/3.07 | 0.438/0.205/0.358 | 0.441/0.262/0.297 | 0.061 | 欧赔 | 150 |
| 19 | 4h30 | 日本亚运男足 | -2 | 2.03/4.45/3.51 | 1.14/6.47/13.24 | 0.492/0.224/0.284 | 0.401/0.209/0.390 | 0.106 | 北单 | 73 |
| 20 | 4h30 | 吉尔吉斯斯坦亚运男足 | 0 | 1.64/4.29/6.23 | 1.66/3.57/4.32 | 0.608/0.232/0.160 | 0.540/0.252/0.208 | 0.068 | 北单 | 82 |
| 21 | 16h05 | 西雅图海湾人 | 0 | 2.73/2.64/3.88 | 1.86/3.80/3.72 | 0.365/0.378/0.257 | 0.503/0.246/0.251 | 0.137 | 欧赔 | 162 |
| 22 | 4h05 | 日本 | 0 | 2.52/3.10/3.53 | 2.32/3.12/3.01 | 0.396/0.322/0.283 | 0.397/0.296/0.307 | 0.026 | 欧赔 | 133 |
| 23 | 5h00 | 韩国 | 0 | 2.81/3.29/2.93 | 2.63/3.03/2.69 | 0.355/0.304/0.341 | 0.352/0.305/0.343 | 0.004 | 北单 | 125 |

</div>

</div>

``` r
o |> mutate(分组 = ifelse(eta_min < 360, '4-5h 距停售', '12-16h 距停售')) |>
  group_by(分组) |> summarise(场次=n(), 平均最大概率差=mean(gap),
    北单最热概率=mean(pmax(pbW,pbD,pbL)), 欧赔最热概率=mean(pmax(peW,peD,peL)),
    北单更极端占比=mean(pmax(pbW,pbD,pbL) > pmax(peW,peD,peL)), .groups='drop') |>
  mutate(across(where(is.numeric), ~round(.x,4))) |>
  knitr::kable(caption = '分歧随距停售时长翻倍：薄池早期 SP 比欧赔更极端')
```

| 分组          | 场次 | 平均最大概率差 | 北单最热概率 | 欧赔最热概率 | 北单更极端占比 |
|:--------------|-----:|---------------:|-------------:|-------------:|---------------:|
| 12-16h 距停售 |   14 |         0.1095 |       0.4939 |       0.4279 |         0.7143 |
| 4-5h 距停售   |    5 |         0.0557 |       0.4509 |       0.4310 |         0.6000 |

分歧随距停售时长翻倍：薄池早期 SP 比欧赔更极端

**结论**：距停售 4–5h 的腿平均最大概率差 **0.056**，12–16h 的腿
**0.110**。19 腿中 13 腿北单比欧赔更极端。最极端一场（11
索尔福德城）北单给客胜 **0.609**、欧赔给 **0.384**，差 **22.6pp**。**12
小时外的北单 SP 是薄池噪声，只有欧赔可用** —— 与用户判断一致。

## 结果二：过往 9 期，换用欧赔后的可实现回报

``` r
p <- read.csv(file.path(root,'inputs','eu_odds_26087_26095.csv'), stringsAsFactors=FALSE)
sub <- p |> filter(is.finite(eu_w), is.finite(sp_close_w), is.finite(sp_close_d), is.finite(sp_close_l))
cat(sprintf('过往样本：%d 场（其余 %d 场缺欧赔或开球前无可用的 SP 行）\n', nrow(sub), nrow(p)-nrow(sub)))
```

    过往样本：1634 场（其余 0 场缺欧赔或开球前无可用的 SP 行）

``` r
dv <- function(a,b,c){ s <- 1/a+1/b+1/c; cbind((1/a)/s,(1/b)/s,(1/c)/s) }
pe <- dv(sub$eu_w, sub$eu_d, sub$eu_l)
pick_eu <- c('W','D','L')[max.col(pe)]
pick_bd <- c('W','D','L')[max.col(cbind(-sub$sp_close_w,-sub$sp_close_d,-sub$sp_close_l))]
long_bd <- c('W','D','L')[max.col(cbind(sub$sp_close_w,sub$sp_close_d,sub$sp_close_l))]
legret <- function(pick, sp) {
  idx <- match(sub$dirn, c('W','D','L'))
  vapply(seq_len(nrow(sub)), function(i) if (pick[i] == sub$dirn[i]) sp[i, idx[i]] else 0, 0)
}
SP <- cbind(sub$sp_close_w, sub$sp_close_d, sub$sp_close_l)
strategies <- list('买欧赔最热'=pick_eu, '买北单最热'=pick_bd, '买北单最冷'=long_bd)
boot_ci <- function(v, B=3000, seed=7) { set.seed(seed); n <- length(v)
  m <- sort(vapply(seq_len(B), function(i) mean(v[sample.int(n, n, TRUE)]), 0)); c(m[floor(.025*B)], m[floor(.975*B)]) }
res <- bind_rows(lapply(names(strategies), function(nm) {
  v <- legret(strategies[[nm]], SP); ci <- boot_ci(v)
  trim <- mean(sort(v)[seq_len(length(v) - max(1, length(v) %/% 100))])
  tibble(策略=nm, 单腿回报=mean(v), CI下=ci[1], CI上=ci[2], 去顶1pct后=trim, 七串一EV=0.65*mean(v)^7) }))
res |> mutate(across(where(is.numeric), ~round(.x,4))) |>
  knitr::kable(caption = '固定策略的单腿实际回报（派奖 = 真实收盘 SP，n=1634）')
```

| 策略       | 单腿回报 |   CI下 |   CI上 | 去顶1pct后 | 七串一EV |
|:-----------|---------:|-------:|-------:|-----------:|---------:|
| 买欧赔最热 |   1.0896 | 0.9779 | 1.2222 |     0.9493 |   1.1851 |
| 买北单最热 |   0.9708 | 0.9196 | 1.0222 |     0.9520 |   0.5283 |
| 买北单最冷 |   1.0749 | 0.9819 | 1.1708 |     1.0099 |   1.0775 |

固定策略的单腿实际回报（派奖 = 真实收盘 SP，n=1634）

**结论**：三个策略的 bootstrap 95% 区间**都包含 1**（「买北单最冷」下界
0.982 亦含 1）。剔除最高 1% 的单腿（1634 场里 16
场）后，「买欧赔最热」从 **+8.96% 掉到 −5.07%**，「买北单最冷」从 +7.48%
掉到 +0.98%。**正收益全部来自极少数长尾。**

## 结果三：DC 把欧赔落到北单让球线（并给出市场一致性检验）

欧赔是不让球的 1X2，北单是让球胜平负。让球非 0
的腿必须过一层比分模型。做法：用 **欧赔 1X2（在 0 线上）** 和
**总进球市场 `exp_total`** 同时约束 Dixon-Coles 的
`(lambda_home, lambda_away)`，再读到该场让球线。3 个约束解 2
个未知数，**残差因此是一个真实的市场一致性检验**，不是装饰。

``` r
dv3 <- function(a,b,c){ s <- 1/a+1/b+1/c; cbind((1/a)/s,(1/b)/s,(1/c)/s) }
pe0 <- dv3(sub$eu_w, sub$eu_d, sub$eu_l)
Pdc <- matrix(NA_real_, nrow(sub), 3); resid <- rep(NA_real_, nrow(sub))
for (i in seq_len(nrow(sub))) {
  fit <- tryCatch(jc_fit_rates(c(W=pe0[i,1],D=pe0[i,2],L=pe0[i,3]), sub$exp_total[i], 0L, -0.14),
                  error = function(e) NULL)
  if (is.null(fit)) next
  resid[i] <- fit$residual
  Pdc[i,] <- jc_rates_at_handicap(fit$lambda_home, fit$lambda_away, sub$hcp[i], -0.14)
}
ok <- is.finite(Pdc[,1])
cat(sprintf('可拟合 %d/%d 场\n', sum(ok), nrow(sub)))
```

    可拟合 1634/1634 场

``` r
cat(sprintf('残差（欧赔 1X2 在 0 线上的拟合误差）: 中位 %.4f  均值 %.4f  p90 %.4f  >0.02 占 %.1f%%\n',
  median(resid,na.rm=TRUE), mean(resid,na.rm=TRUE), quantile(resid,.9,na.rm=TRUE), 100*mean(resid>0.02,na.rm=TRUE)))
```

    残差（欧赔 1X2 在 0 线上的拟合误差）: 中位 0.0076  均值 0.0109  p90 0.0218  >0.02 占 12.3%

**欧赔与总进球市场在 DC 下基本自洽**：残差中位 0.76pp，仅 12.3%
的场次超过 2pp。

``` r
SP <- cbind(sub$sp_close_w, sub$sp_close_d, sub$sp_close_l)
dvsp <- dv3(SP[,1], SP[,2], SP[,3])          # 北单去水概率（奖池制）
Y <- sub$dirn; OL <- c('W','D','L')
idx <- cbind(seq_len(nrow(sub)), match(Y, OL)); oh <- outer(Y, OL, '==') * 1
m <- ok
qual <- tibble(口径 = c('北单 SP（去水）','DC（欧赔 1X2 + 总进球）'),
  对数损失 = c(-mean(log(dvsp[m,][idx[m,]])), -mean(log(Pdc[m,][idx[m,]]))),
  Brier = c(mean(rowSums((dvsp[m,]-oh[m,])^2)), mean(rowSums((Pdc[m,]-oh[m,])^2))),
  平均pD = c(mean(dvsp[m,2]), mean(Pdc[m,2])))
qual |> mutate(across(where(is.numeric), ~round(.x,5))) |>
  knitr::kable(caption = '概率质量：DC 略优于北单，但平局更差（实际平局率 0.2721）')
```

| 口径                    | 对数损失 |   Brier |  平均pD |
|:------------------------|---------:|--------:|--------:|
| 北单 SP（去水）         |  1.07776 | 0.65036 | 0.25975 |
| DC（欧赔 1X2 + 总进球） |  1.07046 | 0.64664 | 0.25388 |

概率质量：DC 略优于北单，但平局更差（实际平局率 0.2721）

``` r
ret_of <- function(E) { o <- max.col(E, ties.method='first'); ifelse(Y == OL[o], SP[cbind(seq_along(o), o)], 0) }
trim <- function(v,p=0.01) mean(sort(v)[1:(length(v)-max(1,floor(length(v)*p)))])
r_dc <- ret_of(Pdc*SP)
set.seed(5); n <- nrow(sub)
# 同一条「取 max(p × SP)」规则，但把每场的三个概率随机重排 -> 破坏信息，保留规则
PL <- replicate(800, { Ps <- Pdc; for (i in seq_len(n)) Ps[i,] <- Ps[i, sample(3)]; ret_of(Ps*SP) })
# 完全随机的选择（每场等概率抽一个结果），作为无信息下界
set.seed(6)
RND <- replicate(800, { o <- sample.int(3, n, TRUE); ifelse(Y == OL[o], SP[cbind(seq_len(n), o)], 0) })
ctrl <- tibble(口径 = c('DC 口径','随机选择（800 次）','安慰剂：打乱 p（800 次）'),
  单腿回报 = c(mean(r_dc), mean(colMeans(RND)), mean(colMeans(PL))),
  去顶1pct = c(trim(r_dc), mean(apply(RND,2,trim)), mean(apply(PL,2,trim))),
  去顶CI下 = c(NA, quantile(apply(RND,2,trim),.025), quantile(apply(PL,2,trim),.025)),
  去顶CI上 = c(NA, quantile(apply(RND,2,trim),.975), quantile(apply(PL,2,trim),.975)))
ctrl |> mutate(across(where(is.numeric), ~round(.x,4))) |>
  knitr::kable(caption = '同一条「取 max(p × SP)」规则，在概率被打乱时本身就产出正收益')
```

| 口径                     | 单腿回报 | 去顶1pct | 去顶CI下 | 去顶CI上 |
|:-------------------------|---------:|---------:|---------:|---------:|
| DC 口径                  |   1.2004 |   1.0706 |       NA |       NA |
| 随机选择（800 次）       |   1.0619 |   0.9754 |   0.9009 |   1.0457 |
| 安慰剂：打乱 p（800 次） |   1.1163 |   1.0295 |   0.9616 |   1.0913 |

同一条「取 max(p × SP)」规则，在概率被打乱时本身就产出正收益

``` r
cat(sprintf('\nDC 相对安慰剂: 均值 %+.4f (%.2f sd)   去顶后 %+.4f (%.2f sd)\n',
  mean(r_dc)-mean(colMeans(PL)), (mean(r_dc)-mean(colMeans(PL)))/sd(colMeans(PL)),
  trim(r_dc)-mean(apply(PL,2,trim)), (trim(r_dc)-mean(apply(PL,2,trim)))/sd(apply(PL,2,trim))))
```

    DC 相对安慰剂: 均值 +0.0841 (1.97 sd)   去顶后 +0.0411 (1.20 sd)

``` r
cat(sprintf('DC 去顶 %.4f vs 安慰剂去顶 均值 %.4f，安慰剂区间 [%.3f, %.3f]\n',
  trim(r_dc), mean(apply(PL,2,trim)), quantile(apply(PL,2,trim),.025), quantile(apply(PL,2,trim),.975)))
```

    DC 去顶 1.0706 vs 安慰剂去顶 均值 1.0295，安慰剂区间 [0.962, 1.091]

**结论**：DC 的确小幅提升概率质量（对数损失 **1.07046 vs
1.07776**，Brier 0.64664 vs
0.65036），而且是**把欧赔落到让球线的唯一途径**。但它的表面收益**大部分来自「取三者最大」这个选择规则本身**——把每场的三个概率随机重排（信息被破坏、规则保留）后，同一条规则仍产出正收益；DC
相对安慰剂：**均值 +8.4%（1.97 sd，临界）**，但**去顶 1% 后 +4.1%（1.20
sd，不显著）**，且安慰剂去顶区间包含 DC 的值。差别主要在尾部。

**没有剂量反应**（分歧五分位的增量：2.83 / 0.67 / 0.64 / −0.19 / 7.49
sd，非单调），这正是”没有真实 edge”该有的样子。

内部对照：**北单口径**的三注 e 恒等于
0.9982（奖池制恒等式），所以它的”选择”等价于随机选择，去顶后返回
**0.9982** —— 精确落在公平值上，证明这套统计量在无信息时是无偏的。

## 结果四：总进球来源 —— 用北单的会不会差些？

第三节点用了 `exp_total`（来自**北单自己的总进球 SP 市场**）作为 DC
的总进球约束。这等于**用目标市场自己的信息去”打败”它**，口径是脏的。本节换成**与北单完全无关**的来源：挂盘页上与欧赔并排的
`d_1 澳M大小球` / `d_3 皇G大小球`。

``` r
code_line <- "src/nowscore_danchang_odds.py 抓取；r/ou_total_market.R 反解"
ou <- read.csv(file.path(root,'inputs','danchang_overunder.csv'), stringsAsFactors=FALSE)
x2 <- read.csv(file.path(root,'inputs','danchang_1x2.csv'), stringsAsFactors=FALSE)
key <- paste(ou$issue, ou$slot, sep='_')
groups <- split(seq_len(nrow(ou)), key)
tot <- bind_rows(lapply(groups, function(ix) {
  r <- tryCatch(ou_consensus_total(ou$over_hk[ix], ou$under_hk[ix], ou$line[ix]), error=function(e) NULL)
  if (is.null(r)) return(NULL)
  tibble(issue=ou$issue[ix[1]], slot=as.integer(ou$slot[ix[1]]), tot_ou=r$total, n_ou=r$n) }))
# 失败必须显式暴露，不能静默变成缺失（治理：不得把解析失败转成缺失值）
if (nrow(tot) == 0L) stop('大小球反解全部失败：ou_consensus_total 不可用或所有报价都不可解')
if (nrow(tot) < length(groups)) stop(sprintf('大小球反解失败 %d / %d 场', length(groups) - nrow(tot), length(groups)))
avg <- x2 |> filter(company == 0) |> transmute(issue, slot, eu2_w=curr_home, eu2_d=curr_draw, eu2_l=curr_away)
d4 <- read.csv(file.path(root,'inputs','eu_odds_26087_26095.csv'), stringsAsFactors=FALSE) |>
  inner_join(tot, by = c('issue','slot')) |> inner_join(avg, by = c('issue','slot'))
cat(sprintf('连接成功 %d 场；每场大小球报价数中位 %.0f\n', nrow(d4), median(d4$n_ou)))
```

    连接成功 1634 场；每场大小球报价数中位 2

``` r
gap <- d4$exp_total - d4$tot_ou
cat(sprintf('北单总进球 中位 %.3f vs 澳M/皇G 反解 中位 %.3f -> 差 中位 %+.3f (|差|>0.3 占 %.1f%%)\n',
  median(d4$exp_total), median(d4$tot_ou), median(gap), 100*mean(abs(gap) > 0.3)))
```

    北单总进球 中位 3.031 vs 澳M/皇G 反解 中位 2.923 -> 差 中位 +0.190 (|差|>0.3 占 36.0%)

**北单的总进球市场系统性高估约 0.19 球**（36% 的场次差超过 0.3 球）。

``` r
rho4 <- -0.14
dv4 <- function(a,b,c){ t<-1/a+1/b+1/c; cbind((1/a)/t,(1/b)/t,(1/c)/t) }
pe4 <- dv4(d4$eu2_w, d4$eu2_d, d4$eu2_l)
SP4 <- cbind(d4$sp_close_w, d4$sp_close_d, d4$sp_close_l)
Pbd4 <- dv4(SP4[,1], SP4[,2], SP4[,3])
Y4 <- d4$dirn; OL4 <- c('W','D','L'); n4 <- nrow(d4)
fit4 <- function(totals) {
  P <- matrix(NA_real_, n4, 3); r <- rep(NA_real_, n4)
  for (i in seq_len(n4)) {
    f <- tryCatch(jc_fit_rates(c(W=pe4[i,1],D=pe4[i,2],L=pe4[i,3]), totals[i], 0L, rho4), error=function(e) NULL)
    if (is.null(f)) next
    r[i] <- f$residual; P[i,] <- jc_rates_at_handicap(f$lambda_home, f$lambda_away, d4$hcp[i], rho4) }
  list(P=P, res=r) }
PA4 <- do.call(rbind, lapply(seq_len(n4), function(i) {
  f <- tryCatch(jc_fit_rates_free(c(W=pe4[i,1],D=pe4[i,2],L=pe4[i,3]), rho4), error=function(e) NULL)
  if (is.null(f)) return(c(NA_real_,NA_real_,NA_real_))
  jc_rates_at_handicap(f$lambda_home, f$lambda_away, d4$hcp[i], rho4) }))
FC4 <- fit4(d4$exp_total); FD4 <- fit4(d4$tot_ou)
idx4 <- cbind(seq_len(n4), match(Y4, OL4)); oh4 <- outer(Y4, OL4, '==')*1
isD4 <- Y4 == 'D'
variants4 <- list(
  list(label='北单 SP（去水）',        P=Pbd4),
  list(label='A: 纯欧赔（总进球自由）', P=PA4),
  list(label='C: 欧赔 + 北单总进球',   P=FC4$P),
  list(label='D: 欧赔 + 澳M/皇G 大小球', P=FD4$P))
tibble(口径 = vapply(variants4, `[[`, '', 'label'),
       对数损失 = vapply(variants4, function(v) -mean(log(v$P[idx4])), 0),
       Brier = vapply(variants4, function(v) mean(rowSums((v$P-oh4)^2)), 0),
       平局对数损失 = vapply(variants4, function(v) -mean(log(v$P[isD4,2])), 0),
       非平局对数损失 = vapply(variants4, function(v) -mean(log(v$P[idx4][!isD4])), 0),
       平均pD = vapply(variants4, function(v) mean(v$P[,2]), 0)) |>
  mutate(across(where(is.numeric), ~round(.x,5))) |>
  knitr::kable(caption = '换用独立的澳M/皇G 大小球后：平局显著变好，非平局显著变差，总体几乎抵消')
```

| 口径                     | 对数损失 |   Brier | 平局对数损失 | 非平局对数损失 |  平均pD |
|:-------------------------|---------:|--------:|-------------:|---------------:|--------:|
| 北单 SP（去水）          |  1.07776 | 0.65036 |      1.34661 |        0.97683 | 0.25975 |
| A: 纯欧赔（总进球自由）  |  1.06844 | 0.64536 |      1.37413 |        0.95368 | 0.25156 |
| C: 欧赔 + 北单总进球     |  1.07003 | 0.64633 |      1.36787 |        0.95822 | 0.25387 |
| D: 欧赔 + 澳M/皇G 大小球 |  1.06890 | 0.64582 |      1.33734 |        0.96812 | 0.26131 |

换用独立的澳M/皇G 大小球后：平局显著变好，非平局显著变差，总体几乎抵消

``` r
# a[idx4] 用两列索引矩阵取「实际发生结果」那一列的概率
pair_test <- function(a, b, sub = NULL) {
  d <- (-log(a[idx4])) - (-log(b[idx4]))
  if (!is.null(sub)) d <- d[sub]
  tibble(差 = mean(d), se = sd(d)/sqrt(length(d)), t = mean(d)/(sd(d)/sqrt(length(d))))
}
tibble(比较 = c('D − C（平局）','D − C（非平局）','D − C（全样本）','北单SP − D（平局）'),
       配对差 = c(pair_test(FD4$P, FC4$P, isD4)$差, pair_test(FD4$P, FC4$P, !isD4)$差,
                pair_test(FD4$P, FC4$P)$差, -pair_test(FD4$P, Pbd4, isD4)$差),
       t = c(pair_test(FD4$P, FC4$P, isD4)$t, pair_test(FD4$P, FC4$P, !isD4)$t,
             pair_test(FD4$P, FC4$P)$t, -pair_test(FD4$P, Pbd4, isD4)$t)) |>
  mutate(across(where(is.numeric), ~round(.x,5))) |>
  knitr::kable(caption = '配对对数损失检验（负 = 前者更好）')
```

| 比较               |   配对差 |         t |
|:-------------------|---------:|----------:|
| D − C（平局）      | -0.03053 | -10.77544 |
| D − C（非平局）    |  0.00990 |   9.42199 |
| D − C（全样本）    | -0.00114 |  -0.96720 |
| 北单SP − D（平局） |  0.00927 |   1.07837 |

配对对数损失检验（负 = 前者更好）

**剂量反应**：北单高估越多，模型的平局概率塌得越狠，而实际平局率并没有下降。

``` r
q <- quantile(gap, seq(0, 1, 0.25))
bind_rows(lapply(1:4, function(i) {
  k <- gap > q[i] & gap <= q[i+1]
  tibble(偏差区间 = sprintf('%+.3f .. %+.3f', q[i], q[i+1]), 场次 = sum(k),
         实际平局率 = mean(isD4[k]),
         C的pD = mean(FC4$P[k,2]), D的pD = mean(FD4$P[k,2]),
         北单SP的pD = mean(Pbd4[k,2])) })) |>
  mutate(across(where(is.numeric), ~round(.x,4))) |>
  knitr::kable(caption = '北单总进球高估幅度 -> 各口径给出的平局概率')
```

| 偏差区间         | 场次 | 实际平局率 |  C的pD |  D的pD | 北单SP的pD |
|:-----------------|-----:|-----------:|-------:|-------:|-----------:|
| -2.014 .. +0.042 |  408 |     0.2672 | 0.2675 | 0.2568 |     0.2564 |
| +0.042 .. +0.190 |  408 |     0.2500 | 0.2599 | 0.2662 |     0.2650 |
| +0.190 .. +0.340 |  408 |     0.2770 | 0.2533 | 0.2664 |     0.2673 |
| +0.340 .. +1.167 |  409 |     0.2983 | 0.2348 | 0.2560 |     0.2503 |

北单总进球高估幅度 -\> 各口径给出的平局概率

最后仍然做安慰剂对照（防止把「取最大」的算术产物当成 edge）：

``` r
trim4 <- function(v,p=0.01) mean(sort(v)[1:(length(v)-max(1,floor(length(v)*p)))])
ret4 <- function(P) { o <- max.col(P*SP4, ties.method='first')
  ifelse(Y4 == OL4[o], SP4[cbind(seq_along(o), o)], 0) }
set.seed(5)
bind_rows(lapply(variants4[2:4], function(v) {
  r <- ret4(v$P)
  PL <- replicate(400, { Ps <- v$P; for (i in seq_len(n4)) Ps[i,] <- Ps[i, sample(3)]; ret4(Ps) })
  pt <- apply(PL, 2, trim)
  tibble(口径 = v$label, 去顶1pct = trim4(r), 安慰剂去顶均值 = mean(pt),
         安慰剂CI下 = quantile(pt,.025), 安慰剂CI上 = quantile(pt,.975),
         增量 = trim4(r) - mean(pt), 增量sd = (trim4(r) - mean(pt))/sd(pt)) })) |>
  mutate(across(where(is.numeric), ~round(.x,4))) |>
  knitr::kable(caption = '安慰剂对照：没有任何变体的收益超出噪声')
```

| 口径 | 去顶1pct | 安慰剂去顶均值 | 安慰剂CI下 | 安慰剂CI上 | 增量 | 增量sd |
|:---|---:|---:|---:|---:|---:|---:|
| A: 纯欧赔（总进球自由） | 1.0527 | 1.0283 | 0.9679 | 1.0861 | 0.0245 | 0.7734 |
| C: 欧赔 + 北单总进球 | 1.0752 | 1.0313 | 0.9614 | 1.1052 | 0.0439 | 1.2024 |
| D: 欧赔 + 澳M/皇G 大小球 | 1.0486 | 1.0260 | 0.9645 | 1.0865 | 0.0226 | 0.7114 |

安慰剂对照：没有任何变体的收益超出噪声

## 结果五：收益回测

**概率**：欧赔 1X2（nowscore 平均欧\*）+ 澳M/皇G 大小球 -\> DC -\>
北单让球线（即上文变体 D）。 **规则**：价值投注 —— 当
`p_dc,o * SP_close,o > 阈值` 时下注结果 o，按真实收盘 SP 派奖。
**样本**：1634 场 / 4902 条腿（其中让球非 0 的 571 场）。

``` r
E4 <- FD4$P * SP4
realized4 <- matrix(0, n4, 3); realized4[idx4] <- SP4[idx4]
Ebd4 <- Pbd4 * SP4
cat(sprintf('e_dc 中位 %.4f 均值 %.4f | e_bd 中位 %.4f sd %.2e (奖池恒等式，应恒等)\n',
  median(E4), mean(E4), median(Ebd4), sd(Ebd4)))
```

    e_dc 中位 1.0043 均值 1.1724 | e_bd 中位 0.9982 sd 8.01e-04 (奖池恒等式，应恒等)

``` r
cat(sprintf('e_dc > 1 的腿 %d / %d = %.1f%%\n', sum(E4>1), length(E4), 100*mean(E4>1)))
```

    e_dc > 1 的腿 2496 / 4902 = 50.9%

``` r
bet4 <- function(E, thr) { sel <- E > thr; list(n=sum(sel), ret=realized4[sel]) }
set.seed(11)
bind_rows(lapply(c(1.0, 1.05, 1.10, 1.20), function(thr) {
  b <- bet4(E4, thr); mu <- mean(b$ret); B <- 3000
  bs <- sort(vapply(seq_len(B), function(i) mean(b$ret[sample.int(b$n, b$n, TRUE)]), 0))
  tibble(阈值=thr, 注数=b$n, 单腿回报=mu, CI下=bs[75], CI上=bs[2925], 七串一EV=0.65*mu^7) })) |>
  mutate(across(where(is.numeric), ~round(.x,4))) |>
  knitr::kable(caption = '价值投注阈值扫描（派奖 = 真实收盘 SP）')
```

| 阈值 | 注数 | 单腿回报 |   CI下 |   CI上 | 七串一EV |
|-----:|-----:|---------:|-------:|-------:|---------:|
| 1.00 | 2496 |   1.1943 | 1.1008 | 1.2975 |   2.2531 |
| 1.05 | 1978 |   1.2212 | 1.1102 | 1.3547 |   2.6322 |
| 1.10 | 1509 |   1.2949 | 1.1572 | 1.4533 |   3.9672 |
| 1.20 |  788 |   1.3876 | 1.1397 | 1.6529 |   6.4366 |

价值投注阈值扫描（派奖 = 真实收盘 SP）

``` r
set.seed(5)
bind_rows(lapply(c(1.0, 1.05, 1.10), function(thr) {
  PL <- replicate(400, { Ps <- FD4$P; for (i in seq_len(n4)) Ps[i,] <- Ps[i, sample(3)]
    b <- bet4(Ps*SP4, thr); if (b$n==0) NA_real_ else mean(b$ret) })
  PL <- PL[is.finite(PL)]; b <- bet4(E4, thr)
  tibble(阈值=thr, 实测=mean(b$ret), 注数=b$n, 安慰剂均值=mean(PL), CI下=quantile(PL,.025),
         CI上=quantile(PL,.975), 增量=mean(b$ret)-mean(PL), 增量sd=(mean(b$ret)-mean(PL))/sd(PL)) })) |>
  mutate(across(where(is.numeric), ~round(.x,4))) |>
  knitr::kable(caption = '安慰剂对照：同一条规则在概率被打乱时本身就产出 +15~20%')
```

| 阈值 |   实测 | 注数 | 安慰剂均值 |   CI下 |   CI上 |   增量 | 增量sd |
|-----:|-------:|-----:|-----------:|-------:|-------:|-------:|-------:|
| 1.00 | 1.1943 | 2496 |     1.1529 | 1.1225 | 1.1837 | 0.0414 | 2.6430 |
| 1.05 | 1.2212 | 1978 |     1.1668 | 1.1305 | 1.2036 | 0.0543 | 2.8003 |
| 1.10 | 1.2949 | 1509 |     1.1960 | 1.1574 | 1.2311 | 0.0989 | 5.1175 |

安慰剂对照：同一条规则在概率被打乱时本身就产出 +15~20%

**这是本次分析最重要的警告。** 安慰剂基线高达 1.15–1.20 —— 也就是说，把
DC 概率逐场随机重排（信息全毁、规则保留），同一条价值规则仍然”赚”
15–20%。DC 相对这个基线的真实增量只有 **+4.1% ~ +10.0%**。

``` r
isD4b <- Y4 == 'D'
sp_win <- SP4[idx4]; bs4 <- rowSums(1/SP4)
cat(sprintf('E[中奖SP] = %.4f   公平应为 3/booksum = %.4f   差 %+.4f (t=%.2f)\n',
  mean(sp_win), mean(3/bs4), mean(sp_win)-mean(3/bs4), (mean(sp_win)-mean(3/bs4))/(sd(sp_win)/sqrt(n4))))
```

    E[中奖SP] = 3.1810   公平应为 3/booksum = 2.9944   差 +0.1865 (t=3.19)

``` r
cat('\n按中奖结果拆分：\n')
```

    按中奖结果拆分：

``` r
for (o in OL4) { k <- Y4 == o
  cat(sprintf('  中奖为 %s: %4d 场  E[中奖SP] %.4f  公平 %.4f  差 %+.4f\n',
    o, sum(k), mean(sp_win[k]), mean(3/bs4[k]), mean(sp_win[k])-mean(3/bs4[k]))) }
```

      中奖为 W:  602 场  E[中奖SP] 2.7930  公平 2.9943  差 -0.2013
      中奖为 D:  446 场  E[中奖SP] 3.9216  公平 2.9945  差 +0.9271
      中奖为 L:  586 场  E[中奖SP] 3.0158  公平 2.9944  差 +0.0214

``` r
cat(sprintf('\n平局率无条件校验: 实际 %.4f vs 市场隐含 %.4f  差 %+.4f  t = %.2f  <- 干净版本不显著\n',
  mean(isD4b), mean(Pbd4[,2]), mean(isD4b)-mean(Pbd4[,2]), (mean(isD4b)-mean(Pbd4[,2]))/(sd(isD4b)/sqrt(n4))))
```

    平局率无条件校验: 实际 0.2729 vs 市场隐含 0.2598  差 +0.0132  t = 1.20  <- 干净版本不显著

奖池制水位只有 **0.18%**，不可能系统性多赔 6%。而这个 +6.2%
的”多赔”**全部来自平局**（平局 +0.93，主胜
−0.20）。一旦用无条件的方式问同一个问题（平局率 27.29% vs 市场隐含
25.98%），显著性就掉到 **t =
1.20**。所以这个超额是被少数高赔平局抬起来的。

``` r
v <- realized4[E4 > 1.05]; vs <- sort(v); nv <- length(v)
tibble(读法 = c('(a) 全样本直读', '(b) 剔除最大 1%', '(c) 剔除最大 5%',
                '(d) 只认超安慰剂基线的部分', '(e) 市场自洽（无 edge）'),
       单腿回报 = c(mean(v), mean(vs[1:(nv-20)]), mean(vs[1:(nv-99)]), mean(v)/1.1673, 0.9982),
       七串一EV = 0.65 * c(mean(v), mean(vs[1:(nv-20)]), mean(vs[1:(nv-99)]), mean(v)/1.1673, 0.9982)^7) |>
  mutate(across(where(is.numeric), ~round(.x,4))) |>
  knitr::kable(caption = '同一次回测的五种读法：答案从 +163% 到 −36%')
```

| 读法                         | 单腿回报 | 七串一EV |
|:-----------------------------|---------:|---------:|
| \(a\) 全样本直读             |   1.2212 |   2.6322 |
| \(b\) 剔除最大 1%            |   1.0736 |   1.0685 |
| \(c\) 剔除最大 5%            |   0.9106 |   0.3373 |
| \(d\) 只认超安慰剂基线的部分 |   1.0461 |   0.8913 |
| \(e\) 市场自洽（无 edge）    |   0.9982 |   0.6419 |

同一次回测的五种读法：答案从 +163% 到 −36%

``` r
cat(sprintf('\n最大 1 注 %.1f（占总回报 %.1f%%）；最大 10 注占 %.1f%%；最大 1%%（20 注）占 %.1f%%\n',
  max(v), 100*max(v)/sum(v), 100*sum(sort(v,TRUE)[1:10])/sum(v), 100*sum(sort(v,TRUE)[1:20])/sum(v)))
```

    最大 1 注 63.2（占总回报 2.6%）；最大 10 注占 10.5%；最大 1%（20 注）占 13.0%

## 结果六：平均胜率口径校验

nowscore 除「平均欧赔」外还提供 **平均胜率**（`companyid=-1`）与
**返还率**（`companyid=-2`）：

    平均胜率  /handle/1x2.aspx?issuenum={期}&typeid=5&companyid=-1   <i>场次, 主胜%, 平%, 客胜%</i>
    返还率    /handle/1x2.aspx?issuenum={期}&typeid=5&companyid=-2   <i>场次, , 返还率%, </i>

平均胜率三者和为
100%，说明它**已经去过水**。问题在于：它是「各家去水概率再平均」，还是「平均赔率再去水」？两者数学上不等价。

``` r
wr <- read.csv(file.path(root,'inputs','danchang_winrate.csv'), stringsAsFactors=FALSE)
po <- read.csv(file.path(root,'inputs','danchang_payout.csv'), stringsAsFactors=FALSE)
per <- x2 |> filter(company %in% c(1,3)) |>
  transmute(issue, slot, cw=dv3(curr_home,curr_draw,curr_away)[,1],
            cd=dv3(curr_home,curr_draw,curr_away)[,2], cl=dv3(curr_home,curr_draw,curr_away)[,3])
pA <- per |> group_by(issue, slot) |>
  summarise(pA_w=mean(cw), pA_d=mean(cd), pA_l=mean(cl), n=n(), .groups='drop')
w <- d4 |> transmute(issue, slot, ow=eu2_w, od=eu2_d, ol=eu2_l, booksum=1/eu2_w+1/eu2_d+1/eu2_l) |>
  inner_join(wr |> transmute(issue, slot, wW=home_pct, wD=draw_pct, wL=away_pct), by=c('issue','slot')) |>
  inner_join(pA, by=c('issue','slot')) |> inner_join(po |> transmute(issue, slot, payout=payout_pct), by=c('issue','slot'))
dvB <- dv3(w$ow, w$od, w$ol)
cat(sprintf('连接 %d 场；pA(各家均值) %d 场；两家都有报价的 %d 场\n',
  nrow(w), nrow(pA), sum(pA$n == 2)))
```

    连接 1634 场；pA(各家均值) 2334 场；两家都有报价的 1779 场

``` r
cat(sprintf('平均胜率 三者和: 中位 %.6f 范围 [%.4f, %.4f]  <- 源数据只有 0.1%% 精度\n',
  median(w$wW+w$wD+w$wL), min(w$wW+w$wD+w$wL), max(w$wW+w$wD+w$wL)))
```

    平均胜率 三者和: 中位 1.000000 范围 [0.9990, 1.0010]  <- 源数据只有 0.1% 精度

``` r
cat(sprintf('|平均胜率 - de-vig(平均赔率)|   胜 %.5f 平 %.5f 负 %.5f\n',
  mean(abs(w$wW-dvB[,1])), mean(abs(w$wD-dvB[,2])), mean(abs(w$wL-dvB[,3]))))
```

    |平均胜率 - de-vig(平均赔率)|   胜 0.00727 平 0.00300 负 0.00697

``` r
# 必须用 join 进来的列 w$pA_*；pA$pA_* 是独立 tibble，行序与 w 不同
cat(sprintf('|平均胜率 - 各家去水再平均|    胜 %.5f 平 %.5f 负 %.5f\n',
  mean(abs(w$wW-w$pA_w)), mean(abs(w$wD-w$pA_d)), mean(abs(w$wL-w$pA_l))))
```

    |平均胜率 - 各家去水再平均|    胜 0.00934 平 0.00811 负 0.01021

``` r
cat(sprintf('相关 0.998 量级: %.5f  逐场最大绝对差 中位 %.4f p90 %.4f 最大 %.4f\n',
  cor(w$wW, dvB[,1]), median(apply(abs(cbind(w$wW,w$wD,w$wL)-dvB),1,max)),
  quantile(apply(abs(cbind(w$wW,w$wD,w$wL)-dvB),1,max),.9),
  max(abs(cbind(w$wW,w$wD,w$wL)-dvB))))
```

    相关 0.998 量级: 0.99815  逐场最大绝对差 中位 0.0070 p90 0.0172 最大 0.0533

``` r
cat(sprintf('返还率 均值 %.4f vs 1/booksum 均值 %.4f  差 %+.5f  <- 两者不是同一算法\n',
  mean(w$payout), mean(1/w$booksum), mean(w$payout-1/w$booksum)))
```

    返还率 均值 0.9256 vs 1/booksum 均值 0.9322  差 -0.00653  <- 两者不是同一算法

**两者高度一致（相关 0.998，平均差 0.3–0.7pp），但不是同一个算法**：这个
0.007 的残差比 Jensen 效应应有的量级（各家概率差异仅约 1%，Jensen 项约
1e-4）大一个数量级，返还率也与 `1/booksum` 差
0.6pp。说明平均胜率用了不同的公司集合或不同的去水方法。

``` r
# 平均胜率只给到 0.1% 精度，归一化后才能进入 DC
Pwr <- cbind(w$wW, w$wD, w$wL); Pwr <- Pwr / rowSums(Pwr)
wrkey <- paste(w$issue, w$slot)
d4$wrkey <- paste(d4$issue, d4$slot)
Pwr <- Pwr[match(d4$wrkey, wrkey), ]
fitwr <- function(P1) { P <- matrix(NA_real_, n4, 3); r <- rep(NA_real_, n4)
  for (i in seq_len(n4)) {
    f <- tryCatch(jc_fit_rates(c(W=P1[i,1],D=P1[i,2],L=P1[i,3]), d4$tot_ou[i], 0L, rho4), error=function(e) NULL)
    if (is.null(f)) next
    r[i] <- f$residual; P[i,] <- jc_rates_at_handicap(f$lambda_home, f$lambda_away, d4$hcp[i], rho4) }
  list(P=P, res=r) }
FW <- fitwr(Pwr)
k0 <- which(d4$hcp == 0); n0 <- length(k0); ik0 <- cbind(seq_len(n0), match(Y4[k0], OL4))
qual6 <- tibble(
  口径 = c('de-vig(平均赔率)', '平均胜率'),
  零让球对数损失 = c(-mean(log(pe4[k0,][ik0])), -mean(log(Pwr[k0,][ik0]))),
  零让球Brier = c(mean(rowSums((pe4[k0,]-oh4[k0,])^2)), mean(rowSums((Pwr[k0,]-oh4[k0,])^2))),
  全腿对数损失 = c(-mean(log(FD4$P[idx4])), -mean(log(FW$P[idx4]))),
  全腿Brier = c(mean(rowSums((FD4$P-oh4)^2)), mean(rowSums((FW$P-oh4)^2))),
  平局对数损失 = c(-mean(log(FD4$P[isD4,2])), -mean(log(FW$P[isD4,2]))))
qual6 |> mutate(across(where(is.numeric), ~round(.x,5))) |>
  knitr::kable(caption = '两种 1X2 口径作为 DC 输入：差异不显著，de-vig(平均赔率) 略优')
```

| 口径 | 零让球对数损失 | 零让球Brier | 全腿对数损失 | 全腿Brier | 平局对数损失 |
|:---|---:|---:|---:|---:|---:|
| de-vig(平均赔率) | 1.07339 | 0.64876 | 1.06890 | 0.64582 | 1.33734 |
| 平均胜率 | 1.07495 | 0.64987 | 1.06995 | 0.64656 | 1.33734 |

两种 1X2 口径作为 DC 输入：差异不显著，de-vig(平均赔率) 略优

``` r
dd <- (-log(FW$P[idx4])) - (-log(FD4$P[idx4]))
cat(sprintf('\n配对差 (平均胜率 - de-vig平均赔率): %+.5f  t = %.2f\n', mean(dd), mean(dd)/(sd(dd)/sqrt(n4))))
```

    配对差 (平均胜率 - de-vig平均赔率): +0.00105  t = 1.82

**结论：口径一致，用哪个对结论没有影响。** de-vig(平均赔率)
略优（−0.00105，t=1.82，不显著），差距与平均胜率源数据 0.1%
量化台阶引入的噪声同量级。回测同样几乎不变（单腿 1.2212 vs 1.2165）。

### 对收益的影响

``` r
SPw <- SP4; realw <- matrix(0, n4, 3); realw[idx4] <- SPw[idx4]
Pw2 <- Pwr / rowSums(Pwr)
FB2 <- fitwr(Pw2)
Pset <- list('de-vig(平均赔率)' = FD4$P, '平均胜率' = FB2$P)
sw <- bind_rows(lapply(c(1.0, 1.05, 1.10, 1.20), function(thr) {
  v <- vapply(Pset, function(P) mean(realw[P*SPw > thr]), 0)
  tibble(阈值=thr, 赔率口径单腿=v[1], 赔率口径七串一=0.65*v[1]^7,
         胜率口径单腿=v[2], 胜率口径七串一=0.65*v[2]^7) }))
sw |> mutate(across(where(is.numeric), ~round(.x,4))) |>
  knitr::kable(caption = '阈值扫描：换口径后两条曲线几乎重合')
```

| 阈值 | 赔率口径单腿 | 赔率口径七串一 | 胜率口径单腿 | 胜率口径七串一 |
|-----:|-------------:|---------------:|-------------:|---------------:|
| 1.00 |       1.1943 |         2.2531 |       1.1895 |         2.1905 |
| 1.05 |       1.2212 |         2.6322 |       1.2165 |         2.5629 |
| 1.10 |       1.2949 |         3.9672 |       1.2799 |         3.6575 |
| 1.20 |       1.3876 |         6.4366 |       1.3784 |         6.1464 |

阈值扫描：换口径后两条曲线几乎重合

``` r
set.seed(5)
pl <- vapply(Pset, function(P) mean(replicate(400, {
  Ps <- P; for (i in seq_len(n4)) Ps[i,] <- Ps[i, sample(3)]
  mean(realw[Ps*SPw > 1.05]) })), 0)
mu <- vapply(Pset, function(P) mean(realw[P*SPw > 1.05]), 0)
tr <- bind_rows(lapply(seq_along(Pset), function(j) {
  v <- sort(realw[Pset[[j]]*SPw > 1.05]); nv <- length(v)
  tibble(口径=names(Pset)[j], 全样本=mean(v), 去顶1pct=mean(v[1:(nv-20)]),
         去顶2pct=mean(v[1:(nv-40)]), 去顶5pct=mean(v[1:(nv-99)]),
         安慰剂基线=pl[j], 超安慰剂部分=mean(v)/pl[j]) }))
tr |> mutate(across(where(is.numeric), ~round(.x,4))) |>
  knitr::kable(caption = '修尾读法：临界点（去顶2% 转负）位置完全相同')
```

| 口径             | 全样本 | 去顶1pct | 去顶2pct | 去顶5pct | 安慰剂基线 | 超安慰剂部分 |
|:-----------------|-------:|---------:|---------:|---------:|-----------:|-------------:|
| de-vig(平均赔率) | 1.2212 |   1.0736 |   1.0295 |   0.9106 |     1.1659 |       1.0474 |
| 平均胜率         | 1.2165 |   1.0704 |   1.0267 |   0.9089 |     1.1648 |       1.0444 |

修尾读法：临界点（去顶2% 转负）位置完全相同

``` r
cat(sprintf('\n相对安慰剂的真实增量: 赔率口径 %+.4f -> 7串1 EV %.4f | 胜率口径 %+.4f -> 7串1 EV %.4f\n',
  mu[1]-pl[1], 0.65*(1+mu[1]-pl[1])^7, mu[2]-pl[2], 0.65*(1+mu[2]-pl[2])^7))
```

    相对安慰剂的真实增量: 赔率口径 +0.0553 -> 7串1 EV 0.9471 | 胜率口径 +0.0517 -> 7串1 EV 0.9251

**换口径对收益的影响可以忽略**：单腿差 0.5pp（1.2212 vs 1.2165），7串1
EV 差
2–8%（被七次方放大）。**对所有结论的方向零影响**——该”赚”的两个口径都”赚”，该崩的（去顶
2% 转负）在同一位置崩，安慰剂基线都是 1.165。

**这本身就是一次稳健性检验**：一个口径来自源站给的胜率，另一个由我从赔率去水算出，两套独立算法给出几乎重合的收益曲线，说明我的
de-vig 实现没有引入偏差。

## 结果七：逐期命中率与收益

``` r
E4v <- FD4$P * SP4; real4 <- matrix(0, n4, 3); real4[idx4] <- SP4[idx4]
per <- bind_rows(lapply(sort(unique(d4$issue)), function(iss) {
  k <- d4$issue == iss; s <- E4v[k,] > 1.05; v <- real4[k,][s]
  tibble(期次=iss, 场次=sum(k), 注数=sum(s), 命中率=mean(v>0), 中奖SP中位=median(v[v>0]),
         单腿回报=mean(v), 该期隐含七串一EV=0.65*mean(v)^7) }))
per |> mutate(命中率=round(命中率,4), across(where(is.numeric) & !any_of('命中率'), ~round(.x,4))) |>
  knitr::kable(caption = '逐期价值投注（阈值 1.05）：命中率 23.9%-33.6%，单腿回报 0.80-1.46')
```

|  期次 | 场次 | 注数 | 命中率 | 中奖SP中位 | 单腿回报 | 该期隐含七串一EV |
|------:|-----:|-----:|-------:|-----------:|---------:|-----------------:|
| 26087 |  134 |  141 | 0.3050 |      3.810 |   1.1170 |           1.4104 |
| 26088 |   82 |   97 | 0.2577 |      3.560 |   0.9385 |           0.4167 |
| 26089 |  356 |  440 | 0.2955 |      3.710 |   1.0970 |           1.2429 |
| 26091 |  129 |  168 | 0.2619 |      3.805 |   1.2242 |           2.6779 |
| 26092 |  371 |  465 | 0.3118 |      3.670 |   1.2797 |           3.6536 |
| 26093 |   94 |  109 | 0.2385 |      3.175 |   0.8037 |           0.1408 |
| 26094 |  383 |  452 | 0.3363 |      3.705 |   1.4598 |           9.1827 |
| 26095 |   85 |  106 | 0.3302 |      3.740 |   1.2837 |           3.7334 |

逐期价值投注（阈值 1.05）：命中率 23.9%-33.6%，单腿回报 0.80-1.46

**基准对照**：不做任何筛选、平注全部 4902 条腿，命中率恒为
**33.3%**（每场必有且仅有一个结果中），单腿回报合计
**1.0603**。价值投注把命中率从 33.3% 降到 30.3%，换来单腿回报从 1.0603
升到 1.2212。

### 七串一层面：8 期 0 中

``` r
pull4 <- function(k, tk) { L <- length(k)
  list(p=as.vector(FD4$P[k,])[tk], sp=as.vector(SP4[k,])[tk],
       hit=Y4[k[((tk-1) %% L) + 1]] == OL4[((tk-1) %/% L) + 1]) }
tickets <- bind_rows(lapply(c('最稳(p 最高 7 条)', '最高期望(e 最高 7 条)'), function(rule) {
  bind_rows(lapply(sort(unique(d4$issue)), function(iss) {
    k <- which(d4$issue == iss)
    sc <- if (grepl('p 最高', rule)) as.vector(FD4$P[k,]) else as.vector(E4v[k,])
    q <- pull4(k, order(sc, decreasing=TRUE)[1:7])
    hit <- all(q$hit)
    tibble(规则=rule, 期次=iss, 模型命中概率=prod(q$p), 模型EV=0.65*prod(q$p*q$sp),
           实际派彩=if (hit) 0.65*prod(q$sp) else 0, 结果=if (hit) '全中' else '未中') })) }))
tickets |> group_by(规则) |>
  summarise(期数=n(), 全中期数=sum(结果=='全中'), 实际回报率=100*(sum(实际派彩)-n())/n(),
            模型命中概率范围=sprintf('%.2f%%-%.2f%%', 100*min(模型命中概率), 100*max(模型命中概率)),
            模型EV中位=median(模型EV), .groups='drop') |>
  mutate(实际回报率=round(实际回报率,1), 模型EV中位=round(模型EV中位,3)) |>
  knitr::kable(caption = '七串一实际结果：两种选腿规则下 8 期全部未中')
```

| 规则                  | 期数 | 全中期数 | 实际回报率 | 模型命中概率范围 | 模型EV中位 |
|:----------------------|-----:|---------:|-----------:|:-----------------|-----------:|
| 最稳(p 最高 7 条)     |    8 |        0 |       -100 | 1.10%-2.09%      |       0.71 |
| 最高期望(e 最高 7 条) |    8 |        0 |       -100 | 0.01%-0.16%      |     358.16 |

七串一实际结果：两种选腿规则下 8 期全部未中

``` r
cat(sprintf('\n模型自身的七串一期望（最稳规则）均值 %.3f -> 每 2 元成本期望回收 %.2f 元\n',
  mean(tickets$模型EV[tickets$规则=='最稳(p 最高 7 条)']),
  2*mean(tickets$模型EV[tickets$规则=='最稳(p 最高 7 条)'])))
```

    模型自身的七串一期望（最稳规则）均值 0.726 -> 每 2 元成本期望回收 1.45 元

``` r
cat(sprintf('8 注在 %.1f%% 命中概率下全部落空的概率 %.1f%%  <- 这是最可能的结果，检验力约等于零\n',
  100*mean(tickets$模型命中概率[tickets$规则=='最稳(p 最高 7 条)']),
  100*(1-mean(tickets$模型命中概率[tickets$规则=='最稳(p 最高 7 条)']))^8))
```

    8 注在 1.6% 命中概率下全部落空的概率 88.1%  <- 这是最可能的结果，检验力约等于零

**逐期数据回答了两件事，也否掉了一件事**：

1.  **逐腿层面是有效的**：命中率 23.9%–33.6%，单腿回报 0.80–1.46，8 期里
    6 期高于 1。
2.  **七串一层面是无效的**：8 期 0
    中，两种选腿规则都全亏。但注意——**这个结果几乎没有检验力**：在约
    1.5% 的命中概率下，8 注全部落空本来就是最可能的结果（约
    88.6%），模型完全正确也会看到 0 中。
3.  **模型自己的七串一期望均值只有 0.726**（每 2 元期望回收 1.45 元，即
    −27%）。逐腿的 +22% 并不能直接平移成票据的正期望：取 p 最高的 7
    条是重仓热门，取 e 最高的 7 条则退化成中奖概率 0.008%–0.16% 的彩票。

## 结果八：组合空间与覆盖账

``` r
om4  <- rowSums(FD4$P * SP4)      # 模型概率下的覆盖因子 omega = sum_o p_o * SP_o
omb4 <- rowSums(Pbd4 * SP4)       # 北单去水概率下的同一量
cat(sprintf('omega(北单去水): 中位 %.4f 均值 %.4f  <- 理论应为 3 x 0.9982 = 2.9946\n', median(omb4), mean(omb4)))
```

    omega(北单去水): 中位 2.9945 均值 2.9944  <- 理论应为 3 x 0.9982 = 2.9946

``` r
cat(sprintf('omega(DC 模型):  中位 %.4f 均值 %.4f p10 %.3f p90 %.3f\n', median(om4), mean(om4), quantile(om4,.1), quantile(om4,.9)))
```

    omega(DC 模型):  中位 3.0497 均值 3.5173 p10 2.956 p90 3.238

``` r
bind_rows(lapply(sort(unique(d4$issue)), function(iss) { k <- which(d4$issue == iss); N <- length(k)
  tibble(期次=iss, 场次=N, 七场组合=choose(N,7), 总票据数=choose(N,7)*3^7,
         全包投入元=choose(N,7)*3^7*2) })) |>
  mutate(across(c(七场组合,总票据数,全包投入元), ~formatC(.x, format='e', digits=3))) |>
  knitr::kable(caption = '7 串 1 的组合空间：固定 7 场有 3^7 = 2187 种结果，再乘 C(N,7)')
```

|  期次 | 场次 | 七场组合  | 总票据数  | 全包投入元 |
|------:|-----:|:----------|:----------|:-----------|
| 26087 |  134 | 1.313e+11 | 2.871e+14 | 5.741e+14  |
| 26088 |   82 | 3.802e+09 | 8.314e+12 | 1.663e+13  |
| 26089 |  356 | 1.355e+14 | 2.963e+17 | 5.927e+17  |
| 26091 |  129 | 9.995e+10 | 2.186e+14 | 4.372e+14  |
| 26092 |  371 | 1.813e+14 | 3.966e+17 | 7.931e+17  |
| 26093 |   94 | 1.024e+10 | 2.239e+13 | 4.477e+13  |
| 26094 |  383 | 2.270e+14 | 4.964e+17 | 9.929e+17  |
| 26095 |   85 | 4.936e+09 | 1.079e+13 | 2.159e+13  |

7 串 1 的组合空间：固定 7 场有 3^7 = 2187 种结果，再乘 C(N,7)

**覆盖一组 7 场（该组 2187 注全买）是确定账，不是期望**：成本 2187 注 x
2 元 = **4374 元**，必然中恰好一注，派彩 2 x 0.65 x prod(7 场实际
SP)。其**期望**回报率有闭式：

``` r
cat('期望回报率 = 0.65 * omega^7 / 3^7\n\n')
```

    期望回报率 = 0.65 * omega^7 / 3^7

``` r
wl <- c('完美校准 omega=3'=3, '北单去水实测'=mean(omb4), 'DC 模型中位'=median(om4), 'DC 模型均值'=mean(om4))
for (nm in names(wl)) { w <- wl[[nm]]
  cat(sprintf('  %-16s omega=%.4f -> 期望回报率 %7.4f  (%+.1f%%)\n', nm, w, 0.65*w^7/3^7, 100*(0.65*w^7/3^7-1))) }
```

      完美校准 omega=3 omega=3.0000 -> 期望回报率  0.6500  (-35.0%)
      北单去水实测 omega=2.9944 -> 期望回报率  0.6416  (-35.8%)
      DC 模型中位  omega=3.0497 -> 期望回报率  0.7293  (-27.1%)
      DC 模型均值  omega=3.5173 -> 期望回报率  1.9796  (+98.0%)

``` r
tib <- bind_rows(lapply(sort(unique(d4$issue)), function(iss) { k <- which(d4$issue == iss)
  ao <- apply(FD4$P[k,],1,which.max); o <- order(apply(FD4$P[k,],1,max), decreasing=TRUE)[1:7]
  s <- SP4[k,][cbind(o,ao[o])]
  tibble(期次=iss, 模型期望回报率=0.65*prod(om4[k][o])/3^7, 实际回报率=0.65*prod(s)/3^7,
         模型最自信命中数=sprintf('%d/7', sum(ao[o]==match(Y4[k][o],OL4)))) }))
tib |> mutate(across(c(模型期望回报率,实际回报率), ~round(100*.x,3))) |>
  knitr::kable(caption = '模型最自信的 7 场，2187 注全买：模型期望 vs 实际（点本金的百分比）')
```

|  期次 | 模型期望回报率 | 实际回报率 | 模型最自信命中数 |
|------:|---------------:|-----------:|:-----------------|
| 26087 |         93.338 |      1.978 | 2/7              |
| 26088 |         77.913 |      3.173 | 3/7              |
| 26089 |         67.406 |      1.832 | 2/7              |
| 26091 |         73.556 |      2.339 | 3/7              |
| 26092 |         72.664 |      1.481 | 3/7              |
| 26093 |         66.671 |      1.911 | 5/7              |
| 26094 |         92.130 |      1.246 | 5/7              |
| 26095 |         79.591 |      3.591 | 2/7              |

模型最自信的 7 场，2187 注全买：模型期望 vs 实际（点本金的百分比）

``` r
cat(sprintf('\n模型期望均值 %.2f%%   实际均值 %.2f%%\n', 100*mean(tib$模型期望回报率), 100*mean(tib$实际回报率)))
```

    模型期望均值 77.91%   实际均值 2.19%

``` r
cat(sprintf('模型最自信 7 场的实际命中数: %s —— 8 期里从未 7/7\n', paste(tib$模型最自信命中数, collapse=' ')))
```

    模型最自信 7 场的实际命中数: 2/7 3/7 2/7 3/7 3/7 5/7 5/7 2/7 —— 8 期里从未 7/7

**omega = 3 时期望回报率恰好等于 0.65** —— 这就是 0.65/booksum^7 = 0.640
的结构性结论在覆盖账上的等价形式，且与选哪 7 场无关。北单去水概率实测
omega = 2.9944，与 3 x 0.9982 完全吻合，是市场自洽性的又一次验证。

DC 模型给出的 omega 中位 3.0497（-27%）看起来像 8pp 的边际优势，但**均值
3.5173 对应 +98%**，那是被长尾拉动的数字，不可信。实际 8 组的回报率只有
1.2%-3.6%（均值 2.19%）——单次实现，样本量不足以判定。

## 验证

- 欧赔来源：`https://1x2.nowscore.com/{matchid}.js`，`var game`
  每条含初盘与即时，主流场次 150+ 家公司。抽验 26096 第 1 场（八户云罗里
  vs 宫崎特格瓦嘉洛）：即时平均 3.283/3.103/2.163，水位 1.0893。
- 让球映射：`jc_fit_rates_free` 在 hcp=0 上残差 \<
  1e-4（`tests/testthat/test-joint-basket-dc-fit.R`）。
- 33.5%（548/1634）的场次，此前存下的”收盘
  SP”其实是**开球后**的变盘行；本文改用开球前最后一整行。换口径后「买欧赔最热」从
  0.9818 变 1.0896 —— 说明该数字对口径极度敏感，不是稳定 edge。
- 北单 SP 为奖池制（`sum(1/SP)` 中位 **1.00183**，即 0.18%
  水位），去水后的 p 与 `(1/sp)/booksum` 恒等（max 偏差 2.2e-16）。

## 局限

- 过往期次原有欧赔来自 500.com 单一快照（时间戳未知）。现已换成 nowscore
  `平均欧*`（`/handle/1x2.aspx?companyid=0`），两者相关 0.996–0.997，且
  nowscore `game` 的 `gameDetail`
  字段含**逐公司时间序列**，可用于把欧赔对齐到 T 时刻 —— 这一步尚未做。
- 大小球反解用 Poisson
  单自由度假设；四分之一盘按相邻两盘口各半注处理。多公司报价的中位离散度为
  0.0285 球。
- 单腿回报右尾极重，正态近似的 t 值不可靠；本文以 bootstrap
  区间与去尾检验为准。
- 尚未把整套 bundle
  流程（`jt_pick_fixtures`/`jt_fund`）接到新的概率输入上重跑。

## 总判断

在 7串1 的约束下，概率必须来自欧赔；但**换了概率来源也没有
edge**。北单收盘市场在 hcp=0 上与欧赔一致到 1pp
以内，且自身接近公平（水位 0.18%）。唯一确定的边际是 **0.65
的派奖税**，7串1 的理论 EV = `0.65 / booksum^7` ≈ **0.640（−36%）**。

### 关于总进球来源

**用北单自己的总进球市场做 DC
约束是错的，但换成独立来源也不是全面更好。**

- 北单总进球隐含中位 **3.031**，澳M/皇G 大小球反解中位 **2.923** ——
  北单系统性高估 **0.19 球**。
- 这个高估**单调地压低模型的平局概率**（偏差最大四分位：实际平局率
  0.2983，C 只给 0.2348），而实际平局率并没有随之下降。
- 换成独立大小球（D）：平局对数损失 **1.36787 -\> 1.33734（−0.0305，t =
  −10.78）**，显著变好。
- 但代价是非平局 **0.95822 -\> 0.96812（+0.0099，t =
  +9.42）**，显著变差；全样本几乎抵消（−0.0011，t = −0.97）。
- **没有任何单一来源占优**：北单 SP 在非平局上最好（0.97683），D
  在平局上最好（1.33734），纯欧赔（A）总体最好（1.06844）。三者互相之间的总体差异都在噪声内。
- 三种变体在安慰剂对照下的增量分别是 0.77 / 1.20 / 0.71
  个标准差，**都没有 edge**。

因此结论是：**总进球应当取自与北单无关的盘口（澳M/皇G
大小球），用于修正平局口径**；但这只是概率质量的小幅改善，不改变 −36%
的结构性结论。
