test_that("context logical/null/empty/time/ID columns cross the installed boundary", {
  beidan::python_backend(Sys.getenv("BEIDAN_TEST_PYTHON"))
  root <- tempfile("context-types-");dir.create(root)
  code <- "
from pathlib import Path
import json
from beidan_backend.fundamentals_context import context_arrow_table
from beidan_backend.settlement_backfill import write_parquet_atomically
p=Path(ROOT_LITERAL)/'datasets/context_boundary/versions/v1';p.mkdir(parents=True)
schema=dict(id='character',neutral='logical',observed_at='timestamp')
rows=[dict(id='0001',neutral=x,observed_at='2026-10-18T00:00:00.123456+00:00') for x in (True,False,None)]
entries={}
for name,data in [('fixture',rows),('empty',[])]:
 info=write_parquet_atomically(context_arrow_table(data,schema),p/'tables'/(name+'.parquet'))
 entries[name]=dict(kind='whole',rows=info['rows'],files=[dict(name=name+'.parquet',sha256=info['sha256'])])
(p/'manifest.json').write_text(json.dumps(dict(version='v1',tables=entries)))
"
  code <- sub("ROOT_LITERAL",jsonlite::toJSON(normalizePath(root),auto_unbox=TRUE),code,fixed=TRUE)
  reticulate::py_run_string(code,local=TRUE)
  x <- beidan::read_dataset("context_boundary","fixture",version="v1",root=root)
  expect_s3_class(x,"tbl_df")
  expect_identical(x$id,rep("0001",3L))
  expect_identical(x$neutral,c(TRUE,FALSE,NA))
  expect_s3_class(x$observed_at,"POSIXct")
  expect_equal(as.numeric(x$observed_at[1L]),as.numeric(as.POSIXct("2026-10-18",tz="UTC"))+0.123456,tolerance=1e-6)
  empty <- beidan::read_dataset("context_boundary","empty",version="v1",root=root)
  expect_s3_class(empty,"tbl_df")
  expect_equal(nrow(empty),0L)
  expect_type(empty$id,"character")
  expect_type(empty$neutral,"logical")
  expect_s3_class(empty$observed_at,"POSIXct")
})

