#include <algorithm>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#ifdef _OPENMP
#include <omp.h>
#endif

namespace {

struct Target {
  std::string policy;
  std::string arm;
  std::vector<double> candidate;
  std::vector<double> baseline;
  std::vector<double> candidate_tax;
  std::vector<double> baseline_tax;
};

struct Result {
  std::vector<double> candidate;
  std::vector<double> lift;
  std::vector<double> candidate_tax;
  std::vector<double> tax_lift;
};

std::vector<std::string> split(const std::string &value, char delimiter) {
  std::vector<std::string> output;
  std::stringstream stream(value);
  std::string item;
  while (std::getline(stream, item, delimiter)) output.push_back(item);
  if (!value.empty() && value.back() == delimiter) output.emplace_back();
  return output;
}

std::vector<double> doubles(const std::string &value) {
  std::vector<double> output;
  if (value.empty()) return output;
  for (const auto &item : split(value, ',')) output.push_back(std::stod(item));
  return output;
}

double quantile(std::vector<double> values, double probability) {
  if (values.empty()) throw std::runtime_error("quantile on empty vector");
  std::sort(values.begin(), values.end());
  const double position = probability * static_cast<double>(values.size() - 1);
  const auto lower = static_cast<std::size_t>(std::floor(position));
  const auto upper = static_cast<std::size_t>(std::ceil(position));
  if (lower == upper) return values[lower];
  const double weight = position - static_cast<double>(lower);
  return values[lower] * (1.0 - weight) + values[upper] * weight;
}

double mean(const std::vector<double> &values) {
  return std::accumulate(values.begin(), values.end(), 0.0) /
         static_cast<double>(values.size());
}

double mcse(const std::vector<double> &values) {
  const double average = mean(values);
  double variance = 0.0;
  for (const double value : values) variance += (value - average) * (value - average);
  variance /= static_cast<double>(values.size());
  return std::sqrt(variance) / std::sqrt(static_cast<double>(values.size()));
}

void emit(std::ostream &out, double value) {
  if (!std::isfinite(value)) return;
  out << std::fixed << std::setprecision(12) << value;
}

}  // namespace

