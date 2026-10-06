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
  path <- file.path(parquet_root(root), "registry", paste0(dataset, "-parquet-current.json"))
  if (!file.exists(path)) {
    stop("dataset_registry: no registry for dataset '", dataset, "': ", path)
  }
  jsonlite::fromJSON(path, simplifyVector = FALSE)
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
  if (is.null(version)) version <- dataset_registry(dataset, root)$version
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

# Verify the selected files against the manifest's recorded size and sha256.
verify_table_files <- function(manifest, table, files) {
  entry <- manifest$tables[[table]]
  recorded <- stats::setNames(
    vapply(entry$files, function(f) f$sha256, character(1)),
    vapply(entry$files, function(f) f$name, character(1))
  )
  for (path in files) {
    name <- basename(path)
    expected <- recorded[[name]]
    if (is.null(expected)) stop("read_dataset: file '", name, "' is not in the manifest")
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
  manifest <- dataset_manifest(dataset, version, root)
  version_dir <- file.path(root, "datasets", dataset, "versions", manifest$version)
  files <- dataset_table_files(manifest, version_dir, table)
  schema <- arrow::read_parquet(files[[1]], as_data_frame = FALSE)$schema
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
#' @param issue_year 可选整数年份，仅对分区表有效；给出时只读该年分区文件。
#' @param columns 可选字符向量，指定要读的列子集；`NULL` 读全部列。
#' @param verify 逻辑值；`TRUE`（默认）时对读到的每个文件核对 manifest 记录的
#'   sha256，防止读到被替换或损坏的分区。大文件读取会增加哈希开销。
#' @return 类型化 tibble。行数与列类型受 manifest 与 [parquet_type_map()] 约束；
#'   空结果是合法的 0 行 tibble（与"根缺失"错误区分）。
#' @details 读取路径是 **Arrow**（零拷贝）；跨分区聚合请用 [dataset_query()]。
#'   读到的每个文件的 sha256 与 manifest 绑定，且 `int64` 列映射为 `double`。
#'   未在此契约内的 Arrow 类型会 `stop()`，不做静默转换。
#' @export
read_dataset <- function(dataset, table, version = NULL, root = NULL,
                         issue_year = NULL, columns = NULL, verify = TRUE) {
  checkmate::assert_string(table, min.chars = 1L, na.ok = FALSE)
  checkmate::assert_flag(verify)
  root <- parquet_root(root)
  manifest <- dataset_manifest(dataset, version, root)
  version_dir <- file.path(root, "datasets", dataset, "versions", manifest$version)
  files <- dataset_table_files(manifest, version_dir, table, issue_year = issue_year)
  missing_files <- files[!file.exists(files)]
  if (length(missing_files) > 0L) {
    stop("read_dataset: published file(s) missing: ", paste(missing_files, collapse = ", "))
  }
  if (verify) verify_table_files(manifest, table, files)

  # `columns` selects a projection; `include` is not used, so unknown names error.
  if (!is.null(columns)) {
    checkmate::assert_character(columns, min.len = 1L, any.missing = FALSE, unique = TRUE)
    available <- names(dataset_contract(dataset, table, version = manifest$version, root = root))
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
  contract <- dataset_contract(dataset, table, version = manifest$version, root = root)
  out <- cast_dataset_columns(tibble::as_tibble(dplyr::bind_rows(tables)), contract)
  out <- tibble::as_tibble(out)

  expected <- manifest$row_counts[[table]]
  if (!is.null(expected) && is.null(issue_year)) {
    if (nrow(out) != as.integer(expected)) {
      stop("read_dataset: row count ", nrow(out), " != manifest ", expected, " for table '", table, "'")
    }
  }
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
#' @details 在只读连接上对 `read_parquet(<表全部分区 glob>)` 建视图再执行 `sql`，
#'   适合跨分区聚合；单分区零拷贝读取请用 [read_dataset()]。运行时不写任何文件。
#' @export
dataset_query <- function(dataset, sql, table, version = NULL, root = NULL,
                          memory_limit = NULL, threads = NULL) {
  checkmate::assert_string(sql, min.chars = 1L, na.ok = FALSE)
  checkmate::assert_string(table, min.chars = 1L, na.ok = FALSE)
  root <- parquet_root(root)
  manifest <- dataset_manifest(dataset, version, root)
  version_dir <- file.path(root, "datasets", dataset, "versions", manifest$version)
  files <- dataset_table_files(manifest, version_dir, table)
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
