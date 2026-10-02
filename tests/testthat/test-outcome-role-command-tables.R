testthat::test_that("all QMD command cells preserve original command bytes", {
  root <- rprojroot::find_root(rprojroot::has_file("packages/beidan/DESCRIPTION"))
  text <- readLines(file.path(root,"quarto/classify_outcomes_contract.qmd"))
  sources <- c(forced_acceptance="docs/reviews/forced-complement-purchase.json",
    accept333="docs/reviews/3332222-comparison.json",
    variants_evidence="docs/reviews/outcome-role-variants.json")
  for (name in names(sources)) {
    env <- new.env(parent=globalenv())
    receipt <- jsonlite::read_json(file.path(root,sources[[name]]))
    assign(name,receipt,env)
    start <- which(grepl(paste0("command=names(",name,"$commands)"),text,fixed=TRUE))
    testthat::expect_length(start,1L)
    end <- which(seq_along(text)>=start & grepl('format="html",escape=FALSE)',text,fixed=TRUE))[1L]
    table <- eval(parse(text=text[start:end]),env)
    dom <- xml2::read_html(as.character(table))
    cells <- xml2::xml_find_all(dom,"//tbody/tr/td[2]/code")
    testthat::expect_identical(xml2::xml_text(cells),unname(unlist(receipt$commands)))
  }
})
