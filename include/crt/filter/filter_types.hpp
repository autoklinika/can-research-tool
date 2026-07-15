#pragma once

#include <cstdint>
#include <memory>
#include <optional>
#include <string>
#include <variant>
#include <vector>

namespace crt::filter {

enum class MatchState {
    Match,
    NoMatch,
    Unavailable,
};

enum class LogicalOperator {
    And,
    Or,
    Not,
};

enum class FilterMode {
    Include,
    Exclude,
    Highlight,
};

enum class FilterScope : std::uint32_t {
    None = 0,
    LiveCapture = 1U << 0U,
    StoredSession = 1U << 1U,
    Analysis = 1U << 2U,
    Export = 1U << 3U,
};

constexpr FilterScope operator|(FilterScope lhs, FilterScope rhs) noexcept {
    return static_cast<FilterScope>(
        static_cast<std::uint32_t>(lhs) | static_cast<std::uint32_t>(rhs));
}

enum class FrameFormat {
    Standard,
    Extended,
};

enum class FilterField {
    CanId,
    FrameFormat,
    Dlc,
    RelativeTimeUs,
};

enum class NumericOperator {
    Equal,
    NotEqual,
    Greater,
    GreaterOrEqual,
    Less,
    LessOrEqual,
    BetweenInclusive,
    OutsideInclusive,
    InSet,
    NotInSet,
};

struct NumericCondition {
    FilterField field{FilterField::CanId};
    NumericOperator op{NumericOperator::Equal};
    std::vector<std::uint64_t> values;
};

struct FilterCondition {
    std::string id;
    std::string label;
    NumericCondition expression;
};

struct FilterNode;
using FilterNodePtr = std::shared_ptr<FilterNode>;

struct FilterGroup {
    LogicalOperator op{LogicalOperator::And};
    std::vector<FilterNodePtr> children;
};

struct FilterNode {
    std::variant<FilterGroup, FilterCondition> value;
};

struct FilterPreset {
    std::string id;
    std::string name;
    std::string description;
    std::uint32_t formatVersion{1};
    bool enabled{true};
    FilterMode mode{FilterMode::Include};
    FilterScope scope{FilterScope::LiveCapture | FilterScope::StoredSession};
    std::optional<std::string> shortcut;
    FilterNodePtr root;
};

struct CanFrameRecord {
    std::uint64_t sequence{0};
    std::uint64_t relativeTimeUs{0};
    std::uint32_t canId{0};
    FrameFormat format{FrameFormat::Standard};
    std::uint8_t dlc{0};
    std::uint8_t channel{0};
    bool hasData{false};
};

struct FilterContext {
    const CanFrameRecord* frame{nullptr};
};

struct FilterResult {
    MatchState state{MatchState::Unavailable};
    std::string reason;
};

struct ValidationIssue {
    enum class Severity {
        Warning,
        Error,
    };

    Severity severity{Severity::Error};
    std::string nodeId;
    std::string message;
};

struct ValidationResult {
    std::vector<ValidationIssue> issues;

    [[nodiscard]] bool valid() const noexcept;
};

[[nodiscard]] FilterNodePtr makeGroup(LogicalOperator op,
                                      std::vector<FilterNodePtr> children);
[[nodiscard]] FilterNodePtr makeCondition(std::string id,
                                          std::string label,
                                          FilterField field,
                                          NumericOperator op,
                                          std::vector<std::uint64_t> values);

} // namespace crt::filter