test_that("R context publisher reads fixed base identities/history and repeats safely", {
  python <- Sys.getenv("BEIDAN_TEST_PYTHON")
  beidan::python_backend(python)
  root <- tempfile("context-publication-");dir.create(root)
  fixtures <- normalizePath(testthat::test_path("..","fixtures","fundamentals_context"))
  code <- "
from pathlib import Path
import json,hashlib
from beidan_backend.source_issue_update import arrow_table
from beidan_backend.settlement_backfill import write_parquet_atomically
from beidan_backend.versioning import sha256_file
root=Path(ROOT_LITERAL);fixtures=Path(FIXTURE_LITERAL)
frozen=root/'nas';hot=root/'hot';hot.mkdir();(frozen/'registry').mkdir(parents=True)
(frozen/'registry/catalog.json').write_text(json.dumps({'schema':'beijing_lot_catalog_v1','datasets':{}}))
base=frozen/'datasets/source_issue_26098/versions/v1';base.mkdir(parents=True)
f=dict(fixture_id='26098:1',provider_id='9',home_id='1',away_id='2')
h=dict(fixture_id='26098:1',scope='home_recent',match_id='9001',event_date='2026-01-01',home_id='1',away_id='2',selected_source='titan')
entries={}
for name,row in [('match',f),('history',h)]:
 schema={k:('date' if k=='event_date' else 'character') for k in row}
 info=write_parquet_atomically(arrow_table([row],schema),base/'tables'/(name+'.parquet'))
 entries[name]=dict(kind='whole',rows=info['rows'],files=[dict(name=name+'.parquet',sha256=info['sha256'])])
(base/'manifest.json').write_text(json.dumps(dict(version='v1',tables=entries)))
rawroot=frozen/'reports/raw';(rawroot/'raw').mkdir(parents=True);receipts=[]
for source in ('titan','nowscore'):
 for resource in (['analysis','auxiliary'] if source=='nowscore' else ['analysis']):
  raw=(fixtures/('nowscore-data.js' if resource=='auxiliary' else source+'.html')).read_bytes()
  url=('https://live.nowscore.com/analysisJs/data9.js' if resource=='auxiliary' else
       'https://zq.titan007.com/analysis/9cn.htm' if source=='titan' else 'https://live.nowscore.com/analysis/9cn.html')
  sha=hashlib.sha256(raw).hexdigest();path='raw/'+sha+'.bin';(rawroot/path).write_bytes(raw)
  receipts.append(dict(fixture_id='26098:1',source=source,url=url,sha256=sha,path=path,capture_observed_at='2026-10-18T00:00:00.123456+00:00'))
(rawroot/'raw-receipts.json').write_text(json.dumps(receipts))
rawmanifest=dict(dataset='source_issue_26098',version='v1',base_manifest_sha256=sha256_file(base/'manifest.json'),members={'raw-receipts.json':sha256_file(rawroot/'raw-receipts.json')})
(rawroot/'asset-manifest.json').write_text(json.dumps(rawmanifest))
kwargs=dict(issue='26098',base_version='v1',base_manifest_sha256=rawmanifest['base_manifest_sha256'],raw_evidence_relative='reports/raw',raw_manifest_sha256=sha256_file(rawroot/'asset-manifest.json'))
"
  code <- sub("ROOT_LITERAL",jsonlite::toJSON(normalizePath(root),auto_unbox=TRUE),code,fixed=TRUE)
  code <- sub("FIXTURE_LITERAL",jsonlite::toJSON(fixtures,auto_unbox=TRUE),code,fixed=TRUE)
  scope <- reticulate::py_run_string(code,local=TRUE)
  args <- c(scope$kwargs,list(python=python,root=file.path(root,"nas"),hot_root=file.path(root,"hot")))
  first <- do.call(beidan::publish_fundamentals_context,args)
  expect_identical(first$status,"published")
  f <- beidan::read_dataset(first$dataset,"fixture",version=first$version,root=args$root)
  h <- beidan::read_dataset(first$dataset,"history",version=first$version,root=args$root)
  expect_identical(f$neutral,FALSE)
  expect_identical(f$competition_id,"77")
  expect_identical(h$competition_id,"007")
  expect_identical(h$explicit_neutral,TRUE)
  expect_identical(h$base_selected_source,"titan")
  source <- beidan::read_dataset(first$dataset,"source_history",version=first$version,root=args$root)
  expect_equal(nrow(source),2L)
  expect_s3_class(source$event_date,"Date")
  expect_s3_class(source$data_observed_at,"POSIXct")
  expect_identical(do.call(beidan::publish_fundamentals_context,args),modifyList(first,list(status="unchanged")))
})

test_that("context R base callback rejects broken keys/types and preserves empty schemas", {
  valid <- tibble::tibble(fixture_id="26098:1",scope="home_recent",match_id="0001",
    event_date=as.Date("2026-01-01"),home_id="1",away_id="2",selected_source="titan")
  original <- valid
  testthat::local_mocked_bindings(read_dataset=function(...) valid,.package="beidan")
  value <- beidan:::.context_base_rows_json("x","history","v1","unused")
  expect_match(value,'"match_id":"0001"',fixed=TRUE)
  expect_match(value,'"event_date":"2026-01-01"',fixed=TRUE)
  valid$home_id <- 1L
  expect_error(beidan:::.context_base_rows_json("x","history","v1","unused"),"history contract")
  valid$home_id <- "1";valid <- dplyr::bind_rows(valid,valid)
  expect_error(beidan:::.context_base_rows_json("x","history","v1","unused"),"history contract")
  valid <- original;valid$event_date <- as.character(valid$event_date)
  expect_error(beidan:::.context_base_rows_json("x","history","v1","unused"),"history contract")
  valid <- original;valid$event_date[1L] <- as.Date(NA_character_)
  expect_error(beidan:::.context_base_rows_json("x","history","v1","unused"),"history contract")
  valid <- original;valid$match_id <- ""
  expect_error(beidan:::.context_base_rows_json("x","history","v1","unused"),"history contract")
  valid <- original;valid$selected_source <- "other"
  expect_error(beidan:::.context_base_rows_json("x","history","v1","unused"),"history contract")
  valid <- original[0,]
  expect_identical(beidan:::.context_base_rows_json("x","history","v1","unused"),"[]")
  expect_error(beidan:::.context_base_rows_json("x","unknown","v1","unused"),"unsupported")
})
