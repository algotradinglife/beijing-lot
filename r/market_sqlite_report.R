# Convert verified Python query output into a typed report table.
# Input: list of records with scalar issue/kind/import_state strings.
# Output: tibble with one row per record. Empty input retains column types.
# Missing/invalid fields are errors; no writes, fetching or global state.
market_sqlite_record_table <- function(records) {
  if (!is.list(records)) stop("records must be a list")
  prototype <- tibble::tibble(issue = character(), kind = character(),
                             import_state = character())
  rows <- lapply(records, function(record) {
    fields <- record[c("issue", "kind", "import_state")]
    valid <- vapply(fields, function(value) {
      is.character(value) && length(value) == 1L && !is.na(value) && nzchar(value)
    }, logical(1))
    if (length(fields) != 3L || !all(valid)) stop("invalid market record fields")
    tibble::as_tibble(fields)
  })
  do.call(vctrs::vec_rbind, c(rows, list(.ptype = prototype)))
}
