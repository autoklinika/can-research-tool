#pragma once

#include "crt/filter/filter_types.hpp"

#include <functional>
#include <memory>

namespace crt::filter {

class CompiledFilter {
public:
    using Predicate = std::function<FilterResult(const FilterContext&)>;

    CompiledFilter() = default;
    explicit CompiledFilter(Predicate predicate);

    [[nodiscard]] FilterResult evaluate(const FilterContext& context) const;
    [[nodiscard]] explicit operator bool() const noexcept;

private:
    Predicate predicate_;
};

class FilterCompiler {
public:
    static constexpr std::size_t kDefaultMaxDepth = 12;

    explicit FilterCompiler(std::size_t maxDepth = kDefaultMaxDepth);

    [[nodiscard]] ValidationResult validate(const FilterPreset& preset) const;
    [[nodiscard]] std::optional<CompiledFilter> compile(
        const FilterPreset& preset,
        ValidationResult* validation = nullptr) const;

private:
    std::size_t maxDepth_;
};

} // namespace crt::filter
