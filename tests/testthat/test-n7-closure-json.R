testthat::test_that('singleton Python closure roots retain list shape through JSON', {
 root<-normalizePath('../..')
 python<-Sys.getenv('RETICULATE_PYTHON')
 testthat::expect_true(nzchar(python))
 reticulate::use_python(python,required=TRUE)
 sys<-reticulate::import('sys',convert=FALSE);sys$path$insert(0L,root)
 prov<-reticulate::import('src.temporal_learning.provenance')
 pathlib<-reticulate::import('pathlib');json<-reticulate::import('json',convert=FALSE)
 closure<-prov$implementation_closure(pathlib$Path(root),as.list('src.fundamentals_n7_baseline'),
   distributions=c('numpy','pandas'))
 closure$root_modules<-as.list(closure$root_modules)
 encoded<-jsonlite::toJSON(closure,auto_unbox=TRUE)
 testthat::expect_type(jsonlite::fromJSON(encoded,simplifyVector=FALSE)$root_modules,'list')
 testthat::expect_no_error(prov$verify_implementation_closure(pathlib$Path(root),json$loads(encoded)))
 malformed<-closure;malformed$root_modules<-unlist(malformed$root_modules)
 testthat::expect_error(prov$verify_implementation_closure(pathlib$Path(root),
   json$loads(jsonlite::toJSON(malformed,auto_unbox=TRUE))))
})
