test_that("cup schemas cross Python Parquet into typed R tibbles", {
  python <- Sys.getenv("BEIDAN_TEST_PYTHON")
  expect_true(nzchar(python))
  beidan::python_backend(python)
  root <- tempfile("cup-boundary-")
  dir.create(root)
  code <- "\nfrom pathlib import Path\nimport json\nfrom beidan_backend.cup_standings import SCHEMAS\nfrom beidan_backend.source_issue_update import arrow_table\nfrom beidan_backend.settlement_backfill import write_parquet_atomically\np=Path(ROOT_PATH_LITERAL)/'datasets/cup_boundary/versions/v1'\np.mkdir(parents=True)\nrows={key:[] for key in SCHEMAS}\nrows['standings']=[dict(fixture_id='0001',group_membership_sha256='0'*64,team_id='0002',team_name=None,rank=None,played=None,wins=None,draws=None,losses=None,goals_for=None,goals_against=None,goal_difference=None,points=None,state='CONFLICT')]\nrows['coverage']=[dict(fixture_id='0001',source='titan',state='ABSENT',group_count=None,team_rows=None),dict(fixture_id='0001',source='nowscore',state='PUBLISHED_EMPTY',group_count=1,team_rows=0)]\nrows['provenance']=[dict(fixture_id='0001',source='titan',url='https://example.test/fixture',observed_at='2026-10-18T00:00:00.123456+00:00',sha256='1'*64)]\nentries={}\nfor name,schema in SCHEMAS.items():\n written=write_parquet_atomically(arrow_table(rows[name],schema),p/'tables'/(name+'.parquet'))\n entries[name]=dict(kind='whole',rows=written['rows'],files=[dict(name=name+'.parquet',sha256=written['sha256'])])\n(p/'manifest.json').write_text(json.dumps(dict(version='v1',tables=entries)))\n"
  code <- sub("ROOT_PATH_LITERAL", jsonlite::toJSON(normalizePath(root), auto_unbox=TRUE), code, fixed=TRUE)
  reticulate::py_run_string(code, local=TRUE)
  for (name in c("source_standings", "reconciliation")) {
    x <- beidan::read_dataset("cup_boundary", name, version="v1", root=root)
    expect_s3_class(x,"tbl_df")
    expect_equal(nrow(x),0L)
    expect_type(x$fixture_id,"character")
  }
  x <- beidan::read_dataset("cup_boundary","source_standings",version="v1",root=root)
  expect_type(x$rank,"integer")
  expect_s3_class(x$observed_at,"POSIXct")
  x <- beidan::read_dataset("cup_boundary","standings",version="v1",root=root)
  expect_identical(x$fixture_id,"0001")
  expect_identical(x$team_id,"0002")
  expect_type(x$points,"integer")
  expect_true(is.na(x$points))
  expect_true(is.na(x$team_name))
  x <- beidan::read_dataset("cup_boundary","coverage",version="v1",root=root)
  expect_identical(x$team_rows,c(NA_integer_,0L))
  expect_identical(x$group_count,c(NA_integer_,1L))
  x <- beidan::read_dataset("cup_boundary","provenance",version="v1",root=root)
  expect_s3_class(x$observed_at,"POSIXct")
  expect_equal(as.numeric(x$observed_at),as.numeric(as.POSIXct("2026-10-18 00:00:00",tz="UTC"))+0.123456,tolerance=1e-6)
})

