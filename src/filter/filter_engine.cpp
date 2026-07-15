#include "crt/filter/filter_engine.hpp"

#include <algorithm>
#include <stdexcept>
#include <utility>

namespace crt::filter {
namespace {

using Predicate = CompiledFilter::Predicate;

std::optional<std::uint64_t> readNumericField(const FilterContext& context,
                                              FilterField field) {
    if (context.frame == nullptr) {
        return std::nullopt;
    }

    switch (field) {
    case FilterField::CanId:
        return context.frame->canId;
    case FilterField::FrameFormat:
        return context.frame->format == FrameFormat::Extended ? 1U : 0U;
    case FilterField::Dlc:
        return context.frame->dlc;
    case FilterField::RelativeTimeUs:
        return context.frame->relativeTimeUs;
    }

    return std::nullopt;
}

bool compareNumeric(std::uint64_t actual,
                    NumericOperator op,
                    const std::vector<std::uint64_t>& values) {
    switch (op) {
    case NumericOperator::Equal:
        return actual == values.at(0);
    case NumericOperator::NotEqual:
        return actual != values.at(0);
    case NumericOperator::Greater:
        return actual > values.at(0);
    case NumericOperator::GreaterOrEqual:
        return actual >= values.at(0);
    case NumericOperator::Less:
        return actual < values.at(0);
    case NumericOperator::LessOrEqual:
        return actual <= values.at(0);
    case NumericOperator::BetweenInclusive:
        return actual >= values.at(0) && actual <= values.at(1);
    case NumericOperator::OutsideInclusive:
        return actual < values.at(0) || actual > values.at(1);
    case NumericOperator::InSet:
        return std::find(values.begin(), values.end(), actual) != values.end();
    case NumericOperator::NotInSet:
        return std::find(values.begin(), values.end(), actual) == values.end();
    }

    return false;
}

std::size_t expectedValueCount(NumericOperator op) {
    switch (op) {
    case NumericOperator::BetweenInclusive:
    case NumericOperator::OutsideInclusive:
        return 2;
    case NumericOperator::InSet:
    case NumericOperator::NotInSet:
        return 1;
    default:
        return 1;
    }
}

void validateNode(const FilterNodePtr& node,
                  std::size_t depth,
                  std::size_t maxDepth,
                  ValidationResult& result) {
    if (!node) {
        result.issues.push_back({ValidationIssue::Severity::Error, {},
                                 "Filter node is null"});
        return;
    }

    if (depth > maxDepth) {
        result.issues.push_back({ValidationIssue::Severity::Error, {},
                                 "Maximum filter nesting depth exceeded"});
        return;
    }

    if (const auto* group = std::get_if<FilterGroup>(&node->value)) {
        if (group->children.empty()) {
            result.issues.push_back({ValidationIssue::Severity::Error, {},
                                     "Logical group cannot be empty"});
        }
        if (group->op == LogicalOperator::Not && group->children.size() != 1U) {
            result.issues.push_back({ValidationIssue::Severity::Error, {},
                                     "NOT group must contain exactly one child"});
        }
        for (const auto& child : group->children) {
            validateNode(child, depth + 1U, maxDepth, result);
        }
        return;
    }

    const auto& condition = std::get<FilterCondition>(node->value);
    if (condition.id.empty()) {
        result.issues.push_back({ValidationIssue::Severity::Warning, {},
                                 "Condition has no stable identifier"});
    }

    const auto& expression = condition.expression;
    const auto minimum = expectedValueCount(expression.op);
    if (expression.values.size() < minimum) {
        result.issues.push_back({ValidationIssue::Severity::Error, condition.id,
                                 "Condition has too few comparison values"});
    }
    if ((expression.op == NumericOperator::BetweenInclusive ||
         expression.op == NumericOperator::OutsideInclusive) &&
        expression.values.size() >= 2U &&
        expression.values[0] > expression.values[1]) {
        result.issues.push_back({ValidationIssue::Severity::Error, condition.id,
                                 "Range lower bound is greater than upper bound"});
    }
    if ((expression.op == NumericOperator::InSet ||
         expression.op == NumericOperator::NotInSet) &&
        expression.values.empty()) {
        result.issues.push_back({ValidationIssue::Severity::Error, condition.id,
                                 "Set comparison requires at least one value"});
    }
}

Predicate compileNode(const FilterNodePtr& node) {
    if (const auto* condition = std::get_if<FilterCondition>(&node->value)) {
        const auto expression = condition->expression;
        return [expression](const FilterContext& context) -> FilterResult {
            const auto actual = readNumericField(context, expression.field);
            if (!actual.has_value()) {
                return {MatchState::Unavailable,
                        "Required CAN frame field is unavailable"};
            }
            return {compareNumeric(*actual, expression.op, expression.values)
                        ? MatchState::Match
                        : MatchState::NoMatch,
                    {}};
        };
    }

    const auto group = std::get<FilterGroup>(node->value);
    std::vector<Predicate> children;
    children.reserve(group.children.size());
    for (const auto& child : group.children) {
        children.push_back(compileNode(child));
    }

    return [op = group.op, children = std::move(children)](
               const FilterContext& context) -> FilterResult {
        if (op == LogicalOperator::Not) {
            auto result = children.front()(context);
            if (result.state == MatchState::Match) {
                result.state = MatchState::NoMatch;
            } else if (result.state == MatchState::NoMatch) {
                result.state = MatchState::Match;
            }
            return result;
        }

        bool sawUnavailable = false;
        std::string unavailableReason;

        for (const auto& child : children) {
            const auto result = child(context);
            if (result.state == MatchState::Unavailable) {
                sawUnavailable = true;
                if (unavailableReason.empty()) {
                    unavailableReason = result.reason;
                }
                continue;
            }

            if (op == LogicalOperator::And && result.state == MatchState::NoMatch) {
                return {MatchState::NoMatch, {}};
            }
            if (op == LogicalOperator::Or && result.state == MatchState::Match) {
                return {MatchState::Match, {}};
            }
        }

        if (sawUnavailable) {
            return {MatchState::Unavailable, unavailableReason};
        }

        return {op == LogicalOperator::And ? MatchState::Match
                                           : MatchState::NoMatch,
                {}};
    };
}

} // namespace

bool ValidationResult::valid() const noexcept {
    return std::none_of(issues.begin(), issues.end(), [](const ValidationIssue& issue) {
        return issue.severity == ValidationIssue::Severity::Error;
    });
}

FilterNodePtr makeGroup(LogicalOperator op, std::vector<FilterNodePtr> children) {
    return std::make_shared<FilterNode>(FilterNode{FilterGroup{op, std::move(children)}});
}

FilterNodePtr makeCondition(std::string id,
                            std::string label,
                            FilterField field,
                            NumericOperator op,
                            std::vector<std::uint64_t> values) {
    NumericCondition numeric{field, op, std::move(values)};
    FilterCondition condition{std::move(id), std::move(label), std::move(numeric)};
    return std::make_shared<FilterNode>(FilterNode{std::move(condition)});
}

CompiledFilter::CompiledFilter(Predicate predicate)
    : predicate_(std::move(predicate)) {}

FilterResult CompiledFilter::evaluate(const FilterContext& context) const {
    if (!predicate_) {
        return {MatchState::Unavailable, "Filter is not compiled"};
    }
    return predicate_(context);
}

CompiledFilter::operator bool() const noexcept {
    return static_cast<bool>(predicate_);
}

FilterCompiler::FilterCompiler(std::size_t maxDepth)
    : maxDepth_(maxDepth) {
    if (maxDepth_ == 0U) {
        throw std::invalid_argument("Maximum filter depth must be greater than zero");
    }
}

ValidationResult FilterCompiler::validate(const FilterPreset& preset) const {
    ValidationResult result;
    if (preset.id.empty()) {
        result.issues.push_back({ValidationIssue::Severity::Error, {},
                                 "Preset identifier cannot be empty"});
    }
    if (preset.name.empty()) {
        result.issues.push_back({ValidationIssue::Severity::Error, {},
                                 "Preset name cannot be empty"});
    }
    if (preset.formatVersion == 0U) {
        result.issues.push_back({ValidationIssue::Severity::Error, {},
                                 "Format version must be greater than zero"});
    }
    validateNode(preset.root, 1U, maxDepth_, result);
    return result;
}

std::optional<CompiledFilter> FilterCompiler::compile(
    const FilterPreset& preset,
    ValidationResult* validation) const {
    auto result = validate(preset);
    if (validation != nullptr) {
        *validation = result;
    }
    if (!result.valid()) {
        return std::nullopt;
    }
    return CompiledFilter{compileNode(preset.root)};
}

} // namespace crt::filter
