# Parse exactly the bytes whose SHA-256 matches an explicit receipt. Character
# identifiers and other column types are declared by the caller via readr cols.
# This closes the gap between a prior path check and a later settlement read.
# Returns a tibble; reads once, no writes; missing/changed/invalid data fails.
diagnostic_read_verified_csv <- function(path, expected_sha256, col_types) {
 stopifnot(is.character(path),length(path)==1,!is.na(path),file.exists(path),
  !dir.exists(path),is.character(expected_sha256),length(expected_sha256)==1,
  !is.na(expected_sha256),grepl('^[0-9a-f]{64}$',expected_sha256))
 bytes<-readBin(path,'raw',n=file.info(path)$size)
 stopifnot(identical(digest::digest(bytes,serialize=FALSE,algo='sha256'),expected_sha256))
 result<-readr::read_csv(I(rawToChar(bytes)),col_types=col_types,show_col_types=FALSE)
 readr::stop_for_problems(result)
 result
}