test_that("R cup publisher binds real base read and preserves repeat execution", {
  python <- Sys.getenv("BEIDAN_TEST_PYTHON")
  beidan::python_backend(python)
  root <- tempfile("cup-publisher-")
  dir.create(root)
  fixture_root <- normalizePath(testthat::test_path("..","fixtures","cup_standings"))
  code <- "
from pathlib import Path
import json,hashlib
from beidan_backend.cup_standings import parse_cup_standings
from beidan_backend.source_issue_update import arrow_table
from beidan_backend.settlement_backfill import write_parquet_atomically
from beidan_backend.versioning import sha256_file
root=Path(ROOT_LITERAL); fixtures=Path(FIXTURE_LITERAL)
frozen=root/'nas';hot=root/'hot';hot.mkdir();(frozen/'registry').mkdir(parents=True)
(frozen/'registry/catalog.json').write_text(json.dumps({'schema':'beijing_lot_catalog_v1','datasets':{}}))
base=frozen/'datasets/source_issue_26098/versions/v1';base.mkdir(parents=True)
identity=dict(fixture_id='26098:1',provider_id='9',home_id='1',away_id='2')
schema={key:'character' for key in identity}
written=write_parquet_atomically(arrow_table([identity],schema),base/'tables/match.parquet')
(base/'manifest.json').write_text(json.dumps({'version':'v1','tables':{'match':{'kind':'whole','rows':1,'files':[{'name':'match.parquet','sha256':written['sha256']}]}}}))
rawroot=frozen/'reports/raw';(rawroot/'raw').mkdir(parents=True)
parsed=[];receipts=[]
for source in ('titan','nowscore'):
 raw=(fixtures/(source+'.html')).read_bytes()
 url=('https://zq.titan007.com/analysis/9cn.htm' if source=='titan' else 'https://live.nowscore.com/analysis/9cn.html')
 receipt=dict(source=source,url=url,observed_at='2026-10-18T00:00:00.123456+00:00',sha256=hashlib.sha256(raw).hexdigest())
 parsed.append(parse_cup_standings(raw,fixture_id=identity['fixture_id'],source=source,identity=identity,receipt=receipt))
 path='raw/'+receipt['sha256']+'.bin';(rawroot/path).write_bytes(raw)
 receipts.append(dict(fixture_id=identity['fixture_id'],**receipt,path=path,capture_observed_at=receipt['observed_at']))
(rawroot/'raw-receipts.json').write_text(json.dumps(receipts))
rawmanifest=dict(dataset='source_issue_26098',version='v1',base_manifest_sha256=sha256_file(base/'manifest.json'),members={'raw-receipts.json':sha256_file(rawroot/'raw-receipts.json')})
(rawroot/'asset-manifest.json').write_text(json.dumps(rawmanifest))
kwargs=dict(issue='26098',base_version='v1',base_manifest_sha256=rawmanifest['base_manifest_sha256'],raw_evidence_relative='reports/raw',raw_manifest_sha256=sha256_file(rawroot/'asset-manifest.json'))
"
  code <- sub("ROOT_LITERAL",jsonlite::toJSON(normalizePath(root),auto_unbox=TRUE),code,fixed=TRUE)
  code <- sub("FIXTURE_LITERAL",jsonlite::toJSON(fixture_root,auto_unbox=TRUE),code,fixed=TRUE)
  scope <- reticulate::py_run_string(code,local=TRUE)
  args <- c(list(parsed_sources=scope$parsed),scope$kwargs,
            list(python=python,root=file.path(root,"nas"),hot_root=file.path(root,"hot")))
  first <- do.call(beidan::publish_cup_standings,args)
  expect_identical(first$status,"published")
  x <- beidan::read_dataset(first$dataset,"standings",version=first$version,root=file.path(root,"nas"))
  expect_s3_class(x,"tbl_df")
  expect_identical(x$team_id,c("1","2"))
  expect_identical(x$points,c(4L,1L))
  expect_identical(x$state,c("AGREEMENT","AGREEMENT"))
  again <- do.call(beidan::publish_cup_standings,args)
  expect_identical(again$status,"unchanged")
  expect_identical(again$version,first$version)
})

test_that("R base identity boundary rejects mistyped IDs", {
  testthat::local_mocked_bindings(
    read_dataset=function(...) tibble::tibble(fixture_id="26098:1",provider_id="9",home_id=1L,away_id="2"),
    .package="beidan")
  expect_error(beidan:::.cup_base_fixture_json("x","match","v1","unused"),"identity contract")
})


test_that("R base identity boundary rejects duplicate fixture IDs", {
  testthat::local_mocked_bindings(
    read_dataset=function(...) tibble::tibble(fixture_id=c("26098:1","26098:1"),provider_id="9",home_id="1",away_id="2"),
    .package="beidan")
  expect_error(beidan:::.cup_base_fixture_json("x","match","v1","unused"),"identity contract")
})
