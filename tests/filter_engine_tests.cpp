#include "crt/filter/filter_engine.hpp"

#include <cstdlib>
#include <iostream>
#include <string>
#include <vector>

using namespace crt::filter;

namespace {

int failures = 0;

void expect(bool condition, const std::string& message) {
    if (!condition) {
        ++failures;
        std::cerr << "FAIL: " << message << '\n';
    }
}

FilterPreset makePreset(FilterNodePtr root) {
    FilterPreset preset;
    preset.id = "test-filter";
    preset.name = "Test filter";
    preset.root = std::move(root);
    return preset;
}

void testCanIdAndDlc() {
    auto root = makeGroup(LogicalOperator::And, {
        makeCondition("id", "CAN ID", FilterField::CanId,
                      NumericOperator::Equal, {0x18FEAE30U}),
        makeCondition("dlc", "DLC", FilterField::Dlc,
                      NumericOperator::Equal, {8U}),
    });

    FilterCompiler compiler;
    const auto compiled = compiler.compile(makePreset(root));
    expect(compiled.has_value(), "valid AND filter should compile");

    CanFrameRecord frame;
    frame.canId = 0x18FEAE30U;
    frame.format = FrameFormat::Extended;
    frame.dlc = 8U;

    expect(compiled->evaluate(FilterContext{&frame}).state == MatchState::Match,
           "matching CAN ID and DLC should match");

    frame.dlc = 7U;
    expect(compiled->evaluate(FilterContext{&frame}).state == MatchState::NoMatch,
           "different DLC should not match");
}

void testNestedOrAndNot() {
    auto extended = makeCondition("ext", "EXT", FilterField::FrameFormat,
                                  NumericOperator::Equal, {1U});
    auto id30 = makeCondition("id30", "ID 30", FilterField::CanId,
                              NumericOperator::Equal, {0x30U});
    auto id31 = makeCondition("id31", "ID 31", FilterField::CanId,
                              NumericOperator::Equal, {0x31U});
    auto excluded = makeCondition("excluded", "Excluded ID", FilterField::CanId,
                                  NumericOperator::Equal, {0x31U});

    auto root = makeGroup(LogicalOperator::And, {
        extended,
        makeGroup(LogicalOperator::Or, {id30, id31}),
        makeGroup(LogicalOperator::Not, {excluded}),
    });

    const auto compiled = FilterCompiler{}.compile(makePreset(root));
    expect(compiled.has_value(), "nested filter should compile");

    CanFrameRecord frame;
    frame.canId = 0x30U;
    frame.format = FrameFormat::Extended;
    expect(compiled->evaluate(FilterContext{&frame}).state == MatchState::Match,
           "EXT ID 0x30 should match");

    frame.canId = 0x31U;
    expect(compiled->evaluate(FilterContext{&frame}).state == MatchState::NoMatch,
           "NOT should exclude ID 0x31");
}

void testUnavailable() {
    auto preset = makePreset(makeCondition(
        "id", "CAN ID", FilterField::CanId, NumericOperator::Equal, {1U}));
    const auto compiled = FilterCompiler{}.compile(preset);
    expect(compiled.has_value(), "simple filter should compile");
    expect(compiled->evaluate(FilterContext{}).state == MatchState::Unavailable,
           "missing frame context should be unavailable");
}

void testValidation() {
    FilterPreset preset;
    preset.id = "invalid";
    preset.name = "Invalid";
    preset.root = makeGroup(LogicalOperator::Not, {
        makeCondition("a", "A", FilterField::CanId, NumericOperator::Equal, {1U}),
        makeCondition("b", "B", FilterField::CanId, NumericOperator::Equal, {2U}),
    });

    ValidationResult validation;
    const auto compiled = FilterCompiler{}.compile(preset, &validation);
    expect(!compiled.has_value(), "invalid NOT group must not compile");
    expect(!validation.valid(), "invalid NOT group must report validation error");
}

void testRangeAndSet() {
    auto root = makeGroup(LogicalOperator::And, {
        makeCondition("time", "Time", FilterField::RelativeTimeUs,
                      NumericOperator::BetweenInclusive, {1'000U, 5'000U}),
        makeCondition("id", "ID set", FilterField::CanId,
                      NumericOperator::InSet, {0x100U, 0x200U}),
    });

    const auto compiled = FilterCompiler{}.compile(makePreset(root));
    CanFrameRecord frame;
    frame.relativeTimeUs = 2'000U;
    frame.canId = 0x200U;
    expect(compiled->evaluate(FilterContext{&frame}).state == MatchState::Match,
           "range and set condition should match");
}

} // namespace

int main() {
    testCanIdAndDlc();
    testNestedOrAndNot();
    testUnavailable();
    testValidation();
    testRangeAndSet();

    if (failures != 0) {
        std::cerr << failures << " test(s) failed\n";
        return EXIT_FAILURE;
    }

    std::cout << "All Global Filter Engine tests passed\n";
    return EXIT_SUCCESS;
}
