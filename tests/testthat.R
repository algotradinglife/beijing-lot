library(testthat)

# The migrated N7 suite lives with its package.
test_local("packages/beidan", reporter = "summary")

test_dir(file.path("tests", "testthat"), reporter = "summary")