int main(int argc, char **argv) {
  try {
    if (argc != 6) {
      throw std::runtime_error(
          "usage: bj190_bootstrap_exact TARGETS DRAWS OUTPUT DRAW_COUNT MASTER_N");
    }
    const std::string target_path = argv[1];
    const std::string draw_path = argv[2];
    const std::string output_path = argv[3];
    const std::size_t draw_count = std::stoull(argv[4]);
    const std::size_t master_n = std::stoull(argv[5]);

    std::vector<Target> targets;
    std::ifstream target_file(target_path);
    if (!target_file) throw std::runtime_error("cannot open bootstrap targets");
    std::string line;
    while (std::getline(target_file, line)) {
      if (line.empty()) continue;
      const auto fields = split(line, '\t');
      if (fields.size() != 7) throw std::runtime_error("bootstrap target width drift");
      const std::size_t n = std::stoull(fields[2]);
      Target target{fields[0], fields[1], doubles(fields[3]), doubles(fields[4]),
                    doubles(fields[5]), doubles(fields[6])};
      if (target.candidate.size() != n || target.baseline.size() != n ||
          target.candidate_tax.size() != n || target.baseline_tax.size() != n) {
        throw std::runtime_error("bootstrap target vector-length drift");
      }
      targets.push_back(std::move(target));
    }

    std::ifstream draw_file(draw_path, std::ios::binary | std::ios::ate);
    if (!draw_file) throw std::runtime_error("cannot open bootstrap draws");
    const auto draw_bytes = static_cast<std::size_t>(draw_file.tellg());
    const std::size_t expected = draw_count * master_n * sizeof(std::uint64_t);
    if (draw_bytes != expected) throw std::runtime_error("bootstrap draw size drift");
    draw_file.seekg(0);
    std::vector<std::uint64_t> draws(draw_count * master_n);
    draw_file.read(reinterpret_cast<char *>(draws.data()), expected);
    if (!draw_file) throw std::runtime_error("cannot read bootstrap draws");

    std::vector<Result> results(targets.size());
#pragma omp parallel for schedule(dynamic)
    for (std::int64_t target_index = 0;
         target_index < static_cast<std::int64_t>(targets.size()); ++target_index) {
      const auto &target = targets[static_cast<std::size_t>(target_index)];
      const std::size_t n = target.candidate.size();
      auto &result = results[static_cast<std::size_t>(target_index)];
      if (!n) continue;
      result.candidate.resize(draw_count);
      result.lift.resize(draw_count);
      result.candidate_tax.resize(draw_count);
      result.tax_lift.resize(draw_count);
      const double stake = static_cast<double>(n) * 4374.0;
      for (std::size_t draw = 0; draw < draw_count; ++draw) {
        double candidate_sum = 0.0, baseline_sum = 0.0;
        double candidate_tax_sum = 0.0, baseline_tax_sum = 0.0;
        const std::size_t offset = draw * master_n;
        for (std::size_t position = 0; position < n; ++position) {
          const std::size_t index = static_cast<std::size_t>(
              (static_cast<unsigned __int128>(draws[offset + position]) * n) >> 64);
          candidate_sum += target.candidate[index];
          baseline_sum += target.baseline[index];
          candidate_tax_sum += target.candidate_tax[index];
          baseline_tax_sum += target.baseline_tax[index];
        }
        result.candidate[draw] = candidate_sum / stake;
        result.lift[draw] = (candidate_sum - baseline_sum) / stake;
        result.candidate_tax[draw] = candidate_tax_sum / stake;
        result.tax_lift[draw] = (candidate_tax_sum - baseline_tax_sum) / stake;
      }
    }

    std::ofstream output(output_path);
    if (!output) throw std::runtime_error("cannot open bootstrap output");
    output << "policy_id,arm,common_issue_count,draw_count,candidate_roi_mean,"
              "candidate_roi_ci_low,candidate_roi_ci_high,lift_mean,lift_ci_low,"
              "lift_ci_high,probability_lift_positive,monte_carlo_se_lift,"
              "candidate_tax_roi_mean,candidate_tax_roi_ci_low,"
              "candidate_tax_roi_ci_high,tax_lift_mean,tax_lift_ci_low,"
              "tax_lift_ci_high\n";
    for (std::size_t i = 0; i < targets.size(); ++i) {
      const auto &target = targets[i];
      const auto &result = results[i];
      output << target.policy << ',' << target.arm << ',' << target.candidate.size()
             << ',' << draw_count << ',';
      if (!target.candidate.empty()) {
        emit(output, mean(result.candidate)); output << ',';
        emit(output, quantile(result.candidate, 0.025)); output << ',';
        emit(output, quantile(result.candidate, 0.975)); output << ',';
        emit(output, mean(result.lift)); output << ',';
        emit(output, quantile(result.lift, 0.025)); output << ',';
        emit(output, quantile(result.lift, 0.975)); output << ',';
        emit(output, static_cast<double>(std::count_if(
                         result.lift.begin(), result.lift.end(),
                         [](double value) { return value > 0.0; })) /
                         static_cast<double>(draw_count));
        output << ','; emit(output, mcse(result.lift)); output << ',';
        emit(output, mean(result.candidate_tax)); output << ',';
        emit(output, quantile(result.candidate_tax, 0.025)); output << ',';
        emit(output, quantile(result.candidate_tax, 0.975)); output << ',';
        emit(output, mean(result.tax_lift)); output << ',';
        emit(output, quantile(result.tax_lift, 0.025)); output << ',';
        emit(output, quantile(result.tax_lift, 0.975));
      } else {
        output << ",,,,,,,,,,,,,";
      }
      output << '\n';
    }
    return 0;
  } catch (const std::exception &error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
