#' Persistent Parquet dataset root
#'
#' @param root 长度 1 的非空字符串，持久化 Parquet 根目录；`NULL` 时取环境变量
#'   `BEIDAN_PARQUET_ROOT`，再退回本机默认值。
#' @return 规范化后的根目录路径。
#' @details 数据在 NAS 上（CIFS 自动挂载），可能未挂载。**未挂载时 `stop()`**，
#'   绝不把"根不可用"当成"数据集为空"：空数据集是 0 行，根缺失是错误。导入本
#'   模块不产生任何 I/O，只有调用本函数才检查磁盘。
#' @export
parquet_root <- function(root = NULL) {
  if (is.null(root)) root <- Sys.getenv("BEIDAN_PARQUET_ROOT", unset = "")
  if (!nzchar(root)) root <- "/mnt/nas/Data/beijing-lot"
  checkmate::assert_string(root, min.chars = 1L, na.ok = FALSE)
  if (!dir.exists(root)) {
    stop("parquet_root: persistent root is not available: ", root,
         " (NAS not mounted? set BEIDAN_PARQUET_ROOT)")
  }
  normalizePath(root, mustWork = TRUE)
}

#' Arrow 到 R 的类型契约
#'
#' @return 具名字符向量：名字为 Arrow 基础类型名（`DataType$ToString()` 去掉参数
#'   后的部分），值为 R 边界上的目标类型（`"character"` / `"integer"` /
#'   `"double"` / `"logical"` / `"POSIXct"` / `"Date"` / `"blob"`）。
#' @details 这是读取路径的显式类型契约。**未在此表出现的 Arrow 类型会 `stop()`**，
#'   不会静默地当成字符或列表——嵌套类型需要调用方显式处理。`int64`/`uint32`/
#'   `uint64` 映射为 `double` 以免整数溢出（R 的 integer 是 32 位）。
#' @export
parquet_type_map <- function() {
  c(
    bool = "logical",
    int8 = "integer", int16 = "integer", int32 = "integer", int64 = "double",
    uint8 = "integer", uint16 = "integer", uint32 = "double", uint64 = "double",
    float16 = "double", halffloat = "double", float32 = "double",
    float = "double", float64 = "double", double = "double",
    string = "character", utf8 = "character",
    large_string = "character", large_utf8 = "character",
    binary = "blob", large_binary = "blob",
    date32 = "Date", date64 = "Date", date = "Date",
    timestamp = "POSIXct"
  )
}

# Canonical Arrow type name for a Field, e.g. "large_string", "timestamp[us, tz=UTC]".
arrow_field_type <- function(field) {
  field$type$ToString()
}

# Base Arrow type without parameters, e.g. "timestamp" from "timestamp[us, tz=UTC]".
arrow_base_type <- function(type_string) {
  sub("\\[.*$", "", sub("^<|>$", "", type_string))
}

# Explicitly cast a data frame's columns to the declared contract types.
cast_dataset_columns <- function(data, contract) {
  for (column in names(contract)) {
    if (!column %in% names(data)) next
    data[[column]] <- switch(contract[[column]],
      character = as.character(data[[column]]),
      integer = as.integer(data[[column]]),
      double = as.numeric(data[[column]]),
      logical = as.logical(data[[column]]),
      Date = as.Date(data[[column]]),
      POSIXct = as.POSIXct(data[[column]], tz = "UTC"),
      blob = data[[column]],
      stop("read_dataset: unsupported contract type ", contract[[column]])
    )
  }
  data
}

#' 读一个数据集的版本 registry 指针
#'
#' @param dataset 长度 1 的非空字符串数据集名，如 `"settlement"`。
#' @param root 见 [parquet_root()]。
#' @return 该数据集当前版本的 registry 内容（list）。
#' @export
dataset_registry <- function(dataset, root = NULL) {
  checkmate::assert_string(dataset, min.chars = 1L, na.ok = FALSE)
  root <- parquet_root(root)
  # The dataset's own pointer is authoritative and is what the converter
  # maintains; the registry copy is a snapshot kept for older readers.
  pointer <- file.path(root, "datasets", dataset, "current.json")
  if (file.exists(pointer)) {
    current <- jsonlite::fromJSON(pointer, simplifyVector = FALSE)
    return(c(current, list(path = pointer)))
  }
  path <- file.path(root, "registry", paste0(dataset, "-parquet-current.json"))
  if (!file.exists(path)) {
    stop("dataset_registry: no registry or pointer for dataset '", dataset, "': ", path)
  }
  c(jsonlite::fromJSON(path, simplifyVector = FALSE), list(path = path))
}

