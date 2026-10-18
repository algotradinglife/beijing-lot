suppressPackageStartupMessages(library(tidyverse))
root <- normalizePath(commandArgs(TRUE)[1],mustWork=TRUE);setwd(root)
parsed_path <- '/home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/global-dynamic-26105-channel-parsed-20261019-v4/parsed.json'
inventory_path <- '/home/drwho1985/workspace/algotradinglife/beijing-lot-data/hot/global-dynamic-26105-channel-inventory-20261018/inventory.json'
p <- jsonlite::fromJSON(parsed_path,simplifyVector=FALSE)
i <- jsonlite::fromJSON(inventory_path,simplifyVector=FALSE)
f <- bind_rows(i$fixtures) |> select(fixture_id,cutoff_utc) |> mutate(cutoff_utc=lubridate::ymd_hms(cutoff_utc,tz='UTC'))
s <- map_dfr(p$records, ~map_dfr(.x$snapshots, ~tibble(snapshot_ts_hkt=.x$snapshot_ts_hkt)) |> mutate(fixture_id=.x$fixture_id,kind=.x$kind)) |>
 mutate(quote_utc=lubridate::ymd_hms(snapshot_ts_hkt,tz='UTC')) |>
 left_join(f,by='fixture_id',relationship='many-to-one') |>
 mutate(prior_quote=quote_utc<=cutoff_utc,fresh_prior=prior_quote & quote_utc>=cutoff_utc-lubridate::hours(48))
stopifnot(nrow(f)==365L,!anyDuplicated(f$fixture_id),!anyNA(s[c('quote_utc','cutoff_utc')]),p$network_attempts==0L)
a <- s |> group_by(fixture_id,kind) |> summarise(quotes=n(),prior_quotes=sum(prior_quote),fresh_prior_quotes=sum(fresh_prior),.groups='drop')
stopifnot(nrow(a)==730L)
z <- a |> group_by(kind) |> summarise(fixtures=n(),quotes=sum(quotes),fixtures_with_prior=sum(prior_quotes>0),fixtures_with_fresh_prior=sum(fresh_prior_quotes>0),.groups='drop')
out <- 'results/global-dynamic-26105-line-cutoff-20261019'
write_csv(a,file.path(out,'fixture-audit.csv'));write_csv(z,file.path(out,'summary.csv'))
jsonlite::write_json(list(parsed_sha256=digest::digest(file=parsed_path,algo='sha256'),inventory_sha256=digest::digest(file=inventory_path,algo='sha256'),client_sha256=digest::digest(file=file.path(out,'audit.R'),algo='sha256'),historical_admission=FALSE,rule='Original fixture T-24h; quote at or before cutoff; freshness48h; source quote clocks diagnostic only'),file.path(out,'receipt.json'),auto_unbox=TRUE,pretty=TRUE)
print(z)
joint <- a |> select(fixture_id,kind,fresh_prior_quotes) |> mutate(available=fresh_prior_quotes>0L) |> select(-fresh_prior_quotes) |> pivot_wider(names_from=kind,values_from=available) |>
 count(asian,total,name='fixtures')
stopifnot(sum(joint$fixtures)==365L)
write_csv(joint,file.path(out,'joint-availability.csv'))
print(joint)
