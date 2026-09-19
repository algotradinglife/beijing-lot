# Read a gzip RDS snapshot after verifying the exact bytes to be deserialized.
# path: existing gzip RDS; sha256: lowercase 64-digit expected hash.
# Returns the saved object, no writes. Wrong hash/encoding/corruption fails.
diagnostic_read_verified_rds <- function(path,sha256) {
 stopifnot(is.character(path),length(path)==1,file.exists(path),
  is.character(sha256),length(sha256)==1,!is.na(sha256),grepl('^[0-9a-f]{64}$',sha256))
 bytes<-readBin(path,'raw',n=file.info(path)$size)
 stopifnot(digest::digest(bytes,serialize=FALSE,algo='sha256')==sha256,
  length(bytes)>2,identical(bytes[1:2],as.raw(c(31,139))))
 unserialize(memDecompress(bytes,type='gzip'))
}