#' 读一个已发布版本的 manifest
#'
#' @param dataset 数据集名。
#' @param version 版本字符串；`NULL` 时取 registry 的当前版本。
#' @param root 见 [parquet_root()]。
#' @return manifest（list），含来源 identity、行数与逐文件 sha256。
#' @export
dataset_manifest <- function(dataset, version = NULL, root = NULL) {
  root <- parquet_root(root)
  if (is.null(version)) {
    registry <- dataset_registry(dataset, root)
    # The dataset pointer uses the shared `label_version` vocabulary; the older
    # registry snapshot uses `version`. Accept either.
    version <- registry$version %||% registry$label_version
    if (is.null(version)) {
      stop("dataset_manifest: registry names no version for dataset '", dataset, "'")
    }
  }
  path <- file.path(root, "datasets", dataset, "versions", version, "manifest.json")
  if (!file.exists(path)) stop("dataset_manifest: version is not published: ", path)
  jsonlite::fromJSON(path, simplifyVector = FALSE)
}

#' 列出一个数据集版本里的表
#'
#' @inheritParams dataset_manifest
#' @return 字符向量：已发布的表名（排序后）。
#' @export
dataset_tables <- function(dataset, version = NULL, root = NULL) {
  names(dataset_manifest(dataset, version, root)$tables)
}

# The catalog is the authoritative list of what data exists; the version
# manifest describes the base tables only.
dataset_catalog_entry <- function(dataset, root = NULL) {
  path <- file.path(parquet_root(root), "registry", "catalog.json")
  if (!file.exists(path)) return(NULL)
  catalog <- jsonlite::fromJSON(path, simplifyVector = FALSE)
  if (!identical(catalog$schema, "beijing_lot_catalog_v1")) {
    stop("catalog schema must be 'beijing_lot_catalog_v1'; got ", catalog$schema)
  }
  catalog$datasets[[dataset]]
}

#' 列出一个数据集版本的派生产物
#'
#' @inheritParams dataset_manifest
#' @return 字符向量：catalog 登记的派生产物名（排序后）；无登记时为空向量。
#' @details 派生产物（如 `spf_labels`）由 catalog 登记，不在版本 manifest 的
#'   `tables` 内。它们与 base 表一样可用 [read_dataset()] 读取。
#' @export
dataset_derived_tables <- function(dataset, version = NULL, root = NULL) {
  entry <- dataset_catalog_entry(dataset, root)
  if (is.null(entry) || is.null(entry$derived)) return(character(0))
  sort(names(entry$derived))
}

# Resolve a `tier:relative/path` token against an already-resolved root.
resolve_location_token <- function(token, root) {
  if (!is.character(token) || length(token) != 1L || !grepl(":", token, fixed = TRUE)) {
    stop("read_dataset: malformed location token: ", paste(token, collapse = ", "))
  }
  tier <- sub(":.*$", "", token)
  relative <- sub("^[^:]*:", "", token)
  if (!identical(tier, "frozen")) {
    stop("read_dataset: unsupported location tier '", tier, "' (only 'frozen' is readable)")
  }
  file.path(root, relative)
}

# Resolve one derived artifact registered in the catalog for this version.
dataset_derived_entry <- function(dataset, table, version = NULL, root = NULL) {
  entry <- dataset_catalog_entry(dataset, root)
  if (is.null(entry) || is.null(entry$derived)) return(NULL)
  derived <- entry$derived[[table]]
  if (is.null(derived)) return(NULL)
  if (!is.null(version)) {
    # A stale catalog would point at another version's file; fail closed.
    expected <- paste0("versions/", version, "/")
    if (!grepl(expected, derived$location, fixed = TRUE)) {
      stop("read_dataset: catalog entry for derived '", table,
           "' does not belong to version ", version, ": ", derived$location)
    }
  }
  derived
}

# One resolution path for base tables and derived artifacts: files plus the
# hashes to verify and the expected total row count.
dataset_table_source <- function(dataset, table, version = NULL, root = NULL,
                                 issue_year = NULL, play = NULL) {
  root <- parquet_root(root)
  manifest <- dataset_manifest(dataset, version, root)
  version_dir <- file.path(root, "datasets", dataset, "versions", manifest$version)

  if (!is.null(manifest$tables[[table]])) {
    # A base table is partitioned by issue_year, never by play; accepting a
    # play argument silently would hide a caller's mistake.
    if (!is.null(play)) {
      stop("read_dataset: base table '", table, "' is not partitioned by play")
    }
    entry <- manifest$tables[[table]]
    files <- dataset_table_files(manifest, version_dir, table, issue_year = issue_year)
    hashes <- stats::setNames(
      vapply(entry$files, function(f) f$sha256, character(1)),
      vapply(entry$files, function(f) f$name, character(1)))
    return(list(kind = "base", files = files, hashes = hashes,
                rows = as.integer(entry$rows), version = manifest$version))
  }

  derived <- dataset_derived_entry(dataset, table, version = manifest$version, root = root)
  if (is.null(derived)) {
    stop("read_dataset: table '", table, "' is neither a base table of dataset '",
         dataset, "' nor a catalog-registered derived artifact")
  }
  if (!is.null(issue_year)) {
    stop("read_dataset: derived '", table, "' is not partitioned by issue_year")
  }
  # A derived artifact may be versioned: its location then names a
  # `current.json` pointer, and the artifact path/hash live in that pointer so a
  # new label version becomes visible without editing the catalog.
  pointer <- resolve_location_token(derived$location, root)
  if (!file.exists(pointer)) stop("read_dataset: derived location is missing: ", pointer)
  label_version <- NULL
  partition_files <- NULL
  if (identical(basename(pointer), "current.json")) {
    current <- jsonlite::fromJSON(pointer, simplifyVector = FALSE)
    artifact <- current$artifact$path
    if (is.null(artifact) || !startsWith(artifact, root)) {
      stop("read_dataset: current pointer does not name an artifact under the root: ", pointer)
    }
    if (!file.exists(artifact)) stop("read_dataset: current artifact is missing: ", artifact)
    label_version <- current$label_version
    path <- artifact
    recorded_sha <- current$artifact$sha256
    rows <- current$artifact$rows
    partition_files <- current$partition
  } else {
    path <- pointer
    recorded_sha <- derived$sha256
    rows <- derived$rows
  }
  # A play-partitioned artifact: a `play` argument selects one file, so taking a
  # single play does not read all five. Verified against the partition's own
  # recorded sha256.
  if (!is.null(play) && is.list(partition_files) &&
      identical(partition_files$key, "play")) {
    parts <- partition_files$parts
    if (is.null(parts[[play]])) {
      stop("read_dataset: no partition for play '", play, "'; available: ",
           paste(names(parts), collapse = ", "))
    }
    wanted <- file.path(dirname(path), partition_files$directory, parts[[play]]$file)
    if (!file.exists(wanted)) {
      stop("read_dataset: play partition is missing: ", wanted)
    }
    return(list(kind = "derived", files = wanted,
                hashes = stats::setNames(parts[[play]]$sha256, basename(wanted)),
                rows = as.integer(parts[[play]]$rows),
                version = manifest$version, receipt = derived$receipt,
                label_version = label_version, partition = "play", play = play))
  }
  hashes <- if (is.null(recorded_sha)) character(0) else
    stats::setNames(recorded_sha, basename(path))
  list(kind = "derived", files = path, hashes = hashes,
       rows = if (is.null(rows)) NULL else as.integer(rows),
       version = manifest$version, receipt = derived$receipt,
       label_version = label_version, partition = if (is.null(partition_files)) NULL else "play")
}

# Resolve the on-disk files for one table; `issue_year` restricts partitions.
dataset_table_files <- function(manifest, version_dir, table, issue_year = NULL) {
  entry <- manifest$tables[[table]]
  if (is.null(entry)) stop("read_dataset: table '", table, "' is not in the version manifest")
  if (identical(entry$kind, "whole")) {
    if (!is.null(issue_year)) {
      stop("read_dataset: table '", table, "' is not partitioned (issue_year is not valid)")
    }
    return(file.path(version_dir, "tables", paste0(table, ".parquet")))
  }
  directory <- file.path(version_dir, "tables", table)
  files <- sort(list.files(directory, pattern = "^part-issue-year=[0-9]+\\.parquet$", full.names = TRUE))
  if (length(files) == 0L) stop("read_dataset: no partition files for table '", table, "': ", directory)
  if (!is.null(issue_year)) {
    checkmate::assert_integerish(issue_year, lower = 2000L, upper = 2100L, any.missing = FALSE)
    want <- file.path(directory, sprintf("part-issue-year=%d.parquet", as.integer(issue_year)))
    if (!file.exists(want)) {
      stop("read_dataset: partition issue_year=", issue_year, " is not published for table '", table, "'")
    }
    return(want)
  }
  files
}

# Verify the selected files against the recorded sha256 for each name.
verify_table_files <- function(files, hashes, table) {
  for (path in files) {
    name <- basename(path)
    expected <- hashes[[name]]
    if (is.null(expected)) stop("read_dataset: file '", name, "' has no recorded sha256")
    actual <- digest::digest(file = path, algo = "sha256")
    if (!identical(actual, expected)) {
      stop("read_dataset: sha256 mismatch for ", path)
    }
  }
  invisible(TRUE)
}

# Fail closed on Arrow types the contract does not cover, instead of coercing.
assert_supported_schema <- function(schema) {
  type_map <- parquet_type_map()
  unsupported <- character(0)
  for (i in seq_len(schema$num_fields)) {
    field <- schema$field(i - 1L)
    base <- arrow_base_type(arrow_field_type(field))
    if (!base %in% names(type_map)) unsupported <- c(unsupported, paste0(field$name, ":", base))
  }
  if (length(unsupported) > 0L) {
    stop("read_dataset: unsupported Arrow type(s): ", paste(unsupported, collapse = ", "),
         "; extend parquet_type_map() explicitly")
  }
  invisible(TRUE)
}

#' 数据表的类型化契约
#'
#' @param table 长度 1 的非空字符串表名。
#' @inheritParams dataset_manifest
#' @return 具名字符向量，名字为列名，值为 R 边界类型（见 [parquet_type_map()]）。
#' @details 契约取自该版本 Parquet 文件自身的 Arrow schema（文件内容已被 manifest
#'   的 sha256 绑定），并映射到 R 类型。这与 [issue_schedule_types()] 的词汇一致。
#' @export
dataset_contract <- function(dataset, table, version = NULL, root = NULL) {
  root <- parquet_root(root)
  source <- dataset_table_source(dataset, table, version = version, root = root)
  schema <- arrow::read_parquet(source$files[[1]], as_data_frame = FALSE)$schema
  assert_supported_schema(schema)
  type_map <- parquet_type_map()
  names_out <- character(schema$num_fields)
  types_out <- character(schema$num_fields)
  for (i in seq_len(schema$num_fields)) {
    field <- schema$field(i - 1L)
    names_out[[i]] <- field$name
    types_out[[i]] <- unname(type_map[[arrow_base_type(arrow_field_type(field))]])
  }
  stats::setNames(types_out, names_out)
}

#' 读取一个 Parquet 数据集表
#'
#' @inheritParams dataset_contract
#' @param issue_year 可选整数年份，仅对分区 base 表有效；给出时只读该年分区文件。
#' @param columns 可选字符向量，指定要读的列子集；`NULL` 读全部列。
#' @param play 可选字符串，仅对按 `play` 分区的派生产物有效（如 `play_labels`）；
#'   给出时只读该玩法的分片文件，避免扫描全部五个玩法。
#' @param issue 可选字符向量，按期号过滤行（`issue` 是各表的列，不是物理分区）。
#'   给出时只返回这些期号的行；请求了不存在的期号会 `stop()`，不静默返回空表。
#'   与 `issue_year` 的区别：`issue_year` 选物理分区文件，`issue` 过滤分区内的行。
#' @param verify 逻辑值；`TRUE`（默认）时对读到的每个文件核对记录的 sha256，
#'   防止读到被替换或损坏的文件。大文件读取会增加哈希开销。
#' @return 类型化 tibble。行数与列类型受 manifest / catalog 与
#'   [parquet_type_map()] 约束；空结果是合法的 0 行 tibble（与"根缺失"错误区分）。
#' @details 读取路径是 **Arrow**（零拷贝）；跨分区聚合请用 [dataset_query()]。
#'   `table` 可以是版本 manifest 里的 base 表，也可以是 catalog 登记的派生产物
#'   （例如 `settlement` 的 `spf_labels`，见 [dataset_derived_tables()]）；派生产物
#'   不做分区，其 sha256 与行数取自 catalog 登记，读取时同样校验。
#'   未在此契约内的 Arrow 类型会 `stop()`，不做静默转换。
#' @export
read_dataset <- function(dataset, table, version = NULL, root = NULL,
                         issue_year = NULL, columns = NULL, verify = TRUE,
                         play = NULL, issue = NULL) {
  checkmate::assert_string(table, min.chars = 1L, na.ok = FALSE)
  checkmate::assert_flag(verify)
  if (!is.null(issue)) {
    checkmate::assert_character(issue, min.len = 1L, any.missing = FALSE)
  }
  root <- parquet_root(root)
  source <- dataset_table_source(dataset, table, version = version, root = root,
                                 issue_year = issue_year, play = play)
  files <- source$files
  missing_files <- files[!file.exists(files)]
  if (length(missing_files) > 0L) {
    stop("read_dataset: published file(s) missing: ", paste(missing_files, collapse = ", "))
  }

  # `columns` selects a projection; `include` is not used, so unknown names error.
  if (!is.null(columns)) {
    checkmate::assert_character(columns, min.len = 1L, any.missing = FALSE, unique = TRUE)
    available <- names(dataset_contract(dataset, table, version = source$version, root = root))
    unknown <- setdiff(columns, available)
    if (length(unknown) > 0L) {
      stop("read_dataset: unknown column(s): ", paste(unknown, collapse = ", "))
    }
  }

  reader <- if (is.null(columns)) {
    function(path) arrow::read_parquet(path)
  } else {
    function(path) arrow::read_parquet(path, col_select = tidyselect::all_of(columns))
  }
  tables <- lapply(files, function(path) {
    table_schema <- arrow::read_parquet(path, as_data_frame = FALSE)$schema
    assert_supported_schema(table_schema)
    reader(path)
  })
  contract <- dataset_contract(dataset, table, version = source$version, root = root)
  out <- cast_dataset_columns(tibble::as_tibble(dplyr::bind_rows(tables)), contract)
  out <- tibble::as_tibble(out)

  # Verify after reading so a corrupt file is reported as corruption, not as a
  # row-count mismatch.
  if (verify) verify_table_files(files, source$hashes, table)

  # `issue` filters rows (it is a column, not a partition). Requesting an issue
  # the table does not hold fails rather than returning an empty tibble, which
  # would be indistinguishable from "this issue has no rows".
  if (!is.null(issue)) {
    absent <- setdiff(issue, unique(out$issue))
    if (length(absent) > 0L) {
      stop("read_dataset: issue(s) not present: ", paste(absent, collapse = ", "))
    }
    out <- dplyr::filter(out, .data$issue %in% .env$issue)
    out <- tibble::as_tibble(out)
  }

  if (!is.null(source$rows) && is.null(issue_year) && is.null(issue)) {
    if (nrow(out) != source$rows) {
      stop("read_dataset: row count ", nrow(out), " != recorded ", source$rows,
           " for table '", table, "'")
    }
  }
  attr(out, "dataset") <- dataset
  attr(out, "table") <- table
  attr(out, "version") <- source$version
  attr(out, "kind") <- source$kind
  if (!is.null(source$label_version)) attr(out, "label_version") <- source$label_version
  if (!is.null(source$partition)) attr(out, "partition") <- source$partition
  if (!is.null(source$receipt)) attr(out, "receipt") <- source$receipt
  out
}

#' 用 DuckDB 对数据集表做聚合
#'
#' @param sql 长度 1 的非空字符串 SQL，可引用由 `table` 建立的视图名。
#' @param table 长度 1 的非空字符串表名；先按其全部分区建立同名视图，供 `sql` 使用。
#' @inheritParams dataset_manifest
#' @param memory_limit 可选 DuckDB 内存上限（如 `"2GB"`）；`NULL` 用默认。
#' @param threads 可选整数线程数；`NULL` 用默认。
#' @return 查询结果 tibble。
#' @details 在只读连接上对 `read_parquet(<表全部文件>)` 建视图再执行 `sql`，
#'   适合跨分区聚合；单分区零拷贝读取请用 [read_dataset()]。`table` 可以是 base
#'   表或 catalog 登记的派生产物。运行时不写任何文件。
#' @export
dataset_query <- function(dataset, sql, table, version = NULL, root = NULL,
                          memory_limit = NULL, threads = NULL) {
  checkmate::assert_string(sql, min.chars = 1L, na.ok = FALSE)
  checkmate::assert_string(table, min.chars = 1L, na.ok = FALSE)
  source <- dataset_table_source(dataset, table, version = version, root = root)
  files <- source$files
  con <- DBI::dbConnect(duckdb::duckdb())
  on.exit(DBI::dbDisconnect(con, shutdown = TRUE), add = TRUE)
  if (!is.null(memory_limit)) DBI::dbExecute(con, paste0("SET memory_limit='", memory_limit, "'"))
  if (!is.null(threads)) DBI::dbExecute(con, paste0("SET threads=", as.integer(threads)))
  DBI::dbExecute(con, sprintf(
    "CREATE OR REPLACE VIEW %s AS SELECT * FROM read_parquet(%s)",
    DBI::dbQuoteIdentifier(con, table),
    paste0("[", paste(sprintf("'%s'", files), collapse = ","), "]")
  ))
  tibble::as_tibble(DBI::dbGetQuery(con, sql))
}
